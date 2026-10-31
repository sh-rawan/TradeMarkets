"""Thin layer over the Parquet store."""
from pathlib import Path


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
        raise FileNotFoundError(f"No raw snapshots under {source_dir}. Run: python collect.py")
    return snaps[-1]
