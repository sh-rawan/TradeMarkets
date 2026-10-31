# DataVisualizer

Interactive dashboard over the shared **MarketData** store (Parquet files queried with
DuckDB), which holds market data only, and over the model outputs that
[BankPrediction](../BankPrediction) publishes to its own `output/` folder. It only reads files,
so the visualizer never depends on any project's code.

## Run (global Python 3.11)

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py          # http://localhost:8501
```

The store defaults to `C:\Users\<you>\MarketData` (set `MARKETDATA_ROOT` to change it), and the
model outputs to `../BankPrediction/output` (set `PREDICTIONS_ROOT`). In the tables below,
`features/...` means a file in that output folder.
The app re-reads a table whenever its file changes, so refreshing the browser after a new
download or model run shows the new data.

## Pages

**Data → Market data** (opens first) charts every market data table in the store (`curated/`), one
page per country (India, US, Europe & UK, Japan, China & HK, Korea/Taiwan/Brazil, commodities &
crypto): pick a table and a value, and it draws one panel per stock / series / participant, each on
its own scale. Tables that mix countries (markets and currencies, bond yields and rates, GDP) are
split by series. New tables show up automatically.

**Data → Financials** shows one company the way its screener.in page does (`curated/fundamentals`):
the company picker (each name with its verdict dot 🟢 🟡 🔴 and market cap), the verdict badge, the
headline ratios, the price with its 200-day average, the investment categorizer below, then quarterly
results, profit & loss, balance sheet, cash flows, ratios and shareholding as tables.

The verdicts and the rules behind them are explained in
[documentations/investment_categorizer.md](../documentations/investment_categorizer.md).

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
- `views/data.py`: the Market data page
- `views/financials.py`: the Financials page and the investment categorizer (`assess`)
- `views/monitor.py`: the Bank Nifty monitor
- `views/accuracy.py`: predictions vs actual
- `charts.py`: shared light/dark design tokens and Plotly helpers
- `dist.py`: Student-t forecast ranges and CRPS
- `marketdata.py`: read-only store access (paths, table catalog, DuckDB helpers, SQL views)
- `.streamlit/config.toml`: accent colour per light/dark theme
