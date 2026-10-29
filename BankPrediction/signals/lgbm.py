"""LightGBM distribution model. One gradient-boosted model learns the mean of the holding-period
return from the feature panel (signals/features.py); a second learns its variance from the first
model's out-of-sample errors, so the std dev reflects how wrong the mean really is, not how well
it fits its own training data. Both are retrained every LGBM_RETRAIN trading days on the
outcomes known by then over the last LGBM_TRAIN_DAYS trading days, pooled across banks."""
import lightgbm as lgb
import numpy as np
import pandas as pd
from tqdm import tqdm

from config import ENTRY_LAG, LGBM_FOLDS, LGBM_PARAMS, LGBM_RETRAIN, LGBM_ROUNDS, LGBM_TRAIN_DAYS
from data import load_panel
from signals import to_long
from signals.features import feature_panel

LOG_CHI2_MEAN = -1.2704  # E[log z^2] for a standard normal z: turns mean log e^2 into log variance


def _fit(x, y):
    return lgb.train(LGBM_PARAMS, lgb.Dataset(x, y), num_boost_round=LGBM_ROUNDS)


def _train(train, features, h):
    """Mean model on all rows; variance model on out-of-sample errors from an expanding
    walk-forward over LGBM_FOLDS time blocks, purged so no training target overlaps a test day."""
    days = train.index.get_level_values("date")
    unique = days.unique().sort_values()
    edges = unique[np.linspace(0, len(unique) - 1, LGBM_FOLDS + 1).astype(int)]
    gap = pd.Timedelta(days=2 * (ENTRY_LAG + h))  # calendar-day purge, generous for weekends
    errors = []
    for lo, hi in zip(edges[1:-1], edges[2:]):
        fit = train[days < lo - gap]
        test = train[(days >= lo) & (days <= hi)]
        if len(fit) < 2000 or not len(test):
            continue
        errors.append(test["y"] - _fit(fit[features], fit["y"]).predict(test[features]))
    oos = pd.concat(errors)
    var_target = np.log(oos ** 2 + 1e-10)
    return _fit(train[features], train["y"]), _fit(train.loc[oos.index, features], var_target)


def lgbm(dates, horizons):
    x = feature_panel()
    features = list(x.columns)
    close = load_panel("close")
    pos = pd.Series(np.arange(len(close)), index=close.index)
    row_pos = pos.reindex(x.index.get_level_values("date")).values
    out = {}
    for h in horizons:
        y = np.log(close.shift(-(ENTRY_LAG + h)) / close.shift(-ENTRY_LAG)).stack().rename("y")
        y.index.names = ["date", "ticker"]
        data = x.join(y)
        mean, std = {}, {}
        models, trained_at = None, None
        for d in tqdm(sorted(dates), desc=f"lgbm {h}d"):
            p = pos[d]
            if models is None or p - trained_at >= LGBM_RETRAIN:
                # Day t's outcome is known at the close of t+ENTRY_LAG+h, so only t <= p-ENTRY_LAG-h is
                # usable; of that, only the most recent LGBM_TRAIN_DAYS, so stale regimes drop out.
                last = p - ENTRY_LAG - h
                train = data[(row_pos <= last) & (row_pos > last - LGBM_TRAIN_DAYS)].dropna(subset=["y"])
                models, trained_at = _train(train, features, h), p
            today = x.xs(d, level="date")
            mean[d] = pd.Series(models[0].predict(today[features]), index=today.index)
            std[d] = pd.Series(np.sqrt(np.exp(models[1].predict(today[features]) - LOG_CHI2_MEAN)), index=today.index)
        out[h] = (pd.DataFrame(mean).T, pd.DataFrame(std).T)
    return to_long(out)
