"""NSE's public end-of-day archive: every stock and ETF, every index, every futures and options
contract, and who holds what in derivatives (FII / DII / Pro / Client).

Raw, one file per trading day, never modified (re-runs only fetch missing days):
  raw/nse/cm_bhavcopy/<date>.parquet      every security traded in the cash market, original columns
  raw/nse/fo_bhavcopy/<date>.parquet      every futures and options contract, original columns
  raw/nse/index_close/<date>.csv          every NSE index, as published
  raw/nse/participant_oi/<date>.csv       open interest by participant type, as published
  raw/nse/participant_vol/<date>.csv      traded contracts by participant type, as published
  raw/nse/fiidii_cash/<date>.json         cash-market FII/DII buy/sell (NSE publishes only the latest
                                          day, so this history starts when collection started)
"""
import io
import json
from concurrent.futures import ThreadPoolExecutor

import duckdb
import numpy as np
import pandas as pd
import requests

from config import (EQUITY_SERIES, ETFS_TABLE, FIIDII_CASH_TABLE, FUTURES_TABLE, INDICES_TABLE, NSE_RAW,
                    NSE_START, OPTIONS_TABLE, PARTICIPANT_OI_TABLE, PARTICIPANT_VOL_TABLE, STOCKS_TABLE)
from store import write

ARCHIVES = "https://archives.nseindia.com/content"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36"}
UDIFF_FROM = pd.Timestamp("2024-07-08")  # NSE switched the bhavcopies to the UDiFF format
PARTICIPANTS = ["Client", "DII", "FII", "Pro"]
ATM_STRADDLE = np.sqrt(2 / np.pi)  # an at-the-money straddle is worth ~ this x price x vol x sqrt(T)
RAW_KINDS = ["cm_bhavcopy", "fo_bhavcopy", "index_close", "participant_oi", "participant_vol"]


def _get(url):
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
        except requests.RequestException:
            continue
        return r.content if r.status_code == 200 and not r.content.lstrip().startswith(b"<") else None
    return None


def _save_zip_csv(url, path):
    body = _get(url)
    if body is None:
        return False
    df = pd.read_csv(io.BytesIO(body), compression="zip", low_memory=False)
    write(df.dropna(axis=1, how="all"), path)
    return True


def _save_bytes(url, path):
    body = _get(url)
    if body is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return True


def _fetch(kind, d):
    """One raw file; True if it is on disk afterwards."""
    ext = "csv" if kind in ("index_close", "participant_oi", "participant_vol") else "parquet"
    path = NSE_RAW / kind / f"{d:%Y-%m-%d}.{ext}"
    if path.exists():
        return True
    mon = d.strftime("%b").upper()
    if kind == "cm_bhavcopy":
        url = (f"{ARCHIVES}/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip" if d >= UDIFF_FROM else
               f"{ARCHIVES}/historical/EQUITIES/{d:%Y}/{mon}/cm{d:%d}{mon}{d:%Y}bhav.csv.zip")
        return _save_zip_csv(url, path)
    if kind == "fo_bhavcopy":
        url = (f"{ARCHIVES}/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip" if d >= UDIFF_FROM else
               f"{ARCHIVES}/historical/DERIVATIVES/{d:%Y}/{mon}/fo{d:%d}{mon}{d:%Y}bhav.csv.zip")
        return _save_zip_csv(url, path)
    if kind == "index_close":
        return _save_bytes(f"{ARCHIVES}/indices/ind_close_all_{d:%d%m%Y}.csv", path)
    side = kind.removeprefix("participant_")
    return _save_bytes(f"{ARCHIVES}/nsccl/fao_participant_{side}_{d:%d%m%Y}.csv", path)


def fetch_fiidii_cash():
    """Today's cash-market FII/DII buy/sell from NSE (no history is published)."""
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        s.get("https://www.nseindia.com", timeout=30)
        rows = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=30).json()
    except Exception as e:  # noqa: BLE001
        print(f"  cash FII/DII: not available ({e})")
        return
    d = pd.Timestamp(rows[0]["date"])
    path = NSE_RAW / "fiidii_cash" / f"{d:%Y-%m-%d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows))


NO_SESSION = NSE_RAW / "no_session_days.txt"  # days NSE published nothing for (holidays), not retried


def download():
    """Fetch every missing raw file since NSE_START. Every calendar day is tried once, so special
    sessions (Saturday budget days, Diwali Muhurat trading) are not missed; days with no cash-market
    file at all are remembered as holidays once they are a week old."""
    known = set(NO_SESSION.read_text().split()) if NO_SESSION.exists() else set()
    today = pd.Timestamp.today().normalize()
    days = [d for d in pd.date_range(NSE_START, today) if f"{d:%Y-%m-%d}" not in known]
    jobs = [(k, d) for d in days for k in RAW_KINDS]
    with ThreadPoolExecutor(max_workers=6) as pool:
        ok = dict(zip(jobs, pool.map(lambda job: _fetch(*job), jobs)))
    holidays = [d for d in days if not ok[("cm_bhavcopy", d)] and d < today - pd.Timedelta(days=7)]
    NO_SESSION.write_text("\n".join(sorted(known | {f"{d:%Y-%m-%d}" for d in holidays})))
    sessions = [d for d in days if ok[("cm_bhavcopy", d)]]
    for kind in RAW_KINDS:
        missing = [d for d in sessions if not ok[(kind, d)]]
        print(f"  NSE {kind}: {len(sessions) - len(missing)} of {len(sessions)} new or checked sessions"
              + (f" (missing e.g. {', '.join(f'{d:%Y-%m-%d}' for d in missing[:3])})" if missing else ""))
    fetch_fiidii_cash()


# --- Curated tables -----------------------------------------------------------------------------
def _files(kind, skip=()):
    """Raw files of one kind, optionally leaving out days already processed."""
    return [p for p in sorted((NSE_RAW / kind).glob("*.*")) if pd.Timestamp(p.stem) not in skip]


# Split and bonus ratios as price factors: n-for-1 splits and a:b bonuses ((a + b) / b).
CLEAN_RATIOS = sorted({float(n) for n in range(2, 21)} | {50.0, 100.0}
                      | {(a + b) / b for a in range(1, 6) for b in range(1, 6) if a + b > b})


def _snap(factor, tolerance):
    """The standard ratio nearest to an observed price factor, if within tolerance."""
    best = min(CLEAN_RATIOS, key=lambda r: abs(np.log(factor / r)))
    return best if abs(np.log(factor / best)) <= tolerance else None


def adjustment_factors(df, splits, covered):
    """Split / bonus factor per (ticker, date): the ex-date's overnight drop (open vs previous close),
    snapped to a standard ratio. Event dates come from Yahoo, which can understate combined events
    (Bajaj Finance 2025: a 2-for-1 split plus a 4:1 bonus shows as 2), so the size comes from NSE's
    own prices. For stocks Yahoo does not cover (mostly delisted), a clean split-sized overnight
    drop of at least 45% counts as an event."""
    prev = df.groupby("ticker")["close"].shift()
    gap = (prev / df["open"].where(df["open"] > 0, df["close"])).rename("gap")  # > 1 when the price fell
    frame = pd.concat([df[["ticker", "date"]], gap], axis=1).dropna()
    by_ticker = dict(list(frame.groupby("ticker")))
    factors = {}
    for (ticker, d), split in splits.items():
        # Yahoo's date can be a day or two off: take the biggest overnight drop around it.
        g = by_ticker.get(ticker)
        if g is None:
            continue
        near = g[g["date"].sub(d).abs() <= pd.Timedelta(days=4)]
        if near.empty:
            continue
        row = near.loc[near["gap"].idxmax()]
        f = _snap(row["gap"], 0.12) if row["gap"] > 1.2 else None
        if f:
            factors[(ticker, row["date"])] = f
    big = frame[(frame["gap"] >= 1.8) & ~frame["ticker"].isin(covered)]
    for _, row in big.iterrows():
        f = _snap(row["gap"], 0.04)
        if f:
            factors.setdefault((row["ticker"], row["date"]), f)
    return factors


def build_stocks(etf_symbols, splits, covered):
    """Stocks and ETFs, one row per symbol and day (main-board series only). adj_close divides each
    price by every later split / bonus factor (see adjustment_factors); ordinary dividends are not
    adjusted."""
    old = [p.as_posix() for p in _files("cm_bhavcopy") if pd.Timestamp(p.stem) < UDIFF_FROM]
    new = [p.as_posix() for p in _files("cm_bhavcopy") if pd.Timestamp(p.stem) >= UDIFF_FROM]
    con = duckdb.connect()
    parts = []
    if old:
        parts.append(f"""select cast(regexp_extract(filename, '(\\d{{4}}-\\d{{2}}-\\d{{2}})', 1) as date) as date,
            trim(SYMBOL) as ticker, trim(SERIES) as series, try_cast(OPEN as double) as open,
            try_cast(HIGH as double) as high, try_cast(LOW as double) as low, try_cast(CLOSE as double) as close,
            try_cast(PREVCLOSE as double) as prev_close, try_cast(TOTTRDQTY as double) as volume,
            try_cast(TOTTRDVAL as double) as value, try_cast(TOTALTRADES as double) as trades
            from read_parquet({old}, filename=true, union_by_name=true)""")
    if new:
        parts.append(f"""select cast(regexp_extract(filename, '(\\d{{4}}-\\d{{2}}-\\d{{2}})', 1) as date) as date,
            trim(TckrSymb) as ticker, trim(SctySrs) as series, try_cast(OpnPric as double) as open,
            try_cast(HghPric as double) as high, try_cast(LwPric as double) as low,
            try_cast(ClsPric as double) as close, try_cast(PrvsClsgPric as double) as prev_close,
            try_cast(TtlTradgVol as double) as volume, try_cast(TtlTrfVal as double) as value,
            try_cast(TtlNbOfTxsExctd as double) as trades
            from read_parquet({new}, filename=true, union_by_name=true)""")
    series = ", ".join(f"'{s}'" for s in EQUITY_SERIES)
    con.execute(f"""create temp table cm as
        select * from ({' union all '.join(parts)}) where series in ({series}) and close > 0
        -- a symbol can move between series (EQ <-> BE); keep its busiest row per day
        qualify row_number() over (partition by ticker, date order by volume desc nulls last) = 1""")
    df = con.execute("select date, ticker, series, open, high, low, close, volume, value, trades "
                     "from cm order by ticker, date").df()
    df["date"] = pd.to_datetime(df["date"])
    factors = adjustment_factors(df, splits, covered)
    event = pd.Series(factors, dtype=float)
    event.index.names = ["ticker", "date"]
    f = df.join(event.rename("f"), on=["ticker", "date"])["f"].fillna(1.0)
    # Each price is divided by the product of all later factors of the same ticker.
    later = np.log(f).groupby(df["ticker"]).transform(lambda s: s[::-1].cumsum()[::-1].shift(-1, fill_value=0))
    df["adj_close"] = df["close"] / np.exp(later)
    print(f"  Splits and bonuses applied: {len(factors):,}")
    is_etf = df["ticker"].isin(etf_symbols)
    write(df[~is_etf], STOCKS_TABLE)
    write(df[is_etf], ETFS_TABLE)
    print(f"  NSE stocks: {df.loc[~is_etf, 'ticker'].nunique():,} symbols, {(~is_etf).sum():,} rows; "
          f"ETFs: {df.loc[is_etf, 'ticker'].nunique():,} symbols")


def build_indices():
    frames = []
    for path in _files("index_close"):
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        frames.append(pd.DataFrame({
            "date": pd.Timestamp(path.stem), "index": df["Index Name"].str.strip(),
            "open": df["Open Index Value"], "high": df["High Index Value"], "low": df["Low Index Value"],
            "close": df["Closing Index Value"], "volume": df["Volume"], "turnover_cr": df["Turnover (Rs. Cr.)"],
            "pe": df["P/E"], "pb": df["P/B"], "div_yield": df["Div Yield"]}))
    out = pd.concat(frames, ignore_index=True)
    num = [c for c in out.columns if c not in ("date", "index")]
    out[num] = out[num].apply(lambda s: pd.to_numeric(s, errors="coerce"))
    write(out.dropna(subset=["close"]), INDICES_TABLE)
    print(f"  NSE indices: {out['index'].nunique()} indices")


def _normalise_fo(path):
    """One day's F&O rows in a common schema across the old and UDiFF formats."""
    df = pd.read_parquet(path)
    d = pd.Timestamp(path.stem)
    if "TckrSymb" in df:
        kind = df["FinInstrmTp"].map({"STF": "fut", "IDF": "fut", "STO": "opt", "IDO": "opt"})
        under = df["FinInstrmTp"].map({"STF": "stock", "STO": "stock", "IDF": "index", "IDO": "index"})
        # Both formats count traded contracts and report open interest in shares (checked across the switch).
        out = pd.DataFrame({"ticker": df["TckrSymb"], "kind": kind, "underlying": under,
                            "expiry": pd.to_datetime(df["XpryDt"]), "strike": df.get("StrkPric"),
                            "opt": df.get("OptnTp"), "close": df["ClsPric"], "settle": df["SttlmPric"],
                            "oi": df["OpnIntrst"], "volume": df["TtlTradgVol"]})
    else:
        kind = df["INSTRUMENT"].map({"FUTSTK": "fut", "FUTIDX": "fut", "OPTSTK": "opt", "OPTIDX": "opt"})
        under = df["INSTRUMENT"].map({"FUTSTK": "stock", "OPTSTK": "stock", "FUTIDX": "index", "OPTIDX": "index"})
        out = pd.DataFrame({"ticker": df["SYMBOL"], "kind": kind, "underlying": under,
                            "expiry": pd.to_datetime(df["EXPIRY_DT"], format="%d-%b-%Y"),
                            "strike": df["STRIKE_PR"], "opt": df["OPTION_TYP"], "close": df["CLOSE"],
                            "settle": df["SETTLE_PR"], "oi": df["OPEN_INT"], "volume": df["CONTRACTS"]})
    return out.dropna(subset=["kind"]).assign(date=d)


def _options_day(df):
    """Per underlying: futures and options positioning, and the at-the-money implied volatility."""
    rows = []
    for ticker, g in df.groupby("ticker"):
        fut = g[g["kind"] == "fut"].sort_values("expiry")
        opt = g[g["kind"] == "opt"]
        calls, puts = opt[opt["opt"] == "CE"], opt[opt["opt"] == "PE"]
        row = {"date": g["date"].iloc[0], "ticker": ticker, "underlying": g["underlying"].iloc[0],
               "fut_oi": fut["oi"].sum(), "fut_volume": fut["volume"].sum(),
               "call_oi": calls["oi"].sum(), "put_oi": puts["oi"].sum(),
               "call_volume": calls["volume"].sum(), "put_volume": puts["volume"].sum(),
               "atm_iv": np.nan, "fut_close": np.nan}
        if len(fut):
            row["fut_close"] = fut["settle"].iloc[0]
            # Implied vol from the at-the-money straddle of the nearest expiry at least a week out,
            # using the near future as the forward price.
            days_left = (opt["expiry"] - row["date"]).dt.days
            expiries = sorted(opt.loc[days_left >= 7, "expiry"].unique())
            if expiries:
                e = expiries[0]
                c = calls[calls["expiry"] == e].set_index("strike")["settle"]
                p = puts[puts["expiry"] == e].set_index("strike")["settle"]
                both = c.index.intersection(p.index)
                if len(both):
                    k = min(both, key=lambda s: abs(s - row["fut_close"]))
                    t = (e - row["date"]).days / 365
                    row["atm_iv"] = (c[k] + p[k]) / (ATM_STRADDLE * row["fut_close"] * np.sqrt(t))
        rows.append(row)
    return rows


def build_derivatives():
    """Futures (every contract) and a per-underlying options summary. Only days not yet in the
    tables are processed, so the daily update stays quick."""
    have = pd.read_parquet(FUTURES_TABLE) if FUTURES_TABLE.exists() else None
    done = set(have["date"]) if have is not None else set()
    futs, summary = [], []
    for path in _files("fo_bhavcopy", done):
        df = _normalise_fo(path)
        futs.append(df.loc[df["kind"] == "fut", ["date", "ticker", "underlying", "expiry", "close", "settle", "oi",
                                                 "volume"]])
        summary += _options_day(df)
    if not futs:
        return
    new_f, new_s = pd.concat(futs, ignore_index=True), pd.DataFrame(summary)
    if have is not None:
        new_f = pd.concat([have, new_f], ignore_index=True)
        new_s = pd.concat([pd.read_parquet(OPTIONS_TABLE), new_s], ignore_index=True)
    write(new_f, FUTURES_TABLE)
    write(new_s, OPTIONS_TABLE)
    print(f"  NSE F&O: {new_s['ticker'].nunique()} underlyings, {len(futs)} new days")


def _participant_table(kind):
    frames = []
    for path in _files(f"participant_{kind}"):
        # Most files start with a title line, a few don't: start at the header row either way.
        lines = path.read_text(errors="replace").splitlines()
        start = next(i for i, line in enumerate(lines) if line.strip().strip('"').startswith("Client Type"))
        df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df = df[df["client_type"].str.strip().isin(PARTICIPANTS)]
        frames.append(df.assign(date=pd.Timestamp(path.stem)))
    out = pd.concat(frames, ignore_index=True).rename(columns={"client_type": "participant"})
    out["participant"] = out["participant"].str.strip()
    # A few days have the counts as text with stray whitespace.
    counts = [c for c in out.columns if c not in ("date", "participant")]
    out[counts] = out[counts].apply(lambda s: pd.to_numeric(s.astype(str).str.strip(), errors="coerce"))
    return out[["date", "participant"] + counts]


def build_flows():
    write(_participant_table("oi"), PARTICIPANT_OI_TABLE)
    write(_participant_table("vol"), PARTICIPANT_VOL_TABLE)
    cash = [r for p in _files("fiidii_cash") for r in json.loads(p.read_text())]
    if cash:
        df = pd.DataFrame(cash)
        write(pd.DataFrame({"date": pd.to_datetime(df["date"]), "category": df["category"],
                            "buy": pd.to_numeric(df["buyValue"]), "sell": pd.to_numeric(df["sellValue"]),
                            "net": pd.to_numeric(df["netValue"])}), FIIDII_CASH_TABLE)
