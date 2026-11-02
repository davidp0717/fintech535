# Assignment 4: Wheel Strategy

[Published page](https://davidp0717.github.io/fintech535/wheel.html)

AAPL, May 4–October 30, 2026. Sell a fully cash-secured weekly put; after
assignment sell covered calls against 100 shares; after call assignment return
to puts. Monday 09:59 New York signals, 10:00 orders. The frozen rules are in
[SPECIFICATION.md](SPECIFICATION.md). The rules were selected before calculating
performance on November 1, not before the historical sample began.

## Read the code in this order

1. `config.py`: dates, capital, strike rules, fees and quote limits.
2. `download.py`: fetch LSEG stock/option history, confirm RIC aliases using
   signal-time quotes, and export plain CSV/JSON inputs.
3. `backtest.py`: walk forward, transact, mark positions, reconcile the ledger,
   calculate metrics, and save `book.json` and Wheel CSVs.
4. `test_backtest.py`: synthetic accounting, assignment, coverage, dividend,
   missing-data and no-look-ahead checks.
5. `../wheel.html` and `view.js`: display saved results and the portfolio viewer.

## Offline reproduction

From the repository root:

```sh
python3 -m pip install -r requirements.txt
python3 assignment4/backtest.py
python3 -m unittest discover -s assignment4 -p 'test_*.py'
python3 -m http.server 8000
```

Open `http://localhost:8000/wheel.html`. No Workspace login is needed to rerun
the published inputs. The page is static HTML/CSS/JavaScript with Plotly; no
Node build or server-side strategy is required by GitHub Pages.

To refresh prices, sign in to LSEG Workspace, then run
`python3 assignment4/download.py` followed by `python3 assignment4/backtest.py`.
The downloader resumes from local `cache/` pickle files. To fetch all prices
again, move that directory aside first. Pickles, credentials and the Python
environment are never published. Do not load untrusted pickle files.

## Data and accounting

`quotes.csv` contains the retained one-minute observations used for signals,
fills and hourly marks. `inputs.json` contains selected contracts, raw daily
stock closes and dividend events. `dividends.csv` makes the events separately
readable. `data_manifest.json` documents the request window and completion time.
`book.json` includes source/rule SHA-256 hashes, every account's blotter/ledger,
summary statistics, decisions and quote diagnostics.

The expired RIC suffix uses the calendar month A–L for both puts and calls.
For example, `AAPLQ082627250.U^E26` is the May 8 $272.50 put. Alias checks never
choose a contract based on its later return or coverage. May and August dividends
are requested by ex-date (`DateType=ED`), avoiding an announcement-date filter
that would omit the April-announced May dividend.

Each assignment has an option-removal row and a stock-transfer row sharing an
event number. The ledger records atomic before/after states, so an intermediate
cash row is not an independently tradable portfolio. Put collateral stays in
cash and NAV. Dividend entitlement becomes a receivable on ex-date and cash on
payment date. Final shares remain marked, without a fictional liquidation.

The portfolio viewer selects the latest saved state at or before any requested
time in the window. Positions and cash are complete between events; valuations
remain at the displayed observation and quote times. The recorded-state selector
can inspect separate transactions sharing the same timestamp.

## Execution and interpretation

Main fills are option bid sales and ask purchases with a $0.65 option fee.
Valid prior and execution quotes, positive bid, spread/midpoint <=20% and quote
age <=60 seconds are required. Quotes do not prove executable size. Midpoint and
an additional adverse 10% of spread rerun the same entries. The scatter uses
valid quote/trade observations with positive reported volume; a high R-squared
does not establish simultaneous trades or guaranteed midpoint fills.

The base model assigns at expiry when at least $0.01 ITM at the closing print.
The separate early-assignment case uses a prior-time-value threshold; it is a
timing sensitivity, not a probability model. No rolls, contrary exercise,
after-hours pin risk, settlement delay, borrowing, taxes or cash interest.

Daily closing returns drive drawdown, volatility and Sharpe. Sharpe uses a zero
reference rate and sqrt(252) annualization; idle cash also earns zero in every
account. Equal initial cash does not mean equal market exposure. Option cash
receipts and stock P&L at assignment strikes are presented together, because put
assignment losses must not disappear behind a premium-income statistic.

The Wheel returned 4.38%, compared with 17.43% for buy and hold and 14.83% for the
matched covered call. It had lower volatility and drawdown, but a lower Sharpe.
The thesis of improved Sharpe is not supported by this six-month sample.
