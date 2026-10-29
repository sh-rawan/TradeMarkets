"""Bank Nifty short-horizon signal stack.

    python run.py data                                  # download prices + macro from Yahoo
    python run.py signals --models historical,egarch    # forecast mean + std on rebalance dates
    python run.py evaluate                              # walk-forward scores vs the historical benchmark
    python run.py today                                 # forecasts for the latest close
"""
import argparse
import warnings

import pandas as pd

warnings.filterwarnings("ignore", module="yfinance")

import signals
from config import (BENCHMARK, ENSEMBLE_WEIGHTS_TABLE, ENTRY_LAG, EVALUATION_TABLE, FORECASTS_DIR, HORIZONS,
                    MODEL_RAM_GB, MODELS, OUTCOMES_TABLE, PSU_BANKS, REPORT_DIR)
from data import calendar, download_all, forward_returns, rebalance_dates
from ensemble import calibrate, combine, crps_t, known_at, long_short, summarise, wide
from memlimit import limit_ram
from store import write


def available(models):
    """Models with an up-to-date (mean + std) forecast cache."""
    return [m for m in models if len(signals.load_cached(m))]


def load_dists(models, h, fwd):
    """{model: (mean, std, nu)}: each model's forecasts, Student-t calibrated on its own past errors."""
    out = {}
    for m in models:
        long = signals.load_cached(m)
        mean, std = wide(long, h, "mean"), wide(long, h, "std")
        out[m] = (mean, *calibrate(mean, std, fwd, h))
    return out


def publish_forecasts(results):
    """Write the calibrated forecasts of every model and the ensemble, and the ensemble weights,
    as long tables for DataVisualizer. results: {horizon: ({model: (mean, std, nu)}, weights)}."""
    tables, weights = {}, []
    for h, (dists, w) in results.items():
        for m, (mean, std, nu) in dists.items():
            df = pd.concat({"mean": mean.stack(), "std": std.stack(), "nu": nu.stack()}, axis=1).dropna()
            tables.setdefault(m, []).append(df.rename_axis(["date", "ticker"]).reset_index().assign(horizon=h))
        weights.append(w.rename_axis(index="date", columns="model").stack().rename("weight")
                       .reset_index().assign(horizon=h))
    for m, frames in tables.items():
        write(pd.concat(frames, ignore_index=True)[["date", "ticker", "horizon", "mean", "std", "nu"]],
              FORECASTS_DIR / f"{m}.parquet")
    write(pd.concat(weights, ignore_index=True), ENSEMBLE_WEIGHTS_TABLE)


def publish_outcomes():
    """What actually happened after every signal date, so DataVisualizer can score each prediction.
    Same timing as the backtest: enter at close t+ENTRY_LAG, exit h days later. Outcomes that are
    not known yet have no actual return or exit date."""
    dates = pd.DatetimeIndex(sorted(set().union(*(signals.load_cached(m)["date"].unique()
                                                  for m in available(list(signals.REGISTRY))))))
    cal = calendar()
    entry = pd.Series(cal[(cal.get_indexer(dates) + ENTRY_LAG).clip(max=len(cal) - 1)], index=dates)
    frames = []
    for h in HORIZONS:
        fwd = forward_returns(h).reindex(dates)
        df = fwd.rename_axis(index="date", columns="ticker").stack(future_stack=True).rename("actual").reset_index()
        df["horizon"] = h
        df["actual_vs_peers"] = df["actual"] - df.groupby("date")["actual"].transform("mean")
        df["entry_date"] = df["date"].map(entry)
        df["exit_date"] = df["date"].map(known_at(dates, h)).where(df["actual"].notna())
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    write(out[["date", "ticker", "horizon", "entry_date", "exit_date", "actual", "actual_vs_peers"]], OUTCOMES_TABLE)


def cmd_signals(args):
    dates = rebalance_dates(args.start, args.step)
    for m in args.models.split(","):
        signals.compute(m, dates, HORIZONS, refresh=args.refresh)


def cmd_evaluate(args):
    models = available(MODELS)
    if BENCHMARK not in models:
        raise SystemExit(f"No {BENCHMARK} forecasts. Run: python run.py signals")
    print("Ensemble inputs:", ", ".join(models))

    REPORT_DIR.mkdir(exist_ok=True)
    rows, results = [], {}
    for h in HORIZONS:
        fwd = forward_returns(h)
        dists = load_dists(models, h, fwd)
        ens, weights = combine(dists, fwd, h)
        dists["ensemble"] = ens
        results[h] = (dists, weights)
        bench_crps = crps_t(*dists[BENCHMARK], fwd.reindex_like(dists[BENCHMARK][0]))
        for name, (mean, std, nu) in dists.items():
            pnl = long_short(mean, std, fwd)
            rows.append({"horizon": h, **summarise(name, mean, std, nu, fwd, pnl, h, bench_crps)})
        weights.to_csv(REPORT_DIR / f"ensemble_weights_h{h}.csv")

    table = pd.DataFrame(rows)
    table.to_csv(REPORT_DIR / "evaluation.csv", index=False)
    write(table, EVALUATION_TABLE)
    publish_forecasts(results)
    publish_outcomes()
    with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 160):
        for h, g in table.groupby("horizon"):
            print(f"\n=== {h}-day horizon ===")
            print(g.drop(columns="horizon").to_string(index=False))
    print(f"\nSaved to {REPORT_DIR}")


def cmd_today(args):
    last = calendar()[-1]
    models = [m for m in args.models.split(",") if m in MODELS]
    for m in models:
        signals.compute(m, pd.DatetimeIndex([last]), HORIZONS)
    models = available(models)
    print(f"\nForecasts as of close {last.date()} (position opens next close); mean and std are % log return")
    results = {}
    for h in HORIZONS:
        fwd = forward_returns(h)
        dists = load_dists(models, h, fwd)
        (mean, std, nu), w = combine(dists, fwd, h)
        dists["ensemble"] = (mean, std, nu)
        results[h] = (dists, w)
        out = pd.DataFrame({"mean_%": 100 * mean.loc[last], "std_%": 100 * std.loc[last],
                            "mean/std": mean.loc[last] / std.loc[last], "tail_nu": nu.loc[last]})
        out["type"] = ["PSU" if b in PSU_BANKS else "private" for b in out.index]
        wl = w.loc[last]
        print(f"\n--- {h}-day | weights: " + ", ".join(f"{m}={wl[m]:.2f}" for m in wl.index if wl[m] > 0) + " ---")
        print(out.sort_values("mean/std", ascending=False).to_string(float_format="{:.3f}".format))
    publish_forecasts(results)
    publish_outcomes()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("data")
    s = sub.add_parser("signals")
    s.add_argument("--models", default="historical,reversal,resid_reversal,egarch")
    s.add_argument("--start", default=None)
    s.add_argument("--step", type=int, default=None)
    s.add_argument("--refresh", action="store_true")
    sub.add_parser("evaluate")
    t = sub.add_parser("today")
    t.add_argument("--models", default=",".join(MODELS))
    args = p.parse_args()

    if limit_ram(MODEL_RAM_GB):
        print(f"RAM capped at {MODEL_RAM_GB:g} GB")
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
