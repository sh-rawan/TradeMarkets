import os
from pathlib import Path

# Market data store: Parquet files queried with DuckDB, kept outside OneDrive. Market data only.
#   raw/       exactly what each source returned, never modified (re-runs only fetch what is missing)
#   curated/   clean tables rebuilt from raw
#   manual/    hand-maintained inputs
DATA_ROOT = Path(os.environ.get("MARKETDATA_ROOT", Path.home() / "MarketData"))
RAW_DIR = DATA_ROOT / "raw"
CURATED_DIR = DATA_ROOT / "curated"
NSE_RAW = RAW_DIR / "nse"
YAHOO_DAILY = RAW_DIR / "yahoo" / "daily"
YAHOO_SPLITS = RAW_DIR / "yahoo" / "splits"
RATES_RAW = RAW_DIR / "rates"
FBIL_RAW = RAW_DIR / "fbil"
SCREENER_RAW = RAW_DIR / "screener"
GDP_RAW = RAW_DIR / "gdp"

# --- Curated tables ---------------------------------------------------------------------------
# Yahoo (split- and dividend-adjusted): the Bank Nifty banks and macro series.
PRICES_TABLE = CURATED_DIR / "prices_daily.parquet"          # date, ticker, open, high, low, close, volume
MACRO_TABLE = CURATED_DIR / "macro_daily.parquet"            # date, series, value
TICKERS_TABLE = CURATED_DIR / "tickers.parquet"              # ticker, group (the Bank Nifty banks)
# NSE, the whole market (prices as traded; adj_close corrects for splits and bonus issues).
STOCKS_TABLE = CURATED_DIR / "stocks_daily.parquet"          # date, ticker, series, open...close, adj_close, volume
ETFS_TABLE = CURATED_DIR / "etfs_daily.parquet"              # same columns, for ETFs
INDICES_TABLE = CURATED_DIR / "indices_daily.parquet"        # date, index, open...close, volume, pe, pb, div_yield
FUTURES_TABLE = CURATED_DIR / "futures_daily.parquet"        # date, ticker, expiry, close, settle, oi, volume
OPTIONS_TABLE = CURATED_DIR / "options_daily.parquet"        # date, ticker, futures/options OI, volume, ATM IV
TAGS_TABLE = CURATED_DIR / "stock_tags.parquet"              # ticker, kind (size/sector/theme/market/etf), tag
PARTICIPANT_OI_TABLE = CURATED_DIR / "participant_oi.parquet"    # date, participant, open interest by product
PARTICIPANT_VOL_TABLE = CURATED_DIR / "participant_vol.parquet"  # date, participant, traded contracts by product
FIIDII_CASH_TABLE = CURATED_DIR / "fiidii_cash.parquet"          # date, category, buy, sell, net (Rs crore)
# Government bond yields and overnight rates (US, Japan, euro area, UK), in percent.
RATES_TABLE = CURATED_DIR / "rates_daily.parquet"                # date, series, value
# Company fundamentals from screener.in: results, balance sheet, cash flow, ratios, shareholding.
FUNDAMENTALS_TABLE = CURATED_DIR / "fundamentals.parquet"        # ticker, view, statement, item, date, value
COMPANIES_TABLE = CURATED_DIR / "companies.parquet"              # ticker, broad_sector, sector, broad_industry, industry
# GDP growth (quarterly, OECD) and size (yearly, IMF) by country.
GDP_TABLE = CURATED_DIR / "gdp.parquet"                          # date, series, value

# --- What to collect --------------------------------------------------------------------------
YAHOO_START = "2015-01-01"
NSE_START = "2016-01-01"  # NSE's public daily archive starts in January 2016
RATES_START = "2015-01-01"
GDP_START = "2000-01-01"

# Bank Nifty constituents (NSE symbols), fetched adjusted from Yahoo for BankPrediction.
BANKS = [
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
    "BANKBARODA", "PNB", "CANBK", "AUBANK", "FEDERALBNK", "IDFCFIRSTB",
]
PSU_BANKS = {"SBIN", "BANKBARODA", "PNB", "CANBK"}
MACRO_TICKERS = {
    "banknifty": "^NSEBANK",
    "nifty": "^NSEI",
    "vix": "^INDIAVIX",
    "usdinr": "INR=X",
    "us10y": "^TNX",
    "us3m": "^IRX",        # 13-week T-bill: with us10y, the US curve slope
    "spx": "^GSPC",
    "usvix": "^VIX",
    "dxy": "DX-Y.NYB",
    "brent": "BZ=F",
    "gold": "GC=F",
    "btc": "BTC-USD",      # trades every day, weekends included
    # Other markets that move India: US tech, China, Japan, Europe, emerging-market peers.
    "nasdaq": "^IXIC",
    "hangseng": "^HSI",
    "shanghai": "000001.SS",
    "usdcny": "CNY=X",
    "nikkei": "^N225",
    "usdjpy": "JPY=X",
    "dax": "^GDAXI",
    "ftse": "^FTSE",
    "eurinr": "EURINR=X",
    "kospi": "^KS11",
    "taiwan": "^TWII",
    "brazil": "^BVSP",
    "em_etf": "EEM",       # iShares MSCI Emerging Markets: where foreign "EM" money goes
    "copper": "HG=F",
    "natgas": "NG=F",
    # Credit stress (FRED's spreads are not reachable): high-yield and investment-grade bond ETFs
    # against Treasuries; when HYG falls relative to IEF, credit spreads are widening.
    "hy_bonds": "HYG",
    "ig_bonds": "LQD",
    "treasuries_7_10y": "IEF",
}
# Series that start later than YAHOO_START.
MACRO_START = {"btc": "2017-01-01"}

# Main-board equity series. ETFs trade as EQ too; SME (SM/ST), bonds and other series are left out.
EQUITY_SERIES = ["EQ", "BE", "BZ"]

# NSE index member lists that become tags: size buckets, then sectors and themes.
SIZE_LISTS = {"Large cap": "nifty100", "Mid cap": "niftymidcap150", "Small cap": "niftysmallcap250",
              "Micro cap": "niftymicrocap250_"}
THEME_LISTS = {
    "Banks": "niftybank", "PSU banks": "niftypsubank", "Financial services": "niftyfinance",
    "IT": "niftyit", "Pharma": "niftypharma", "Healthcare": "niftyhealthcare", "Auto": "niftyauto",
    "FMCG": "niftyfmcg", "Metals": "niftymetal", "Realty": "niftyrealty", "Energy": "niftyenergy",
    "Oil & gas": "niftyoilgas", "Infrastructure": "niftyinfra", "Media": "niftymedia",
    "Consumer durables": "niftyconsumerdurables", "Consumption": "niftyconsumption",
    "Commodities": "niftycommodities", "PSU (government owned)": "niftypse", "Central PSU": "niftycpse",
    "MNC": "niftymnc", "Defence": "niftyindiadefence_", "Digital": "niftyindiadigital_",
    "Manufacturing": "niftyindiamanufacturing_", "Tourism": "niftyindiatourism_",
    "Housing": "niftycorehousing_", "Mobility": "niftymobility_",
}
SECTOR_LIST = "niftytotalmarket_"  # the 750 largest companies, each with NSE's industry
