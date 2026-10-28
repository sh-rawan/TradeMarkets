import numpy as np
import pandas as pd
from tqdm import tqdm

from config import CHRONOS_MODEL, CONTEXT_LEN, ENTRY_LAG
from data import load_macro, load_panel

COVARIATES = ["us10y", "in10y", "usdinr", "vix"]


def chronos_signal(dates, horizons):
    """Chronos-2 zero-shot forecast of log price, with yields / USD-INR / VIX as past
    covariates. Value = forecast median log return over the holding period."""
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
        pred = pipe.predict_df(pd.concat(frames), prediction_length=steps, quantile_levels=[0.5],
                               id_column="id", timestamp_column="timestamp", target="target")
        median_col = "0.5" if "0.5" in pred.columns else "predictions"
        for bank, g in pred.groupby("id"):
            path = np.concatenate([[log_close[bank].iloc[loc]], g.sort_values("timestamp")[median_col].values])
            for h in horizons:
                rows.append((d, bank, h, path[ENTRY_LAG + h] - path[ENTRY_LAG]))
    return pd.DataFrame(rows, columns=["date", "ticker", "horizon", "value"])
