"""India money-market rates from FBIL (fbil.org.in), downloaded by hand as CSV from the site:
  Overnight MIBOR, Term MIBOR (14 days, 1 and 3 months), MROR (market repo), SORR (secured overnight,
  from Jul 2025), CD curve (certificates of deposit) and the T-bill curve.

    python collect.py --fbil <folder>    # copy the CSVs in <folder> into the store, then rebuild

Each imported file is kept unchanged as raw/fbil/<benchmark>/imported=<date>_<n>.csv. Files may cover
any date range and may overlap: the build merges them all, the most recently imported one winning."""
import shutil
from pathlib import Path

import pandas as pd

from config import FBIL_RAW

# The benchmark name on the file's second line -> (folder, series prefix, one series for every tenor?)
BENCHMARKS = {"overnight - mibor": ("overnight_mibor", "in_mibor_on", True),
              "mror": ("mror", "in_mror", True),
              "sorr": ("sorr", "in_sorr", True),
              "term mibor": ("term_mibor", "in_mibor", False),
              "cd curve": ("cd_curve", "in_cd", False),
              "t-bill curve": ("tbill_curve", "in_tbill", False)}
# Tenors kept from the curves.
TENORS = {"14 days": "14d", "1 month": "1m", "3 months": "3m", "6 months": "6m", "12 months": "12m"}


def _benchmark(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        f.readline()
        return f.readline().strip().strip(",").lower()


def import_folder(folder):
    stamp = f"{pd.Timestamp.today():%Y-%m-%d}"
    done, skipped = [], []
    for path in sorted(Path(folder).glob("*.csv")):
        name = _benchmark(path)
        if name not in BENCHMARKS:
            skipped.append(path.name)
            continue
        dest = FBIL_RAW / BENCHMARKS[name][0]
        dest.mkdir(parents=True, exist_ok=True)
        n = len(list(dest.glob(f"imported={stamp}_*.csv")))
        shutil.copyfile(path, dest / f"imported={stamp}_{n}.csv")
        done.append(path.name)
    print(f"  FBIL: imported {len(done)} files" + (f" (not recognised: {skipped})" if skipped else ""))
    return done


def frames():
    """Long rows (date, series, value) for every imported FBIL file."""
    out = []
    for folder, prefix, single in BENCHMARKS.values():
        for path in sorted((FBIL_RAW / folder).glob("imported=*.csv")):
            # Two title lines, then: Date, Tenor, Time, Rate, Comments (columns in varying order).
            df = pd.read_csv(path, skiprows=2)
            df.columns = [c.strip() for c in df.columns]
            rate = next(c for c in df.columns if "(%)" in c)
            tenor = df["Tenor"].astype(str).str.strip().str.lower()
            series = prefix if single else prefix + "_" + tenor.map(TENORS)
            out.append(pd.DataFrame({"date": pd.to_datetime(df["Date"].str.strip(), format="%d %b %Y"),
                                     "series": series, "value": pd.to_numeric(df[rate], errors="coerce")})
                       .dropna(subset=["series"]))
    return out
