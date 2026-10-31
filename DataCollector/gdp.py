"""GDP for the countries the market pages cover, from two official free sources:
  quarterly   real GDP growth from the OECD (seasonally adjusted, chain-linked volumes):
              <c>_gdp_yoy   vs the same quarter a year earlier, %
              <c>_gdp_qoq   vs the previous quarter, %
              India, US, euro area, Germany, France, UK, Japan, China, Korea, Brazil (no Taiwan or HK)
  yearly      from the IMF World Economic Outlook, actuals only (its projections are left out):
              <c>_gdp_growth_yearly   real GDP growth, %
              <c>_gdp_usd_bn          nominal GDP, USD billion
              <c>_gdp_per_capita_usd  nominal GDP per person, USD
              the same countries plus Taiwan and Hong Kong. India's IMF years are fiscal (April-March).
Dates are period ends (a quarter's last day, 31 December for a year), not the day the figure was
published: GDP comes out ~1-2 months after the quarter ends.

Each run saves the full history as a raw snapshot (raw/gdp/fetched=<date>/), then rebuilds
curated/gdp (date, series, value)."""
import io
import json

import pandas as pd
import requests

from config import GDP_RAW, GDP_START, GDP_TABLE
from store import latest_snapshot, write

# Series prefix -> (OECD area, IMF country). None where the source doesn't cover it.
COUNTRIES = {"in": ("IND", "IND"), "us": ("USA", "USA"), "eu": ("EA", "EURO"), "de": ("DEU", "DEU"),
             "fr": ("FRA", "FRA"), "uk": ("GBR", "GBR"), "jp": ("JPN", "JPN"), "cn": ("CHN", "CHN"),
             "hk": (None, "HKG"), "kr": ("KOR", "KOR"), "tw": (None, "TWN"), "br": ("BRA", "BRA")}
OECD = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD,/"
        "Q..{areas}.S1..B1GQ......G1+GY.?startPeriod={start}&format=csv")
OECD_SERIES = {"GY": "gdp_yoy", "G1": "gdp_qoq"}
IMF = "https://www.imf.org/external/datamapper/api/v1/{indicator}/{countries}"
IMF_SERIES = {"NGDP_RPCH": "gdp_growth_yearly", "NGDPD": "gdp_usd_bn", "NGDPDPC": "gdp_per_capita_usd"}


def _get(url):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def download():
    snap = GDP_RAW / f"fetched={pd.Timestamp.today():%Y-%m-%d}"
    snap.mkdir(parents=True, exist_ok=True)
    areas = "+".join(a for a, _ in COUNTRIES.values() if a)
    imf = "/".join(c for _, c in COUNTRIES.values() if c)
    jobs = {"oecd_quarterly.csv": OECD.format(areas=areas, start=f"{pd.Timestamp(GDP_START):%Y}-Q1")}
    jobs |= {f"imf_{ind}.json": IMF.format(indicator=ind, countries=imf) for ind in IMF_SERIES}
    for name, url in jobs.items():
        try:
            (snap / name).write_bytes(_get(url))
        except requests.RequestException as e:
            print(f"  GDP: {name} failed ({type(e).__name__})")
    print(f"  GDP: saved {len(list(snap.glob('*')))} of {len(jobs)} files")


def build_curated():
    snap = latest_snapshot(GDP_RAW)
    prefix = {a: c for c, (a, _) in COUNTRIES.items() if a} | {i: c for c, (_, i) in COUNTRIES.items()}
    frames = []
    oecd = snap / "oecd_quarterly.csv"
    if oecd.exists():
        q = pd.read_csv(io.BytesIO(oecd.read_bytes()))
        q = q[q["ADJUSTMENT"] == "Y"]
        frames.append(pd.DataFrame({
            "date": pd.PeriodIndex(q["TIME_PERIOD"].str.replace("-", ""), freq="Q").end_time.normalize(),
            "series": q["REF_AREA"].map(prefix) + "_" + q["TRANSFORMATION"].map(OECD_SERIES),
            "value": q["OBS_VALUE"].values}))
    last_year = pd.Timestamp.today().year - 1  # later IMF years are projections
    for ind, name in IMF_SERIES.items():
        path = snap / f"imf_{ind}.json"
        if not path.exists():
            continue
        for country, years in json.loads(path.read_bytes())["values"][ind].items():
            if country not in prefix:  # the API answers with every country
                continue
            frames.append(pd.DataFrame([(pd.Timestamp(f"{y}-12-31"), f"{prefix[country]}_{name}", v)
                                        for y, v in years.items()
                                        if pd.Timestamp(GDP_START).year <= int(y) <= last_year],
                                       columns=["date", "series", "value"]))
    out = pd.concat(frames).dropna().sort_values(["series", "date"]).reset_index(drop=True)
    write(out, GDP_TABLE)
    print(f"  GDP: {out['series'].nunique()} series, {len(out):,} values")


if __name__ == "__main__":
    download()
    build_curated()
