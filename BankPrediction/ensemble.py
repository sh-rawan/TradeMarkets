"""Calibrate, combine and score distribution forecasts.

Each forecast is a Student-t distribution of the holding-period log return, given by its mean,
std dev and tail parameter nu (lower nu = fatter tails; large nu ~ normal). Bank returns have
fat tails, so a normal distribution makes big moves look rarer than they are.

Scores, computed on realised outcomes:
- CRPS: how far the whole forecast distribution was from what happened (lower is better).
  It rewards a mean close to the outcome and a range that is neither too narrow nor too wide.
- Coverage: share of outcomes inside the central 68% and 95% ranges (68% and 95% if calibrated).
- IC: rank correlation between forecast means and outcomes across banks.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import beta as beta_fn
from scipy.stats import t as student_t

from config import (BENCHMARK, CAL_MIN, CAL_WINDOW, COST_BPS_PER_SIDE, DEFAULT_NU, ENTRY_LAG, IC_WINDOW,
                    MIN_IC_HISTORY, NU_BOUNDS, STEP, TOP_K)
from data import calendar


def wide(long, horizon, col):
    s = long[long["horizon"] == horizon]
    return s.pivot_table(index="date", columns="ticker", values=col)


def t_scale(std, nu):
    """Scale parameter of a Student-t with the given std dev."""
    return std * np.sqrt((nu - 2) / nu)


def crps_t(mean, std, nu, actual):
    """CRPS of a Student-t forecast (closed form, Jordan et al. 2019), elementwise."""
    s = t_scale(std, nu)
    z = (actual - mean) / s
    tail = 2 * np.sqrt(nu) * beta_fn(0.5, nu - 0.5) / ((nu - 1) * beta_fn(0.5, nu / 2) ** 2)
    return s * (z * (2 * student_t.cdf(z, nu) - 1)
                + 2 * student_t.pdf(z, nu) * (nu + z ** 2) / (nu - 1) - tail)


def central(std, nu, p):
    """Half-width of the central p range of a Student-t with this std dev."""
    return student_t.ppf(0.5 + p / 2, nu) * t_scale(std, nu)


def ic_series(sig, fwd):
    """Spearman correlation across banks between forecast and realised return, per date."""
    fwd = fwd.reindex(index=sig.index, columns=sig.columns)
    s, f = sig.where(fwd.notna()), fwd.where(sig.notna())
    return s.rank(axis=1).corrwith(f.rank(axis=1), axis=1)


def known_at(dates, h, lag=ENTRY_LAG):
    """Date on which the outcome of a forecast made on each date is fully realised."""
    cal = calendar()
    pos = np.minimum(cal.get_indexer(dates) + lag + h, len(cal) - 1)
    return pd.Series(cal[pos], index=dates)


def _fit_t(e, start):
    """Width multiplier k and tail nu that make e (errors in units of the forecast std) most
    likely under k * (unit-variance Student-t with nu)."""
    def nll(p):
        k, nu = np.exp(p[0]), p[1]
        s = k * np.sqrt((nu - 2) / nu)
        return -(student_t.logpdf(e / s, nu) - np.log(s)).sum()
    res = minimize(nll, [np.log(start[0]), start[1]], method="L-BFGS-B",
                   bounds=[(np.log(0.2), np.log(5.0)), NU_BOUNDS])
    return (np.exp(res.x[0]), res.x[1]) if res.success else start


def calibrate(mean, std, fwd, h):
    """Recalibrate a model on its own track record. At each date, fit a width multiplier and a
    tail parameter to its last CAL_WINDOW standardised errors whose outcomes are known by then
    (no look-ahead). Returns (std, nu) frames: the calibrated std dev and the tail parameter."""
    z = (fwd.reindex_like(mean) - mean) / std
    ready = known_at(mean.index, h)
    stacked = z.stack().dropna()
    err_dates = stacked.index.get_level_values(0)
    params, fit = {}, (1.0, DEFAULT_NU)
    for d in mean.index:
        usable = stacked[ready.reindex(err_dates).values <= d].tail(CAL_WINDOW)
        if len(usable) >= CAL_MIN:
            fit = _fit_t(usable.values, fit)
        params[d] = fit if len(usable) >= CAL_MIN else (1.0, DEFAULT_NU)
    k = pd.Series({d: p[0] for d, p in params.items()})
    nu = pd.Series({d: p[1] for d, p in params.items()})
    return std.mul(k, axis=0), pd.DataFrame(np.tile(nu.values[:, None], (1, mean.shape[1])),
                                            index=mean.index, columns=mean.columns).where(mean.notna())


def combine(dists, fwd, h, window=IC_WINDOW):
    """Mix the models' calibrated distributions. Each model is weighted by how much lower its
    average CRPS was than the benchmark's over its last `window` forecasts whose outcomes are
    known on the date (no look-ahead); models that did not beat the benchmark get no weight, and
    if none did, the benchmark alone is used. The mixture's std dev includes the models'
    disagreement; its tails are then calibrated like any other model's.
    dists: {model: (mean, std, nu)}. Returns (mean, std, nu), weights."""
    dates = sorted(set().union(*(m.index for m, *_ in dists.values())))
    tickers = sorted(set().union(*(m.columns for m, *_ in dists.values())))
    score = pd.DataFrame({m: crps_t(mu, sd, nu, fwd.reindex_like(mu)).mean(axis=1)
                          for m, (mu, sd, nu) in dists.items()}).reindex(dates)
    gain = score.rsub(score[BENCHMARK], axis=0)  # positive = better than the benchmark
    ready = known_at(pd.DatetimeIndex(dates), h)

    means, stds, weights = {}, {}, {}
    for d in dates:
        hist = gain[ready.values <= d].tail(window)
        w = hist.mean().clip(lower=0).fillna(0) if len(hist) >= MIN_IC_HISTORY else pd.Series(0.0, index=gain.columns)
        if w.sum() == 0:
            w[BENCHMARK] = 1.0
        w = w / w.sum()
        # Mixture moments per bank, renormalised over the models that cover that bank.
        m1, m2, total = (pd.Series(0.0, index=tickers) for _ in range(3))
        for m, (mu, sd, _) in dists.items():
            if w[m] == 0 or d not in mu.index:
                continue
            mu_d, sd_d = mu.loc[d].reindex(tickers), sd.loc[d].reindex(tickers)
            ok = mu_d.notna() & sd_d.notna()
            m1 += (w[m] * mu_d).where(ok, 0)
            m2 += (w[m] * (sd_d ** 2 + mu_d ** 2)).where(ok, 0)
            total += w[m] * ok
        total = total.replace(0, np.nan)
        mean = m1 / total
        means[d], stds[d] = mean, np.sqrt((m2 / total - mean ** 2).clip(lower=0))
        weights[d] = w
    mean, std = pd.DataFrame(means).T, pd.DataFrame(stds).T
    std, nu = calibrate(mean, std, fwd, h)
    return (mean, std, nu), pd.DataFrame(weights).T


def long_short(mean, std, fwd, k=TOP_K, cost_bps=COST_BPS_PER_SIDE):
    """Long the k banks with the highest mean / std (expected return per unit of risk), short the
    k lowest, via stock futures; 0.5 gross per leg, legs weighted by inverse forecast std dev.
    Each trade pays cost to enter and exit. Returns net log return per rebalance."""
    score = mean / std.reindex_like(mean)
    out = {}
    for d in score.index:
        if d not in fwd.index:
            continue
        s = score.loc[d].dropna()
        s = s[fwd.loc[d, s.index].notna()]
        if len(s) < 2 * k:
            continue
        w = pd.Series(0.0, index=s.index)
        for sign, names in {1: s.nlargest(k).index, -1: s.nsmallest(k).index}.items():
            iv = 1 / std.loc[d, names]
            w[names] = sign * 0.5 * iv / iv.sum()
        gross = (w * fwd.loc[d, w.index]).sum()
        out[d] = gross - w.abs().sum() * 2 * cost_bps / 1e4
    return pd.Series(out, dtype=float)


def summarise(name, mean, std, nu, fwd, pnl, h, bench_crps):
    """One row of the evaluation: distribution scores first, then ranking and trading."""
    actual = fwd.reindex_like(mean)
    c = crps_t(mean, std, nu, actual)
    known = c.notna()
    err = (actual - mean).abs()
    ic = ic_series(mean, fwd).dropna()
    both = c.stack().index.intersection(bench_crps.stack().index)
    periods_per_year = 252 / max(h, STEP)
    return {
        "model": name,
        "n": int(known.any(axis=1).sum()),
        "crps_bps": c.stack().mean() * 1e4,
        "crps_skill": 1 - c.stack()[both].mean() / bench_crps.stack()[both].mean(),
        "cover_68": (err <= central(std, nu, 0.68))[known].sum().sum() / known.sum().sum(),
        "cover_95": (err <= central(std, nu, 0.95))[known].sum().sum() / known.sum().sum(),
        "nu": nu[known].stack().median(),
        "mean_ic": ic.mean(),
        "ic_t": ic.mean() / ic.std() * np.sqrt(len(ic)) if len(ic) > 1 else np.nan,
        "net_bps_per_trade": pnl.mean() * 1e4,
        "sharpe_ann": pnl.mean() / pnl.std() * np.sqrt(periods_per_year) if len(pnl) > 1 else np.nan,
    }
