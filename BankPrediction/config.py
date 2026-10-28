import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports"

# Market data store: Parquet files queried with DuckDB, kept outside OneDrive.
#   raw/       exactly what each source returned, one immutable snapshot per download
#   curated/   cleaned long-format tables built from the latest raw snapshot
#   features/  derived data (model signals)
#   manual/    hand-maintained inputs
DATA_ROOT = Path(os.environ.get("MARKETDATA_ROOT", Path.home() / "MarketData"))
RAW_DIR = DATA_ROOT / "raw"
CURATED_DIR = DATA_ROOT / "curated"
FEATURES_DIR = DATA_ROOT / "features"
PRICES_TABLE = CURATED_DIR / "prices_daily.parquet"  # date, ticker, open, high, low, close, volume
MACRO_TABLE = CURATED_DIR / "macro_daily.parquet"    # date, series, value
TICKERS_TABLE = CURATED_DIR / "tickers.parquet"      # ticker, group
SIGNALS_DIR = FEATURES_DIR / "signals"               # one file per model: date, ticker, horizon, value
# Published for DataVisualizer, which reads the store and never imports this project's code.
ENSEMBLE_TABLE = FEATURES_DIR / "ensemble.parquet"                 # date, ticker, horizon, score
ENSEMBLE_WEIGHTS_TABLE = FEATURES_DIR / "ensemble_weights.parquet"  # date, model, horizon, weight
EVALUATION_TABLE = FEATURES_DIR / "evaluation.parquet"             # horizon, model, metrics...

# Bank Nifty constituents (NSE symbols). Using today's list for history adds survivorship bias.
BANKS = [
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
    "BANKBARODA", "PNB", "CANBK", "AUBANK", "FEDERALBNK", "IDFCFIRSTB",
]
PSU_BANKS = {"SBIN", "BANKBARODA", "PNB", "CANBK"}

# Indian-session series are used as of the same day; US/FX series are lagged one day in data.py.
MACRO_TICKERS = {
    "banknifty": "^NSEBANK",
    "nifty": "^NSEI",
    "vix": "^INDIAVIX",
    "usdinr": "INR=X",
    "us10y": "^TNX",
}
US_SESSION = {"usdinr", "us10y"}
# Optional: daily India 10Y G-sec yield as CSV with columns date,yield (RBI DBIE / FBIL / investing.com).
INDIA_10Y_CSV = DATA_ROOT / "manual" / "india_10y.csv"

START = "2015-01-01"
HORIZONS = [1, 3, 7]
# Signal is computed after close t; position opens at close t+ENTRY_LAG and is held h days.
ENTRY_LAG = 1

EVAL_START = "2023-01-01"
STEP = 5             # compute signals every STEP trading days (foundation models are slow)
IC_WINDOW = 24       # rebalances of realised IC used to weight each model in the ensemble
MIN_IC_HISTORY = 5   # below this, the ensemble uses equal weights
TOP_K = 3            # banks per leg in the long/short backtest
COST_BPS_PER_SIDE = 5  # stock futures: brokerage + STT + exchange fees + slippage, per side

CONTEXT_LEN = 512
CHRONOS_MODEL = "amazon/chronos-2"
KRONOS_DIR = ROOT / "vendor" / "Kronos"
KRONOS_MODEL = "NeoQuasar/Kronos-small"
KRONOS_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
KRONOS_SAMPLES = 5

# Models that feed the ensemble. "random" is a benchmark only; "egarch" is used for sizing.
RETURN_MODELS = ["reversal", "resid_reversal", "chronos", "kronos"]
