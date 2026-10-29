import sys

import numpy as np
import pandas as pd
from tqdm import tqdm

from config import (CONTEXT_LEN, ENTRY_LAG, KRONOS_BATCH, KRONOS_DIR, KRONOS_MODEL, KRONOS_SAMPLES,
                    KRONOS_TOKENIZER)
from data import load_prices


def kronos_signal(dates, horizons):
    """Kronos zero-shot candlestick forecast. Kronos samples future candles like a language
    model samples words; each bank gets KRONOS_SAMPLES independent paths, and the mean and std
    dev of the holding-period log return across those paths are the forecast."""
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
        # predict_batch averages its own samples, so each bank is repeated instead: every copy
        # is one independent sampled path.
        reps = [i for i in range(len(banks)) for _ in range(KRONOS_SAMPLES)]
        closes = []
        for start in range(0, len(reps), KRONOS_BATCH):
            chunk = reps[start:start + KRONOS_BATCH]
            preds = predictor.predict_batch([xs[i] for i in chunk], [x_ts[i] for i in chunk], [y_ts] * len(chunk),
                                            pred_len=steps, T=1.0, top_p=0.9, sample_count=1, verbose=False)
            closes += [p["close"].values for p in preds]
        for i, (bank, x) in enumerate(zip(banks, xs)):
            paths = np.log(np.array(closes[i * KRONOS_SAMPLES:(i + 1) * KRONOS_SAMPLES]))
            paths = np.column_stack([np.full(len(paths), np.log(x["close"].iloc[-1])), paths])
            for h in horizons:
                r = paths[:, ENTRY_LAG + h] - paths[:, ENTRY_LAG]
                rows.append((d, bank, h, r.mean(), r.std(ddof=1)))
    return pd.DataFrame(rows, columns=["date", "ticker", "horizon", "mean", "std"])
