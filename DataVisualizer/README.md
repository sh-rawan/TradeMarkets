# DataVisualizer

Interactive dashboard over the shared **MarketData** store (Parquet files queried with
DuckDB). It only reads the store. Projects such as [BankPrediction](../BankPrediction) write
to it, so the visualizer never depends on their code.

## Run (global Python 3.11)

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py          # http://localhost:8501
```

The store defaults to `C:\Users\<you>\MarketData`. Set `MARKETDATA_ROOT` to use another folder.
The app re-reads a table whenever its file changes, so refreshing the browser after a new
download or model run shows the new data.

## Pages

**Data** (opens first) shows what is in the store:

- an overview of every table, grouped into curated / features / raw, with its rows, columns, size, date range and last update
- **Open a table** to browse its rows, newest first. Filter by date range and by any column with
  few distinct values (ticker, series, model, horizon...), then download the result as CSV
- **Columns**: each column's type, min, max, distinct count and missing share
- **SQL**: ad-hoc DuckDB queries over the whole store

New tables show up automatically: the page lists every Parquet file under the store.

**Bank Nifty monitor**:

| Tab | Charts | Reads |
|---|---|---|
| Performance | growth of 100 vs Bank Nifty, period returns, Bank Nifty monthly heatmap | `curated/prices_daily`, `curated/macro_daily` |
| Risk | EGARCH forecast vs realised volatility, return correlation, forecast vol by bank | `features/signals/egarch` |
| Rates & macro | small multiples on one time axis: Bank Nifty, PSU-minus-private spread, yields, VIX, USD/INR | `curated/macro_daily`, `curated/tickers` |
| Model signals | latest ensemble ranking, per-model signals, model weights, walk-forward evaluation | `features/ensemble*`, `features/evaluation` |

A period filter and a bank picker (up to 3) at the top scope every chart. Each chart has a
table view, and the app follows the system light/dark setting.

**Predictions vs actual** checks every model's calibrated Student-t forecast
(`features/forecasts`) against what then happened (`features/outcomes`), both published by BankPrediction:

- **Scorecard** per model and horizon: skill vs the historical benchmark (CRPS) and the share of
  outcomes inside the 68% and 95% ranges.
- **One forecast date**: every bank's forecast mean and 68% / 95% ranges, with the actual return.
- **One bank over time**: the forecast range band with every actual return; misses outside the
  95% range are red.
- **Track record**: rolling coverage and rolling skill.
- **Every forecast** next to its outcome (downloadable), and all models side by side.

## Files

- `app.py`: entry point and page navigation
- `views/data.py`: the Data page
- `views/monitor.py`: the Bank Nifty monitor
- `views/accuracy.py`: predictions vs actual
- `charts.py`: shared light/dark design tokens and Plotly helpers
- `dist.py`: Student-t forecast ranges and CRPS
- `marketdata.py`: read-only store access (paths, table catalog, DuckDB helpers, SQL views)
- `.streamlit/config.toml`: accent colour per light/dark theme
