"""Thin layer over the Parquet store. DuckDB reads the files directly, so a table path can
be used anywhere a table name would go: sql(f"select * from {table(PRICES_TABLE)}")."""
from pathlib import Path

import duckdb
import pandas as pd


def table(path):
    """SQL expression for a Parquet file or glob."""
    return f"read_parquet('{Path(path).as_posix()}')"


def sql(query):
    return duckdb.sql(query).df()


def write(df, path):
    """Write atomically, so an interrupted run never leaves a half-written table."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def latest_snapshot(source_dir):
    """Most recent fetched=YYYY-MM-DD folder under a raw source directory."""
    snaps = sorted(Path(source_dir).glob("fetched=*"))
    if not snaps:
        raise FileNotFoundError(f"No raw snapshots under {source_dir}. Run: python run.py data")
    return snaps[-1]
