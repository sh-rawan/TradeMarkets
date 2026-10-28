# BankPrediction

Short-horizon (1/3/7 trading day) signals for the Bank Nifty stocks, built by stacking
existing models rather than inventing new ones. Background and sources: [docs/research.md](docs/research.md).

## What it does

| Signal | Source | Output |
|---|---|---|
| `reversal` | 3-day short-term reversal | baseline return signal |
| `resid_reversal` | Rolling regression on Nifty, Δ US 10Y, Δ USD/INR (+ Δ India 10Y if provided); reversal of the residual | rate-aware return signal |
| `chronos` | Amazon Chronos-2, zero-shot, yields/FX/VIX as covariates | forecast log return |
| `kronos` | Kronos-small (finance candlestick foundation model), zero-shot | forecast log return |
| `egarch` | EGARCH(1,1)-t via `arch` | forecast holding-period volatility (position sizing) |
| `random` | noise | benchmark |

The **ensemble** ranks the banks under each return model, then averages the ranks. Each
model is weighted by its rolling realised IC, using only ICs known on the signal date.
The backtest goes long the top 3 banks and short the bottom 3 through stock futures,
sizes each leg by inverse EGARCH vol, and charges 5 bps per side.

Timing: the signal is computed after close *t*, the trade opens at close *t+1* and is held
*h* days. US yields and USD/INR are lagged a day because they close after the NSE.

## Setup (Windows, global Python 3.11)

```powershell
cd BankPrediction
python -m pip install torch --index-url https://download.pytorch.org/whl/cu124
python -m pip install -r requirements.txt
git clone https://github.com/shiyu-coder/Kronos vendor/Kronos
```

## Data store

Market data lives outside the repo (and outside OneDrive) in `C:\Users\<you>\MarketData`.
To use another folder, set the `MARKETDATA_ROOT` environment variable.

```
MarketData/
  raw/yahoo/daily/fetched=YYYY-MM-DD/<symbol>.parquet   # every download, never modified
  curated/prices_daily.parquet                          # date, ticker, open, high, low, close, volume
  curated/macro_daily.parquet                           # date, series, value
  features/signals/<model>.parquet                      # date, ticker, horizon, value
  manual/india_10y.csv                                  # optional, date,yield
```

Query any of it with DuckDB:

```python
import duckdb
duckdb.sql("select ticker, max(close) from 'C:/Users/agraw/MarketData/curated/prices_daily.parquet' group by ticker").df()
```

`python run.py data` saves a new raw snapshot and rebuilds `curated/`. Each snapshot is the
full history (~3 MB), so old ones can be deleted whenever you like.

Optional: put daily India 10Y G-sec yields in `manual/india_10y.csv` (`date,yield`) from
RBI DBIE / FBIL. Yahoo has no reliable daily India 10Y series.

## Run

```powershell
python run.py data                                            # ~1 min
python run.py signals --models reversal,resid_reversal,random,egarch
python run.py signals --models chronos,kronos                 # GPU, slower
python run.py evaluate                                        # reports/evaluation.csv
python run.py today                                           # ranking for the latest close
```

Signals are cached in `MarketData/features/signals/`, so re-runs only compute new dates.

## Visualization

Charts live in the separate [DataVisualizer](../DataVisualizer) app, which reads the
MarketData store and never imports this project's code. `run.py evaluate` and `run.py today`
publish the ensemble scores, weights and evaluation to `MarketData/features/` for it. The defaults in
`config.py` are evaluation from 2023-01-01 with a rebalance every 5 trading days.

## Reading the evaluation

- `mean_ic`: average cross-sectional Spearman correlation with realised returns. Anything
  persistently above ~0.03 with `ic_t` above ~2 is worth a closer look.
- `net_bps_per_trade` / `sharpe_ann` are **after costs**. Compare every model against `random`.
- Holding periods overlap when *h* > `STEP`, so `ic_t` overstates significance at 7 days.

## Next steps

- TimesFM-2.5 / Moirai-2.0 as additional return signals (same interface as `signals/chronos.py`).
- FII/DII flows (jugaad-data / nsepython) and RBI liquidity features.
- Replace rank-averaging with a Qlib LightGBM meta-model (Alpha158 + these signals).
- Fine-tune Kronos on NSE banks using its Qlib pipeline.

Not financial advice.
