# Assignment 3: Poor Man's Covered Call

Live page: https://davidp0717.github.io/fintech535/poor-mans-covered-call.html

An AAPL diagonal-call backtest using one-minute historical LSEG quote bars.
The page compares capital and performance with a covered call, 100 shares,
and the long call alone. All trade decisions and account updates use ordinary
Python functions and loops; the website is plain HTML/CSS/JavaScript and Plotly.

## Read the code in this order

1. `config.py` — the fixed dates, capital, moneyness rules, and fee assumption.
2. `SPECIFICATION.md` — the rules and the disclosed quote-age amendment.
3. `download.py` — fetch LSEG quotes and dividend information; save local caches.
4. `backtest.py` — walk forward through time, book trades, update cash and marks,
   calculate results, and export `book.json` plus audit tables.
5. `../poor-mans-covered-call.html` and `view.js` — explain and display the results.
6. `test_backtest.py` — artificial edge cases; these never supply published prices.

## Reproduce offline

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python assignment3/backtest.py
.venv/bin/python -m unittest discover -s assignment3 -p 'test_*.py'
.venv/bin/python -m http.server 8000
```

Open http://localhost:8000/poor-mans-covered-call.html.
The public `quotes.csv`, `inputs.json`, and `data_manifest.json` are sufficient
for the default backtest. Dividend inputs are also in `inputs.json` and the
human-readable `dividends.csv`. No LSEG login is needed for this rerun.
The output includes SHA-256 hashes of the quote file and configuration.

## Refresh from LSEG

Keep Workspace open and signed in, then run:

```sh
.venv/bin/python assignment3/download.py
.venv/bin/python assignment3/backtest.py --from-cache
```

Requests reuse local `assignment3/cache` files. Move the folder aside to make a
fresh download; do not load pickle files from an untrusted source. The raw
pickle cache and credentials are excluded from publication by the root .gitignore.
Refresh requests do not silently expand the fixed sample or optimize parameters.

## Strategy

The fixed sample is July 13–October 2, 2026. All strategies start with $40,000.
Buy one January 15, 2027 $240 call, then sell one weekly call at a time. The long
strike is a $5 grid at or below 75% of the initial 09:59 stock print. This is a
six-month backing call, not a claim that a multi-year LEAPS contract was used.
Short strikes are the next $2.50 grid point at or above 103% of Monday's 09:59
stock print. Orders occur at 10:00, using no later information.

Buy back each short on Friday at 10:00. An earlier daily 09:59 ITM/time-value
check or an announced ex-dividend event can trigger a 10:00 exit. Sell the long
at the fixed terminal 10:00 timestamp. Full details are in SPECIFICATION.md.

The stock covered-call benchmark uses the same short contracts and rules while
holding 100 shares. It does not reuse Assignment 2's 11:00/expiry results.
Stockholders accrue dividends on ex-date and collect cash on payment date.

## Execution and missing data

- One-minute bars are explicitly end-labeled, requested in UTC, and converted to
  America/New_York. Only 09:59 and 10:00 observations are kept.
- Quotes must be valid, with positive bid and at most 20% relative spread for entry.
- Main case: buy at ask, sell at bid, $0.65 per option contract on each transaction.
  Stock fees are assumed zero. Midpoint and 10%-of-spread adverse sensitivities
  use the same signals and contract choices.
- The August 14 short call has no 10:00 bar. A universal maximum 60-second as-of
  quote rule was added before the first completed performance run. The 09:59
  quote is used for that one simulated exit and its age is reported. This is
  an execution assumption, not evidence that the old quote remained available.
- Missing entries are skipped. Missing mandatory exits beyond that age limit
  stop the run. There is no future-price fill or interpolation.
- Marks may carry prior quotes with age disclosed. The main run has no carried
  end-of-observation marks. Bar quotes do not establish quote size or exact
  quote-change timestamps; the feed itself can retain unchanged quote values.
- A raw-versus-CCH stock comparison screens for splits, not every possible
  adjusted option contract. RIC selection uses signal-time quote availability,
  never future performance or coverage.

## Accounting and interpretation

NAV = cash + long option MV - short option MV + stock MV + dividend receivable.
Only blotter events change cash. The daily ledger follows all 10:00 events.
All positions are fully paid and cash must stay nonnegative. Capital deployed
is net cash outlay, not a broker margin requirement. Entry premiums reduce
opening debit; later short buybacks can increase the peak cash requirement.

Account return divides P&L by $40,000. Return on initial outlay divides the same
P&L by the stated net opening debit. Those denominators answer different
questions and must not be mixed. Maximum drawdown uses daily 10:00 midpoint
NAV and includes the initial $40,000 point. It is not an intraday risk maximum.
Liquidation NAV uses bid/ask marks plus assumed exit fees. Ending NAV is cash.

The baseline assumes no unscheduled early assignment. The separate stress
scenario assigns the first ITM short observed at 09:59 and exercises the long
at 10:00, then holds cash. It records the assigned option, short stock sale,
long option exercise, and covering stock purchase separately. It charges $10
per exercise/assignment and forfeits the long's remaining time value. This
stylized immediate-settlement scenario is not an empirical assignment model,
not a worst-case bound, and not proof of actual broker treatment. It excludes
settlement delays, overnight stock financing, and forced liquidation.

Other omissions: cash interest, taxes, stock transaction fees, market impact,
partial fills, and quote-size constraints. Twelve weeks of AAPL are too short
to establish persistent profitability. There is no annualized return or Sharpe
ratio and no parameter search. Rules were chosen before calculating returns
in this research session, not before the historical dates occurred.

## Sources

- LSEG Workspace: minute BID/ASK/TRDPRC_1/ACVOL_UNS and dividend event fields.
- https://www.fidelity.com/learning-center/investment-products/options/options-strategy-guide/long-diagonal-spread-calls
- https://www.optionseducation.org/referencelibrary/faq/strategies
- https://investor.apple.com/dividend-history/default.aspx

Publish the page, shared navigation/CSS, and the files in this folder except
`cache`, `__pycache__`, and `probe.py`. Saved `book.json` contains every benchmark
and sensitivity blotter and ledger; the standalone CSV outputs show main PMCC.
