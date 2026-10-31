"""Yahoo daily bars (split- and dividend-adjusted): the Bank Nifty banks and the macro series.
Each run saves a full pull as an immutable raw snapshot, then rebuilds the curated tables."""
import warnings

import pandas as pd

from config import (BANKS, MACRO_START, MACRO_TABLE, MACRO_TICKERS, NSE_START, PRICES_TABLE, PSU_BANKS, TICKERS_TABLE,
                    YAHOO_DAILY, YAHOO_SPLITS, YAHOO_START)
from store import latest_snapshot, write

warnings.filterwarnings("ignore", module="yfinance")
OHLCV = ["open", "high", "low", "close", "volume"]


def _download(ticker, start):
    import yfinance as yf
    df = yf.download(ticker, start=start, auto_adjust=True, progress=False, multi_level_index=False)
    if df.empty:
        raise RuntimeError(f"No data from Yahoo for {ticker}")
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    return df[OHLCV].dropna(subset=["close"])


def download(start=YAHOO_START):
    snap = YAHOO_DAILY / f"fetched={pd.Timestamp.today():%Y-%m-%d}"
    starts = {**{f"{b}.NS": start for b in BANKS}, **{t: MACRO_START.get(n, start) for n, t in MACRO_TICKERS.items()}}
    for symbol, since in starts.items():
        write(_download(symbol, since).reset_index(), snap / f"{symbol}.parquet")
    print(f"  Yahoo: {len(BANKS)} banks + {len(MACRO_TICKERS)} macro series")
    build_curated(snap)


def build_curated(snap=None):
    snap = snap or latest_snapshot(YAHOO_DAILY)
    prices = pd.concat([pd.read_parquet(snap / f"{b}.NS.parquet").assign(ticker=b) for b in BANKS])
    write(prices[["date", "ticker"] + OHLCV].sort_values(["ticker", "date"]), PRICES_TABLE)
    macro = pd.concat([pd.read_parquet(snap / f"{t}.parquet")[["date", "close"]]
                       .rename(columns={"close": "value"}).assign(series=name)
                       for name, t in MACRO_TICKERS.items()])
    write(macro[["date", "series", "value"]].sort_values(["series", "date"]), MACRO_TABLE)
    write(pd.DataFrame({"ticker": BANKS, "group": ["PSU" if b in PSU_BANKS else "Private" for b in BANKS]}),
          TICKERS_TABLE)


def download_splits(symbols):
    """Split and bonus dates for every listed NSE stock and ETF (Yahoo records bonuses as splits).
    Saves the events and the symbols Yahoo knows, as one raw snapshot."""
    import yfinance as yf
    events, covered = [], []
    symbols = sorted(symbols)
    for i in range(0, len(symbols), 200):
        batch = [f"{s}.NS" for s in symbols[i:i + 200]]
        df = yf.download(batch, start=NSE_START, actions=True, auto_adjust=False, progress=False, threads=True)
        if df.empty:
            continue
        covered += [t.removesuffix(".NS") for t in df["Close"].columns[df["Close"].notna().any()]]
        sp = df["Stock Splits"].where(df["Stock Splits"] > 0).stack().dropna()
        events += [(t.removesuffix(".NS"), d, v) for (d, t), v in sp.items()]
    snap = YAHOO_SPLITS / f"fetched={pd.Timestamp.today():%Y-%m-%d}"
    write(pd.DataFrame(events, columns=["ticker", "date", "split"]), snap / "splits.parquet")
    write(pd.DataFrame({"ticker": covered}), snap / "covered.parquet")
    print(f"  Yahoo splits: {len(events):,} events for {len(covered):,} of {len(symbols):,} symbols")


def load_splits():
    """({(ticker, date): split}, set of tickers Yahoo covers) from the latest snapshot."""
    snap = latest_snapshot(YAHOO_SPLITS)
    ev = pd.read_parquet(snap / "splits.parquet")
    ev["date"] = pd.to_datetime(ev["date"]).dt.tz_localize(None).dt.normalize()
    return dict(zip(zip(ev["ticker"], ev["date"]), ev["split"])), set(pd.read_parquet(snap / "covered.parquet")["ticker"])

