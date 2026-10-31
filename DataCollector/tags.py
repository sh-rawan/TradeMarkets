"""Tags for every stock and ETF, from NSE's published lists (as they stand today):
  size    Large / Mid / Small / Micro cap by index membership (Nifty 100, Midcap 150, Smallcap 250,
          Microcap 250), and "Below micro cap" for every other listed stock
  sector  NSE's industry for the 750 largest companies (Nifty Total Market)
  theme   membership of NSE's sector and theme indices (Banks, IT, Infrastructure, Defence, PSU...)
  market  "F&O stock" when the stock has futures and options
  etf     what an ETF holds (Equity, Gold, Silver, Debt...) and the index it tracks

Raw lists: raw/nse/lists/fetched=<date>/<name>.csv, one snapshot per day they are fetched."""
import io

import pandas as pd

from config import (ETFS_TABLE, FUTURES_TABLE, NSE_RAW, PSU_BANKS, SECTOR_LIST, SIZE_LISTS, STOCKS_TABLE,
                    TAGS_TABLE, THEME_LISTS)
from nse import ARCHIVES, _get
from store import latest_snapshot, write

LISTS = NSE_RAW / "lists"
OTHER_LISTS = {"equities": f"{ARCHIVES}/equities/EQUITY_L.csv", "etfs": f"{ARCHIVES}/equities/eq_etfseclist.csv"}


def _index_url(name):
    return f"{ARCHIVES}/indices/ind_{name}list.csv"


def download():
    snap = LISTS / f"fetched={pd.Timestamp.today():%Y-%m-%d}"
    snap.mkdir(parents=True, exist_ok=True)
    names = {n: _index_url(n) for n in [*SIZE_LISTS.values(), *THEME_LISTS.values(), SECTOR_LIST]} | OTHER_LISTS
    missing = []
    for name, url in names.items():
        body = _get(url)
        if body is None:
            missing.append(name)
        else:
            (snap / f"{name}.csv").write_bytes(body)
    print(f"  NSE lists: {len(names) - len(missing)} of {len(names)}" + (f" (missing {missing})" if missing else ""))


def _read(snap, name):
    path = snap / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(io.BytesIO(path.read_bytes()))
    df.columns = [c.strip() for c in df.columns]
    return df


def etf_symbols():
    return set(_read(latest_snapshot(LISTS), "etfs")["Symbol"].str.strip())


def listed_symbols():
    """Every stock and ETF listed on NSE today."""
    snap = latest_snapshot(LISTS)
    return set(_read(snap, "equities")["SYMBOL"].str.strip()) | etf_symbols()


def build():
    snap = latest_snapshot(LISTS)
    tags = []
    sized = set()
    for tag, name in SIZE_LISTS.items():
        symbols = set(_read(snap, name)["Symbol"].str.strip()) - sized
        tags += [(s, "size", tag) for s in symbols]
        sized |= symbols
    stocks = pd.read_parquet(STOCKS_TABLE, columns=["date", "ticker"])
    listed = set(stocks.loc[stocks["date"] >= stocks["date"].max() - pd.Timedelta(days=30), "ticker"])
    tags += [(s, "size", "Below micro cap") for s in listed - sized]

    sectors = _read(snap, SECTOR_LIST)
    tags += [(s.strip(), "sector", i.strip()) for s, i in zip(sectors["Symbol"], sectors["Industry"])]
    for tag, name in THEME_LISTS.items():
        tags += [(s.strip(), "theme", tag) for s in _read(snap, name).get("Symbol", [])]
    banks = {s for s, k, t in tags if t == "Banks"}
    psu = {s for s, k, t in tags if t == "PSU banks"} | PSU_BANKS
    tags += [(s, "theme", "Private banks") for s in banks - psu]

    futures = pd.read_parquet(FUTURES_TABLE, columns=["date", "ticker", "underlying"])
    latest = futures[(futures["date"] == futures["date"].max()) & (futures["underlying"] == "stock")]
    tags += [(s, "market", "F&O stock") for s in set(latest["ticker"])]

    etfs = _read(snap, "etfs")
    traded = set(pd.read_parquet(ETFS_TABLE, columns=["ticker"])["ticker"])
    for _, r in etfs[etfs["Symbol"].str.strip().isin(traded)].iterrows():
        s = r["Symbol"].strip()
        tags.append((s, "etf", str(r["ETF Underlying"]).strip().title()))
        if pd.notna(r.get("Underlying Key")):
            tags.append((s, "etf_index", str(r["Underlying Key"]).strip()))
    out = pd.DataFrame(tags, columns=["ticker", "kind", "tag"]).drop_duplicates().sort_values(["kind", "tag", "ticker"])
    write(out, TAGS_TABLE)
    print(f"  Tags: {out['ticker'].nunique():,} symbols, {len(out):,} tags")
