# Short-horizon prediction for Indian bank stocks — research notes

Saved from an earlier claude.ai chat (Oct 2026) so it lives with the code.

## Core idea

Short-horizon models for Indian banks work best when they predict **volatility** and
**relative moves** (bank vs bank, banks vs Nifty), not raw direction. Banks have
identifiable drivers — rates, liquidity, RBI actions, credit quality — so models can use
real economic features, not just price history.

## What the research says

- **Direction is hard but not hopeless.** Banerjee & Mukherjee (ISI) tested MLP/LSTM/GRU
  (and bidirectional variants) on three NSE banks; trend predictions beat the 50%
  random-walk baseline. Inani et al. compared random walk, ARIMA and ANNs on Bank Nifty.
  Random walk is the benchmark: if you can't beat it net of costs, you have nothing.
- **Volatility is very predictable.** GARCH on Bank Nifty: persistence ≈ 0.996, shocks take
  ~16 days to revert, "anti-leverage" effect (vol rises more after positive shocks).
  EGARCH with Student-t errors had the lowest forecast errors. Most reliable 1–7 day model.
- **Rates and liquidity hit banks directly.** Higher yields → MTM losses on G-sec books;
  tighter liquidity → higher funding costs. PSU banks take the larger hit. Example:
  12 Oct 2026, Bank Nifty −~470 pts on RBI liquidity measures + 3-year-high 10Y yield.
  Q2 FY27 results expected to show treasury MTM losses.

## Models by horizon

| Horizon | Predict | Models | Key features |
|---|---|---|---|
| 1 day | Overnight gap, next-day direction, next-day vol | Logistic / LightGBM classifier; EGARCH-t or HAR-RV | GIFT Nifty, US 10Y & USD/INR overnight change, ADRs (HDB, IBN), prior-day FII cash/futures flows, India VIX change, intraday realised vol, close location in range |
| 3 days | Excess return vs Nifty; PSU vs private spread | Ridge / LightGBM; cointegration pairs | Δ10Y G-sec (3d), net LAF liquidity, call rate vs repo, Bank Nifty futures OI & basis, PCR, 1–3 day reversal |
| 7 days | Weekly direction; ranking across Bank Nifty stocks | LightGBM LambdaRank; Markov regime switching | 1–4 week momentum, yield trend, weekly FPI flows, event dummies (RBI policy, results, expiry), credit spread changes |

Model types worth building: volatility model (start here), rate-sensitivity factor model
(trade residual reversal), pairs / relative value (HDFCBANK–ICICIBANK, SBIN–BANKBARODA,
PSU vs private basket), event models (RBI days, results, OMO/CRR), LightGBM direction
classifier (trade only the confident tail), LSTM/GRU only after simpler models work.

## Use existing models, combine them

| Component | What it is | Role |
|---|---|---|
| **Kronos** (MIT, HF: `NeoQuasar/Kronos-small`/`-base`) | Finance foundation model for candlesticks, 12B+ records, 45 exchanges; ships Qlib fine-tune/backtest pipeline | Price-pattern signal |
| **Chronos-2** / TimesFM-2.5 / Moirai-2.0 | General time-series foundation models; Chronos-2 takes covariates | Second opinion, macro-aware |
| **Qlib** (Microsoft) + Alpha158 + LightGBM | Quant platform, 158 features, backtester | Meta-model combining everything |
| **arch** EGARCH-t | Volatility model | Position sizing, risk feature |
| FinBERT (optional) | Financial sentiment | Event signal |

Evidence on foundation models: a June 2026 benchmark ranked Moirai-2.0 and TimesFM-2.5 best
for return forecasting, but gains over random walk were small and sparse; zero-shot Chronos
and TimesFM underperformed LightGBM/CatBoost on daily returns (~51% directional accuracy).
**Use them as inputs, not as the final predictor.**

Combination plan:
1. Data: Yahoo `.NS` OHLCV, FII/DII flows (jugaad-data / nsepython), 10Y G-sec + liquidity (RBI DBIE).
2. Base signals per bank per horizon (1/3/7): Kronos return, Chronos-2 return with yield &
   USD/INR covariates, TimesFM/Moirai return, EGARCH-t vol, optional FinBERT.
3. Simple version first: **rank-average** signals across banks, weight each model by rolling
   IC. Later: Qlib LightGBM meta-model with walk-forward splits.
4. Output: rank banks, long/short strongest vs weakest, size inversely to EGARCH vol.
5. Evaluate against random walk with realistic Indian costs.

## Pitfalls

- Predict log returns/direction, never price levels (price RMSE always looks great).
- Look-ahead: FII data is post-close, RBI liquidity lags, US data closes after India.
- Costs: at 1-day horizons STT + brokerage + slippage can eat the whole edge.
- Regime shifts: bank/rate relationship differs between easing and tightening cycles.
- Foundation models give features, not alpha; 1-day is mostly noise, 3–7 days is better.

## Sources

- Short Term Stock Price Prediction in Indian Market (ISI)
- ANN vs conventional models for Bank Nifty (JGU)
- Modeling Bank Nifty volatility using GARCH
- Bank Nifty falls on RBI liquidity measures (Kotak Neo)
- Rising bond yields hit PSU banks; Q2 FY27 treasury losses
- Kronos GitHub (shiyu-coder/Kronos); Kronos (NeurIPS 2025 workshop)
- Pretrained TSFMs for Financial Return Forecasting (2026); TSFMs on global daily excess returns
- Qlib guide

Not financial advice.
