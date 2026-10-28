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

## What it shows

| Tab | Charts | Reads |
|---|---|---|
| Performance | growth of 100 vs Bank Nifty, period returns, Bank Nifty monthly heatmap | `curated/prices_daily`, `curated/macro_daily` |
| Risk | EGARCH forecast vs realised volatility, return correlation, forecast vol by bank | `features/signals/egarch` |
| Rates & macro | small multiples on one time axis: Bank Nifty, PSU-minus-private spread, yields, VIX, USD/INR | `curated/macro_daily`, `curated/tickers` |
| Model signals | latest ensemble ranking, per-model signals, model weights, walk-forward evaluation | `features/ensemble*`, `features/evaluation` |
| SQL | ad-hoc DuckDB queries over every table in the store | everything |

A period filter and a bank picker (up to 3) at the top scope every chart. Each chart has a
table view, and the app follows the system light/dark setting.

## Files

- `app.py`: the Streamlit app
- `marketdata.py`: read-only store access (paths, DuckDB helpers, SQL views)
- `.streamlit/config.toml`: accent colour per light/dark theme
