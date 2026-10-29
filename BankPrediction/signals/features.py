"""Daily feature panel for the LightGBM model: price/volume features in the spirit of Qlib's
Alpha158, cross-sectional versions of the key ones, macro, and (when the NSE tables exist) each
bank's futures and options positioning plus FII / DII / Pro / Client flows in derivatives.
Every feature at date t uses data up to the close of t only (US-session series are already
lagged a day in load_macro; NSE publishes its end-of-day files the same evening)."""
import numpy as np
import pandas as pd

from config import OPTIONS_TABLE, PARTICIPANT_OI_TABLE, PARTICIPANT_VOL_TABLE, PSU_BANKS
from data import load_macro, load_panel
from store import sql, table


def _stack(frames):
    """{feature: date x ticker frame} -> one frame indexed by (date, ticker)."""
    return pd.concat({k: v.stack(future_stack=True) for k, v in frames.items()}, axis=1)


def feature_panel():
    close, open_, high, low, volume = (load_panel(f) for f in ["close", "open", "high", "low", "volume"])
    ret = np.log(close).diff()
    macro = load_macro().reindex(close.index)
    mkt = np.log(macro["nifty"]).diff()
    f = {}

    # Momentum / reversal over several windows, and the same relative to the other banks.
    for k in [1, 2, 3, 5, 10, 20, 60, 120]:
        f[f"ret_{k}"] = np.log(close / close.shift(k))
    for k in [1, 5, 20, 60]:
        f[f"rel_ret_{k}"] = f[f"ret_{k}"].sub(f[f"ret_{k}"].mean(axis=1), axis=0)
    # Volatility and its trend.
    for k in [5, 10, 20, 60]:
        f[f"vol_{k}"] = ret.rolling(k).std()
    f["vol_ratio_5_60"] = f["vol_5"] / f["vol_60"]
    f["skew_60"] = ret.rolling(60).skew()
    # Where the price sits: distance from moving averages and position in the recent range.
    for k in [5, 10, 20, 60]:
        f[f"ma_gap_{k}"] = close / close.rolling(k).mean() - 1
    for k in [10, 20, 60]:
        lo, hi = low.rolling(k).min(), high.rolling(k).max()
        f[f"range_pos_{k}"] = (close - lo) / (hi - lo)
    # Today's candle.
    f["hl_range"] = (high - low) / close
    f["hl_range_20"] = f["hl_range"].rolling(20).mean()
    f["open_close"] = np.log(close / open_)
    f["gap"] = np.log(open_ / close.shift(1))
    # Volume: surprise, trend, and whether volume and returns move together.
    logv = np.log(volume.where(volume > 0))
    f["volume_surprise"] = logv - logv.rolling(20).mean()
    f["volume_trend"] = logv.rolling(5).mean() - logv.rolling(60).mean()
    f["volume_ret_corr_20"] = ret.rolling(20).corr(logv.diff())
    # Market sensitivity and the bank-specific part of recent moves.
    beta = ret.rolling(60).cov(mkt) / mkt.rolling(60).var().values[:, None]
    f["beta_60"] = beta
    f["resid_ret_5"] = f["ret_5"] - beta * np.log(macro["nifty"] / macro["nifty"].shift(5)).values[:, None]
    # Cross-sectional ranks (0..1) of the most used features.
    for name in ["ret_5", "ret_20", "vol_20", "volume_surprise"]:
        f[f"rank_{name}"] = f[name].rank(axis=1, pct=True)
    f["psu"] = pd.DataFrame(np.tile([b in PSU_BANKS for b in close.columns], (len(close), 1)).astype(float),
                            index=close.index, columns=close.columns)

    panel = _stack(f)
    # Macro: the same value for every bank on a date.
    m = pd.DataFrame(index=close.index)
    for k in [1, 5, 20]:
        m[f"nifty_ret_{k}"] = np.log(macro["nifty"] / macro["nifty"].shift(k))
        m[f"banknifty_ret_{k}"] = np.log(macro["banknifty"] / macro["banknifty"].shift(k))
    m["vix"] = macro["vix"]
    m["vix_chg_5"] = macro["vix"] - macro["vix"].shift(5)
    for k in [1, 5, 20]:
        m[f"us10y_chg_{k}"] = macro["us10y"] - macro["us10y"].shift(k)
        m[f"usdinr_ret_{k}"] = np.log(macro["usdinr"] / macro["usdinr"].shift(k))
        if "in10y" in macro:
            m[f"in10y_chg_{k}"] = macro["in10y"] - macro["in10y"].shift(k)
    panel.index.names = ["date", "ticker"]
    panel = panel.join(m.rename_axis("date"), on="date")
    if OPTIONS_TABLE.exists():
        panel = panel.join(_stack(options_features(close, f["vol_20"])).rename_axis(["date", "ticker"]))
    if PARTICIPANT_OI_TABLE.exists():
        panel = panel.join(flow_features(close.index).rename_axis("date"), on="date")
    return panel.replace([np.inf, -np.inf], np.nan)


def options_features(close, vol_20):
    """Per bank, from its futures and options: positioning (put/call open interest, futures OI
    build-up), activity (volume surprises) and fear (at-the-money implied vol vs realised vol).
    Bank Nifty index options give the same for the whole sector."""
    o = sql(f"select * from {table(OPTIONS_TABLE)}")
    wide = {c: o.pivot(index="date", columns="ticker", values=c).reindex(close.index) for c in
            ["fut_oi", "fut_volume", "call_oi", "put_oi", "call_volume", "put_volume", "atm_iv"]}
    bn = {c: w.pop("BANKNIFTY") if "BANKNIFTY" in w else None for c, w in wide.items()}
    w = {c: v.reindex(columns=close.columns) for c, v in wide.items()}
    ret = np.log(close).diff()
    f = {}
    f["pcr_oi"] = np.log(w["put_oi"] / w["call_oi"])
    f["pcr_oi_chg_5"] = f["pcr_oi"] - f["pcr_oi"].shift(5)
    f["pcr_volume_5"] = np.log(w["put_volume"].rolling(5).sum() / w["call_volume"].rolling(5).sum())
    opt_oi = w["put_oi"] + w["call_oi"]
    f["opt_oi_chg_5"] = np.log(opt_oi / opt_oi.shift(5))
    for k in [1, 5]:
        f[f"fut_oi_chg_{k}"] = np.log(w["fut_oi"] / w["fut_oi"].shift(k))
        # Price up with OI up = new longs; price down with OI up = new shorts.
        f[f"oi_price_{k}"] = f[f"fut_oi_chg_{k}"] * np.sign(np.log(close / close.shift(k)))
    f["fut_volume_surprise"] = np.log(w["fut_volume"] / w["fut_volume"].rolling(20).mean())
    opt_vol = w["call_volume"] + w["put_volume"]
    f["opt_volume_surprise"] = np.log(opt_vol / opt_vol.rolling(20).mean())
    f["iv"] = w["atm_iv"]
    f["iv_chg_5"] = w["atm_iv"] - w["atm_iv"].shift(5)
    f["iv_minus_rv"] = w["atm_iv"] - vol_20 * np.sqrt(252)
    f["rank_iv"] = w["atm_iv"].rank(axis=1, pct=True)
    f["rank_pcr_oi"] = f["pcr_oi"].rank(axis=1, pct=True)
    # Sector level, from Bank Nifty index options: the same value for every bank on a date.
    if bn["put_oi"] is not None:
        sector = pd.DataFrame({
            "bn_pcr_oi": np.log(bn["put_oi"] / bn["call_oi"]),
            "bn_iv": bn["atm_iv"],
            "bn_iv_chg_5": bn["atm_iv"] - bn["atm_iv"].shift(5),
            "bn_iv_minus_rv": bn["atm_iv"] - ret.mean(axis=1).rolling(20).std() * np.sqrt(252),
        })
        sector["bn_pcr_oi_chg_5"] = sector["bn_pcr_oi"] - sector["bn_pcr_oi"].shift(5)
        for c in sector:
            f[c] = pd.DataFrame(np.tile(sector[c].values[:, None], (1, close.shape[1])),
                                index=close.index, columns=close.columns)
    return f


def flow_features(dates):
    """Market-wide institutional positioning and flows in derivatives, by participant type:
    net long share in index and stock futures (open interest), the net buying share of the day's
    futures trades (volume), and FII index options bias."""
    def net(df, long, short):
        return (df[long] - df[short]) / (df[long] + df[short])

    oi = sql(f"select * from {table(PARTICIPANT_OI_TABLE)}")
    vol = sql(f"select * from {table(PARTICIPANT_VOL_TABLE)}")
    out = pd.DataFrame(index=dates)
    for who in ["FII", "DII", "Pro", "Client"]:
        p = oi[oi["participant"] == who].set_index("date").reindex(dates)
        v = vol[vol["participant"] == who].set_index("date").reindex(dates)
        tag = who.lower()
        out[f"{tag}_idx_fut_net"] = net(p, "future_index_long", "future_index_short")
        out[f"{tag}_stk_fut_net"] = net(p, "future_stock_long", "future_stock_short")
        out[f"{tag}_idx_fut_flow_5"] = net(v, "future_index_long", "future_index_short").rolling(5).mean()
        out[f"{tag}_stk_fut_flow_5"] = net(v, "future_stock_long", "future_stock_short").rolling(5).mean()
    for c in ["fii_idx_fut_net", "dii_stk_fut_net", "fii_stk_fut_net"]:
        out[f"{c}_chg_5"] = out[c] - out[c].shift(5)
    fii = oi[oi["participant"] == "FII"].set_index("date").reindex(dates)
    calls = fii["option_index_call_long"] - fii["option_index_call_short"]
    puts = fii["option_index_put_long"] - fii["option_index_put_short"]
    gross = fii[["option_index_call_long", "option_index_call_short", "option_index_put_long",
                 "option_index_put_short"]].sum(axis=1)
    out["fii_idx_opt_bias"] = (calls - puts) / gross
    out["fii_idx_put_call_long"] = np.log(fii["option_index_put_long"] / fii["option_index_call_long"])
    return out
