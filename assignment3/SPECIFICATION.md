# Frozen PMCC specification

Chosen before calculating performance on October 9, 2026. This is an in-sample
educational backtest, not a claim that the strategy was invented before July.
No parameter search or performance-based contract selection is used.

- AAPL, November 3, 2025 through October 30, 2026 (52 complete weeks).
- Every strategy starts with $40,000; one contract represents 100 shares.
- Signals use the one-minute bar ending 09:59 New York time. Orders use the
  next bar ending 10:00. Never use that day's later price or full-day close.
- Buy one January 15, 2027 call on the first Monday at 10:00. This is the standard January expiry after the full one-year window. Strike is the
  largest $5 grid strike no greater than 75% of the initial signal stock price.
  A moneyness rule is used; no estimated delta is presented as observed delta.
- Every eligible Monday, sell one Friday call at the smallest $2.50 grid strike
  at least 103% of that Monday's 09:59 stock print. Short strike must exceed the
  long strike, and its expiry must precede the long expiry. Missing Monday
  session means skip, with no Tuesday catch-up.
- Both signal and execution quotes must be valid. The latest quote at or before
  execution must be no more than 60 seconds old; log its timestamp and age. Entry relative spread must
  be no more than 20% of midpoint and the bid must be positive. No substitution
  with a different strike based on later data or availability at the exit.
- Buy back the short on its expiry day at 10:00. Also close at 10:00 on an earlier day
  if the 09:59 short is ITM with no more than $0.10 of midpoint time value, or if
  tomorrow/next business day is an announced ex-date before its expiry.
  Dividend announcements become usable the day after the reported announcement
  date, since the exact intraday announcement time is not supplied.
- Keep the long call; sell it at 10:00 on the final Friday, after covering any
  short. The backing call outlives the window, so no long roll is needed.
- Main fills: buy at ask, sell at bid, $0.65 per contract per transaction.
  Quote snapshots do not prove execution or available size. No partial fills.
- Compare against a covered call using the SAME short decisions and exit rules,
  buy-and-hold 100 shares, and the long call alone. Both stock benchmarks hold
  100 shares throughout, closing at the same terminal timestamp. Include stock
  dividends as ex-date receivables and cash on payment date. No dividend for calls.
- Show midpoint sensitivity and fills beyond bid/ask by 10% of quoted spread.
  Retain entry decisions across fill scenarios; do not re-optimize.
- Baseline assumes no unscheduled early assignment. Separately stress the first
  ITM short at a daily 09:59 observation by assignment at its strike and exercise
  of the long, then stop trading. This stylized simultaneous settlement loses
  the long's remaining time value; it does not model overnight stock borrowing,
  settlement timing, or broker liquidation. It is a scenario, not an empirical
  assignment model or worst-case bound.
- Report dollar P&L, return on equal $40,000 accounts, initial net cash deployed,
  return on that stated initial outlay, and daily 10:00 maximum drawdown.
  No annualized return or Sharpe ratio from this descriptive sample.
- Use fully paid positions with no margin loan. Capital deployed is cash outlay,
  NOT a broker margin quote. Show cash and both option values in the ledger.
- Missing entry quotes skip trades. Missing mandatory exit quotes stop the run;
  never backfill an exit from future prices. Missing valuation quotes can only
  carry a prior quote and must disclose age. Stop for a failed stock split screen.
- Cash interest, taxes, stock transaction fees, market impact, overnight
  assignment financing, and counterparty-level option exercise behavior are omitted.

## Data-quality amendment before the first completed performance run

The August 14 short call has a 09:59 quote but no 10:00 bar. A universal
maximum 60-second as-of quote rule replaces the exact-bar-only execution rule.
This is a disclosed simulated-fill assumption, not proof that an old quote
was still executable. No later quote is used; no strike or strategy parameter
was changed. Fills and valuations retain the observed quote timestamp.

## One-year extension — November 3, 2026

The sample now covers November 3, 2025–October 30, 2026 (52 complete weeks).
Existing strike, funding and execution rules were retained without optimization.
The exchange calendar handles closed Mondays, Thursday expirations when Friday
is closed, and 13:00 closes on November 28 and December 24, 2025. Request times
use America/New_York so winter and summer UTC offsets are correct. This is an
extension of an in-sample study, not an independently selected out-of-sample test.
The January 15, 2027 long expiry remains fixed and outlives the whole window.
Its strike is recomputed from the new initial signal; dividend retrieval uses
ex-date filtering to include events announced before the sample began.
