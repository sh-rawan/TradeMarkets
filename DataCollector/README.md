# DataCollector

Downloads Indian market data into the shared **MarketData** store
(`C:\Users\<you>\MarketData`, Parquet files queried with DuckDB). It is the only thing that
writes market data; [BankPrediction](../BankPrediction) and [DataVisualizer](../DataVisualizer)
only read it. The store holds market data only.

## Run (global Python 3.11)

```powershell
python -m pip install -r requirements.txt
python collect.py              # fetch everything new, then rebuild the curated tables
python collect.py --rebuild    # rebuild the curated tables from raw, no downloads
python screener.py             # company fundamentals from screener.in (~3 hours; resumes; monthly is enough)
```

The first run downloads the full history since 2016 (about 30 minutes, ~3 GB). Later runs
fetch only the missing days. Set `MARKETDATA_ROOT` to use another folder.

## What it collects

| Source | What | From |
|---|---|---|
| NSE archive | every stock and ETF traded on the main board, every day | 2016 |
| NSE archive | every NSE index (Nifty 50, sectors, themes, size, strategy...) with P/E, P/B, yield | 2016 |
| NSE archive | every futures and options contract, every day | 2016 |
| NSE archive | open interest and volume by participant (FII / DII / Pro / Client) | 2016 |
| NSE | cash-market FII / DII flows (only the latest day is published) | when collection started |
| NSE lists | index members, industries, ETF list (for the tags) | today's lists |
| Yahoo | the 12 Bank Nifty banks (adjusted), Nifty, Bank Nifty, India VIX | 2015 |
| Yahoo | US: S&P 500, Nasdaq, VIX, 3-month and 10-year yields, dollar index | 2015 |
| Yahoo | China (Hang Seng, Shanghai, USD/CNY), Japan (Nikkei, USD/JPY), Europe (DAX, FTSE 100, EUR/INR), Korea, Taiwan, Brazil, emerging-markets ETF (EEM), USD/INR | 2015 |
| Yahoo | Brent crude, natural gas, copper, gold; Bitcoin (every day, from 2017) | 2015 |
| Yahoo | credit stress: high-yield (HYG) and investment-grade (LQD) bond ETFs vs Treasuries (IEF) | 2015 |
| US Treasury, New York Fed | US yield curve (3-month to 30-year), real 5- and 10-year yields, SOFR, Fed funds | 2015 (SOFR 2018) |
| Japan Ministry of Finance | JGB yields: 1, 2, 5, 10, 30 years | 2015 |
| ECB | euro-area AAA government yields (2, 10 years, close to German Bunds), €STR | 2015 (€STR 2019) |
| Bank of England | UK 10-year gilt, SONIA, Bank Rate | 2015 |

NSE's public daily archive starts in January 2016. True OIS swap curves are not free; each
country's bill and 2-year yields track them closely and stand in for them. FRED (credit spreads)
is not reachable from this machine, hence the bond ETFs. India's money-market rates come from
FBIL CSVs downloaded by hand from fbil.org.in (Overnight and Term MIBOR, MROR, SORR, CD and T-bill
curves): `python collect.py --rebuild --fbil <folder>` copies them into `raw/fbil/` and rebuilds.
Overlapping date ranges are fine; the latest import wins.

## Store layout

```
MarketData/
  raw/                                    exactly as downloaded, never modified
    nse/cm_bhavcopy/<date>.parquet        every security in the cash market
    nse/fo_bhavcopy/<date>.parquet        every futures and options contract
    nse/index_close/<date>.csv            every index
    nse/participant_oi|vol/<date>.csv     positions and trading by participant
    nse/fiidii_cash/<date>.json           cash-market FII / DII
    nse/lists/fetched=<date>/*.csv        index members, equity and ETF lists
    yahoo/splits/fetched=<date>/          split and bonus dates for listed stocks
    yahoo/daily/fetched=<date>/*.parquet  a full Yahoo pull per run
    rates/fetched=<date>/*                the full history from each rates source, per run
    gdp/fetched=<date>/*                  GDP from the OECD (quarterly) and IMF (yearly), per run
  curated/                                clean tables, rebuilt from raw
    stocks_daily     date, ticker, series, open, high, low, close, adj_close, volume, value, trades
    etfs_daily       the same, for ETFs
    indices_daily    date, index, open, high, low, close, volume, turnover_cr, pe, pb, div_yield
    futures_daily    date, ticker, underlying, expiry, close, settle, oi, volume (every contract)
    options_daily    date, ticker, underlying, futures and options OI and volume, ATM implied vol
    stock_tags       ticker, kind, tag
    participant_oi, participant_vol, fiidii_cash
    prices_daily, macro_daily, tickers    (Yahoo: Bank Nifty banks and global series)
    rates_daily      date, series, value: bond yields and overnight rates in percent
    fundamentals     ticker, view, statement, item, date, value: results, balance sheet, cash flow,
                     ratios and shareholding from screener.in (Rs crore; date = period end, not announcement)
    gdp              date, series, value: real GDP growth by quarter (OECD) and GDP growth, size and per
                     person by year (IMF), for India, US, euro area, Germany, France, UK, Japan, China,
                     Hong Kong, Korea, Taiwan, Brazil (date = period end; see gdp.py)
```

**Prices** in `stocks_daily` and `etfs_daily` are as traded. `adj_close` corrects them for
splits and bonus issues: the event dates come from Yahoo, and each event's size is read from NSE's
own prices (the ex-date open against the previous close, rounded to a standard ratio), because
Yahoo sometimes understates combined events. For delisted stocks Yahoo doesn't know, a clean
split-sized overnight drop counts as an event. Ordinary dividends are not adjusted. Delisted
companies stay in the history, so backtests have no survivorship bias.

Every calendar day is tried once, so special sessions (Saturday budget days, Diwali Muhurat
trading) are included; days with nothing published are remembered in
`raw/nse/no_session_days.txt` and not retried.

**Tags** (`stock_tags`, from today's NSE lists, so they describe each company as it is now):

| kind | tags |
|---|---|
| size | Large cap (Nifty 100), Mid cap (Midcap 150), Small cap (Smallcap 250), Micro cap (Microcap 250), Below micro cap |
| sector | NSE's industry for the 750 largest companies (Financial Services, Information Technology, Construction...) |
| theme | Banks, PSU banks, Private banks, IT, Pharma, Auto, FMCG, Metals, Realty, Energy, Infrastructure, Defence, Digital, Manufacturing, PSU, MNC, Consumption... |
| market | F&O stock |
| etf / etf_index | what an ETF holds (Equity, Commodity, Debt...) and the index it tracks |

A stock can have many tags, e.g. RELIANCE: Large cap, Oil Gas & Consumable Fuels, Energy,
Infrastructure, F&O stock.
