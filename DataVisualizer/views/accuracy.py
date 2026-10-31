"""Predictions vs actual — each model's forecast distribution (mean and std dev) checked against
what the banks then did."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import marketdata as md
from charts import EVAL_COLUMNS, band, intervals, line, show, style, theme
from dist import crps, halfwidth

T = theme()
LABELS = {"ensemble": "Ensemble (combined)", "chronos": "Chronos-2", "kronos": "Kronos", "egarch": "EGARCH", "lgbm": "LightGBM",
          "resid_reversal": "Rate-aware reversal", "reversal": "Reversal", "historical": "Historical (benchmark)"}
BENCHMARK = "historical"
ROLLING = 12  # forecasts in the rolling averages (~3 months at one every 5 trading days)


@st.cache_data
def load(path, mtime):
    return md.load_parquet(path)


def forecasts():
    """{model: long frame date, ticker, horizon, mean, std, nu}, ensemble first, benchmark last."""
    out = {p.stem: load(p, md.mtime(p)) for p in sorted(md.FORECASTS_DIR.glob("*.parquet"))}
    order = list(LABELS) + sorted(set(out) - set(LABELS))
    return {m: out[m] for m in order if m in out}


def scored(fc, outcomes, h):
    """Join one model's forecasts to the outcomes and score each one."""
    df = fc[fc["horizon"] == h].merge(outcomes[outcomes["horizon"] == h], on=["date", "ticker", "horizon"])
    err = (df["actual"] - df["mean"]).abs()
    known = df["actual"].notna()
    df["z"] = (df["actual"] - df["mean"]) / df["std"]
    df["inside_68"] = (err <= halfwidth(df["std"], df["nu"], 0.68)).where(known)
    df["inside_95"] = (err <= halfwidth(df["std"], df["nu"], 0.95)).where(known)
    df["crps"] = crps(df["mean"], df["std"], df["nu"], df["actual"])
    return df


def per_date(df):
    known = df.dropna(subset=["actual"])
    return known.groupby("date").agg(crps=("crps", "mean"), inside_68=("inside_68", "mean"),
                                     inside_95=("inside_95", "mean"))


fcs = forecasts()
outcomes = load(md.OUTCOMES, md.mtime(md.OUTCOMES))
st.title("Predictions vs actual")
if outcomes is None or not fcs:
    st.info("No forecasts or outcomes yet. In BankPrediction run `python run.py signals` and `python run.py evaluate`.")
    st.stop()
st.caption("Every model forecasts a **distribution** for each bank's return over the holding period: a mean "
           "(the most likely outcome), a standard deviation (how far it could reasonably land from that), and "
           "fat tails (a Student-t distribution, because big moves happen more often than a normal curve "
           "allows), all recalibrated on the model's own past errors. The trade opens at the next close after "
           "the forecast and is held for the horizon. If a model is honest about its uncertainty, 68% of actual "
           "returns land inside its 68% range and 95% inside its 95% range.")

f1, f2 = st.columns([3, 2])
models = list(fcs)
model = f1.selectbox("Model", models, index=models.index("lgbm") if "lgbm" in models else 0,
                     format_func=lambda m: LABELS.get(m, m))
horizons = sorted(outcomes["horizon"].unique().tolist())
h0 = 7 if 7 in horizons else horizons[0]
h = f2.segmented_control("Horizon (trading days)", horizons, default=h0) or h0

df = scored(fcs[model], outcomes, h)
known = df.dropna(subset=["actual"])
stats = per_date(df)
bench = per_date(scored(fcs[BENCHMARK], outcomes, h)) if BENCHMARK in fcs else None

# --- Scorecard ---------------------------------------------------------------------------------
k = st.columns(4)
if bench is not None:
    both = stats.index.intersection(bench.index)
    skill = 1 - stats.loc[both, "crps"].mean() / bench.loc[both, "crps"].mean()
    k[0].metric("Skill vs historical", f"{skill:+.1%}", border=True,
                help="How much closer the whole forecast distribution came to the outcomes than the historical "
                     "benchmark (the bank's own last-year average and volatility), measured by CRPS. "
                     "Above 0 = better than the benchmark.")
k[1].metric("Inside 68% range", f"{known['inside_68'].mean():.0%}", f"{known['inside_68'].mean() - 0.68:+.0%} vs target",
            delta_color="off", border=True,
            help="Above 68%: the forecast ranges are too wide. Below: too narrow (overconfident).")
k[2].metric("Inside 95% range", f"{known['inside_95'].mean():.0%}", f"{known['inside_95'].mean() - 0.95:+.0%} vs target",
            delta_color="off", border=True,
            help="Below 95% means big surprises happen more often than the model expects.")
pending = df.loc[df["actual"].isna(), "date"].nunique()
k[3].metric("Forecasts checked", f"{len(known):,}", f"{pending} dates pending" if pending else None,
            delta_color="off", border=True, help=f"{stats.shape[0]} forecast dates × banks")

# --- One date: every bank's forecast range against what happened ----------------------------
st.markdown("#### One forecast date, checked")
dates = sorted(df["date"].unique(), reverse=True)
known_dates = set(stats.index)
if st.session_state.get("forecast_date") not in dates:
    st.session_state["forecast_date"] = next((x for x in dates if x in known_dates), dates[0])


def step(by):
    """Move the shown forecast date: +1 = later, -1 = earlier (dates are newest first)."""
    i = dates.index(st.session_state["forecast_date"]) - by
    st.session_state["forecast_date"] = dates[min(max(i, 0), len(dates) - 1)]


d = st.session_state["forecast_date"]
# The same axis, -10% to +10%, for every date, so zero stays put and widths compare while stepping.
edge = 0.10
day = df[df["date"] == d].set_index("ticker").sort_values("mean", ascending=False)
if d in known_dates:
    st.caption(f"Held from the close of {day['entry_date'].iloc[0]:%d %b} to {day['exit_date'].iloc[0]:%d %b %Y}. "
               f"**{int(day['inside_68'].sum())} of {len(day)}** actual returns landed inside the 68% range and "
               f"**{int(day['inside_95'].sum())} of {len(day)}** inside the 95% range.")
    fig = intervals(day["mean"], day["std"], day["nu"], day["actual"], xrange=[-edge, edge])
else:
    st.caption("The holding period hasn't finished yet, so this shows the forecast only.")
    fig = intervals(day["mean"], day["std"], day["nu"], xrange=[-edge, edge])
show(fig, day[["mean", "std", "nu", "actual", "z"]].round(4), "this forecast",
     f"{LABELS.get(model, model)}: {h}-day return forecast (mean, 68% and 95% ranges) vs actual")
i = dates.index(d)
nav = st.columns([1, 4, 1], vertical_alignment="center")
nav[0].button("◀ Earlier", on_click=step, args=(-1,), disabled=i == len(dates) - 1, use_container_width=True)
# Arrows step one date; the dropdown jumps straight to any date. Both share the same state.
nav[1].selectbox("Forecast made after the close on", dates, key="forecast_date",
                 format_func=lambda x: f"{x:%a %d %b %Y}" + ("" if x in known_dates else " · pending"),
                 help=f"{len(dates) - i} of {len(dates)} forecast dates, newest first")
nav[2].button("Later ▶", on_click=step, args=(1,), disabled=i == 0, use_container_width=True)

# --- One bank over time ------------------------------------------------------------------------
st.markdown("#### One bank over time")
bank = st.selectbox("Bank", sorted(df["ticker"].unique()))
b = known[known["ticker"] == bank].set_index("date").sort_index()
fig = band(b["mean"], b["std"], b["nu"], b["actual"])
show(fig, b[["mean", "std", "nu", "actual", "z"]].round(4), "bank history",
     f"{bank}: forecast range vs actual {h}-day return, {LABELS.get(model, model)}")

# --- Track record: rolling calibration and skill ------------------------------------------
st.markdown("#### Track record")
left, right = st.columns(2)
with left:
    s = stats["inside_68"].rolling(ROLLING, min_periods=ROLLING // 2).mean()
    fig = go.Figure()
    line(fig, s, LABELS.get(model, model), T["series"][0], hover=".0%")
    fig.add_hline(y=0.68, line=dict(color=T["muted"], width=1, dash="dot"),
                  annotation_text="68% target", annotation_font_color=T["muted"], annotation_position="top left")
    style(fig, 320)
    fig.update_yaxes(tickformat=".0%")
    show(fig, s.round(3).rename("inside 68% range"), "coverage", f"Share inside the 68% range, rolling {ROLLING} dates")
with right:
    if bench is not None:
        both = stats.index.intersection(bench.index)
        rel = 1 - (stats.loc[both, "crps"].rolling(ROLLING, min_periods=ROLLING // 2).mean()
                   / bench.loc[both, "crps"].rolling(ROLLING, min_periods=ROLLING // 2).mean())
        fig = go.Figure()
        line(fig, rel, LABELS.get(model, model), T["series"][0], hover="+.1%")
        fig.add_hline(y=0, line=dict(color=T["axis"], width=1))
        style(fig, 320)
        fig.update_yaxes(tickformat="+.0%")
        show(fig, rel.round(4).rename("skill"), "skill", f"Skill vs historical benchmark, rolling {ROLLING} dates")

# --- Every forecast -----------------------------------------------------------------------------
st.markdown("#### Every forecast")
banks = st.multiselect("Banks", sorted(df["ticker"].unique()), placeholder="All banks")
rows = (df[df["ticker"].isin(banks)] if banks else df).sort_values(["date", "mean"], ascending=[False, False])
st.dataframe(rows[["date", "ticker", "mean", "std", "nu", "actual", "z", "inside_68", "inside_95", "exit_date"]],
             hide_index=True, width="stretch", height=420, column_config={
    "date": st.column_config.DateColumn("Forecast on", format="YYYY-MM-DD"), "ticker": "Bank",
    "mean": st.column_config.NumberColumn("Mean", format="percent"),
    "std": st.column_config.NumberColumn("Std", format="percent"),
    "nu": st.column_config.NumberColumn("Tails (ν)", format="%.1f", help="Lower = fatter tails"),
    "actual": st.column_config.NumberColumn("Actual", format="percent"),
    "z": st.column_config.NumberColumn("Error in stds", format="%+.2f",
                                       help="(actual − mean) ÷ std: how many stds the outcome was from the mean"),
    "inside_68": st.column_config.CheckboxColumn("Inside 68%"),
    "inside_95": st.column_config.CheckboxColumn("Inside 95%"),
    "exit_date": st.column_config.DateColumn("Known on", format="YYYY-MM-DD"),
})
st.download_button("Download as CSV", rows.to_csv(index=False).encode(), mime="text/csv",
                   file_name=f"forecasts_vs_actual_{model}_h{h}.csv")

ev = load(md.EVALUATION, md.mtime(md.EVALUATION))
if ev is not None and "crps_skill" in ev:
    st.markdown("#### All models, side by side")
    st.dataframe(ev[ev["horizon"] == h].drop(columns="horizon"), hide_index=True, width="stretch",
                 column_config=EVAL_COLUMNS)
