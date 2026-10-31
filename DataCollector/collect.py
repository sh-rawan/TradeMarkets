"""Collect Indian market data into the MarketData store. Re-runs only fetch what is missing.

    python collect.py              # download everything new, then rebuild the curated tables
    python collect.py --rebuild    # rebuild the curated tables from raw, no downloads
    python collect.py --rebuild --fbil <folder>    # also import FBIL CSVs downloaded by hand
"""
import argparse
import time

import fbil
import gdp
import nse
import rates
import tags
import yahoo


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rebuild", action="store_true", help="only rebuild curated tables from raw files")
    p.add_argument("--fbil", metavar="FOLDER", help="import FBIL CSVs from this folder first")
    args = p.parse_args()
    t = time.time()
    if args.fbil:
        fbil.import_folder(args.fbil)
    if not args.rebuild:
        yahoo.download()
        nse.download()
        tags.download()
        yahoo.download_splits(tags.listed_symbols())
        rates.download()
        gdp.download()
    print("Building curated tables")
    yahoo.build_curated()
    nse.build_stocks(tags.etf_symbols(), *yahoo.load_splits())
    nse.build_indices()
    nse.build_derivatives()
    nse.build_flows()
    rates.build_curated()
    gdp.build_curated()
    tags.build()
    print(f"Done in {(time.time() - t) / 60:.1f} min")


if __name__ == "__main__":
    main()
