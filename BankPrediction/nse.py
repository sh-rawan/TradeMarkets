"""NSE data: who holds what in derivatives (FII / DII / Pro / Client), and futures and options on
the Bank Nifty banks and the BANKNIFTY index.

Raw, one file per trading day, never modified (re-runs only fetch missing days):
  raw/nse/participant_oi/<date>.csv    open interest by participant type, as published
  raw/nse/participant_vol/<date>.csv   traded contracts by participant type, as published
  raw/nse/fo_bhavcopy/<date>.parquet   the F&O bhavcopy rows for our symbols, original columns
  raw/nse/fiidii_cash/<date>.json      cash-market FII/DII buy/sell (NSE publishes only the latest
                                       day, so this history starts when collection started)
Curated (rebuilt from raw): participant_oi, participant_vol, options_daily, fiidii_cash.
"""
import io
import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from config import (BANKS, FIIDII_CASH_TABLE, NSE_START, OPTIONS_TABLE, PARTICIPANT_OI_TABLE,
                    PARTICIPANT_VOL_TABLE, RAW_DIR)
from store import write

NSE_RAW = RAW_DIR / "nse"
ARCHIVES = "https://archives.nseindia.com/content"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36"}
UDIFF_FROM = pd.Timestamp("2024-07-08")  # NSE switched the F&O bhavcopy to the UDiFF format
SYMBOLS = set(BANKS) | {"BANKNIFTY"}
PARTICIPANTS = ["Client", "DII", "FII", "Pro"]
ATM_STRADDLE = np.sqrt(2 / np.pi)  # an at-the-money straddle is worth ~ this x price x vol x sqrt(T)


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    return r.content if r.status_code == 200 and not r.content.lstrip().startswith(b"<") else None


def _fetch_participant(kind, d):
    path = NSE_RAW / f"participant_{kind}" / f"{d:%Y-%m-%d}.csv"
    if path.exists():
        return True
    body = _get(f"{ARCHIVES}/nsccl/fao_participant_{kind}_{d:%d%m%Y}.csv")
    if body is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return True


def _fetch_bhavcopy(d):
    path = NSE_RAW / "fo_bhavcopy" / f"{d:%Y-%m-%d}.parquet"
    if path.exists():
        return True
    if d >= UDIFF_FROM:
        url, symbol = f"{ARCHIVES}/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip", "TckrSymb"
    else:
        mon = d.strftime("%b").upper()
        url, symbol = f"{ARCHIVES}/historical/DERIVATIVES/{d:%Y}/{mon}/fo{d:%d}{mon}{d:%Y}bhav.csv.zip", "SYMBOL"
    body = _get(url)
    if body is None:
        return False
    df = pd.read_csv(io.BytesIO(body), compression="zip", low_memory=False)
    write(df[df[symbol].isin(SYMBOLS)].dropna(axis=1, how="all"), path)
    return True


def _fetch_day(d):
    return {"participant_oi": _fetch_participant("oi", d), "participant_vol": _fetch_participant("vol", d),
            "fo_bhavcopy": _fetch_bhavcopy(d)}


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


def download(days):
    """Fetch every missing raw file for these trading days, then rebuild the curated tables."""
    days = [d for d in days if d >= pd.Timestamp(NSE_START)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_fetch_day, days))
    for kind in ["participant_oi", "participant_vol", "fo_bhavcopy"]:
        missing = [d for d, r in zip(days, results) if not r[kind]]
        print(f"  NSE {kind}: {len(days) - len(missing)} of {len(days)} days"
              + (f" (missing e.g. {', '.join(f'{d:%Y-%m-%d}' for d in missing[:3])})" if missing else ""))
    fetch_fiidii_cash()
    build_curated()


# --- Curated tables -----------------------------------------------------------------------------
def _participant_table(kind):
    frames = []
    for path in sorted((NSE_RAW / f"participant_{kind}").glob("*.csv")):
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
    return out[["date", "participant"] + [c for c in out.columns if c not in ("date", "participant")]]


def _normalise_bhavcopy(path):
    """One day's rows in a common schema across the old and UDiFF formats."""
    df = pd.read_parquet(path)
    d = pd.Timestamp(path.stem)
    if "TckrSymb" in df:
        kind = df["FinInstrmTp"].map({"STF": "fut", "IDF": "fut", "STO": "opt", "IDO": "opt"})
        # Both formats count traded contracts and report open interest in shares (checked across the switch).
        out = pd.DataFrame({"symbol": df["TckrSymb"], "kind": kind, "expiry": pd.to_datetime(df["XpryDt"]),
                            "strike": df.get("StrkPric"), "opt": df.get("OptnTp"), "close": df["ClsPric"],
                            "settle": df["SttlmPric"], "oi": df["OpnIntrst"], "volume": df["TtlTradgVol"]})
    else:
        kind = df["INSTRUMENT"].map({"FUTSTK": "fut", "FUTIDX": "fut", "OPTSTK": "opt", "OPTIDX": "opt"})
        out = pd.DataFrame({"symbol": df["SYMBOL"], "kind": kind, "expiry": pd.to_datetime(df["EXPIRY_DT"], format="%d-%b-%Y"),
                            "strike": df["STRIKE_PR"], "opt": df["OPTION_TYP"], "close": df["CLOSE"],
                            "settle": df["SETTLE_PR"], "oi": df["OPEN_INT"], "volume": df["CONTRACTS"]})
    return out.dropna(subset=["kind"]).assign(date=d)


def _options_day(df):
    """Per symbol: futures and options positioning, and the at-the-money implied volatility."""
    rows = []
    for symbol, g in df.groupby("symbol"):
        fut = g[g["kind"] == "fut"].sort_values("expiry")
        opt = g[g["kind"] == "opt"]
        calls, puts = opt[opt["opt"] == "CE"], opt[opt["opt"] == "PE"]
        row = {"date": g["date"].iloc[0], "ticker": symbol,
               "fut_oi": fut["oi"].sum(), "fut_volume": fut["volume"].sum(),
               "call_oi": calls["oi"].sum(), "put_oi": puts["oi"].sum(),
               "call_volume": calls["volume"].sum(), "put_volume": puts["volume"].sum(), "atm_iv": np.nan}
        if len(fut):
            row["fut_close"] = fut["settle"].iloc[0]
            # Implied vol from the at-the-money straddle of the nearest expiry at least a week out,
            # using the near future as the forward price (Yahoo spot prices are dividend-adjusted).
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


def build_curated():
    write(_participant_table("oi"), PARTICIPANT_OI_TABLE)
    write(_participant_table("vol"), PARTICIPANT_VOL_TABLE)
    rows = []
    for path in sorted((NSE_RAW / "fo_bhavcopy").glob("*.parquet")):
        rows += _options_day(_normalise_bhavcopy(path))
    write(pd.DataFrame(rows), OPTIONS_TABLE)
    cash = [dict(r, date=r["date"]) for p in sorted((NSE_RAW / "fiidii_cash").glob("*.json"))
            for r in json.loads(p.read_text())]
    if cash:
        df = pd.DataFrame(cash)
        df = pd.DataFrame({"date": pd.to_datetime(df["date"]), "category": df["category"],
                           "buy": pd.to_numeric(df["buyValue"]), "sell": pd.to_numeric(df["sellValue"]),
                           "net": pd.to_numeric(df["netValue"])})
        write(df, FIIDII_CASH_TABLE)
    print(f"  NSE curated: {len(rows):,} options/futures rows")
