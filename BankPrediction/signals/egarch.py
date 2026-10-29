import warnings

import numpy as np
import pandas as pd
from tqdm import tqdm

from config import ENTRY_LAG
from data import load_panel


def _plausible(res, r):
    """GARCH fits on windows with crash days (e.g. March 2020) sometimes converge to
    degenerate optima (huge alpha, nu at its lower bound) whose variance forecasts explode
    or collapse to zero."""
    p = res.params
    one_step = res.forecast(horizon=1, reindex=False).variance.values[-1, 0]
    return (res.convergence_flag == 0 and abs(p["beta[1]"]) < 1 and abs(p.get("alpha[1]", 0)) < 2
            and p["nu"] > 2.1 and r.var() / 25 < one_step < 25 * r.var())


def _ewma_var(r, lam=0.94):
    """RiskMetrics variance, the last resort when both GARCH fits are degenerate."""
    return float((r ** 2).ewm(alpha=1 - lam).mean().iloc[-1])


def egarch(dates, horizons, window=1000, simulations=500):
    """EGARCH(1,1,1) with Student-t errors and a constant mean, refit at each date on a rolling
    window, falling back to GJR-GARCH(1,1,1)-t when the EGARCH fit is degenerate.
    Mean = the fitted daily mean times h; std = the forecast std dev over the holding period."""
    from arch import arch_model

    rets = 100 * np.log(load_panel("close")).diff()
    steps = ENTRY_LAG + max(horizons)
    rows, fallbacks = [], {"gjr": 0, "ewma": 0}
    for d in tqdm(dates, desc="egarch"):
        loc = rets.index.get_loc(d)
        for bank in rets.columns:
            r = rets[bank].iloc[max(0, loc - window + 1):loc + 1].dropna()
            if len(r) < 250 or r.index[-1] != d:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = arch_model(r, mean="Constant", vol="EGARCH", p=1, o=1, q=1, dist="t").fit(disp="off")
                if not _plausible(res, r):
                    fallbacks["gjr"] += 1
                    res = arch_model(r, mean="Constant", vol="GARCH", p=1, o=1, q=1, dist="t").fit(disp="off")
                mu = res.params["mu"]
                if _plausible(res, r):
                    paths = res.forecast(horizon=steps, method="simulation", simulations=simulations,
                                         reindex=False).simulations.variances[-1]
                else:
                    fallbacks["ewma"] += 1
                    paths = np.full((1, steps), _ewma_var(r))
                    mu = r.mean()
            # paths[:, k] is the simulated variance of the return on day t+1+k; the holding
            # period is days t+ENTRY_LAG+1 .. t+ENTRY_LAG+h. Median across paths, because with
            # fat-tailed t errors a few simulated EGARCH paths explode and swamp the mean.
            for h in horizons:
                var = np.median(paths[:, ENTRY_LAG:ENTRY_LAG + h].sum(axis=1))
                rows.append((d, bank, h, h * mu / 100, np.sqrt(var) / 100))
    print(f"egarch: of {len(rows) // len(horizons)} fits, {fallbacks['gjr']} fell back to "
          f"GJR-GARCH and {fallbacks['ewma']} to EWMA")
    return pd.DataFrame(rows, columns=["date", "ticker", "horizon", "mean", "std"])
