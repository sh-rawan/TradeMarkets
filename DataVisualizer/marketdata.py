"""Read-only access to the shared MarketData store (Parquet files queried with DuckDB).

Projects such as BankPrediction write into the store; this app only reads it, so it never
depends on any project's code. Point it at another store with MARKETDATA_ROOT.
"""
import os
from pathlib import Path

import duckdb
import pandas as pd

DATA_ROOT = Path(os.environ.get("MARKETDATA_ROOT", Path.home() / "MarketData"))
CURATED = DATA_ROOT / "curated"
FEATURES = DATA_ROOT / "features"

PRICES = CURATED / "prices_daily.parquet"              # date, ticker, open, high, low, close, volume
MACRO = CURATED / "macro_daily.parquet"                # date, series, value
TICKERS = CURATED / "tickers.parquet"                  # ticker, group
SIGNALS_DIR = FEATURES / "signals"                     # <model>.parquet: date, ticker, horizon, value
ENSEMBLE = FEATURES / "ensemble.parquet"               # date, ticker, horizon, score
ENSEMBLE_WEIGHTS = FEATURES / "ensemble_weights.parquet"  # date, model, horizon, weight
EVALUATION = FEATURES / "evaluation.parquet"           # horizon, model, metrics...
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
