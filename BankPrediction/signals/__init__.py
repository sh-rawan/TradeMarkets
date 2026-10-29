"""Each model takes (dates, horizons) and returns a long frame [date, ticker, horizon, mean, std]:
the forecast distribution of the log return over the holding period (enter at close
t+ENTRY_LAG, hold h days), summarised by its mean and standard deviation."""
from importlib import import_module

import pandas as pd

from config import SIGNALS_DIR
from store import write

REGISTRY = {
    "historical": ("signals.baseline", "historical"),
    "reversal": ("signals.baseline", "reversal"),
    "resid_reversal": ("signals.baseline", "resid_reversal"),
    "egarch": ("signals.egarch", "egarch"),
    "lgbm": ("signals.lgbm", "lgbm"),
    "chronos": ("signals.chronos", "chronos_signal"),
    "kronos": ("signals.kronos", "kronos_signal"),
}
COLUMNS = ["date", "ticker", "horizon", "mean", "std"]


def get(name):
    module, fn = REGISTRY[name]
    return getattr(import_module(module), fn)


def cache_path(name):
    return SIGNALS_DIR / f"{name}.parquet"


def load_cached(name):
    path = cache_path(name)
    cached = pd.read_parquet(path) if path.exists() else None
    # Caches from before the switch to distribution forecasts hold a single value column.
    if cached is None or not set(COLUMNS) <= set(cached.columns):
        return pd.DataFrame(columns=COLUMNS)
    return cached


def compute(name, dates, horizons, refresh=False):
    """Compute the forecast for dates not already cached, append, and return the full cache."""
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


def to_long(by_horizon):
    """{horizon: (mean, std)} of (date x ticker) frames -> the long format."""
    frames = []
    for h, (mean, std) in by_horizon.items():
        df = pd.concat({"mean": mean.stack(), "std": std.stack()}, axis=1).dropna()
        df.index.names = ["date", "ticker"]
        frames.append(df.reset_index().assign(horizon=h))
    return pd.concat(frames, ignore_index=True)[COLUMNS]
