from functools import lru_cache

import numpy as np
import pandas as pd

from config import ENTRY_LAG, EVAL_START, INDIA_10Y_CSV, MACRO_TABLE, PRICES_TABLE, STEP, US_SESSION
from store import sql, table

OHLCV = ["open", "high", "low", "close", "volume"]


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
