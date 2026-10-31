"""Company fundamentals from screener.in's public company pages, for every NSE-listed stock:
  quarters        the last ~13 quarterly results (sales, profit, EPS; for banks also Gross / Net NPA %)
  profit_loss     ~12 years of yearly results
  balance_sheet   ~12 years (equity, reserves, borrowings / deposits, assets)
  cash_flow       ~12 years (operating, investing, financing, free cash flow)
  ratios          ~12 years (ROCE / ROE, working-capital days...)
  shareholding_quarterly, shareholding_yearly   promoters, FIIs, DIIs, government, public %
  snapshot        the page's headline numbers on the day it was fetched: Market Cap, Current Price,
                  Stock P/E, Book Value, Dividend Yield, ROCE, ROE, Face Value
Also curated/companies: each company's sector and industry as screener classifies it (broad sector,
sector, broad industry, industry). Amounts are in Rs crore. Each company is fetched standalone, and consolidated too when it has one.
Pages give period ends, not the date a result was announced: allow ~45 days before using one.

    python screener.py           # fetch the pages missing from this month's snapshot, then rebuild
    python screener.py --build   # only rebuild curated/fundamentals and companies from the saved pages

One page every ~2 seconds (robots.txt allows /company/ pages). It stops if the site starts refusing.
Raw pages: raw/screener/fetched=<YYYY-MM>/<view>/<SYMBOL>.html.gz, so a run can resume."""
import argparse
import gzip
import io
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

import tags
from config import COMPANIES_TABLE, FUNDAMENTALS_TABLE, SCREENER_RAW
from store import write

URL = "https://www.screener.in/company/{symbol}/{view}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36"}
PAUSE = 2.0          # seconds between requests
MAX_REFUSALS = 3     # consecutive 403 / 429 answers before giving up for this run
SECTIONS = {"quarters": "section#quarters table.data-table", "profit_loss": "section#profit-loss table.data-table",
            "balance_sheet": "section#balance-sheet table.data-table", "cash_flow": "section#cash-flow table.data-table",
            "ratios": "section#ratios table.data-table", "shareholding_quarterly": "div#quarterly-shp table",
            "shareholding_yearly": "div#yearly-shp table"}
# Every company gets the same rows, in this order. Banks and NBFCs use screener's finance layout
# (Revenue, Financing Profit), which is computed differently, so it is a layout of its own rather
# than a renaming. A row a page leaves out is stored empty; a missing shareholder category is 0%.
_SHAREHOLDING = ["Promoters", "FIIs", "DIIs", "Government", "Public", "Others", "No. of Shareholders"]
_SNAPSHOT = ["Market Cap", "Current Price", "Stock P/E", "Book Value", "Dividend Yield", "ROCE", "ROE", "Face Value"]
_COMMON = {
    "balance_sheet": ["Equity Capital", "Reserves", "Borrowings", "Other Liabilities", "Total Liabilities",
                      "Fixed Assets", "CWIP", "Investments", "Other Assets", "Total Assets"],
    "shareholding_quarterly": _SHAREHOLDING, "shareholding_yearly": _SHAREHOLDING, "snapshot": _SNAPSHOT,
}
_RESULTS = ["Sales", "Expenses", "Operating Profit", "OPM %", "Other Income", "Interest", "Depreciation",
            "Profit before tax", "Tax %", "Net Profit", "EPS in Rs"]
_FINANCE_RESULTS = ["Revenue", "Interest", "Expenses", "Financing Profit", "Financing Margin %", "Other Income",
                    "Depreciation", "Profit before tax", "Tax %", "Net Profit", "EPS in Rs"]
_CASH = ["Cash from Operating Activity", "Cash from Investing Activity", "Cash from Financing Activity",
         "Net Cash Flow", "Free Cash Flow"]
LAYOUTS = {
    "company": {**_COMMON, "quarters": _RESULTS, "profit_loss": _RESULTS + ["Dividend Payout %"],
                "cash_flow": _CASH + ["CFO/EBITDA"],
                "ratios": ["Debtor Days", "Inventory Days", "Days Payable", "Cash Conversion Cycle",
                           "Working Capital Days", "ROCE %"]},
    "finance": {**_COMMON, "balance_sheet": _COMMON["balance_sheet"][:2] + ["Deposits"] + _COMMON["balance_sheet"][2:],
                "quarters": _FINANCE_RESULTS + ["Gross NPA %", "Net NPA %"],
                "profit_loss": _FINANCE_RESULTS + ["Dividend Payout %"], "cash_flow": _CASH, "ratios": ["ROE %"]},
}
RENAME = {"Borrowing": "Borrowings"}


def _snapshot():
    return SCREENER_RAW / f"fetched={pd.Timestamp.today():%Y-%m}"


def _fetch(session, symbol, view):
    """Page HTML, None when screener has no such page, or raises when the site refuses."""
    for attempt in range(3):
        r = session.get(URL.format(symbol=symbol, view="consolidated/" if view == "consolidated" else ""), timeout=60)
        if r.status_code == 200:
            return r.text
        if r.status_code == 404:
            return None
        if r.status_code in (403, 429):
            raise PermissionError(r.status_code)
        time.sleep(10 * (attempt + 1))  # 5xx: wait and try again
    return None


def download():
    snap = _snapshot()
    snap.mkdir(parents=True, exist_ok=True)
    symbols = sorted(tags.listed_symbols() - tags.etf_symbols())
    missing_file = snap / "not_on_screener.txt"
    missing = set(missing_file.read_text().split()) if missing_file.exists() else set()
    session = requests.Session()
    session.headers.update(HEADERS)
    fetched, refusals, t = 0, 0, time.time()
    todo = [s for s in symbols if s not in missing and not (snap / "standalone" / f"{s}.html.gz").exists()]
    print(f"  Screener: {len(symbols) - len(todo)} of {len(symbols)} companies already saved, {len(todo)} to fetch")
    for i, symbol in enumerate(todo):
        for view in ["standalone", "consolidated"]:
            try:
                html = _fetch(session, symbol, view)
                refusals = 0
            except PermissionError as e:
                refusals += 1
                print(f"  Screener refused {symbol} ({e}); waiting 2 minutes")
                if refusals >= MAX_REFUSALS:
                    print("  Screener keeps refusing: stopping. Re-run later to resume.")
                    return
                time.sleep(120)
                break
            except requests.RequestException as e:
                print(f"  Screener: {symbol} {view} failed ({type(e).__name__})")
                break
            finally:
                time.sleep(PAUSE)
            if html is None:
                if view == "standalone":
                    missing.add(symbol)
                    missing_file.write_text("\n".join(sorted(missing)))
                break
            path = snap / view / f"{symbol}.html.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(html.encode("utf-8")))
            fetched += 1
            # Only fetch the consolidated page when the company publishes one.
            if view == "standalone" and f"/company/{symbol}/consolidated/" not in html:
                break
        if (i + 1) % 100 == 0:
            left = (time.time() - t) / (i + 1) * (len(todo) - i - 1) / 60
            print(f"  Screener: {i + 1} of {len(todo)} companies, ~{left:.0f} min left", flush=True)
    print(f"  Screener: {fetched} pages fetched, {len(missing)} symbols not on screener")


def _number(text):
    text = str(text).replace(",", "").replace("%", "").strip()
    try:
        value = float(text)
    except ValueError:
        return None
    return None if pd.isna(value) else value


PROFILE = {"Broad Sector": "broad_sector", "Sector": "sector", "Broad Industry": "broad_industry",
           "Industry": "industry"}


def _parse(html, symbol, view, fetched):
    """(value rows, profile): the page's numbers, and its sector / industry classification."""
    soup = BeautifulSoup(html, "lxml")
    profile = {col: a.get_text(strip=True) for title, col in PROFILE.items()
               if (a := soup.select_one(f'a[title="{title}"]'))}
    # The headline numbers (market cap, price, P/E...) as of the day the page was fetched.
    rows = []
    for li in soup.select("#top-ratios li"):
        name, numbers = li.select_one(".name"), li.select(".number")
        value = _number(numbers[0].get_text()) if name and len(numbers) == 1 else None
        if value is not None:
            rows.append((symbol, view, "snapshot", name.get_text(strip=True), fetched, value))
    for statement, selector in SECTIONS.items():
        table = soup.select_one(selector)
        if table is None:
            continue
        df = pd.read_html(io.StringIO(str(table)), thousands=None)[0]
        periods = pd.to_datetime(pd.Series(df.columns[1:]), format="%b %Y", errors="coerce") + pd.offsets.MonthEnd(0)
        for _, r in df.iterrows():
            item = str(r.iloc[0]).replace("\xa0", " ").rstrip(" +").strip()
            item = RENAME.get(item, item.split("  ")[0])  # drop tooltip text: "CFO/EBITDA  Share of..."
            for period, cell in zip(periods, r.iloc[1:]):
                value = _number(cell)
                if pd.notna(period) and value is not None:
                    rows.append((symbol, view, statement, item, period, value))
    return rows, profile


def build():
    snaps = sorted(SCREENER_RAW.glob("fetched=*"))
    if not snaps:
        print("  Screener: nothing saved yet")
        return
    rows, profiles = [], {}
    # Older snapshots first, so the latest page wins for each period (and periods that have
    # scrolled off screener's pages are kept from older ones).
    for snap in snaps:
        for path in sorted(snap.glob("*/*.html.gz")):
            try:
                html = gzip.decompress(path.read_bytes()).decode("utf-8")
            except (EOFError, OSError):  # a page still being written by a running download
                continue
            fetched = pd.Timestamp(path.stat().st_mtime, unit="s").normalize()
            values, profile = _parse(html, path.name[:-8], path.parent.name, fetched)
            rows += values
            if profile:
                profiles[path.name[:-8]] = profile
    out = pd.DataFrame(rows, columns=["ticker", "view", "statement", "item", "date", "value"])
    out = out.drop_duplicates(["ticker", "view", "statement", "item", "date"], keep="last")
    out = _conform(_npa_to_consolidated(out))
    write(out, FUNDAMENTALS_TABLE)
    print(f"  Fundamentals: {out['ticker'].nunique():,} companies, {out['value'].notna().sum():,} values")
    companies = pd.DataFrame.from_dict(profiles, orient="index").rename_axis("ticker").reset_index()
    write(companies.reindex(columns=["ticker", *PROFILE.values()]).sort_values("ticker"), COMPANIES_TABLE)
    print(f"  Companies: {len(companies):,} with sector and industry")


def _npa_to_consolidated(out):
    """Banks and NBFCs report Gross / Net NPA % for the lender itself, so screener fills them only on
    standalone pages. Copy them into the consolidated figures for the quarters those cover."""
    npa = out[(out["view"] == "standalone") & out["item"].isin(["Gross NPA %", "Net NPA %"])]
    quarters = out.loc[(out["view"] == "consolidated") & (out["statement"] == "quarters"), ["ticker", "date"]]
    copy = npa.merge(quarters.drop_duplicates(), on=["ticker", "date"]).assign(view="consolidated")
    # Real consolidated values, where screener has them, come last and win.
    return pd.concat([copy, out]).drop_duplicates(["ticker", "view", "statement", "item", "date"], keep="last")


def _conform(out):
    """Give every company its layout's full set of rows for every period, in the layout's order."""
    finance = set(map(tuple, out.loc[out["item"].isin(["Revenue", "Financing Profit"]), ["ticker", "view"]]
                      .drop_duplicates().values))
    out["layout"] = [("finance" if (t, v) in finance else "company") for t, v in zip(out["ticker"], out["view"])]
    schema = pd.DataFrame([(layout, statement, item, order) for layout, statements in LAYOUTS.items()
                           for statement, items in statements.items() for order, item in enumerate(items)],
                          columns=["layout", "statement", "item", "order"])
    unknown = out.merge(schema, how="left", on=["layout", "statement", "item"])
    unknown = unknown[unknown["order"].isna()].groupby(["statement", "item"])["ticker"].nunique()
    if len(unknown):
        print("  Screener: rows outside the fixed layouts (dropped; add them to LAYOUTS to keep them):")
        print(unknown.to_string())
    periods = out[["ticker", "view", "layout", "statement", "date"]].drop_duplicates()
    full = periods.merge(schema, on=["layout", "statement"])
    full = full.merge(out[["ticker", "view", "statement", "item", "date", "value"]], how="left",
                      on=["ticker", "view", "statement", "item", "date"])
    share = full["statement"].str.startswith("shareholding") & (full["item"] != "No. of Shareholders")
    full.loc[share, "value"] = full.loc[share, "value"].fillna(0.0)
    full = full.sort_values(["ticker", "view", "statement", "order", "date"])
    return full[["ticker", "view", "statement", "item", "date", "value"]].reset_index(drop=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--build", action="store_true", help="only rebuild the table from saved pages")
    args = p.parse_args()
    t = time.time()
    if not args.build:
        download()
    build()
    print(f"Done in {(time.time() - t) / 60:.1f} min")


if __name__ == "__main__":
    main()
