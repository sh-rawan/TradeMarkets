from functools import lru_cache

import numpy as np
import pandas as pd

from config import (BANKS, ENTRY_LAG, EVAL_START, INDIA_10Y_CSV, MACRO_TABLE, MACRO_TICKERS,
                    PRICES_TABLE, PSU_BANKS, RAW_DIR, START, STEP, TICKERS_TABLE, US_SESSION)
from store import latest_snapshot, sql, table, write

OHLCV = ["open", "high", "low", "close", "volume"]
YAHOO_DAILY = RAW_DIR / "yahoo" / "daily"


def _download(ticker, start):
    import yfinance as yf
    df = yf.download(ticker, start=start, auto_adjust=True, progress=False, multi_level_index=False)
    if df.empty:
        raise RuntimeError(f"No data from Yahoo for {ticker}")
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    return df[OHLCV].dropna(subset=["close"])


def download_all(start=START):
    """Save today's Yahoo pull as an immutable raw snapshot, then rebuild the curated tables."""
    snap = YAHOO_DAILY / f"fetched={pd.Timestamp.today():%Y-%m-%d}"
    for symbol in [f"{b}.NS" for b in BANKS] + list(MACRO_TICKERS.values()):
        write(_download(symbol, start).reset_index(), snap / f"{symbol}.parquet")
        print(f"  {symbol}")
    build_curated(snap)
    import nse
    nse.download(calendar())
    if not INDIA_10Y_CSV.exists():
        print(f"  (optional) add India 10Y yields at {INDIA_10Y_CSV} for the rate features")


def build_curated(snap=None):
    """Long-format prices and macro tables from a raw snapshot (default: the latest)."""
    snap = snap or latest_snapshot(YAHOO_DAILY)
    prices = pd.concat([pd.read_parquet(snap / f"{b}.NS.parquet").assign(ticker=b) for b in BANKS])
    write(prices[["date", "ticker"] + OHLCV].sort_values(["ticker", "date"]), PRICES_TABLE)
    macro = pd.concat([pd.read_parquet(snap / f"{t}.parquet")[["date", "close"]]
                       .rename(columns={"close": "value"}).assign(series=name)
                       for name, t in MACRO_TICKERS.items()])
    write(macro[["date", "series", "value"]].sort_values(["series", "date"]), MACRO_TABLE)
    write(pd.DataFrame({"ticker": BANKS, "group": ["PSU" if b in PSU_BANKS else "Private" for b in BANKS]}),
          TICKERS_TABLE)
    print(f"Curated tables built from {snap.name}: {len(prices):,} price rows, {len(macro):,} macro rows")


@lru_cache
def calendar():
    """NSE trading days, taken from the Bank Nifty index."""
    dates = sql(f"select date from {table(MACRO_TABLE)} where series = 'banknifty' "
                f"and value is not null order by date")["date"]
    return pd.DatetimeIndex(dates, name="date")


@lru_cache
def load_prices():
    cal = calendar()
    prices = sql(f"select * from {table(PRICES_TABLE)} order by ticker, date")
    return {b: g.set_index("date")[OHLCV].reindex(cal).dropna(subset=["close"])
            for b, g in prices.groupby("ticker")}


@lru_cache
def load_panel(field="close"):
    panel = pd.DataFrame({b: df[field] for b, df in load_prices().items()}).reindex(calendar())
    panel.columns.name = "ticker"
    return panel


@lru_cache
def load_macro():
    cal = calendar()
    raw = sql(f"select * from {table(MACRO_TABLE)}").pivot(index="date", columns="series", values="value")
    if INDIA_10Y_CSV.exists():
        g = pd.read_csv(INDIA_10Y_CSV, parse_dates=["date"]).set_index("date")["yield"]
        raw = raw.join(g.rename("in10y"), how="outer")
    out = {}
    for col in raw.columns:
        s = raw[col].dropna()
        if col in US_SESSION:
            # US/FX bars for day u close after the NSE close, so they are only usable from u+1.
            s.index = s.index + pd.Timedelta(days=1)
        out[col] = s.reindex(s.index.union(cal)).ffill().reindex(cal)
    return pd.DataFrame(out)


def forward_returns(h, lag=ENTRY_LAG):
    """Log return from close t+lag to close t+lag+h, indexed by signal date t."""
    close = load_panel("close")
    return np.log(close.shift(-(lag + h)) / close.shift(-lag))


def rebalance_dates(start=EVAL_START, step=STEP):
    cal = calendar()
    return cal[cal >= pd.Timestamp(start)][::step]
