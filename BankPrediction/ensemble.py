import numpy as np
import pandas as pd

from config import COST_BPS_PER_SIDE, ENTRY_LAG, IC_WINDOW, MIN_IC_HISTORY, STEP, TOP_K
from data import calendar


def wide(signals_long, horizon):
    s = signals_long[signals_long["horizon"] == horizon]
    return s.pivot_table(index="date", columns="ticker", values="value")


def cs_rank(w):
    """Cross-sectional percentile rank, centred on zero."""
    return w.rank(axis=1, pct=True) - 0.5


def ic_series(sig, fwd):
    """Spearman correlation across banks between signal and realised forward return, per date."""
    fwd = fwd.reindex(index=sig.index, columns=sig.columns)
    s, f = sig.where(fwd.notna()), fwd.where(sig.notna())
    return s.rank(axis=1).corrwith(f.rank(axis=1), axis=1)


def known_at(dates, h, lag=ENTRY_LAG):
    """Date on which the outcome of a signal made on each date is fully realised."""
    cal = calendar()
    pos = np.minimum(cal.get_indexer(dates) + lag + h, len(cal) - 1)
    return pd.Series(cal[pos], index=dates)


def rank_average(signals, fwd, h, window=IC_WINDOW):
    """Combine model signals by averaging cross-sectional ranks, each weighted by its rolling
    realised IC (negative IC -> weight 0). Only ICs whose outcome is known by the signal date
    are used, so there is no look-ahead."""
    ranks = {m: cs_rank(s) for m, s in signals.items()}
    dates = sorted(set().union(*(s.index for s in signals.values())))
    ics = pd.DataFrame({m: ic_series(s, fwd) for m, s in signals.items()}).reindex(dates)
    ready = known_at(pd.DatetimeIndex(dates), h)

    scores, weights = {}, {}
    for d in dates:
        hist = ics[ready.values <= d].tail(window)
        w = hist.mean().clip(lower=0).fillna(0)
        if len(hist) < MIN_IC_HISTORY or w.sum() == 0:
            w = pd.Series(1.0, index=ics.columns)
        num, den = 0, 0
        for m, r in ranks.items():
            if d in r.index:
                row = r.loc[d]
                num = num + (w[m] * row).fillna(0)
                den = den + w[m] * row.notna()
        scores[d] = num / den.replace(0, np.nan)
        weights[d] = w / w.sum()
    return pd.DataFrame(scores).T, pd.DataFrame(weights).T


def long_short(score, fwd, vol=None, k=TOP_K, cost_bps=COST_BPS_PER_SIDE):
    """Long the top-k, short the bottom-k banks (via stock futures), 0.5 gross per leg.
    With vol, legs are weighted by inverse forecast volatility. Each trade pays cost to
    enter and exit. Returns net log return per rebalance."""
    out = {}
    for d in score.index:
        if d not in fwd.index:
            continue
        s = score.loc[d].dropna()
        s = s[fwd.loc[d, s.index].notna()]
        if len(s) < 2 * k:
            continue
        legs = {1: s.nlargest(k).index, -1: s.nsmallest(k).index}
        w = pd.Series(0.0, index=s.index)
        for sign, names in legs.items():
            iv = pd.Series(1.0, index=names)
            if vol is not None and d in vol.index:
                iv = (1 / vol.loc[d, names]).fillna(1 / vol.loc[d].median())
            w[names] = sign * 0.5 * iv / iv.sum()
        gross = (w * fwd.loc[d, w.index]).sum()
        out[d] = gross - w.abs().sum() * 2 * cost_bps / 1e4
    return pd.Series(out, dtype=float)


def summarise(name, sig, fwd, pnl, h):
    ic = ic_series(sig, fwd).dropna()
    periods_per_year = 252 / max(h, STEP)
    return {
        "model": name,
        "n": len(ic),
        "mean_ic": ic.mean(),
        "ic_t": ic.mean() / ic.std() * np.sqrt(len(ic)) if len(ic) > 1 else np.nan,
        "hit_rate": (pnl > 0).mean(),
        "net_bps_per_trade": pnl.mean() * 1e4,
        "sharpe_ann": pnl.mean() / pnl.std() * np.sqrt(periods_per_year) if len(pnl) > 1 else np.nan,
    }
