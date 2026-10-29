"""Data — what is in the MarketData store: every table, its columns, and its rows."""
import duckdb
import pandas as pd
import streamlit as st

import marketdata as md

LAYERS = {
    "curated": "Cleaned tables built from the latest download",
    "features": "Model outputs and other derived data",
    "raw": "Exactly what each source returned, one folder per download (never modified)",
}
FILTER_MAX_DISTINCT = 60  # columns with fewer distinct values than this get a filter
ROW_LIMITS = [100, 1_000, 10_000, 100_000]


@st.cache_data
def load_catalog(files):
    return md.catalog()


@st.cache_data
def summarize(rel, mtime):
    return md.sql(f"summarize select * from {md.table(md.DATA_ROOT / rel)}")


@st.cache_data
def distinct_values(rel, mtime, col):
    return md.sql(f'select distinct "{col}" as v from {md.table(md.DATA_ROOT / rel)} order by 1')["v"].tolist()


def column_config(df):
    """Show timestamps as plain dates: every table in the store is daily."""
    return {c: st.column_config.DateColumn(c, format="YYYY-MM-DD")
            for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])}


files = md.files()
if not files:
    st.title("Data")
    st.info(f"The store at `{md.DATA_ROOT}` is empty. In BankPrediction run `python run.py data`.")
    st.stop()
cat = load_catalog(files)
mtimes = dict(files)

st.title("Data")
st.caption(f"Store `{md.DATA_ROOT}` · {len(cat)} tables · {cat['rows'].sum():,} rows · "
           f"{cat['size_kb'].sum() / 1024:.1f} MB on disk")

# --- Overview: one row per table, grouped by layer -----------------------------------------
OVERVIEW_CONFIG = {
    "table": st.column_config.TextColumn("Table", width="medium"),
    "rows": st.column_config.NumberColumn("Rows", format="localized"),
    "columns": st.column_config.NumberColumn("Columns"),
    "size": st.column_config.TextColumn("Size", width="small"),
    "first_date": st.column_config.DateColumn("From", format="D MMM YYYY"),
    "last_date": st.column_config.DateColumn("To", format="D MMM YYYY"),
    "updated": st.column_config.DatetimeColumn("Updated", format="D MMM YYYY, HH:mm"),
}


def human_size(kb):
    return f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB"


for layer in [l for l in LAYERS if l in set(cat["layer"])] + sorted(set(cat["layer"]) - set(LAYERS)):
    part = cat[cat["layer"] == layer].drop(columns="layer")
    # The section heading already names the layer, so rows show the path inside it.
    part = part.assign(table=part["table"].str.removeprefix(f"{layer}/"), size=part["size_kb"].map(human_size))
    part = part[["table", "rows", "columns", "size", "first_date", "last_date", "updated"]]
    label = f"{layer} · {len(part)} tables"
    body = st.expander(f"{label} — {LAYERS.get(layer, '')}", expanded=False) if layer == "raw" else st.container()
    with body:
        if layer != "raw":
            st.markdown(f"##### {label}")
            st.caption(LAYERS.get(layer, ""))
        st.dataframe(part, hide_index=True, width="stretch", column_config=OVERVIEW_CONFIG)

st.divider()

# --- One table in detail ----------------------------------------------------------------------
names = cat["table"].tolist()
default = names.index("curated/prices_daily") if "curated/prices_daily" in names else 0
pick = st.selectbox("Open a table", names, index=default)
info = cat.set_index("table").loc[pick]
rel = f"{pick}.parquet"
mtime = mtimes[rel]
src = md.table(md.DATA_ROOT / rel)

m = st.columns(4)
m[0].metric("Rows", f"{info['rows']:,}", border=True)
m[1].metric("Columns", int(info["columns"]), border=True)
# Short values so the cards never truncate; the tooltip carries the exact dates.
if pd.isna(info["first_date"]):
    m[2].metric("Years", "—", border=True, help="This table has no date column")
else:
    first, last = info["first_date"], info["last_date"]
    m[2].metric("Years", f"{first:%Y}–{last:%Y}" if first.year != last.year else f"{first:%Y}", border=True,
                help=f"{first:%d %b %Y} to {last:%d %b %Y}")
m[3].metric("Updated", f"{info['updated']:%d %b}", border=True, help=f"{info['updated']:%d %b %Y, %H:%M}")

summary = summarize(rel, mtime)
rows_tab, cols_tab, sql_tab = st.tabs(["Rows", "Columns", "SQL"])

with rows_tab:
    # Filters: a date range plus one picker per low-cardinality column (ticker, series, model, horizon...).
    types = dict(zip(summary["column_name"], summary["column_type"]))
    pickers = [c for c, t, n in zip(summary["column_name"], summary["column_type"], summary["approx_unique"])
               if c != "date" and n <= FILTER_MAX_DISTINCT and not t.startswith(("DOUBLE", "FLOAT", "TIMESTAMP"))]
    where, params = [], []
    widgets = st.columns(min(4, len(pickers) + ("date" in types) + 1))
    i = 0
    if "date" in types:
        lo, hi = info["first_date"].date(), info["last_date"].date()
        span = widgets[i].date_input("Dates", (lo, hi), min_value=lo, max_value=hi, key=f"dates_{pick}")
        if len(span) == 2:
            where.append('"date" between ? and ?')
            params += [pd.Timestamp(span[0]), pd.Timestamp(span[1]) + pd.Timedelta(days=1) - pd.Timedelta(1)]
        i += 1
    for col in pickers:
        chosen = widgets[i % len(widgets)].multiselect(col, distinct_values(rel, mtime, col),
                                                       placeholder="All", key=f"f_{pick}_{col}")
        if chosen:
            where.append(f'list_contains(?, "{col}")')
            params.append(chosen)
        i += 1
    limit = widgets[i % len(widgets)].selectbox("Show up to", ROW_LIMITS, index=1, format_func="{:,} rows".format,
                                               key=f"limit_{pick}")

    clause = f"where {' and '.join(where)}" if where else ""
    order = 'order by "date" desc' if "date" in types else ""
    con = duckdb.connect()
    total = con.execute(f"select count(*) from {src} {clause}", params).fetchall()[0][0]
    df = con.execute(f"select * from {src} {clause} {order} limit {limit}", params).df()
    st.caption(f"Showing **{len(df):,}** of **{total:,}** matching rows"
               + (" (newest first)" if order else ""))
    st.dataframe(df, hide_index=True, width="stretch", height=560, column_config=column_config(df))
    if total:
        st.download_button(f"Download {total:,} rows as CSV",
                           con.execute(f"select * from {src} {clause} {order}", params).df()
                           .to_csv(index=False).encode(),
                           file_name=f"{pick.replace('/', '_')}.csv", mime="text/csv")

with cols_tab:
    cols = summary[["column_name", "column_type", "min", "max", "approx_unique", "null_percentage"]].copy()
    cols["null_percentage"] = pd.to_numeric(cols["null_percentage"], errors="coerce")
    # SUMMARIZE returns min/max as text: drop midnight times from dates and round long floats.
    for c in ["min", "max"]:
        cols[c] = [v.removesuffix(" 00:00:00") if t.startswith("TIMESTAMP")
                   else f"{float(v):,.6g}" if t.startswith(("DOUBLE", "FLOAT")) and v is not None else v
                   for v, t in zip(cols[c], cols["column_type"])]
    st.dataframe(cols, hide_index=True, width="stretch", column_config={
        "column_name": "Column", "column_type": "Type", "min": "Min", "max": "Max",
        "approx_unique": st.column_config.NumberColumn("Distinct (approx.)", format="localized"),
        "null_percentage": st.column_config.NumberColumn("Missing", format="%.1f%%"),
    })

with sql_tab:
    con = md.connect()
    st.caption("Views: " + ", ".join(f"`{v}`" for v in md.views_available(con))
               + ". Any file also works as `read_parquet('path')`.")
    q = st.text_area("Query", height=140, key=f"sql_{pick}",
                     value=f"select *\nfrom {src}\nlimit 100")
    if st.button("Run", type="primary"):
        try:
            out = con.sql(q).df()
            st.caption(f"{len(out):,} rows")
            st.dataframe(out, hide_index=True, width="stretch", column_config=column_config(out))
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
