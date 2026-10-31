# Investment categorizer

Sorts every company on the Financials page into **Good to invest**, **Maybe** or **Don't invest**, shown as the badge next to its name and the dot in the company picker. The rules are in `DataVisualizer/views/financials.py` (`assess`).

Every company gets one of three verdicts from its yearly financials and price trend:

- **Don't invest**: two or more red flags.
- **Good to invest**: no red flags and at least 6 of the 8 good points.
- **Maybe**: everything else.

| Red flags | Good points |
|---|---|
| Loss in the last year | F-score 6 or more (of 8) |
| Negative net worth | Cash flow backs profits: 3-year operating cash flow / net profit ≥ 0.8 |
| Operating cash flow ≤ 0 over 3 years | P/E 30 or less (on last year's profit) |
| Debt / equity above 1.5 | Price to book 6 or less |
| Interest cover below 1.5: (profit before tax + interest) / interest | Promoter holding not falling over the last year |
| Promoters cut their stake by 5+ points in a year | Profitable in 4+ of the last 5 years |
| F-score 2 or less (of 8) | Sales growing 8%+ a year over 3 years |
| Price 20%+ below its 200-day average | Price above its 200-day average |

- **F-score**: a Piotroski-style 0-8 count of improving health from the last two years. It needs at
  least 6 of the 8 tests to be answerable. One point each:
  - profit > 0;
  - operating cash flow > 0;
  - return on assets rising;
  - cash flow above profit;
  - borrowings / assets not rising;
  - no new shares (equity capital up at most 2%);
  - operating margin not falling;
  - sales / assets not falling.
- **Financial companies**: the debt, interest and cash-flow red flags don't apply, and the cash-flow
  good point counts as met. Their balance sheets are built on borrowed or client money, so these
  tests misfire. This covers:
  - every company in screener's Financial Services sector: banks, NBFCs, insurers, brokers, AMCs,
    exchanges and holding companies;
  - every company screener shows in its bank layout (Revenue and Financing Profit).

  Before Nov 2026 only the bank layout was exempt, so insurers and brokers such as LICI,
  BAJAJFINSV and GROWW were wrongly flagged. Re-tested with the wider exemption, the results are
  unchanged: Good to invest still beats the average by ~4% a year, in 82% of half-years.
- **Missing data**: a test the data can't answer is shown as "–". It is neither a red flag nor a
  good point.

**Why these rules.** The research behind them: every 1 Jan and 1 Jul from Jul 2017 to Jul 2026, every
company that has financials was scored using only the figures known at the time. A fiscal year
counts only 92 days after it ends. Its next 6 and 12 months of returns were then measured.

- **Kept:** only measures that worked in both 2017-21 and 2022-26: cash-backed profits, cheapness,
  promoters not selling, F-score and the price trend.
- **No hard cut-offs:**
  - A market cap floor was dropped: small companies weren't worse.
  - Debt / equity 0.7 was dropped: it flagged 26% of stocks with no difference in returns. Above
    1.5, stocks blew up twice as often.
  - ROE / ROCE and growth on their own were not consistent.

How the three baskets did (equal weight, before costs):

| Basket | Share of stocks | Return a year | Worst fall | Stocks losing 40%+ in a year |
|---|---|---|---|---|
| Good to invest | ~28% | 19.5% | −40% | 5% |
| Maybe | ~51% | 14.3% | −43% | 10% |
| Don't invest | ~21% | 10.9% | −58% | 16% |
| All stocks | 100% | 15.0% | −46% | 10% |

**Robustness:**

- **Good to invest** beat the average stock in 16 of 18 half-years: +3.4% a year in 2017-21 and +4.8%
  in 2022-26.
- **Loosening or tightening** every threshold kept it ahead by 2.4% to 6.5% a year, so the result
  doesn't hang on the exact numbers.
- **Don't invest** is mainly a risk filter. These stocks fall hardest in bad markets but can still
  rally in speculative ones.

**Caveats:**

- **Survivorship:** screener only has companies listed today, so the absolute returns are flattered.
  The gaps between baskets are the reliable part.
- **Market cap history:** past market cap uses today's share count.
- **Restatements:** screener may show past figures restated.
- **The page's numbers:** the page rates on the latest figures. Its P/E uses last year's profit,
  while the ratio box shows screener's trailing P/E.
- **Not advice:** this is a screen, not investment advice.
