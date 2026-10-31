"""Government bond yields and overnight rates, from each country's official free source:
  US       Treasury nominal and real (inflation-protected) yield curves; SOFR and the effective
           Fed funds rate from the New York Fed
  Japan    the JGB yield curve from the Ministry of Finance (1 to 40 years)
  Euro     AAA euro-area government curve (close to German Bunds) and €STR, from the ECB
  UK       10-year gilt, SONIA and Bank Rate, from the Bank of England
  India    MIBOR, repo, CD and T-bill rates from FBIL, imported by hand (see fbil.py)

Each run saves the full history as a raw snapshot (raw/rates/fetched=<date>/<name>.csv, a few MB),
then rebuilds curated/rates_daily (date, series, value, in percent)."""
import io

import pandas as pd
import requests

import fbil
from config import RATES_RAW, RATES_START, RATES_TABLE
from store import latest_snapshot, write

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36"}
TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
            "{year}/all?type={kind}&field_tdr_date_value={year}&page&_format=csv")
NYFED = "https://markets.newyorkfed.org/api/rates/{path}/search.json?startDate={start}&endDate={end}"
MOF = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"
ECB = "https://data-api.ecb.europa.eu/service/data/{key}?format=csvdata&startPeriod={start}"
BOE = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom={start}"
       "&Dateto=now&SeriesCodes={codes}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")

# Curated series: name -> (raw file, column in it).
US_NOMINAL = {"us_3m": "3 Mo", "us_1y": "1 Yr", "us_2y": "2 Yr", "us_5y": "5 Yr", "us_10y": "10 Yr", "us_30y": "30 Yr"}
US_REAL = {"us_real_5y": "5 YR", "us_real_10y": "10 YR"}
JAPAN = {"jp_1y": "1Y", "jp_2y": "2Y", "jp_5y": "5Y", "jp_10y": "10Y", "jp_30y": "30Y"}
ECB_KEYS = {"eu_2y": "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y", "eu_10y": "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y",
            "estr": "EST/B.EU000A2X2A25.WT"}
BOE_CODES = {"uk_10y": "IUDSNPY", "sonia": "IUDSOIA", "uk_bank_rate": "IUDBEDR"}


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=90)
    r.raise_for_status()
    return r.content


def download():
    snap = RATES_RAW / f"fetched={pd.Timestamp.today():%Y-%m-%d}"
    snap.mkdir(parents=True, exist_ok=True)
    start, today = pd.Timestamp(RATES_START), pd.Timestamp.today()
    years = range(start.year, today.year + 1)
    jobs = {f"us_{k}_{y}": TREASURY.format(year=y, kind=f"daily_treasury_{k}_curve")
            for k in ["yield", "real_yield"] for y in years}
    jobs |= {name: NYFED.format(path=path, start=f"{max(start, pd.Timestamp('2018-04-02')):%Y-%m-%d}", end=f"{today:%Y-%m-%d}")
             for name, path in {"sofr": "secured/sofr", "effr": "unsecured/effr"}.items()}
    jobs |= {"jgb_history": MOF + "historical/jgbcme_all.csv", "jgb_month": MOF + "jgbcme.csv"}
    jobs |= {name: ECB.format(key=key, start=f"{start:%Y-%m-%d}") for name, key in ECB_KEYS.items()}
    jobs["boe"] = BOE.format(start=f"{start:%d/%b/%Y}", codes=",".join(BOE_CODES.values()))
    failed = []
    for name, url in jobs.items():
        try:
            body = _get(url)
        except Exception:  # noqa: BLE001
            failed.append(name)
            continue
        (snap / f"{name}.{'json' if name in ('sofr', 'effr') else 'csv'}").write_bytes(body)
    print(f"  Rates: {len(jobs) - len(failed)} of {len(jobs)} files" + (f" (failed: {failed})" if failed else ""))


def _long(df, date_col, columns, fmt=None):
    """Wide table -> long rows for the chosen columns."""
    out = []
    for name, col in columns.items():
        if col in df:
            out.append(pd.DataFrame({"date": pd.to_datetime(df[date_col], format=fmt), "series": name,
                                     "value": pd.to_numeric(df[col], errors="coerce")}))
    return out


def build_curated():
    snap = latest_snapshot(RATES_RAW)
    frames = []
    for kind, cols in [("yield", US_NOMINAL), ("real_yield", US_REAL)]:
        for path in sorted(snap.glob(f"us_{kind}_*.csv")):
            frames += _long(pd.read_csv(path), "Date", cols, "%m/%d/%Y")
    for name in ["sofr", "effr"]:
        path = snap / f"{name}.json"
        if path.exists():
            rows = pd.read_json(path)["refRates"].tolist()
            frames.append(pd.DataFrame({"date": pd.to_datetime([r["effectiveDate"] for r in rows]), "series": name,
                                        "value": [r["percentRate"] for r in rows]}))
    for name in ["jgb_history", "jgb_month"]:
        path = snap / f"{name}.csv"
        if path.exists():
            # A title line, then the header; "-" marks a missing value.
            df = pd.read_csv(path, skiprows=1, na_values=["-"], encoding_errors="replace")
            frames += _long(df[df["Date"].str.match(r"^\d{4}/", na=False)], "Date", JAPAN, "%Y/%m/%d")
    for name in ECB_KEYS:
        path = snap / f"{name}.csv"
        if path.exists():
            df = pd.read_csv(path)
            frames.append(pd.DataFrame({"date": pd.to_datetime(df["TIME_PERIOD"]), "series": name,
                                        "value": pd.to_numeric(df["OBS_VALUE"], errors="coerce")}))
    path = snap / "boe.csv"
    if path.exists():
        frames += _long(pd.read_csv(path), "DATE", {k: v for k, v in BOE_CODES.items()}, "%d %b %Y")
    frames += fbil.frames()
    out = pd.concat(frames, ignore_index=True).dropna(subset=["value"])
    out = out[out["date"] >= pd.Timestamp(RATES_START)].drop_duplicates(["date", "series"], keep="last")
    write(out.sort_values(["series", "date"]), RATES_TABLE)
    print(f"  Rates: {out['series'].nunique()} series")
