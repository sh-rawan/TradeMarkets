"""Each signal function takes (dates, horizons) and returns a long frame
[date, ticker, horizon, value]. Return models give a forecast log return over the holding
period; "egarch" gives a forecast volatility over it."""
from importlib import import_module

import pandas as pd

from config import SIGNALS_DIR
from store import write

REGISTRY = {
    "reversal": ("signals.baseline", "reversal"),
    "resid_reversal": ("signals.baseline", "resid_reversal"),
    "random": ("signals.baseline", "random_signal"),
    "egarch": ("signals.egarch", "egarch_vol"),
    "chronos": ("signals.chronos", "chronos_signal"),
    "kronos": ("signals.kronos", "kronos_signal"),
}
COLUMNS = ["date", "ticker", "horizon", "value"]


def get(name):
    module, fn = REGISTRY[name]
    return getattr(import_module(module), fn)


def cache_path(name):
    return SIGNALS_DIR / f"{name}.parquet"


def load_cached(name):
    path = cache_path(name)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_parquet(path)


def compute(name, dates, horizons, refresh=False):
    """Compute the signal for dates not already cached, append, and return the full cache."""
    cached = pd.DataFrame(columns=COLUMNS) if refresh else load_cached(name)
    todo = pd.DatetimeIndex(dates).difference(pd.DatetimeIndex(cached["date"].unique()))
    if len(todo):
        print(f"{name}: computing {len(todo)} dates")
        new = get(name)(todo, horizons)
        cached = pd.concat([cached, new[COLUMNS]], ignore_index=True) if len(cached) else new[COLUMNS]
        write(cached.sort_values(["date", "horizon", "ticker"]), cache_path(name))
    else:
        print(f"{name}: up to date")
    return cached


def to_long(wide, horizons):
    """Broadcast a horizon-independent (date x ticker) frame to the long format."""
    long = wide.stack().rename("value").reset_index()
    long.columns = ["date", "ticker", "value"]
    return pd.concat([long.assign(horizon=h) for h in horizons], ignore_index=True)
