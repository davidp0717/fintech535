# Assignment 2: AAPL covered call

Published page: https://davidp0717.github.io/fintech535/covered-call.html

Simple Python produces a saved book. Plain HTML, CSS, and JavaScript display it.
No server-side Python or live LSEG connection runs on GitHub Pages.

## Read in this order

1. `download.py`: fetch ten weeks of hourly stock and nearby call history from LSEG.
2. `backtest.py`: walk the history, book trades, update cash and positions, calculate margin.
3. `../covered-call.html`: the rules, charts, tables, and analysis.
4. `view.js`: display the saved `book.js` results using Plotly and ordinary DOM functions.
5. `test_backtest.py`: small artificial scenarios that check the accounting and decisions.

## Run from the repository root

Keep the LSEG Workspace desktop app open and signed in for the download.
Use the root requirements.txt to install dependencies in the local .venv.

```sh
.venv/bin/python assignment2/download.py
.venv/bin/python assignment2/backtest.py
.venv/bin/python -m unittest discover -s assignment2 -p 'test_*.py'
.venv/bin/python -m http.server 8000
```

Open http://localhost:8000/covered-call.html.
The download caches each week in `assignment2/cache`. Move this directory aside
before deliberately refreshing the fixed July 13–September 18, 2026 snapshot.
Do not load untrusted pickle files. Caches and credentials are excluded from Git.

## Strategy and accounting

Start with $40,000. Each Monday at 11:00 New York time, choose
`ceil(stock_print / 2.5) * 2.5`. This is a fixed strike grid, not the nearest strike
on a verified full chain. Request seven candidate strikes around it.
If flat, buy 100 shares. Sell one call expiring that Friday at the same hourly
bar's valid bid/ask midpoint. If either price or sufficient Reg T initial equity
is missing, skip both new legs. Existing shares remain. Skip Monday holidays.

Wait until Friday at 16:00. Above the strike, remove the call and sell the covered
shares at the strike. At or below strike, expire the call and retain the shares.
No rolling, buy-to-close, or early assignment. Missing expiry stock data stops
the calculation. No cash movement occurs outside a booked blotter event.

NAV is cash plus stock value minus short-call value. Initial margin is 50% of
stock value; maintenance is 25%; the covered call adds no margin. Available funds
and excess equity subtract those two requirements from NAV. The initial-margin
check is applied to the proposed complete position before either leg is booked.
These are the assignment's simplified account formulas.

## Data details and limitations

- LSEG hourly summaries explicitly use `summaryTimestampLabel=endPeriod`.
  UTC bars are converted to New York time and restricted to regular hours.
- Fields: BID, ASK, TRDPRC_1, ACVOL_UNS, NUM_MOVES. An available nonpositive volume
  prevents treating TRDPRC_1 as a trade in that bar. Missing volume is allowed
  when a positive trade price exists.
- Entry requires current-bar valid quotes (0 <= bid <= ask and ask > 0).
  No prior quote can fill a new order. Valuation may carry the last valid quote
  with its age disclosed; the actual run uses no carried option marks.
- Last trades and quotes within the same hourly bar can occur at different times.
  Midpoint executions are simulated, not verified real limit fills.
- Expired RIC lookup tries zero-padded days and archived/base forms. The saved
  identifier is the one that returned prices; a failed lookup is not proof that
  the contract did not exist.
- Raw and capital-change-adjusted stock closes match over the window. This is
  a split screen, not a full adjusted-option-contract audit.
- Scatter observations cover requested calls within 5% of contemporaneous spot.
  OLS includes an intercept; R² is 1 minus residual/total sum of squares.
  High R² is not an estimate of execution probability.
- Results exclude fees, slippage, dividends, financing, taxes, and early exercise.
  They are a price-and-premium model, not total investment returns.

Publish `book.js`, `view.js`, the three CSV exports, and source code along with
root `covered-call.html`, navigation, and CSS. The original assignment stays
on `index.html`. Tests use artificial fixtures only; published results use LSEG.
