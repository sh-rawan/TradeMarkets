"""Read-only access to the shared MarketData store (Parquet files queried with DuckDB), and to
BankPrediction's published model outputs.

The store holds market data only. Model outputs (signals, forecasts, outcomes, scores) live in
BankPrediction/output. This app only reads files, so it never depends on any project's code.
Point it elsewhere with MARKETDATA_ROOT and PREDICTIONS_ROOT.
"""
import os
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq

DATA_ROOT = Path(os.environ.get("MARKETDATA_ROOT", Path.home() / "MarketData"))
CURATED = DATA_ROOT / "curated"
FEATURES = Path(os.environ.get("PREDICTIONS_ROOT", Path(__file__).resolve().parent.parent / "BankPrediction" / "output"))

PRICES = CURATED / "prices_daily.parquet"              # date, ticker, open, high, low, close, volume
MACRO = CURATED / "macro_daily.parquet"                # date, series, value
TICKERS = CURATED / "tickers.parquet"                  # ticker, group
TAGS = CURATED / "stock_tags.parquet"                  # ticker, kind, tag (size, sector, theme...)
FUNDAMENTALS = CURATED / "fundamentals.parquet"        # ticker, view, statement, item, date, value (screener.in)
COMPANIES = CURATED / "companies.parquet"              # ticker, broad_sector, sector, broad_industry, industry
STOCKS = CURATED / "stocks_daily.parquet"              # date, ticker, series, open...close, adj_close, volume (NSE)
SIGNALS_DIR = FEATURES / "signals"                     # <model>.parquet: raw model output: date, ticker, horizon, mean, std
FORECASTS_DIR = FEATURES / "forecasts"                 # <model>.parquet: calibrated Student-t: date, ticker, horizon, mean, std, nu
ENSEMBLE = FORECASTS_DIR / "ensemble.parquet"          # the combined forecast, same columns
ENSEMBLE_WEIGHTS = FEATURES / "ensemble_weights.parquet"  # date, model, horizon, weight
EVALUATION = FEATURES / "evaluation.parquet"           # horizon, model, metrics...
OUTCOMES = FEATURES / "outcomes.parquet"               # date, ticker, horizon, entry/exit dates, actual returns
YAHOO_DAILY = DATA_ROOT / "raw" / "yahoo" / "daily"


def table(path):
    return f"read_parquet('{Path(path).as_posix()}')"


def sql(query):
    return duckdb.sql(query).df()


def mtime(path):
    """Cache key that changes whenever a table is rewritten."""
    path = Path(path)
    return path.stat().st_mtime if path.exists() else 0


def latest_snapshot():
    snaps = sorted(YAHOO_DAILY.glob("fetched=*"))
    return snaps[-1].name if snaps else "none"


def connect():
    """DuckDB connection with every store table registered as a view, for ad-hoc SQL."""
    con = duckdb.connect()
    views = {"prices": PRICES, "macro": MACRO, "tickers": TICKERS, "ensemble": ENSEMBLE,
             "ensemble_weights": ENSEMBLE_WEIGHTS, "evaluation": EVALUATION}
    for name, path in views.items():
        if path.exists():
            con.execute(f"create view {name} as select * from {table(path)}")
    if any(SIGNALS_DIR.glob("*.parquet")):
        con.execute("create view signals as select regexp_extract(filename, '([^/\\\\]+)\\.parquet$', 1) as model, "
                    f"* exclude (filename) from read_parquet('{SIGNALS_DIR.as_posix()}/*.parquet', filename=true)")
    return con


def views_available(con):
    return con.sql("select view_name from duckdb_views() where not internal").df()["view_name"].tolist()


def load_parquet(path):
    return pd.read_parquet(path) if Path(path).exists() else None


def files():
    """Every Parquet file in the store, with its modification time (a cache key for catalog())."""
    return tuple((p.relative_to(DATA_ROOT).as_posix(), p.stat().st_mtime)
                 for p in sorted(DATA_ROOT.rglob("*.parquet")))


def catalog():
    """One row per store table: where it lives, its size, and the dates it covers."""
    rows = []
    for rel, mtime in files():
        path = DATA_ROOT / rel
        meta = pq.ParquetFile(path).metadata
        cols = meta.schema.names
        first = last = None
        if "date" in cols:
            first, last = duckdb.sql(f"select min(date), max(date) from {table(path)}").fetchall()[0]
        rows.append({"table": rel.removesuffix(".parquet"), "layer": rel.split("/")[0],
                     "rows": meta.num_rows, "columns": len(cols), "size_kb": path.stat().st_size / 1024,
                     "first_date": first, "last_date": last,
                     "updated": pd.Timestamp.fromtimestamp(mtime)})
    return pd.DataFrame(rows)
