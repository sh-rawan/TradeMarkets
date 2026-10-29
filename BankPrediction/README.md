# BankPrediction

Short-horizon (1/3/7 trading day) signals for the Bank Nifty stocks, built by stacking
existing models rather than inventing new ones. Background and sources: [docs/research.md](docs/research.md).

## What it does

Every model forecasts a **distribution**, not a price: the **mean** and **standard deviation** of
each bank's log return over the holding period. A point forecast says nothing about how much to
trust it; a mean with a std dev does, and it can be checked: if the std dev is honest, about 68%
of outcomes land within ±1 std and 95% within ±2.

| Model | Input | Mean | Std dev |
|---|---|---|---|
| `historical` | the bank's last year of daily returns | average daily return × h | daily std × √h (the **benchmark**) |
| `egarch` | ~4 years of daily returns | fitted constant mean × h | EGARCH(1,1)-t volatility forecast |
| `reversal` | 3-day return | regression of past outcomes on the 3-day reversal, fitted only on outcomes already known | the bank's recent residual std |
| `resid_reversal` | returns, Nifty, Δ US 10Y, Δ USD/INR (+ Δ India 10Y) | the same, on the bank-specific (residual) move | the same |
| `lgbm` | 53 features per bank per day (momentum, volatility, price range, volume, beta, cross-sectional ranks, Nifty / Bank Nifty / VIX / yields / FX), modelled on Qlib's Alpha158 | LightGBM regression, retrained monthly on all known outcomes | a second LightGBM model fitted to the first one's out-of-sample errors |
| `chronos` | 512 days of log price + yields, FX, VIX | change in Chronos-2's median forecast | from its 10–90% forecast range |
| `kronos` | 512 daily candles | mean over 20 sampled paths | std dev across those paths |

**Fat tails.** Bank returns have more big moves than a normal distribution allows, so every
forecast is treated as a **Student-t** distribution. Before scoring, each model is recalibrated
on its own past errors (only outcomes known by the forecast date): a width multiplier for its std
dev and a tail parameter ν (lower = fatter tails). The calibrated forecasts are published to
`MarketData/features/forecasts/` with columns `mean, std, nu`.

The **ensemble** mixes the calibrated distributions. Each model is weighted by how much it beat the
historical benchmark (lower CRPS) over its last 24 forecasts with known outcomes; a model that
didn't beat it gets no weight. The mixture's std dev includes the models' disagreement.

The backtest goes long the 3 banks with the highest mean ÷ std and short the 3 lowest through
stock futures, sizes each leg by inverse forecast std, and charges 5 bps per side.

Timing: the forecast is made after close *t*, the trade opens at close *t+1* and is held
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
  features/signals/<model>.parquet                      # raw model output: date, ticker, horizon, mean, std
  features/forecasts/<model>.parquet                    # Student-t calibrated, + ensemble: ... mean, std, nu
  features/outcomes.parquet                             # what actually happened after each signal date
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
python run.py signals --models historical,reversal,resid_reversal,egarch
python run.py signals --models chronos,kronos                 # GPU, slower
python run.py evaluate                                        # reports/evaluation.csv
python run.py today                                           # ranking for the latest close
```

Signals are cached in `MarketData/features/signals/`, so re-runs only compute new dates.

`run.py` caps its physical RAM at 6 GB (`MODEL_RAM_GB` in `config.py`). Beyond the cap,
Windows moves pages to disk, so a run slows down instead of crashing. Use
`$env:MODEL_RAM_GB=4` for a lower cap, or `0` for no cap. Chronos and Kronos each use about
1.3 GB of RAM because the models run on the GPU.

## Visualization

Charts live in the separate [DataVisualizer](../DataVisualizer) app, which reads the
MarketData store and never imports this project's code. `run.py evaluate` and `run.py today`
publish the ensemble scores, weights, evaluation and realised outcomes to `MarketData/features/` for it. The defaults in
`config.py` are evaluation from 2023-01-01 with a rebalance every 5 trading days.

## Reading the evaluation

- `crps_bps` / `crps_skill`: CRPS scores the whole distribution against the outcome (lower is
  better). `crps_skill` is the improvement over the historical benchmark; above 0 means the model adds something.
- `cover_68` / `cover_95`: share of outcomes inside the forecast's central 68% / 95% range (targets 68% / 95%).
- `nu`: median fitted tail parameter; lower means fatter tails (a normal distribution is ν = ∞).
- `mean_ic`: rank correlation of the forecast means with outcomes across banks. Above ~0.03 with `ic_t` above ~2 is worth a closer look.
- `net_bps_per_trade` / `sharpe_ann` are **after costs**.
- Holding periods overlap when *h* > `STEP`, so `ic_t` overstates significance at 7 days.

## Next steps

- TimesFM-2.5 / Moirai-2.0 as additional return signals (same interface as `signals/chronos.py`).
- FII/DII flows (jugaad-data / nsepython) and RBI liquidity features.
- Replace rank-averaging with a Qlib LightGBM meta-model (Alpha158 + these signals).
- Fine-tune Kronos on NSE banks using its Qlib pipeline.

Not financial advice.
