import sys

import numpy as np
import pandas as pd
from tqdm import tqdm

from config import CONTEXT_LEN, ENTRY_LAG, KRONOS_DIR, KRONOS_MODEL, KRONOS_SAMPLES, KRONOS_TOKENIZER
from data import load_prices


def kronos_signal(dates, horizons):
    """Kronos zero-shot candlestick forecast (mean of KRONOS_SAMPLES sampled paths).
    Value = forecast log return over the holding period."""
    if not KRONOS_DIR.exists():
        raise RuntimeError(f"Clone https://github.com/shiyu-coder/Kronos into {KRONOS_DIR}")
    sys.path.insert(0, str(KRONOS_DIR))
    import torch
    from model import Kronos, KronosPredictor, KronosTokenizer

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    predictor = KronosPredictor(Kronos.from_pretrained(KRONOS_MODEL),
                                KronosTokenizer.from_pretrained(KRONOS_TOKENIZER),
                                device=device, max_context=CONTEXT_LEN)
    prices = load_prices()
    steps = ENTRY_LAG + max(horizons)

    rows = []
    for d in tqdm(dates, desc="kronos"):
        # predict_batch needs equal lengths, so only banks with a full context are scored.
        banks, xs, x_ts = [], [], []
        for bank, df in prices.items():
            hist = df.loc[:d].tail(CONTEXT_LEN)
            if len(hist) < CONTEXT_LEN or hist.index[-1] != d:
                continue
            x = hist[["open", "high", "low", "close", "volume"]].fillna({"volume": 0.0})
            x["amount"] = x["volume"] * x["close"]
            banks.append(bank)
            xs.append(x.reset_index(drop=True))
            x_ts.append(pd.Series(hist.index))
        if not banks:
            continue
        y_ts = pd.Series(pd.bdate_range(d + pd.offsets.BDay(1), periods=steps))
        preds = predictor.predict_batch(xs, x_ts, [y_ts] * len(banks), pred_len=steps, T=1.0,
                                        top_p=0.9, sample_count=KRONOS_SAMPLES, verbose=False)
        for bank, x, pred in zip(banks, xs, preds):
            path = np.log(np.concatenate([[x["close"].iloc[-1]], pred["close"].values]))
            for h in horizons:
                rows.append((d, bank, h, path[ENTRY_LAG + h] - path[ENTRY_LAG]))
    return pd.DataFrame(rows, columns=["date", "ticker", "horizon", "value"])
