"""Financials — one company's key ratios, results, balance sheet, cash flow and shareholding, laid out
like its screener.in page (where the data comes from)."""
import html

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import marketdata as md
from charts import line, style, theme

SECTIONS = {"quarters": "Quarterly Results", "profit_loss": "Profit & Loss", "balance_sheet": "Balance Sheet",
            "cash_flow": "Cash Flows", "ratios": "Ratios", "shareholding_quarterly": "Shareholding Pattern (quarterly)",
            "shareholding_yearly": "Shareholding Pattern (yearly)"}
# Rows screener shows in bold.
TOTALS = {"Operating Profit", "Financing Profit", "Profit before tax", "Net Profit", "Total Liabilities",
          "Total Assets", "Net Cash Flow"}
DEFAULT_COMPANY = "HDFCBANK"
RANGES = {"1Y": 365, "3Y": 3 * 365, "5Y": 5 * 365, "Max": None}
# The investment categorizer (documentations/investment_categorizer.md), tested on every company
# every six months from Jul 2017 using only the figures known at the time. Two or more red flags:
# "Don't invest" (blew up -40% in a year 1.7x as often as average). No red flags and 6+ of the 8 good
# points: "Good to invest" (beat the average stock by ~4%/year, in 16 of 18 half-years). The rest:
# "Maybe". Debt, interest and cash-flow tests don't apply to financial companies (banks, NBFCs,
# insurers, brokers, holding companies), whose balance sheets are built on borrowed or client money.
FINANCIAL_SECTOR = "Financial Services"
MIN_GOOD_POINTS = 6
VERDICTS = {"dont": ("Don't invest", "red", ":material/cancel:"), "maybe": ("Maybe", "orange", ":material/help:"),
            "good": ("Good to invest", "green", ":material/check_circle:")}
DOTS = {"good": "🟢", "maybe": "🟡", "dont": "🔴"}  # the company picker can't color text, so a dot per verdict
# Market cap filter bands, Rs crore.
SIZES = {"Above ₹20,000 Cr": (20000, float("inf")), "₹5,000 - 20,000 Cr": (5000, 20000),
         "₹1,000 - 5,000 Cr": (1000, 5000), "₹250 - 1,000 Cr": (250, 1000), "Below ₹250 Cr": (0, 250)}


@st.cache_data(persist="disk", show_spinner="Rating every company (once after each data update)...")
def companies(mtime, prices_mtime, sectors_mtime):
    """Every company with its sector, market cap and verdict (on the figures the page opens with)."""
    f = pd.read_parquet(md.FUNDAMENTALS)
    sectors = pd.read_parquet(md.COMPANIES).set_index("ticker")["sector"] if md.COMPANIES.exists() else pd.Series(dtype=object)
    px = duckdb.sql(f"select ticker, date, adj_close from (select *, row_number() over (partition by ticker "
                    f"order by date desc) k from {md.table(md.STOCKS)}) where k <= 200 order by date").df()
    px = {t: g.set_index("date")["adj_close"] for t, g in px.groupby("ticker")}
    rows = []
    for ticker, data in f.groupby("ticker"):
        data = data[data["view"] == ("consolidated" if (data["view"] == "consolidated").any() else "standalone")]
        p = px.get(ticker, pd.Series(dtype=float))
        snap = data[data["statement"] == "snapshot"].sort_values("date").groupby("item")["value"].last()
        mcap = snap.get("Market Cap")
        if mcap and len(p) and snap.get("Current Price"):
            mcap *= p.iloc[-1] / snap["Current Price"]
        sector = sectors.get(ticker)
        rows.append((ticker, sector, mcap, assess(data, mcap, p, sector == FINANCIAL_SECTOR)[0]))
    return pd.DataFrame(rows, columns=["ticker", "sector", "mcap", "verdict"]).set_index("ticker")


@st.cache_data
def company(mtime, ticker):
    return duckdb.connect().execute(f"select * from {md.table(md.FUNDAMENTALS)} where ticker = ?", [ticker]).df()


@st.cache_data
def last_close(mtime, ticker):
    row = duckdb.connect().execute(f"select close from {md.table(md.STOCKS)} where ticker = ? order by date desc limit 1",
                                   [ticker]).fetchone()
    return row[0] if row else None


@st.cache_data
def prices(mtime, ticker):
    return duckdb.connect().execute(f"select date, adj_close from {md.table(md.STOCKS)} where ticker = ? order by date",
                                    [ticker]).df().set_index("date")["adj_close"]


def indian(v, decimals=0):
    """Indian digit grouping, as screener shows it: 10,68,298."""
    sign, v = ("-" if v < 0 else ""), abs(v)
    whole, frac = f"{v:.{decimals}f}".partition(".")[::2]
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return sign + ",".join(([head] if head else []) + groups + [tail]) + (f".{frac}" if frac else "")


def cell(v, item, statement):
    if pd.isna(v):
        return ""
    if statement.startswith("shareholding") and item != "No. of Shareholders":
        return f"{v:.2f}%"
    if item.endswith("%"):
        return f"{v:,.0f}%"
    return indian(v, 2 if abs(v) < 100 and v != int(v) else 0)


def ratios(data, close):
    """The ratio box: screener's headline numbers, with the price-based ones moved to the latest close."""
    snap = data[data["statement"] == "snapshot"].sort_values("date").groupby("item")["value"].last()
    price = snap.get("Current Price")
    move = close / price if close and price else 1.0
    bs = data[data["statement"] == "balance_sheet"]
    latest = bs[bs["date"] == bs["date"].max()].set_index("item")["value"] if not bs.empty else pd.Series(dtype=float)
    equity = latest.get("Equity Capital", 0) + latest.get("Reserves", 0)
    debt = latest.get("Borrowings")
    book = snap.get("Book Value")

    def num(v, fmt):
        return "—" if v is None or pd.isna(v) else fmt(v)
    return [
        ("Market Cap", num(snap.get("Market Cap"), lambda v: f"₹ {indian(v * move)} Cr.")),
        ("Current Price", num(close or price, lambda v: f"₹ {indian(v, 2 if v < 100 else 0)}")),
        ("Stock P/E", num(snap.get("Stock P/E"), lambda v: f"{v * move:.1f}")),
        ("Book Value", num(book, lambda v: f"₹ {indian(v)}")),
        ("Price to Book", num((close or price) / book if book and (close or price) else None, lambda v: f"{v:.2f}")),
        ("Dividend Yield", num(snap.get("Dividend Yield"), lambda v: f"{v / move:.2f} %")),
        ("ROCE", num(snap.get("ROCE"), lambda v: f"{v:.2f} %")),
        ("ROE", num(snap.get("ROE"), lambda v: f"{v:.2f} %")),
        ("Debt / Equity", num(debt / equity if debt is not None and equity else None, lambda v: f"{v:.2f}")),
        ("Face Value", num(snap.get("Face Value"), lambda v: f"₹ {v:.2f}")),
    ]


def assess(data, mcap, px, financial=False):
    """The investment categorizer: (verdict key, red flags, good points), each check as (name, value, hit)
    where hit is True / False, or None when it doesn't apply or the data is missing."""
    yearly = data[data["statement"].isin(["profit_loss", "balance_sheet", "cash_flow", "ratios"])]
    years = sorted(data.loc[data["statement"] == "profit_loss", "date"].unique())
    y = yearly[yearly["date"].isin(years)].pivot_table(index="date", columns="item", values="value").sort_index()
    bank_layout = "Revenue" in y  # screener's layout for banks and NBFCs
    finance = bank_layout or financial
    col = lambda name: y[name] if name in y else pd.Series(float("nan"), index=y.index)
    profit, sales = col("Net Profit"), col("Revenue" if bank_layout else "Sales")
    cfo, assets, debt = col("Cash from Operating Activity"), col("Total Assets"), col("Borrowings")
    equity = col("Equity Capital") + col("Reserves")
    last = lambda s, k=0: s.iloc[-1 - k] if len(s) > k else float("nan")
    np0, eq0 = last(profit), last(equity)

    # Piotroski-style F-score from yearly figures: 8 tests of improving health (needs 6 answerable).
    def above(a, b, equal_ok=False):
        return None if pd.isna(a) or pd.isna(b) else bool(a >= b if equal_ok else a > b)
    ratio = lambda s, t, k=0: last(s, k) / last(t, k)
    f = [above(np0, 0),                                                      # profitable
         above(last(cfo), 0),                                                # cash-generating
         above(ratio(profit, assets), ratio(profit, assets, 1)),            # return on assets rising
         above(last(cfo), np0),                                              # cash above profit
         above(ratio(debt, assets, 1), ratio(debt, assets), equal_ok=True),  # leverage not rising
         above(last(col("Equity Capital"), 1) * 1.02, last(col("Equity Capital")), equal_ok=True),  # no new shares
         above(last(col("OPM %")), last(col("OPM %"), 1), equal_ok=True),    # margin not falling
         above(ratio(sales, assets), ratio(sales, assets, 1), equal_ok=True)]  # asset turnover not falling
    known = [v for v in f if v is not None]
    fscore = sum(known) if len(known) >= 6 else None

    sh = data[(data["item"] == "Promoters")]
    q = sh[sh["statement"] == "shareholding_quarterly"].sort_values("date")["value"]
    yr = sh[sh["statement"] == "shareholding_yearly"].sort_values("date")["value"]
    promoter_chg = q.iloc[-1] - q.iloc[-5] if len(q) >= 5 else yr.iloc[-1] - yr.iloc[-2] if len(yr) >= 2 else None
    cfo3, np3 = cfo.iloc[-3:].sum(min_count=3), profit.iloc[-3:].sum()
    cash_conv = cfo3 / np3 if pd.notna(cfo3) and np3 > 0 else None
    interest = last(col("Interest"))
    cover = (last(col("Profit before tax")) + interest) / interest if interest > 0 else None
    de = last(debt) / eq0 if eq0 > 0 else None
    pe = mcap / np0 if mcap and np0 > 0 else None
    pb = mcap / eq0 if mcap and eq0 > 0 else None
    s3 = last(sales, 3)
    growth = (last(sales) / s3) ** (1 / 3) - 1 if s3 > 0 and last(sales) > 0 else None
    profitable = int((profit.iloc[-5:] > 0).sum())
    trend = px.iloc[-1] / px.iloc[-200:].mean() - 1 if len(px) >= 200 else None

    na = lambda v: v is None or pd.isna(v)
    pct = lambda v: "—" if na(v) else f"{v:+.0%}"
    num = lambda v, fmt="{:.2f}": "—" if na(v) else fmt.format(v)
    nonfin = lambda hit: None if finance else hit
    red = [
        ("Loss in the last year", f"₹ {indian(np0)} Cr" if pd.notna(np0) else "—", None if pd.isna(np0) else np0 <= 0),
        ("Negative net worth", f"₹ {indian(eq0)} Cr" if pd.notna(eq0) else "—", None if pd.isna(eq0) else eq0 <= 0),
        ("Operating cash flow ≤ 0 over 3 years", "—" if pd.isna(cfo3) else f"₹ {indian(cfo3)} Cr",
         nonfin(None if pd.isna(cfo3) else cfo3 <= 0)),
        ("Debt / equity above 1.5", num(de), nonfin(None if na(de) else de > 1.5)),
        ("Interest cover below 1.5", num(cover, "{:.1f}x"), nonfin(None if na(cover) else cover < 1.5)),
        ("Promoters cut stake by 5+ points in a year", num(promoter_chg, "{:+.2f} pts"),
         None if na(promoter_chg) else promoter_chg < -5),
        ("F-score 2 or less (of 8)", num(fscore, "{:.0f}"), None if na(fscore) else fscore <= 2),
        ("Price 20%+ below its 200-day average", pct(trend), None if na(trend) else trend < -0.2),
    ]
    good = [
        ("F-score 6 or more (of 8)", num(fscore, "{:.0f}"), None if na(fscore) else fscore >= 6),
        ("Cash flow backs profits (3y cash / profit ≥ 0.8)", num(cash_conv),
         True if finance else None if na(cash_conv) else cash_conv >= 0.8),
        ("P/E 30 or less", num(pe, "{:.1f}"), None if na(pe) else pe <= 30),
        ("Price to book 6 or less", num(pb), None if na(pb) else pb <= 6),
        ("Promoter holding not falling", num(promoter_chg, "{:+.2f} pts"),
         None if na(promoter_chg) else promoter_chg >= 0),
        ("Profitable in 4+ of the last 5 years", f"{profitable} of {min(5, len(profit))}", profitable >= 4),
        ("Sales growing 8%+ a year (3 years)", pct(growth), None if na(growth) else growth >= 0.08),
        ("Price above its 200-day average", pct(trend), None if na(trend) else trend > 0),
    ]
    flags, points = sum(bool(h) for _, _, h in red), sum(bool(h) for _, _, h in good)
    verdict = "dont" if flags >= 2 else "good" if flags == 0 and points >= MIN_GOOD_POINTS else "maybe"
    return verdict, red, good, flags, points, finance


def checklist(title, rows, bad):
    """bad: whether a hit is bad (red flags) or good (good points)."""
    body = ""
    for name, value, hit in rows:
        if hit is None:
            mark = '<span class="na">–</span>'
        elif hit == bad:
            mark = '<span class="no">✗ ' + ("Flag" if bad else "No") + "</span>"
        else:
            mark = '<span class="ok">✓ ' + ("Clear" if bad else "Yes") + "</span>"
        body += f"<tr><td>{html.escape(name)}</td><td>{html.escape(value)}</td><td>{mark}</td></tr>"
    st.html(f'<div class="fin-table fin-check"><table><thead><tr><th>{html.escape(title)}</th><th>Value</th>'
            f"<th></th></tr></thead><tbody>{body}</tbody></table></div>")


def price_chart(px, days):
    T = theme()
    avg = px.rolling(200).mean()
    if days:
        start = px.index[-1] - pd.Timedelta(days=days)
        px, avg = px[px.index >= start], avg[avg.index >= start]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=avg.index, y=avg.values, name="200-day average", mode="lines",
                             line=dict(color=T["muted"], width=1.5, dash="dot"),
                             hovertemplate="%{y:,.1f} 200-day average<extra></extra>"))
    line(fig, px, "Price", T["series"][0], hover=",.1f")
    style(fig, 360)
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False})


def ratio_box(items):
    rows = "".join(f'<li><span class="n">{html.escape(n)}</span><span class="v">{html.escape(v)}</span></li>'
                   for n, v in items)
    st.html(f'<ul class="fin-ratios">{rows}</ul>')


def table(part, statement):
    wide = part.pivot_table(index="item", columns="date", values="value", sort=False)
    wide = wide.reindex(list(dict.fromkeys(part["item"])))
    head = "".join(f"<th>{d:%b %Y}</th>" for d in wide.columns)
    body = ""
    for item, row in wide.iterrows():
        cls = ' class="total"' if item in TOTALS else ""
        body += (f"<tr{cls}><td>{html.escape(item)}</td>"
                 + "".join(f"<td>{cell(v, item, statement)}</td>" for v in row) + "</tr>")
    st.html(f'<div class="fin-table"><table><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table></div>')


T = theme()
st.html(f"""<style>
.fin-ratios {{ list-style: none; margin: 0; padding: 16px 20px; display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); column-gap: 40px; row-gap: 10px;
  border: 1px solid {T["grid"]}; border-radius: 8px; font-size: 15px; }}
.fin-ratios li {{ display: flex; justify-content: space-between; border-bottom: 1px solid {T["grid"]}; padding-bottom: 6px; }}
.fin-ratios .n {{ color: {T["text2"]}; }}
.fin-ratios .v {{ color: {T["text"]}; font-weight: 600; font-variant-numeric: tabular-nums; }}
/* rtl on the scroller, ltr inside: wide tables open scrolled to the newest periods, like screener */
.fin-table {{ overflow-x: auto; direction: rtl; }}
.fin-table table {{ direction: ltr; border-collapse: collapse; width: 100%; font-size: 14px;
  font-variant-numeric: tabular-nums; }}
.fin-table th, .fin-table td {{ padding: 7px 12px; text-align: right; white-space: nowrap;
  border-bottom: 1px solid {T["grid"]}; color: {T["text"]}; }}
.fin-table th {{ color: {T["text2"]}; font-weight: 600; }}
.fin-table th:first-child, .fin-table td:first-child {{ text-align: left; position: sticky; left: 0;
  background: {T["surface"]}; min-width: 190px; }}
.fin-table tr.total td {{ font-weight: 700; }}
.fin-table tbody tr:hover td {{ background: {T["mid"]}; }}
.fin-check {{ direction: ltr; }}
.fin-check th:first-child, .fin-check td:first-child {{ position: static; white-space: normal; }}
.fin-check .ok {{ color: {T["series"][2]}; font-weight: 600; }}
.fin-check .no {{ color: {T["neg"]}; font-weight: 600; }}
.fin-check .na {{ color: {T["muted"]}; }}
</style>""")
st.title("Financials")
if not md.FUNDAMENTALS.exists():
    st.info("No company financials yet. Run `python screener.py` in DataCollector.")
    st.stop()
mtime = md.mtime(md.FUNDAMENTALS)
overview = companies(mtime, md.mtime(md.STOCKS), md.mtime(md.COMPANIES))
overview = overview.sort_values("mcap", ascending=False, na_position="last")  # largest first


def pick_label(ticker):
    mcap, verdict = overview.loc[ticker, ["mcap", "verdict"]]
    cap = "" if pd.isna(mcap) else f"  ·  ₹ {indian(mcap)} Cr"
    return f"{DOTS[verdict]} {ticker}{cap}"


ALL = "All"
f1, f2, f3 = st.columns(3)
sector = f1.selectbox("Sector", [ALL] + sorted(overview["sector"].dropna().unique()))
size = f2.selectbox("Market cap", [ALL] + list(SIZES))
verdict_pick = f3.selectbox("Verdict", [ALL] + list(VERDICTS), format_func=lambda v: v if v == ALL else
                            f"{DOTS[v]} {VERDICTS[v][0]}")
shown = overview
if sector != ALL:
    shown = shown[shown["sector"] == sector]
if size != ALL:
    low, high = SIZES[size]
    shown = shown[(shown["mcap"] >= low) & (shown["mcap"] < high)]
if verdict_pick != ALL:
    shown = shown[shown["verdict"] == verdict_pick]
names = shown.index.tolist()
if not names:
    st.info("No company matches these filters.")
    st.stop()

c1, c2 = st.columns([1, 2])
ticker = c1.selectbox(f"Company ({len(names):,})", names, format_func=pick_label,
                      index=names.index(DEFAULT_COMPANY) if DEFAULT_COMPANY in names else 0)
data = company(mtime, ticker)
views = [v for v in ["consolidated", "standalone"] if v in set(data["view"])]
view = c2.segmented_control("Figures", views, default=views[0], format_func=str.capitalize) or views[0]
data = data[data["view"] == view]

close = last_close(md.mtime(md.STOCKS), ticker) if md.STOCKS.exists() else None
px = prices(md.mtime(md.STOCKS), ticker) if md.STOCKS.exists() else pd.Series(dtype=float)
snap = data[data["statement"] == "snapshot"].sort_values("date").groupby("item")["value"].last()
mcap = snap.get("Market Cap")
if mcap and close and snap.get("Current Price"):
    mcap *= close / snap["Current Price"]
verdict, red, good, flags, points, finance = assess(data, mcap, px, overview.loc[ticker, "sector"] == FINANCIAL_SECTOR)
label, color, icon = VERDICTS[verdict]
st.subheader(f"{ticker} :{color}-badge[{icon} {label}]")
ratio_box(ratios(data, close))

if len(px):
    st.subheader("Price")
    days = RANGES[st.segmented_control("Range", list(RANGES), default="3Y", key="range",
                                       label_visibility="collapsed") or "3Y"]
    price_chart(px, days)

st.subheader("Investment categorizer")
st.caption(f"{flags} red flag{'s' * (flags != 1)}, {points} of {len(good)} good points. "
           f"Two or more red flags: don't invest. No red flags and {MIN_GOOD_POINTS}+ good points: good to invest. "
           + ("Debt, interest and cash-flow tests don't apply to financial companies. " if finance else "")
           + "Rules tested on Indian stocks from 2017; a screen, not advice. "
           "How it was built: documentations/investment_categorizer.md.")
c1, c2 = st.columns(2)
with c1:
    checklist("Red flags", red, bad=True)
with c2:
    checklist("Good points", good, bad=False)
for key, title in SECTIONS.items():
    part = data[data["statement"] == key]
    if part.empty:
        continue
    st.subheader(title)
    if not key.startswith("shareholding") and key != "ratios":
        st.caption(f"{view.capitalize()} figures in Rs. Crores")
    table(part, key)
