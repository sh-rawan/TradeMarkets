"""Simple distribution forecasts: a historical benchmark, and two reversal rules turned into
predictive regressions so that they forecast a mean and a std dev instead of a bare score."""
import numpy as np
import pandas as pd

from config import ENTRY_LAG
from data import load_macro, load_panel
from signals import to_long


def historical(dates, horizons, window=252):
    """Benchmark: the bank's own average daily return and volatility over the last year,
    scaled to the horizon. A model is only useful if its distribution beats this one."""
    rets = np.log(load_panel("close")).diff()
    mu = rets.rolling(window, min_periods=window // 2).mean().reindex(dates)
    sd = rets.rolling(window, min_periods=window // 2).std().reindex(dates)
    return to_long({h: (h * mu, np.sqrt(h) * sd) for h in horizons})


def predictive(signal, dates, horizons, train=500, vol_window=120):
    """Turn a daily signal panel into a distribution: regress realised holding-period returns
    on the signal, pooled across banks, using only outcomes already known on each date.
    Mean = the fitted value; std = the bank's own residual std over the last vol_window days."""
    close = load_panel("close")
    signal = signal.reindex(close.index)
    out = {}
    for h in horizons:
        fwd = np.log(close.shift(-(ENTRY_LAG + h)) / close.shift(-ENTRY_LAG))
        mean, std = {}, {}
        for d in dates:
            # Day t's outcome is known at the close of t+ENTRY_LAG+h, so it must be <= d.
            end = close.index.get_loc(d) - ENTRY_LAG - h
            s, y = signal.iloc[max(0, end - train + 1):end + 1], fwd.iloc[max(0, end - train + 1):end + 1]
            ok = (s.notna() & y.notna()).values
            if ok.sum() < 250:
                continue
            slope, intercept = np.polyfit(s.values[ok], y.values[ok], 1)
            resid = (y - intercept - slope * s).where(ok)
            mean[d] = intercept + slope * signal.loc[d]
            std[d] = resid.tail(vol_window).std()
        out[h] = (pd.DataFrame(mean).T, pd.DataFrame(std).T)
    return to_long(out)


def reversal(dates, horizons, lookback=3):
    """Short-term reversal: banks that fell over the last few days tend to bounce."""
    close = load_panel("close")
    return predictive(-np.log(close / close.shift(lookback)), dates, horizons)


def resid_reversal(dates, horizons, window=120, lookback=3):
    """Reversal of the bank-specific move: regress each bank on Nifty, yields and USD/INR over a
    rolling window and keep the residual, i.e. the part the market and rates don't explain."""
    rets = np.log(load_panel("close")).diff()
    macro = load_macro()
    factors = pd.DataFrame({
        "mkt": np.log(macro["nifty"]).diff(),
        "d_us10y": macro["us10y"].diff(),
        "d_usdinr": np.log(macro["usdinr"]).diff(),
    })
    if "in10y" in macro:
        factors["d_in10y"] = macro["in10y"].diff()
    factors = factors.reindex(rets.index)

    # The regression needs the signal on every past day, not just the forecast dates.
    out = {}
    for loc in range(window, len(rets)):
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
        out[rets.index[loc]] = row
    return predictive(pd.DataFrame.from_dict(out, orient="index"), dates, horizons)
