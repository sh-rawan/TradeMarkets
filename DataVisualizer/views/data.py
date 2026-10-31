"""Market data — every market data table in the store, as charts, one page per country."""
import math

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import marketdata as md
from charts import MACRO_LABELS, style, theme

FILTER_MAX_DISTINCT = 60  # text columns with fewer distinct values than this filter the chart
OWN_PAGE = {"fundamentals", "companies"}  # tables shown on a page of their own (Financials)
# Columns that split a table into one chart panel each, in order of preference.
PANEL_COLUMNS = ["ticker", "index", "series", "participant", "category"]
# The value shown first when a table opens (the first one present wins).
PREFERRED_VALUES = ["adj_close", "close", "value", "net", "future_index_net", "atm_iv"]
# Order and names in the table picker; tables not listed here follow with their file name.
NAMES = {"stocks_daily": "Stocks (all NSE)", "etfs_daily": "ETFs", "indices_daily": "NSE indices",
         "options_daily": "Futures and options by underlying", "futures_daily": "Futures (nearest expiry)",
         "participant_oi": "Positions by participant (open interest)",
         "participant_vol": "Trading by participant (volume)", "fiidii_cash": "FII / DII cash market flows",
         "macro_daily": "Markets and currencies", "rates_daily": "Bond yields and interest rates", "gdp": "GDP",
         "prices_daily": "Bank Nifty banks (Yahoo)",
         "stock_tags": "Stock tags", "tickers": "Banks: PSU vs private"}
TAG_KINDS = {"theme": "Theme", "size": "Size", "sector": "Sector", "market": "Market", "etf": "ETF type",
             "etf_index": "ETF index"}
# Which group a big table opens on, and how its panels are ranked when a group has too many.
DEFAULT_GROUP = {"stocks_daily": "Banks", "options_daily": "Indices", "futures_daily": "Indices", "etfs_daily": "Equity"}
DEFAULT_INDICES = ["Nifty 50", "Nifty Bank", "Nifty IT", "Nifty Midcap 150", "Nifty Smallcap 250", "India VIX"]
ACTIVITY = ["value", "fut_oi", "oi", "volume"]
MAX_PANELS = 24
PANEL_COLS = 3

# One page per country: {key: page title}. India also gets every NSE table; the others get their
# series from the tables that mix countries (markets and currencies; bond yields and rates; GDP).
COUNTRIES = {"india": "India", "us": "US", "europe": "Europe & UK", "japan": "Japan",
             "china": "China & HK", "emerging": "Korea, Taiwan, Brazil", "global": "Commodities & crypto"}
MIXED_TABLES = {"macro_daily", "rates_daily", "gdp"}
COUNTRY_SERIES = {
    "india": {"banknifty", "nifty", "vix", "usdinr", "eurinr", "in10y"},
    "us": {"spx", "nasdaq", "usvix", "dxy", "us10y", "us3m", "hy_bonds", "ig_bonds", "treasuries_7_10y", "sofr", "effr"},
    "europe": {"dax", "ftse", "estr", "sonia"},
    "japan": {"nikkei", "usdjpy"},
    "china": {"hangseng", "shanghai", "usdcny"},
    "emerging": {"kospi", "taiwan", "brazil", "em_etf"},
}
COUNTRY_PREFIXES = {"in_": "india", "us_": "us", "eu_": "europe", "uk_": "europe", "de_": "europe", "fr_": "europe",
                    "jp_": "japan", "cn_": "china", "hk_": "china", "kr_": "emerging", "tw_": "emerging", "br_": "emerging"}


def country_of(series):
    """The page a series belongs on; anything not listed (commodities, Bitcoin, new series) goes to global."""
    for country, names in COUNTRY_SERIES.items():
        if series in names:
            return country
    return next((c for p, c in COUNTRY_PREFIXES.items() if series.startswith(p)), "global")


@st.cache_data
def summarize(path, mtime):
    return md.sql(f"summarize select * from {md.table(path)}")


@st.cache_data
def distinct_values(path, mtime, col):
    return md.sql(f'select distinct "{col}" as v from {md.table(path)} where "{col}" is not null order by 1')["v"].tolist()


@st.cache_data
def country_series(path, mtime, country):
    return [s for s in distinct_values(path, mtime, "series") if country_of(s) == country]


@st.cache_data
def filtered_values(path, mtime, col, where, params):
    """Distinct values of col among the rows the earlier filters keep."""
    clause = f"where {' and '.join(where)} and" if where else "where"
    return duckdb.connect().execute(f'select distinct "{col}" as v from {md.table(path)} {clause} "{col}" is not null '
                                    f'order by 1', list(params)).df()["v"].tolist()


@st.cache_data
def tag_groups(path, mtime, tags_mtime):
    """{group: tickers in this table}: every tag, plus 'Indices' for index derivatives."""
    tags = md.sql(f"select * from {md.table(md.TAGS)}") if md.TAGS.exists() else pd.DataFrame(columns=["ticker", "tag"])
    have = set(distinct_values(path, mtime, "ticker"))
    groups = {}
    if "underlying" in summarize(path, mtime)["column_name"].tolist():
        groups["Indices"] = md.sql(f"select distinct ticker from {md.table(path)} where underlying = 'index'")["ticker"].tolist()
    for tag, g in tags.groupby("tag"):
        members = sorted(set(g["ticker"]) & have)
        if members:
            groups[tag] = members
    return groups


@st.cache_data
def busiest(path, mtime, tickers, col):
    """Tickers ranked by their activity over the last ~3 months (traded value, open interest...)."""
    q = (f'select ticker from {md.table(path)} where list_contains(?, ticker) and date >= '
         f'(select max(date) - interval 90 day from {md.table(path)}) group by 1 order by sum("{col}") desc nulls last')
    return duckdb.connect().execute(q, [list(tickers)]).df()["ticker"].tolist()


def pretty(col):
    return MACRO_LABELS.get(col, col.replace("_", " "))


def plot(fig):
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False})


def bars(labels, values, hover=None):
    fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", customdata=hover,
                           marker=dict(color=T["series"][0], cornerradius=4), texttemplate="%{x:,}",
                           textposition="outside", cliponaxis=False,
                           hovertemplate="<b>%{x:,}</b> %{y}" + ("<br>%{customdata}" if hover is not None else "")
                                         + "<extra></extra>"))
    style(fig, 80 + 28 * len(labels), unified=False)
    fig.update_layout(bargap=0.3)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=T["text2"]), autorange="reversed")
    fig.update_xaxes(showgrid=True, gridcolor=T["grid"])
    plot(fig)


def render(country):
    tables = sorted(p for p in md.CURATED.glob("*.parquet") if p.stem not in OWN_PAGE)
    # India has every table; other countries only their series in the mixed ones.
    tables = [p for p in tables if (p.stem not in MIXED_TABLES and country == "india")
              or (p.stem in MIXED_TABLES and country_series(p, md.mtime(p), country))]
    if not tables:
        st.info(f"No market data for {COUNTRIES[country]} in `{md.DATA_ROOT}` yet. Run `python collect.py` in DataCollector.")
        st.stop()
    tables.sort(key=lambda p: list(NAMES).index(p.stem) if p.stem in NAMES else len(NAMES))
    path = tables[0] if len(tables) == 1 else st.selectbox(
        "Table", tables, format_func=lambda p: NAMES.get(p.stem, p.stem.replace("_", " ")), key=f"table_{country}")
    page = f"{country}_{path.stem}"
    mtime = md.mtime(path)
    src = md.table(path)
    summary = summarize(path, mtime)
    types = dict(zip(summary["column_name"], summary["column_type"]))
    uniques = dict(zip(summary["column_name"], summary["approx_unique"]))
    numeric = [c for c, t in types.items() if t.startswith(("DOUBLE", "FLOAT", "BIGINT", "INTEGER", "DECIMAL", "HUGEINT"))]
    categorical = [c for c, t in types.items() if c != "date" and uniques[c] <= FILTER_MAX_DISTINCT
                   and not t.startswith(("DOUBLE", "FLOAT", "TIMESTAMP", "DATE"))]

    if "tag" in types:
        # The tags table: how many stocks carry each tag, for one kind of tag.
        kinds = [k for k in TAG_KINDS if k in distinct_values(path, mtime, "kind")]
        kind = st.selectbox("Tags", kinds, format_func=TAG_KINDS.get, key="tag_kind")
        data = duckdb.connect().execute(f"select tag, count(*) as n, string_agg(ticker, ', ' order by ticker) as names "
                                        f"from {src} where kind = ? group by 1 order by 2 desc", [kind]).df()
        bars(data["tag"], data["n"], [n if len(n) < 300 else n[:300] + "…" for n in data["names"]])
        st.stop()
    if "date" not in types:
        # e.g. tickers: how many banks fall in each group, with their names.
        label, by = categorical[0], next((c for c in categorical[1:]), categorical[0])
        data = md.sql(f'select "{by}" as k, count(*) as n, string_agg("{label}", \', \' order by "{label}") as names '
                      f'from {src} group by 1 order by 2 desc')
        bars(data["k"], data["n"], data["names"])
        st.stop()

    # Long/short pairs (FII index futures long and short...) also get their net position.
    nets = {c[:-5] + "_net": c[:-5] for c in types if c.endswith("_long") and c[:-5] + "_short" in types}
    values = [c for c in numeric if c not in categorical] + list(nets)
    values = sorted(values, key=lambda c: next((i for i, p in enumerate(PREFERRED_VALUES) if p == c), 99))
    panel = next((c for c in PANEL_COLUMNS if c in types), None)
    others = [c for c in categorical if c not in (panel, "underlying", "series")]

    c1, c2, c3 = st.columns([1, 1, 2])
    value = c1.selectbox("Value", values, format_func=pretty, key=f"value_{page}")
    options = distinct_values(path, mtime, panel) if panel else []
    if panel == "series":
        options = country_series(path, mtime, country)
    default = []
    if panel == "ticker" and len(options) > MAX_PANELS:
        # Too many to draw at once: pick a group (tag), then the busiest names in it.
        groups = tag_groups(path, mtime, md.mtime(md.TAGS))
        names = ["All"] + sorted(groups, key=str.lower)
        start = DEFAULT_GROUP.get(path.stem, "All")
        group = c2.selectbox("Group", names, index=names.index(start) if start in names else 0, key=f"group_{page}")
        options = options if group == "All" else groups[group]
        act = next((c for c in ACTIVITY if c in types), None)
        default = (busiest(path, mtime, tuple(options), act) if act else options)[:MAX_PANELS]
    elif panel == "index" and len(options) > MAX_PANELS:
        default = [i for i in DEFAULT_INDICES if i in options]
    if panel:
        chosen = c3.multiselect(f"Show only these ({pretty(panel)})", options, placeholder=f"All {len(options)}",
                                default=[d for d in default if d in options] if default else None,
                                format_func=lambda v: MACRO_LABELS.get(v, v), key=f"panels_{page}_{len(options)}")
        shown = chosen or default or options
    where, params = [], []
    for col in others:
        opts = filtered_values(path, mtime, col, tuple(where), tuple(params))
        where.append(f'"{col}" = ?')
        # The key follows the earlier filters, so a choice that no longer exists starts over.
        params.append(st.selectbox(pretty(col).capitalize(), opts, format_func=lambda v: pretty(str(v)).capitalize(), key=f"f_{page}_{col}_{hash(tuple(params))}"))
    lo, hi = (d.date() for d in md.sql(f"select min(date), max(date) from {src}").iloc[0])
    one_day = lo == hi
    if not one_day:
        span = st.slider("Dates", lo, hi, (lo, hi), format="MMM YYYY", key=f"span_{page}")
        where.append('"date" between ? and ?')
        params += [pd.Timestamp(span[0]), pd.Timestamp(span[1])]
    if panel:
        where.append(f'list_contains(?, "{panel}")')
        params.append(list(shown))

    expr = f'("{nets[value]}_long" - "{nets[value]}_short")' if value in nets else f'"{value}"'
    cols = ['"date"', f"{expr} as v"] + ([f'"{panel}" as p'] if panel else [])
    clause = f"where {' and '.join(where)}" if where else ""
    # Futures: one line per underlying, following the nearest expiry.
    nearest = ('qualify row_number() over (partition by ticker, date order by expiry) = 1' if "expiry" in types else "")
    data = duckdb.connect().execute(f"select {', '.join(cols)} from {src} {clause} {nearest} order by date", params).df()

    if data.empty:
        st.info("Nothing for these choices.")
    elif one_day:
        # A single date so far (e.g. FII / DII cash flows): one bar per row; it becomes lines as days are added.
        keys = data["p"].astype(str) if panel else pd.Series([pretty(value)] * len(data))
        fig = go.Figure(go.Bar(x=data["v"], y=keys, orientation="h",
                               marker=dict(color=[T["pos"] if v >= 0 else T["neg"] for v in data["v"]], cornerradius=4),
                               texttemplate="%{x:,.4~g}", textposition="outside", cliponaxis=False,
                               hovertemplate="<b>%{x:,.4~g}</b> %{y}<extra></extra>"))
        style(fig, 90 + 50 * len(data), unified=False)
        fig.update_layout(bargap=0.4, title=dict(text=f"{lo:%d %b %Y}", font=dict(size=13, color=T["text2"])))
        fig.update_xaxes(showgrid=True, gridcolor=T["grid"], zeroline=True, zerolinecolor=T["axis"])
        fig.update_yaxes(showgrid=False, tickfont=dict(color=T["text2"]))
        plot(fig)
    else:
        # One panel per stock / index / series / participant, each on its own scale, in the order chosen.
        groups = dict(list(data.groupby("p", sort=False))) if panel else {pretty(value): data}
        order = [k for k in shown if k in groups] if panel else list(groups)
        n_rows, n_cols = math.ceil(len(order) / PANEL_COLS), min(len(order), PANEL_COLS)
        fig = make_subplots(rows=n_rows, cols=n_cols, shared_xaxes=True, vertical_spacing=75 / (230 * n_rows),
                            horizontal_spacing=0.07, subplot_titles=[MACRO_LABELS.get(str(k), str(k)) for k in order])
        for i, k in enumerate(order):
            g = groups[k]
            fig.add_trace(go.Scatter(x=g["date"], y=g["v"], mode="lines", name=pretty(value), showlegend=False,
                                     line=dict(color=T["series"][0], width=1.5),
                                     hovertemplate="<b>%{y:,.4~g}</b><extra></extra>"),
                          row=i // n_cols + 1, col=i % n_cols + 1)
        style(fig, 60 + (230 if n_rows > 1 else 380) * n_rows)
        fig.update_annotations(font=dict(size=13, color=T["text"]))
        fig.update_xaxes(showticklabels=True)
        plot(fig)


T = theme()
st.title("Market data")
render(st.segmented_control("Country", list(COUNTRIES), format_func=COUNTRIES.get, default="india",
                            key="country") or "india")
