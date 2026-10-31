import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports"

# Market data store: Parquet files queried with DuckDB, kept outside OneDrive. Market data only;
# DataCollector (../DataCollector) downloads it, this project only reads it.
#   raw/       exactly what each source returned, one immutable snapshot per download
#   curated/   cleaned long-format tables built from the latest raw snapshot
#   manual/    hand-maintained inputs
DATA_ROOT = Path(os.environ.get("MARKETDATA_ROOT", Path.home() / "MarketData"))
RAW_DIR = DATA_ROOT / "raw"
CURATED_DIR = DATA_ROOT / "curated"
# This project's own outputs (model signals, forecasts, scores) live with the project, not in the store.
FEATURES_DIR = Path(os.environ.get("BANKPREDICTION_OUTPUT", ROOT / "output"))
PRICES_TABLE = CURATED_DIR / "prices_daily.parquet"  # date, ticker, open, high, low, close, volume
MACRO_TABLE = CURATED_DIR / "macro_daily.parquet"    # date, series, value
TICKERS_TABLE = CURATED_DIR / "tickers.parquet"      # ticker, group
# NSE derivatives data: participant positioning, F&O per underlying, cash-market FII/DII.
PARTICIPANT_OI_TABLE = CURATED_DIR / "participant_oi.parquet"    # date, participant, open interest by product
PARTICIPANT_VOL_TABLE = CURATED_DIR / "participant_vol.parquet"  # date, participant, traded contracts by product
OPTIONS_TABLE = CURATED_DIR / "options_daily.parquet"            # date, ticker, futures/options OI, volume, ATM IV
FIIDII_CASH_TABLE = CURATED_DIR / "fiidii_cash.parquet"          # date, category, buy, sell, net (Rs crore)
SIGNALS_DIR = FEATURES_DIR / "signals"               # one file per model: date, ticker, horizon, mean, std
# Published for DataVisualizer, which reads these files and never imports this project's code.
# Calibrated Student-t forecasts of every model, plus the ensemble: date, ticker, horizon, mean, std, nu
FORECASTS_DIR = FEATURES_DIR / "forecasts"
ENSEMBLE_TABLE = FORECASTS_DIR / "ensemble.parquet"
ENSEMBLE_WEIGHTS_TABLE = FEATURES_DIR / "ensemble_weights.parquet"  # date, model, horizon, weight
EVALUATION_TABLE = FEATURES_DIR / "evaluation.parquet"             # horizon, model, metrics...
OUTCOMES_TABLE = FEATURES_DIR / "outcomes.parquet"  # date, ticker, horizon, entry/exit dates, actual returns

# Bank Nifty constituents (NSE symbols). Using today's list for history adds survivorship bias.
BANKS = [
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
    "BANKBARODA", "PNB", "CANBK", "AUBANK", "FEDERALBNK", "IDFCFIRSTB",
]
PSU_BANKS = {"SBIN", "BANKBARODA", "PNB", "CANBK"}

# Macro series (collected by DataCollector) from the US session close after the NSE: lagged a day in data.py.
US_SESSION = {"usdinr", "us10y", "us3m", "spx", "usvix", "dxy", "brent", "gold"}
# Optional: daily India 10Y G-sec yield as CSV with columns date,yield (RBI DBIE / FBIL / investing.com).
INDIA_10Y_CSV = DATA_ROOT / "manual" / "india_10y.csv"

HORIZONS = [1, 3, 7]
# Signal is computed after close t; position opens at close t+ENTRY_LAG and is held h days.
ENTRY_LAG = 1

EVAL_START = "2023-01-01"
STEP = 5             # compute signals every STEP trading days (foundation models are slow)
IC_WINDOW = 24       # rebalances of realised IC used to weight each model in the ensemble
MIN_IC_HISTORY = 5   # below this, the ensemble uses equal weights
TOP_K = 3            # banks per leg in the long/short backtest
COST_BPS_PER_SIDE = 5  # stock futures: brokerage + STT + exchange fees + slippage, per side

# Physical RAM cap for run.py, in GB; beyond it Windows pages to disk instead of failing.
# Override per run with the MODEL_RAM_GB environment variable (0 = no cap).
MODEL_RAM_GB = float(os.environ.get("MODEL_RAM_GB", 6))

CONTEXT_LEN = 512
CHRONOS_MODEL = "amazon/chronos-2"
KRONOS_DIR = ROOT / "vendor" / "Kronos"
KRONOS_MODEL = "NeoQuasar/Kronos-small"
KRONOS_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
KRONOS_SAMPLES = 20  # sampled paths per bank; their spread gives the std dev
KRONOS_BATCH = 60    # series per GPU batch (fits the 6 GB RTX 4050)

# LightGBM mean + variance model on the feature panel (signals/features.py).
LGBM_RETRAIN = 21    # trading days between retrains
LGBM_TRAIN_DAYS = 1400  # rolling training window in trading days (~5.5 years); older data is dropped
LGBM_FOLDS = 5       # time blocks for the out-of-sample errors the variance model learns from
LGBM_ROUNDS = 200
LGBM_PARAMS = dict(objective="regression", learning_rate=0.02, num_leaves=15, min_data_in_leaf=300,
                   feature_fraction=0.7, bagging_fraction=0.7, bagging_freq=1, lambda_l2=10.0,
                   num_threads=8, seed=0, verbose=-1)

# Every model forecasts the mean and std dev of the holding-period log return. "historical" is
# the benchmark; the ensemble weights each model by how much it beats it.
MODELS = ["historical", "egarch", "reversal", "resid_reversal", "lgbm", "chronos", "kronos"]
BENCHMARK = "historical"

# Student-t calibration: before scoring, each model's forecasts are recalibrated on its own past
# errors (only outcomes known by the forecast date): a width multiplier for its std dev and a
# tail parameter nu (lower = fatter tails; ~30+ is close to normal).
CAL_WINDOW = 600     # most recent errors used (~50 forecast dates x 12 banks)
CAL_MIN = 60         # fewer than this: no calibration (width x1, DEFAULT_NU)
DEFAULT_NU = 6.0
NU_BOUNDS = (2.5, 60.0)
