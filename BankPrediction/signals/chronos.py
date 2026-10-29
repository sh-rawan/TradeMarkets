import numpy as np
import pandas as pd
from tqdm import tqdm

from config import CHRONOS_MODEL, CONTEXT_LEN, ENTRY_LAG
from data import load_macro, load_panel

COVARIATES = ["us10y", "in10y", "usdinr", "vix"]
QUANTILES = [0.1, 0.5, 0.9]
Z_80 = 2.5631  # width of the 10-90% range of a standard normal, in std devs


def chronos_signal(dates, horizons):
    """Chronos-2 zero-shot probabilistic forecast of log price, with yields / USD-INR / VIX as
    past covariates. Mean = change in the median forecast over the holding period; std = from
    the 10-90% forecast range, assuming the daily increments are independent (so the
    holding-period variance is the forecast variance at exit minus that at entry)."""
    import torch
    from chronos import Chronos2Pipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = Chronos2Pipeline.from_pretrained(CHRONOS_MODEL, device_map=device)

    log_close = np.log(load_panel("close"))
    macro = load_macro()
    covs = macro[[c for c in COVARIATES if c in macro]]
    steps = ENTRY_LAG + max(horizons)

    rows = []
    for d in tqdm(dates, desc="chronos"):
        loc = log_close.index.get_loc(d)
        frames = []
        for bank in log_close.columns:
            y = log_close[bank].iloc[max(0, loc - CONTEXT_LEN + 1):loc + 1]
            if np.isnan(y.iloc[-1]) or y.notna().sum() < 100:
                continue
            df = covs.loc[y.index].copy()
            df["target"] = y.values
            df = df.dropna(subset=["target"]).ffill().bfill()
            # Trading days are irregular; the model only needs a regular index.
            df["timestamp"] = pd.date_range("2000-01-01", periods=len(df), freq="D")
            df["id"] = bank
            frames.append(df)
        pred = pipe.predict_df(pd.concat(frames), prediction_length=steps, quantile_levels=QUANTILES,
                               id_column="id", timestamp_column="timestamp", target="target")
        for bank, g in pred.groupby("id"):
            g = g.sort_values("timestamp")
            median = np.concatenate([[log_close[bank].iloc[loc]], g["0.5"].values])
            var = np.concatenate([[0.0], ((g["0.9"] - g["0.1"]).values / Z_80) ** 2])
            for h in horizons:
                a, b = ENTRY_LAG, ENTRY_LAG + h
                # Quantile crossings can make the variance shrink; then spread it evenly over the steps.
                v = var[b] - var[a] if var[b] > var[a] else var[b] * h / b
                rows.append((d, bank, h, median[b] - median[a], np.sqrt(v)))
    return pd.DataFrame(rows, columns=["date", "ticker", "horizon", "mean", "std"])
