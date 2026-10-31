"""Strategy — a long-only rule on top of the forecasts: buy only the banks whose forecast is
confident enough (mean / std above a cut-off), at most N of them, and hold cash otherwise.
Each forecast date's expected portfolio return is plotted against what it actually returned."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import marketdata as md
from charts import line, show, style, theme

T = theme()
# The chart pair that follows the cursor runs in the browser (Streamlit never sees hover events).
HOVER_HTML = (Path(__file__).parent / "compounding.html").read_text(encoding="utf-8")
LABELS = {"ensemble": "Ensemble", "chronos": "Chronos-2", "kronos": "Kronos", "egarch": "EGARCH", "lgbm": "LightGBM",
          "resid_reversal": "Rate-aware reversal", "reversal": "Reversal", "historical": "Historical"}


@st.cache_data
def load(path, mtime):
    return md.load_parquet(path)


def picks(g, cutoff, top, weighting):
    """One forecast date: the banks bought and their weights (empty = all cash)."""
    g = g[g["score"] > cutoff].nlargest(top, "score")
    if g.empty:
        return pd.Series(dtype=float)
    w = 1 / g["std"] if weighting == "1 / std" else pd.Series(1.0, g.index)
    return w / w.sum()


def risk_size(dates, macro):
    """Share of the money to put in on each forecast date, from how nervous the market is:
    India VIX above 60% / 85% of the past year's days -> 50% / 25%, and Bank Nifty below its
    50-day average -> 25%. Uses only data up to the date's close."""
    def series(name):
        return macro[macro["series"] == name].set_index("date")["value"].sort_index().dropna()

    vix, bn = series("vix"), series("banknifty")
    vix_pct = vix.rolling(253, min_periods=120).apply(lambda v: (v[:-1] < v[-1]).mean(), raw=True)
    trend = bn / bn.rolling(50).mean() - 1
    rows = []
    for d in dates:
        p, t = vix_pct.asof(d), trend.asof(d)
        size, why = 1.0, [f"VIX {vix.asof(d):.1f}, higher than {p:.0%} of the past year"]
        if p > 0.85:
            size = 0.25
        elif p > 0.6:
            size = 0.5
        if t < 0:
            size = min(size, 0.25)
        why.append(f"Bank Nifty {abs(t):.1%} {'below' if t < 0 else 'above'} its 50-day average")
        rows.append({"date": d, "size": size, "why": "; ".join(why)})
    return pd.DataFrame(rows).set_index("date")


CORR_DAYS = 120  # trading days of daily returns behind the correlations between the banks


def confidence_size(score):
    """Share of the money from the whole portfolio's mean / std: >= 0.2 (about a 58% chance of
    a profit) -> all of it, 0.1 to 0.2 -> half, below 0.1 -> a quarter."""
    return 1.0 if score >= 0.2 else 0.5 if score >= 0.1 else 0.25


def portfolio(w, g, rets, d):
    """Mean and std of the whole basket's return: the weighted means, and the std from each
    bank's forecast std with the correlations of their daily returns over the last CORR_DAYS."""
    if w.empty:
        return np.nan, np.nan
    s = g.loc[w.index, "std"].values
    corr = rets.loc[:d, w.index].tail(CORR_DAYS).corr().fillna(0.6).to_numpy(copy=True)
    np.fill_diagonal(corr, 1.0)
    cov = corr * np.outer(s, s)
    return float(w.values @ g.loc[w.index, "mean"].values), float(np.sqrt(w.values @ cov @ w.values))


def backtest(df, cutoff, top, weighting, cost, rets, sizer):
    """sizer(date, portfolio score) -> share of the money invested (the rest stays in cash)."""
    rows, held = [], []
    for d, g in df.groupby("date"):
        w = picks(g.set_index("ticker"), cutoff, top, weighting)
        g = g.set_index("ticker")
        c = 2 * cost if len(w) else 0.0  # in and out
        known = g["actual_ret"].notna().all()
        pm, ps = portfolio(w, g, rets, d)
        k = sizer(d, pm / ps) if len(w) else 0.0
        rows.append({"date": d, "entry": g["entry_date"].iloc[0], "exit": g["exit_date"].iloc[0], "banks": len(w),
                     "port_mean": pm, "port_std": ps,
                     "chance_of_profit": 0.5 * (1 + math.erf(pm / ps / math.sqrt(2))) if len(w) else np.nan,
                     "money_in": k,
                     "expected": k * ((w * g.loc[w.index, "expected_ret"]).sum() - c),
                     "actual": k * ((w * g.loc[w.index, "actual_ret"]).sum() - c) if known else np.nan,
                     "buy_all": g["actual_ret"].mean() - 2 * cost if known else np.nan})
        held += [{"date": d, "ticker": t, "weight": wt} for t, wt in w.items()]
    return pd.DataFrame(rows).set_index("date"), pd.DataFrame(held, columns=["date", "ticker", "weight"])


st.title("Strategy")
st.caption("**The rule:** after each forecast, score every bank by **mean ÷ std**, which is roughly how sure "
           "the model is that the stock goes up (0 = coin flip, 0.1 ≈ 54% chance, 0.2 ≈ 58%). Buy only the "
           "banks above the cut-off, at most the chosen number, best score first. If none qualify, stay in "
           "cash. Positions open at the next close and are held for the horizon. Long only, no short selling: "
           "banks below the cut-off are simply not bought. Costs are charged on the way in and out.")

models = [m for m in LABELS if (md.FORECASTS_DIR / f"{m}.parquet").exists()]
outcomes = load(md.OUTCOMES, md.mtime(md.OUTCOMES))
if not models or outcomes is None:
    st.info("No forecasts yet. In BankPrediction run `python run.py signals` and `python run.py evaluate`.")
    st.stop()

# --- Settings, as buttons ----------------------------------------------------------------------
c = st.columns([3, 2, 2])
model = c[0].segmented_control("Model", models, default="lgbm" if "lgbm" in models else models[0],
                               format_func=lambda m: LABELS.get(m, m), key="st_model") or models[0]
horizons = sorted(outcomes["horizon"].unique().tolist())
h0 = 7 if 7 in horizons else horizons[-1]
h = c[1].segmented_control("Horizon (trading days)", horizons, default=h0, key="st_h") or h0
sizing = c[2].segmented_control(
    "Money per trade", ["Full", "Risk-based", "Risk + confidence"], default="Full", key="st_size",
    help="**Risk-based** puts in only 50% of the money when India VIX is higher than on 60% of the past year's "
         "days, 25% when higher than on 85%, and 25% whenever Bank Nifty is below its 50-day average.  \n"
         "**Risk + confidence** also looks at the whole basket's forecast mean ÷ std: at least 0.2 (about a 58% "
         "chance of a profit) -> all, 0.1 to 0.2 -> half, below 0.1 -> a quarter. The smaller of the two wins.  \n"
         "The rest stays in cash.") or "Full"
c = st.columns([3, 2, 2, 2])
cutoff = c[0].segmented_control("Cut-off: buy only if mean ÷ std is above", [0.0, 0.05, 0.1, 0.15, 0.2, 0.3],
                                default=0.1, key="st_cut")
cutoff = 0.1 if cutoff is None else cutoff
top = c[1].segmented_control("At most this many banks", [1, 2, 3, 4, 5, 12], default=3,
                             format_func=lambda n: "No limit" if n == 12 else str(n), key="st_top") or 3
weighting = c[2].segmented_control("Weights", ["1 / std", "Equal"], default="1 / std", key="st_w",
                                   help="1 / std puts less money in the more volatile banks.") or "1 / std"
cost_bps = c[3].segmented_control("Cost per side (bps)", [0, 5, 10, 20], default=5, key="st_cost")
cost_bps = 5 if cost_bps is None else cost_bps

fc = load(md.FORECASTS_DIR / f"{model}.parquet", md.mtime(md.FORECASTS_DIR / f"{model}.parquet"))
df = fc[fc["horizon"] == h].merge(outcomes[outcomes["horizon"] == h][["date", "ticker", "entry_date", "exit_date", "actual"]],
                                  on=["date", "ticker"], how="left")
df["score"] = df["mean"] / df["std"]
df["expected_ret"] = np.expm1(df["mean"])
df["actual_ret"] = np.expm1(df["actual"])
macro = load(md.MACRO, md.mtime(md.MACRO))
sizes = risk_size(sorted(df["date"].unique()), macro)
prices = load(md.PRICES, md.mtime(md.PRICES))
rets = np.log(prices.pivot(index="date", columns="ticker", values="close")).diff()
SIZERS = {"Full": lambda d, score: 1.0,
          "Risk-based": lambda d, score: sizes["size"].get(d, 1.0),
          "Risk + confidence": lambda d, score: min(sizes["size"].get(d, 1.0), confidence_size(score))}
res, held = backtest(df, cutoff, top, weighting, cost_bps / 1e4, rets, SIZERS[sizing])
done = res.dropna(subset=["actual"])
traded = done[done["banks"] > 0]

# --- Scorecard ---------------------------------------------------------------------------------
k = st.columns(5)
k[0].metric("Dates invested", f"{len(traded)} of {len(done)}",
            f"{len(traded) / max(len(done), 1):.0%} of the time" + (f", avg {traded['money_in'].mean():.0%} of the money"
                                                                   if sizing != "Full" and len(traded) else ""),
            delta_color="off", border=True, help="The rest of the time nothing passed the cut-off, so the money sat in cash.")
if len(traded):
    t_stat = traded["actual"].mean() / traded["actual"].std() * np.sqrt(len(traded)) if len(traded) > 1 else np.nan
    k[1].metric("Actual return per trade", f"{traded['actual'].mean():+.2%}", f"expected {traded['expected'].mean():+.2%}",
                delta_color="off", border=True, help="Average over the dates it was invested, after costs.")
    k[2].metric("Winning trades", f"{(traded['actual'] > 0).mean():.0%}", border=True)
    edge = (traded["actual"] - traded["buy_all"]).mean()
    k[3].metric("vs benchmark", f"{edge:+.2%}", "per trade", delta_color="off", border=True,
                help="Benchmark only, never traded: buying all 12 banks on the same dates. Shows whether the picking adds anything.")
    k[4].metric("Reliability (t-stat)", f"{t_stat:.1f}", "above 2 = believable" if t_stat < 2 else "believable",
                delta_color="off", border=True,
                help="Average return per trade ÷ its standard error. Below 2, the result could easily be luck.")

# --- Expected vs actual per date, and how the money compounds from the date under the cursor ---
amount = st.segmented_control("Money invested", [10_000, 100_000, 1_000_000], default=100_000, key="st_amt",
                              format_func=lambda a: f"₹{a:,.0f}" if a < 100_000 else f"₹{a / 100_000:g} lakh") or 100_000
st.markdown(f"##### {LABELS.get(model, model)}, {h}-day hold: the portfolio's expected vs actual return on each "
            "forecast date (0 = in cash)")
st.caption("Move the cursor over the top chart: the bottom chart compounds your money from that forecast date "
           "onwards, reinvesting everything in each next trade. A new trade starts only after the previous one "
           "is sold, so the money is never in two trades at once (forecasts made meanwhile are skipped). "
           "For comparison, the same money goes into the Bank Nifty index on exactly the same days (bought at each trade's entry, sold at its exit, cash in between), so both lines are flat while you are out of the market.")


def iso(values):
    return [None if pd.isna(x) else f"{x:%Y-%m-%d}" for x in values]


def nums(values):
    return [None if pd.isna(x) else float(x) for x in values]


bn = macro[macro["series"] == "banknifty"].set_index("date")["value"].sort_index()
bn = bn[bn.index >= res["entry"].min()]
payload = {"date": iso(res.index), "entry": iso(res["entry"]), "exit": iso(res["exit"]), "banks": res["banks"].tolist(),
           "expected": nums(res["expected"]), "actual": nums(res["actual"]), "size": nums(res["money_in"]),
           "bn_date": iso(bn.index), "bn": nums(bn), "amount": amount, "start": 0,
           "colors": {"exp": T["series"][0], "act": T["series"][1], "bn": T["series"][0], "text": T["text"],
                      "text2": T["text2"], "muted": T["muted"], "grid": T["grid"], "axis": T["axis"],
                      "surface": T["surface"]}}
st.iframe(HOVER_HTML.replace("__DATA__", json.dumps(payload)), height=850)
with st.expander("Table: per forecast date"):
    st.dataframe(res.join(sizes["why"].rename("market")).round({"expected": 4, "actual": 4, "buy_all": 4, "port_mean": 4,
                                                                "port_std": 4, "chance_of_profit": 3}),
                 width="stretch")

# --- The latest picks --------------------------------------------------------------------------
last = df["date"].max()
st.markdown(f"#### Picks from the latest forecast ({last:%a %d %b %Y})")
today = df[df["date"] == last].set_index("ticker").sort_values("score", ascending=False)
w = held[held["date"] == last].set_index("ticker")["weight"]
today["decision"] = np.where(today.index.isin(w.index), "Buy",
                             np.where(today["score"] > cutoff, "Skip: limit reached", "Skip: below cut-off"))
today["weight"] = w.reindex(today.index).fillna(0)
k_today = res["money_in"].get(last, 0.0)
today["amount"] = (amount * k_today * today["weight"]).round(-2)
if w.empty:
    st.caption("Nothing passes the cut-off: stay in cash.")
else:
    r = res.loc[last]
    st.caption(f"Whole basket's forecast: mean **{r['port_mean']:+.2%}**, std **{r['port_std']:.2%}** "
               f"(mean ÷ std {r['port_mean'] / r['port_std']:.2f}, about a **{r['chance_of_profit']:.0%}** chance of a profit).")
    reason = f" ({sizes['why'].get(last)})" if sizing != "Full" else ""
    st.caption(f"Invest **₹{amount * k_today:,.0f}** of ₹{amount:,.0f}{reason}; keep ₹{amount * (1 - k_today):,.0f} in cash.")
st.dataframe(today[["decision", "amount", "weight", "score", "mean", "std", "actual"]], width="stretch", column_config={
    "decision": "Decision", "amount": st.column_config.NumberColumn("Amount", format="₹%d"),
    "weight": st.column_config.NumberColumn("Weight", format="percent"),
    "score": st.column_config.NumberColumn("mean ÷ std", format="%.3f"),
    "mean": st.column_config.NumberColumn(f"Expected {h}-day return", format="percent"),
    "std": st.column_config.NumberColumn("Std", format="percent"),
    "actual": st.column_config.NumberColumn("Actual (when known)", format="percent")})
