"""Shared chart styling: design tokens for light/dark and the Plotly helpers every page uses."""
import plotly.graph_objects as go
import streamlit as st

from dist import halfwidth

# --- Design tokens -------------------------------------------------------------------------
# Categorical slots 1-3 of the reference palette, validated all-pairs in both modes
# (light: aqua is below 3:1 contrast, so every chart carries direct labels and a table view).
LIGHT = dict(surface="#ffffff", text="#0b0b0b", text2="#52514e", muted="#898781", grid="#e1e0d9",
             axis="#c3c2b7", series=["#2a78d6", "#eb6834", "#1baf7a"], pos="#2a78d6", neg="#e34948",
             mid="#f0efec")
DARK = dict(surface="#0e1117", text="#f0efec", text2="#c3c2b7", muted="#898781", grid="#2c2c2a",
            axis="#383835", series=["#3987e5", "#d95926", "#199e70"], pos="#3987e5", neg="#e66767",
            mid="#383835")
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
# Sequential blue ramp (steps 100-700); in dark mode more is lighter, so the low end recedes into the surface.
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def theme():
    """Tokens for the viewer's current light/dark setting. Read on every run, never at import:
    the module is shared by all sessions, which may use different themes."""
    light = st.context.theme.type != "dark"
    t = dict(LIGHT if light else DARK)
    t["context"] = t["muted"]  # de-emphasis gray for comparison lines
    t["diverging"] = [[0, t["neg"]], [0.5, t["mid"]], [1, t["pos"]]]
    t["sequential"] = [[i / 6, c] for i, c in enumerate(BLUES if light else BLUES[::-1])]
    return t


MACRO_LABELS = {"banknifty": "Bank Nifty", "nifty": "Nifty 50", "vix": "India VIX",
                "usdinr": "USD/INR", "us10y": "US 10Y yield (%)", "in10y": "India 10Y yield (%)",
                "us3m": "US 3-month yield (%)", "spx": "S&P 500", "usvix": "US VIX", "dxy": "Dollar index (DXY)",
                "brent": "Brent crude ($)", "gold": "Gold ($/oz)", "btc": "Bitcoin ($)",
                "nasdaq": "Nasdaq", "hangseng": "Hang Seng", "shanghai": "Shanghai Composite", "usdcny": "USD/CNY",
                "nikkei": "Nikkei 225", "usdjpy": "USD/JPY", "dax": "DAX", "ftse": "FTSE 100", "eurinr": "EUR/INR",
                "kospi": "KOSPI (Korea)", "taiwan": "Taiwan", "brazil": "Brazil (Bovespa)", "em_etf": "Emerging markets ETF (EEM)",
                "copper": "Copper ($/lb)", "natgas": "Natural gas ($)", "hy_bonds": "US high-yield bonds (HYG)",
                "ig_bonds": "US investment-grade bonds (LQD)", "treasuries_7_10y": "US 7-10y Treasuries (IEF)",
                # Bond yields and overnight rates (rates_daily), in percent.
                "us_3m": "US 3-month (%)", "us_1y": "US 1-year (%)", "us_2y": "US 2-year (%)", "us_5y": "US 5-year (%)",
                "us_10y": "US 10-year (%)", "us_30y": "US 30-year (%)", "us_real_5y": "US real 5-year (%)",
                "us_real_10y": "US real 10-year (%)", "sofr": "SOFR (%)", "effr": "US Fed funds (%)",
                "jp_1y": "Japan 1-year (%)", "jp_2y": "Japan 2-year (%)", "jp_5y": "Japan 5-year (%)",
                "jp_10y": "Japan 10-year (%)", "jp_30y": "Japan 30-year (%)", "eu_2y": "Euro area 2-year (%)",
                "eu_10y": "Euro area 10-year (%)", "estr": "€STR (%)", "uk_10y": "UK 10-year (%)",
                "sonia": "SONIA (%)", "uk_bank_rate": "UK Bank Rate (%)",
                "in_mibor_on": "India overnight MIBOR (%)", "in_mibor_14d": "India MIBOR 14-day (%)",
                "in_mibor_1m": "India MIBOR 1-month (%)", "in_mibor_3m": "India MIBOR 3-month (%)",
                "in_mror": "India market repo rate (%)", "in_sorr": "India secured overnight rate (%)",
                "in_cd_14d": "India CD 14-day (%)", "in_cd_1m": "India CD 1-month (%)",
                "in_cd_3m": "India CD 3-month (%)", "in_cd_6m": "India CD 6-month (%)",
                "in_cd_12m": "India CD 12-month (%)", "in_tbill_14d": "India T-bill 14-day (%)",
                "in_tbill_1m": "India T-bill 1-month (%)", "in_tbill_3m": "India T-bill 3-month (%)",
                "in_tbill_6m": "India T-bill 6-month (%)", "in_tbill_12m": "India T-bill 12-month (%)"}
# GDP series (DataCollector/gdp.py): <country>_<measure>.
GDP_COUNTRIES = {"in": "India", "us": "US", "eu": "Euro area", "de": "Germany", "fr": "France", "uk": "UK",
                 "jp": "Japan", "cn": "China", "hk": "Hong Kong", "kr": "Korea", "tw": "Taiwan", "br": "Brazil"}
GDP_MEASURES = {"gdp_yoy": "real GDP growth, year on year (%)", "gdp_qoq": "real GDP growth, quarter on quarter (%)",
                "gdp_growth_yearly": "real GDP growth, yearly (%)", "gdp_usd_bn": "GDP (USD billion)",
                "gdp_per_capita_usd": "GDP per person (USD)"}
MACRO_LABELS |= {f"{c}_{m}": f"{name} {label}" for c, name in GDP_COUNTRIES.items() for m, label in GDP_MEASURES.items()}


def style(fig, height, unified=True):
    T = theme()
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
    T = theme()
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
    T = theme()
    s = s.dropna()
    fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines", showlegend=showlegend,
                             line=dict(color=color, width=width, shape="linear"),
                             hovertemplate=f"<b>%{{y:{hover}}}</b> {name}<extra></extra>"), row=row, col=col)
    fig.add_trace(go.Scatter(x=s.index[-1:], y=s.values[-1:], mode="markers", showlegend=False, hoverinfo="skip",
                             marker=dict(size=9, color=color, line=dict(color=T["surface"], width=2))),
                  row=row, col=col)


def hbar(values, fmt, colors, height_per=34, sort=True):
    """Horizontal bars, largest on top; sort=False keeps the given order, first on top."""
    T = theme()
    values = values.sort_values() if sort else values[::-1]
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


def rgba(hex_color, alpha):
    return f"rgba({','.join(str(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))},{alpha})"


def intervals(mean, std, nu, actual=None, height_per=34, xrange=None):
    """One forecast distribution per row, first row on top: mean dot, central 68% and 95% ranges
    of the Student-t forecast, and the actual outcome as a diamond when known. Pass xrange to
    keep the axis (and the zero line) fixed while stepping between charts."""
    T = theme()
    mean = mean[::-1]
    std, nu = std.reindex(mean.index), nu.reindex(mean.index)
    y = list(mean.index)
    fig = go.Figure()
    for p, alpha in [(0.95, 0.2), (0.68, 0.45)]:
        hw = halfwidth(std, nu, p)
        fig.add_trace(go.Bar(y=y, x=2 * hw, base=mean - hw, orientation="h", name=f"{p:.0%} range", width=0.5,
                             marker=dict(color=rgba(T["series"][0], alpha), cornerradius=4), hoverinfo="skip"))
    fig.add_trace(go.Scatter(y=y, x=mean, mode="markers", name="Forecast mean", customdata=halfwidth(std, nu, 0.68),
                             marker=dict(size=10, color=T["series"][0], line=dict(color=T["surface"], width=2)),
                             hovertemplate="<b>%{x:+.2%}</b>, 68% range ± %{customdata:.2%} · %{y}<extra></extra>"))
    if actual is not None:
        fig.add_trace(go.Scatter(y=y, x=actual.reindex(mean.index), mode="markers", name="Actual",
                                 marker=dict(symbol="diamond", size=11, color=T["text"],
                                             line=dict(color=T["surface"], width=2)),
                                 hovertemplate="<b>%{x:+.2%}</b> actual · %{y}<extra></extra>"))
    style(fig, 90 + height_per * len(y), unified=False)
    fig.update_layout(barmode="overlay", bargap=0.4)
    fig.update_xaxes(tickformat="+.0%", showgrid=True, gridcolor=T["grid"], zeroline=True,
                     zerolinecolor=T["axis"], zerolinewidth=1, range=xrange, autorange=xrange is None)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=T["text2"]), categoryorder="array", categoryarray=y)
    return fig


def band(mean, std, nu, actual):
    """One series over time: the forecast's central 68% and 95% ranges around the mean, with the
    actual outcomes as dots, red when they fell outside the 95% range."""
    T = theme()
    fig = go.Figure()
    for p, alpha in [(0.95, 0.16), (0.68, 0.32)]:
        hw = halfwidth(std, nu, p)
        fig.add_trace(go.Scatter(x=mean.index, y=mean + hw, mode="lines", line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=mean.index, y=mean - hw, mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor=rgba(T["series"][0], alpha), name=f"{p:.0%} range", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=mean.index, y=mean, mode="lines", name="Forecast mean",
                             line=dict(color=T["series"][0], width=2), customdata=halfwidth(std, nu, 0.68),
                             hovertemplate="<b>%{y:+.2%}</b>, 68% range ± %{customdata:.2%}<extra></extra>"))
    outside = (actual - mean).abs() > halfwidth(std, nu, 0.95)
    for mask, label, color in [(~outside, "Actual", T["text2"]), (outside, "Actual, outside 95% range", T["neg"])]:
        fig.add_trace(go.Scatter(x=actual.index[mask], y=actual[mask], mode="markers", name=label,
                                 marker=dict(size=8, color=color, line=dict(color=T["surface"], width=1.5)),
                                 hovertemplate="<b>%{y:+.2%}</b> actual<extra></extra>"))
    style(fig, 420)
    fig.update_yaxes(tickformat="+.0%")
    return fig


# Walk-forward evaluation table (features/evaluation): readable headers with what each score means.
EVAL_COLUMNS = {
    "model": "Model",
    "n": st.column_config.NumberColumn("Dates", help="Forecast dates with a known outcome"),
    "crps_bps": st.column_config.NumberColumn(
        "CRPS (bps)", format="%.1f",
        help="Distance between the whole forecast distribution and what happened. Lower is better."),
    "crps_skill": st.column_config.NumberColumn(
        "Skill vs historical", format="percent",
        help="How much lower the CRPS is than the historical benchmark's. Above 0 means the model adds something."),
    "cover_68": st.column_config.NumberColumn("Inside 68% range", format="percent",
                                              help="68% if the forecast is calibrated"),
    "cover_95": st.column_config.NumberColumn("Inside 95% range", format="percent",
                                              help="95% if the forecast is calibrated"),
    "nu": st.column_config.NumberColumn(
        "Tails (ν)", format="%.1f",
        help="Student-t tail parameter fitted to the model's past errors: lower = fatter tails; above ~30 is "
             "close to a normal distribution."),
    "mean_ic": st.column_config.NumberColumn("Mean ranks banks (IC)", format="%+.3f",
                                             help="Rank correlation of forecast means with actual returns"),
    "ic_t": st.column_config.NumberColumn("IC t-stat", format="%+.2f"),
    "net_bps_per_trade": st.column_config.NumberColumn(
        "Net bps / trade", format="%+.1f",
        help="Long the 3 best mean ÷ std, short the 3 worst, after 5 bps per side"),
    "sharpe_ann": st.column_config.NumberColumn("Sharpe", format="%+.2f"),
}
