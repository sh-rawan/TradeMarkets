import numpy as np
import pandas as pd

from data import load_macro, load_panel
from signals import to_long


def reversal(dates, horizons, lookback=3):
    """Short-term reversal: banks that fell most over the last few days rank highest."""
    close = load_panel("close")
    return to_long(-np.log(close / close.shift(lookback)).reindex(dates), horizons)


def resid_reversal(dates, horizons, window=120, lookback=3):
    """Rate-sensitivity factor model: regress each bank on Nifty, yields and USD/INR over a
    rolling window, then bet on reversal of the bank-specific (residual) move."""
    rets = np.log(load_panel("close")).diff()
    macro = load_macro()
    factors = pd.DataFrame({
        "mkt": np.log(macro["nifty"]).diff(),
        "d_us10y": macro["us10y"].diff(),
        "d_usdinr": np.log(macro["usdinr"]).diff(),
    })
    if "in10y" in macro:
        factors["d_in10y"] = macro["in10y"].diff()

    out = {}
    for d in dates:
        loc = rets.index.get_loc(d)
        if loc < window:
            continue
        y_win = rets.iloc[loc - window + 1:loc + 1]
        x_win = factors.iloc[loc - window + 1:loc + 1]
        ok = x_win.notna().all(axis=1).values
        x = np.column_stack([np.ones(ok.sum()), x_win.values[ok]])
        row = {}
        for bank in y_win.columns:
            y = y_win[bank].values[ok]
            m = ~np.isnan(y)
            if m.sum() < window // 2 or np.isnan(y[-1]):
                continue
            beta, *_ = np.linalg.lstsq(x[m], y[m], rcond=None)
            row[bank] = -(y[m] - x[m] @ beta)[-lookback:].sum()
        out[d] = row
    wide = pd.DataFrame.from_dict(out, orient="index")
    wide.index.name = "date"
    return to_long(wide, horizons)


def random_signal(dates, horizons, seed=0):
    """Benchmark: what any real model has to beat."""
    close = load_panel("close").reindex(dates)
    rng = np.random.default_rng(seed)
    noise = pd.DataFrame(rng.standard_normal(close.shape), index=close.index, columns=close.columns)
    return to_long(noise.where(close.notna()), horizons)
