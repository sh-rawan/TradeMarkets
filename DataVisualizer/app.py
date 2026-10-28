"""Bank Nifty monitor — interactive dashboard over the shared MarketData store.

    python -m streamlit run app.py
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import marketdata as md

st.set_page_config(page_title="Bank Nifty monitor", page_icon="📈", layout="wide")

# --- Design tokens -------------------------------------------------------------------------
# Categorical slots 1-3 of the reference palette, validated all-pairs in both modes
# (light: aqua is below 3:1 contrast, so every chart carries direct labels and a table view).
LIGHT = dict(surface="#ffffff", text="#0b0b0b", text2="#52514e", muted="#898781", grid="#e1e0d9",
             axis="#c3c2b7", series=["#2a78d6", "#eb6834", "#1baf7a"], pos="#2a78d6", neg="#e34948",
             mid="#f0efec")
DARK = dict(surface="#0e1117", text="#f0efec", text2="#c3c2b7", muted="#898781", grid="#2c2c2a",
            axis="#383835", series=["#3987e5", "#d95926", "#199e70"], pos="#3987e5", neg="#e66767",
            mid="#383835")
T = DARK if st.context.theme.type == "dark" else LIGHT
CONTEXT = T["muted"]  # de-emphasis gray for comparison lines
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
DIVERGING = [[0, T["neg"]], [0.5, T["mid"]], [1, T["pos"]]]
# Sequential blue ramp (steps 100-700); in dark mode more is lighter, so the low end recedes into the surface.
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQUENTIAL = [[i / 6, c] for i, c in enumerate(BLUES if T is LIGHT else BLUES[::-1])]
MACRO_LABELS = {"banknifty": "Bank Nifty", "nifty": "Nifty 50", "vix": "India VIX",
                "usdinr": "USD/INR", "us10y": "US 10Y yield (%)", "in10y": "India 10Y yield (%)"}


def style(fig, height, unified=True):
    fig.update_layout(
        height=height, margin=dict(l=56, r=16, t=36, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=T["text2"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None),
        hoverlabel=dict(bgcolor=T["surface"], bordercolor=T["grid"], font=dict(family=FONT, color=T["text"])),
        hovermode="x unified" if unified else "closest",
    )
    fig.update_xaxes(showgrid=False, linecolor=T["axis"], tickcolor=T["axis"], tickfont=dict(color=T["muted"]),
                     showspikes=unified, spikemode="across", spikethickness=1, spikecolor=T["muted"],
                     spikedash="solid", spikesnap="cursor", automargin=True)
    fig.update_yaxes(gridcolor=T["grid"], gridwidth=1, zeroline=False, linecolor=T["axis"],
                     tickfont=dict(color=T["muted"]), automargin=True)
    return fig


def show(fig, data, name, title):
    """Every chart ships with its table view, so no value is reachable only by hovering."""
    st.markdown(f"##### {title}")
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False})
    with st.expander(f"Table: {name}"):
        st.dataframe(data, width="stretch")


def end_labels(fig, series, fmt, row=None, col=None):
    """Label each line's last point, unless two endpoints are too close to label cleanly
    (then the legend and tooltip carry identity instead of nudged labels)."""
    last = {name: s.dropna() for name, s in series.items()}
    last = {name: s for name, s in last.items() if len(s)}
    values = sorted(s.iloc[-1] for s in last.values())
    span = (max(s.max() for s in last.values()) - min(s.min() for s in last.values())) or 1
    if any(b - a < 0.06 * span for a, b in zip(values, values[1:])):
        return
    for name, s in last.items():
        fig.add_annotation(x=s.index[-1], y=s.iloc[-1], text=f"{name} {fmt.format(s.iloc[-1])}",
                           showarrow=False, xanchor="left", xshift=8, font=dict(color=T["text2"], size=12),
                           row=row, col=col)


def line(fig, s, name, color, width=2, row=None, col=None, showlegend=True, hover=",.1f"):
    s = s.dropna()
    fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines", showlegend=showlegend,
                             line=dict(color=color, width=width, shape="linear"),
                             hovertemplate=f"<b>%{{y:{hover}}}</b> {name}<extra></extra>"), row=row, col=col)
    fig.add_trace(go.Scatter(x=s.index[-1:], y=s.values[-1:], mode="markers", showlegend=False, hoverinfo="skip",
                             marker=dict(size=9, color=color, line=dict(color=T["surface"], width=2))),
                  row=row, col=col)


def hbar(values, fmt, colors, height_per=34):
    values = values.sort_values()
    fig = go.Figure(go.Bar(
        x=values.values, y=values.index, orientation="h", marker=dict(color=colors(values), cornerradius=4),
        texttemplate=f"%{{x:{fmt}}}", textposition="outside", textfont=dict(color=T["text2"]), cliponaxis=False,
        hovertemplate=f"<b>%{{x:{fmt}}}</b> %{{y}}<extra></extra>"))
    style(fig, 60 + height_per * len(values), unified=False)
    fig.update_layout(bargap=0.32)
    # Pad both ends so the outside value labels fit beside the bars instead of over the bank names.
    lo, hi = min(values.min(), 0), max(values.max(), 0)
    pad = 0.18 * (hi - lo)
    fig.update_xaxes(showgrid=True, gridcolor=T["grid"], showticklabels=False, zeroline=True,
                     zerolinecolor=T["axis"], zerolinewidth=1,
                     range=[lo - pad if lo < 0 else 0, hi + pad if hi > 0 else 0])
    fig.update_yaxes(showgrid=False, tickfont=dict(color=T["text2"]))
    return fig


def bank_label(b):
    return f"{b} · PSU" if GROUPS.get(b) == "PSU" else b


# --- Data (re-read whenever a table file changes) -------------------------------------------
@st.cache_data
def load_close(mtime):
    return md.sql(f"select date, ticker, close from {md.table(md.PRICES)}").pivot(
        index="date", columns="ticker", values="close")


@st.cache_data
def load_macro(mtime):
    return md.sql(f"select * from {md.table(md.MACRO)}").pivot(index="date", columns="series", values="value")


@st.cache_data
def load_table(path, mtime):
    return md.load_parquet(path)


try:
    close = load_close(md.mtime(md.PRICES))
    macro = load_macro(md.mtime(md.MACRO))
except Exception as e:  # noqa: BLE001
    st.error(f"No market data in {md.DATA_ROOT} yet ({e}). Run `python run.py data` in BankPrediction.")
    st.stop()

tickers = load_table(md.TICKERS, md.mtime(md.TICKERS))
GROUPS = dict(zip(tickers["ticker"], tickers["group"])) if tickers is not None else {}
BANKS = sorted(close.columns)
cal = macro["banknifty"].dropna().index
close = close.reindex(cal)
macro = macro.reindex(cal).ffill()
last_date = cal[-1]

# --- Header & filter row (scopes everything below) -----------------------------------------
st.title("Bank Nifty monitor")
st.caption(f"Daily closes through **{last_date:%d %b %Y}** · Yahoo snapshot `{md.latest_snapshot()}` "
           f"· store `{md.DATA_ROOT}` · not financial advice")

PERIODS = {"1M": 1, "3M": 3, "6M": 6, "YTD": None, "1Y": 12, "3Y": 36, "Max": 0}
f1, f2 = st.columns([2, 3])
period = f1.segmented_control("Period", list(PERIODS), default="1Y") or "1Y"
default_picks = [b for b in ["HDFCBANK", "ICICIBANK", "SBIN"] if b in BANKS] or BANKS[:3]
picked = f2.multiselect("Compare banks (up to 3)", BANKS, default=default_picks,
                        max_selections=3, format_func=bank_label)

months = PERIODS[period]
if period == "YTD":
    start = pd.Timestamp(last_date.year, 1, 1)
elif months == 0:
    start = cal[0]
else:
    start = last_date - pd.DateOffset(months=months)
view = close.loc[start:]
mview = macro.loc[start:]

# Colour follows the bank, not its position: a bank keeps its slot until it is deselected.
slots = st.session_state.setdefault("slots", {})
for b in list(slots):
    if b not in picked:
        del slots[b]
for b in picked:
    if b not in slots:
        slots[b] = min(set(range(3)) - set(slots.values()))
color = {b: T["series"][slots[b]] for b in picked}

# --- KPI row ---------------------------------------------------------------------------------
def kpi(col, key, fmt, delta, delta_color="normal"):
    s = macro[key].dropna()
    col.metric(MACRO_LABELS[key], fmt.format(s.iloc[-1]), delta(s.iloc[-1], s.iloc[-2]),
               delta_color=delta_color, chart_data=s.tail(60).round(3).tolist(), chart_type="line",
               border=True)


pct = lambda a, b: f"{a / b - 1:+.2%}"  # noqa: E731
k = st.columns(5)
kpi(k[0], "banknifty", "{:,.0f}", pct)
kpi(k[1], "nifty", "{:,.0f}", pct)
kpi(k[2], "vix", "{:.2f}", lambda a, b: f"{a - b:+.2f}", "off")
kpi(k[3], "us10y", "{:.2f}%", lambda a, b: f"{(a - b) * 100:+.0f} bp", "off")
kpi(k[4], "usdinr", "₹{:.2f}", lambda a, b: f"{a - b:+.2f}", "off")

perf, risk, rates, sig, query = st.tabs(["Performance", "Risk", "Rates & macro", "Model signals", "SQL"])

# --- Performance -----------------------------------------------------------------------------
with perf:
    rebased = (pd.concat([view[picked], mview["banknifty"].rename("Bank Nifty")], axis=1)
               .apply(lambda s: 100 * s / s.dropna().iloc[0]))
    fig = go.Figure()
    line(fig, rebased["Bank Nifty"], "Bank Nifty", CONTEXT, width=2)
    for b in picked:
        line(fig, rebased[b], b, color[b])
    end_labels(fig, {c: rebased[c] for c in rebased.columns}, "{:.0f}")
    style(fig, 420)
    fig.update_layout(margin=dict(r=110))
    show(fig, rebased.round(2), "rebased prices", f"Growth of 100 since {view.index[0]:%d %b %Y}")

    left, right = st.columns(2)
    with left:
        ret = view.apply(lambda s: s.dropna().iloc[-1] / s.dropna().iloc[0] - 1).rename(index=bank_label)
        fig = hbar(ret, "+.1%", lambda v: [T["pos"] if x >= 0 else T["neg"] for x in v])
        show(fig, ret.sort_values(ascending=False).map("{:+.2%}".format), "period returns", f"Return over {period}")
    with right:
        monthly = macro["banknifty"].resample("ME").last().pct_change().dropna()
        grid = (monthly.to_frame("r").assign(year=monthly.index.year, month=monthly.index.strftime("%b"))
                .pivot(index="year", columns="month", values="r")
                .reindex(columns=pd.date_range("2000-01-01", periods=12, freq="MS").strftime("%b")))
        grid = grid.loc[grid.index >= last_date.year - 9]
        # Clip the scale at the 95th percentile so one crash month doesn't wash out the rest.
        lim = float(np.nanquantile(np.abs(grid.values), 0.95))
        fig = go.Figure(go.Heatmap(z=grid.values, x=grid.columns, y=grid.index.astype(str), colorscale=DIVERGING,
                                   zmin=-lim, zmax=lim, xgap=2, ygap=2,
                                   colorbar=dict(tickformat="+.0%", outlinewidth=0, thickness=10),
                                   hovertemplate="<b>%{z:+.1%}</b> %{x} %{y}<extra></extra>"))
        style(fig, 60 + 34 * len(grid), unified=False)
        fig.update_yaxes(autorange="reversed", showgrid=False, type="category")
        show(fig, grid.map(lambda v: "" if pd.isna(v) else f"{v:+.1%}"), "monthly returns",
             "Bank Nifty monthly returns")

# --- Risk ------------------------------------------------------------------------------------
with risk:
    rets = np.log(close).diff()
    egarch_path = md.SIGNALS_DIR / "egarch.parquet"
    eg = load_table(egarch_path, md.mtime(egarch_path))
    has_vol = eg is not None
    left, right = st.columns(2)
    with left:
        focus = st.selectbox("Bank", BANKS, index=BANKS.index(picked[0]) if picked else 0, format_func=bank_label)
        realised = (rets[focus].rolling(20).std() * np.sqrt(252) * 100).loc[start:]
        fig = go.Figure()
        line(fig, realised, "Realised (20-day)", CONTEXT, hover=".1f")
        series = {"Realised": realised}
        if has_vol:
            fc =(eg[(eg.ticker == focus) & (eg.horizon == 1)].set_index("date")["value"] * np.sqrt(252) * 100).loc[start:]
            line(fig, fc, "EGARCH forecast", T["series"][0], hover=".1f")
            series["Forecast"] = fc
        end_labels(fig, series, "{:.0f}%")
        style(fig, 380)
        fig.update_layout(margin=dict(r=110))
        show(fig, pd.DataFrame(series).round(2), "volatility", f"{focus} annualised volatility (%)")
    with right:
        corr = rets.loc[start:].corr()
        corr = corr.mask(np.eye(len(corr), dtype=bool))  # the diagonal is always 1 and says nothing
        # Bank returns are positively correlated, so a 0-1 sequential scale shows more than a -1..1 diverging one.
        fig = go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index, colorscale=SEQUENTIAL, zmin=0, zmax=1,
                                   xgap=2, ygap=2, colorbar=dict(outlinewidth=0, thickness=10),
                                   hovertemplate="<b>%{z:.2f}</b> %{y} vs %{x}<extra></extra>"))
        style(fig, 470, unified=False)
        fig.update_yaxes(autorange="reversed", showgrid=False)
        show(fig, corr.round(2), "correlation", f"Daily return correlation, {period}")

    if has_vol:
        latest = eg[(eg.horizon == 1) & (eg.date == eg.date.max())].set_index("ticker")["value"] * np.sqrt(252)
        fig = hbar(latest.rename(index=bank_label), ".0%", lambda v: [T["series"][0]] * len(v))
        show(fig, latest.sort_values(ascending=False).map("{:.1%}".format), "forecast volatility",
             f"Forecast annualised volatility, as of {eg.date.max():%d %b %Y}")

# --- Rates & macro: small multiples on a shared time axis, never a second y-axis -------------
with rates:
    psu = [b for b in BANKS if GROUPS.get(b) == "PSU"]
    private = [b for b in BANKS if GROUPS.get(b) == "Private"]
    panels = {"Bank Nifty": mview["banknifty"]}
    if psu and private:
        spread = rets.loc[start:, psu].mean(axis=1) - rets.loc[start:, private].mean(axis=1)
        panels["PSU minus private banks (cumulative, 100 = period start)"] = 100 * np.exp(spread.fillna(0).cumsum())
    panels.update({MACRO_LABELS[c]: mview[c] for c in ["us10y", "in10y", "vix", "usdinr"] if c in mview})
    fig = make_subplots(rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        subplot_titles=list(panels))
    for i, (name, s) in enumerate(panels.items(), start=1):
        line(fig, s, name, T["series"][0], row=i, col=1, showlegend=False, hover=",.2f")
        end_labels(fig, {"": s}, "{:,.2f}", row=i, col=1)
    style(fig, 190 * len(panels))
    fig.update_layout(margin=dict(r=80))
    fig.update_annotations(font=dict(color=T["text"], size=13), selector=dict(xref="paper"))
    for a in fig.layout.annotations:
        if a.xref == "paper":
            a.update(x=0, xanchor="left")
    show(fig, pd.DataFrame(panels).round(3), "rates & macro", f"Rates & macro, {period}")
    st.caption("US yields and USD/INR close after the NSE; the models use them with a one-day lag.")

# --- Model signals ---------------------------------------------------------------------------
with sig:
    ens = load_table(md.ENSEMBLE, md.mtime(md.ENSEMBLE))
    if ens is None:
        st.info("No ensemble published yet. In BankPrediction run `python run.py evaluate` (or `today`).")
    else:
        horizons = sorted(ens["horizon"].unique().tolist())
        h = st.segmented_control("Horizon (trading days)", horizons, default=horizons[-1]) or horizons[-1]
        ens_h = ens[ens["horizon"] == h]
        asof = ens_h["date"].max()
        s = ens_h[ens_h["date"] == asof].set_index("ticker")["score"].dropna().rename(index=bank_label)
        fig = hbar(s, "+.2f", lambda v: [T["pos"] if x >= 0 else T["neg"] for x in v])
        per_model = {}
        for path in sorted(md.SIGNALS_DIR.glob("*.parquet")):
            if path.stem in ("egarch", "random"):  # sizing input and benchmark, not ensemble members
                continue
            df = load_table(path, md.mtime(path))
            row = df[(df["horizon"] == h) & (df["date"] == asof)]
            if len(row):
                per_model[path.stem] = row.set_index("ticker")["value"]
        show(fig, pd.DataFrame(per_model).rename(index=bank_label).round(4), "per-model signals",
             f"Ensemble rank score, {h}-day horizon, as of {asof:%d %b %Y} (+ = expected to beat peers)")
        weights = load_table(md.ENSEMBLE_WEIGHTS, md.mtime(md.ENSEMBLE_WEIGHTS))
        if weights is not None:
            w = weights[(weights["horizon"] == h) & (weights["date"] == asof)]
            st.caption("Model weights (rolling IC): " + " · ".join(f"{m} {x:.0%}" for m, x in zip(w["model"], w["weight"]))
                       + ". Run `python run.py today` in BankPrediction for signals as of the latest close.")
        ev = load_table(md.EVALUATION, md.mtime(md.EVALUATION))
        if ev is not None:
            st.subheader("Walk-forward evaluation")
            st.dataframe(ev[ev["horizon"] == h].drop(columns="horizon").round(3), hide_index=True, width="stretch")

# --- SQL over the whole store ----------------------------------------------------------------
with query:
    con = md.connect()
    st.caption("Tables: " + ", ".join(f"`{v}`" for v in md.views_available(con)))
    q = st.text_area("Query", height=120, value=(
        "select ticker, max(date) as last_date, arg_max(close, date) as last_close\n"
        "from prices group by ticker order by ticker"))
    if st.button("Run", type="primary"):
        try:
            st.dataframe(con.sql(q).df(), width="stretch")
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
