"""Bank Nifty short-horizon signal stack.

    python run.py data                                  # download prices + macro from Yahoo
    python run.py signals --models reversal,egarch      # compute + cache signals on rebalance dates
    python run.py evaluate                              # walk-forward evaluation vs random baseline
    python run.py today                                 # ranked banks for the latest close
"""
import argparse
import warnings

import pandas as pd

warnings.filterwarnings("ignore", module="yfinance")

import signals
from config import (ENSEMBLE_TABLE, ENSEMBLE_WEIGHTS_TABLE, EVALUATION_TABLE, HORIZONS, PSU_BANKS,
                    REPORT_DIR, RETURN_MODELS)
from data import calendar, download_all, forward_returns, rebalance_dates
from ensemble import long_short, rank_average, summarise, wide
from store import write


def available(models):
    return [m for m in models if signals.cache_path(m).exists()]


def publish_ensemble(results):
    """Write {horizon: (score, weights)} to the store as long tables for DataVisualizer."""
    scores, weights = [], []
    for h, (score, w) in results.items():
        scores.append(score.rename_axis(index="date", columns="ticker").stack().rename("score")
                      .reset_index().assign(horizon=h))
        weights.append(w.rename_axis(index="date", columns="model").stack().rename("weight")
                       .reset_index().assign(horizon=h))
    write(pd.concat(scores, ignore_index=True), ENSEMBLE_TABLE)
    write(pd.concat(weights, ignore_index=True), ENSEMBLE_WEIGHTS_TABLE)


def cmd_signals(args):
    dates = rebalance_dates(args.start, args.step)
    for m in args.models.split(","):
        signals.compute(m, dates, HORIZONS, refresh=args.refresh)


def cmd_evaluate(args):
    models = available(RETURN_MODELS)
    if not models:
        raise SystemExit("No cached return signals. Run: python run.py signals --models reversal,resid_reversal")
    vol_long = signals.load_cached("egarch") if signals.cache_path("egarch").exists() else None
    rand_long = signals.load_cached("random") if signals.cache_path("random").exists() else None
    print("Ensemble inputs:", ", ".join(models), "| vol sizing:", "egarch" if vol_long is not None else "off")

    REPORT_DIR.mkdir(exist_ok=True)
    rows, results = [], {}
    for h in HORIZONS:
        fwd = forward_returns(h)
        vol = wide(vol_long, h) if vol_long is not None else None
        sigs = {m: wide(signals.load_cached(m), h) for m in models}
        score, weights = results[h] = rank_average(sigs, fwd, h)
        candidates = dict(sigs, ensemble=score)
        if rand_long is not None:
            candidates["random"] = wide(rand_long, h)
        for name, sig in candidates.items():
            pnl = long_short(sig, fwd, vol)
            rows.append({"horizon": h, **summarise(name, sig, fwd, pnl, h)})
        weights.to_csv(REPORT_DIR / f"ensemble_weights_h{h}.csv")

    table = pd.DataFrame(rows)
    table.to_csv(REPORT_DIR / "evaluation.csv", index=False)
    write(table, EVALUATION_TABLE)
    publish_ensemble(results)
    with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 120):
        for h, g in table.groupby("horizon"):
            print(f"\n=== {h}-day horizon ===")
            print(g.drop(columns="horizon").to_string(index=False))
    print(f"\nSaved to {REPORT_DIR}")


def cmd_today(args):
    last = calendar()[-1]
    models = [m for m in args.models.split(",") if m in RETURN_MODELS]
    for m in models + ["egarch"]:
        signals.compute(m, pd.DatetimeIndex([last]), HORIZONS)
    print(f"\nSignals as of close {last.date()} (position opens next close)")
    results = {}
    for h in HORIZONS:
        fwd = forward_returns(h)
        sigs = {m: wide(signals.load_cached(m), h) for m in models}
        score, weights = results[h] = rank_average(sigs, fwd, h)
        vol = wide(signals.load_cached("egarch"), h)
        out = pd.DataFrame({"score": score.loc[last], f"vol_{h}d": vol.loc[last]})
        out["type"] = ["PSU" if b in PSU_BANKS else "private" for b in out.index]
        w = weights.loc[last]
        print(f"\n--- {h}-day | weights: " + ", ".join(f"{m}={w[m]:.2f}" for m in w.index) + " ---")
        print(out.sort_values("score", ascending=False).to_string(float_format="{:.3f}".format))
    publish_ensemble(results)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("data")
    s = sub.add_parser("signals")
    s.add_argument("--models", default="reversal,resid_reversal,random,egarch")
    s.add_argument("--start", default=None)
    s.add_argument("--step", type=int, default=None)
    s.add_argument("--refresh", action="store_true")
    sub.add_parser("evaluate")
    t = sub.add_parser("today")
    t.add_argument("--models", default=",".join(RETURN_MODELS))
    args = p.parse_args()

    if args.cmd == "data":
        download_all()
    elif args.cmd == "signals":
        from config import EVAL_START, STEP
        args.start, args.step = args.start or EVAL_START, args.step or STEP
        cmd_signals(args)
    elif args.cmd == "evaluate":
        cmd_evaluate(args)
    elif args.cmd == "today":
        cmd_today(args)


if __name__ == "__main__":
    main()
