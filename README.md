# FINTECH 535

- [Assignment 1: Options Data](https://davidp0717.github.io/fintech535/)
- [Assignment 2: Covered Call](https://davidp0717.github.io/fintech535/covered-call.html) — [code and instructions](assignment2/README.md)

Both assignments share the navigation tabs and GitHub Pages site.

## Assignment 1

Live app: https://davidp0717.github.io/fintech535/

This app compares closing option midpoints (`MID_PRICE`) with daily last trades
(`TRDPRC_1`) for UUUU. It shows observations and missing data; it does not fit a
volatility surface, interpolate prices, or simulate fills.

## Read the code in this order

1. `download_data.py`: connect to Workspace, generate candidate RICs, download
   stock and option history in batches, and save `option_pipeline_data.pkl`.
2. `prepare_data.py`: load that pickle, decode RICs with `parse_option_ric()`,
   create one row per contract per trading date, and export `data.json` and
   `options_long.csv`.
3. `index.html`: page content and controls.
4. `app.js`: filter the saved rows, calculate two statistics, and draw charts.
5. `style.css`: colors, spacing, and mobile layout.

The Python scripts use ordinary functions, loops, and pandas DataFrames. The
website uses plain HTML/CSS/JavaScript with Plotly, without Reflex or a build tool.
The original local `class_1.py` is an obsolete course starter, not the entry point
for this app. Do not run it for this version.

## Run locally

Keep the LSEG Workspace desktop app open and signed in while downloading.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python download_data.py
.venv/bin/python prepare_data.py
.venv/bin/python -m http.server 8000
```

Open http://localhost:8000. Use a local server, since browsers normally block
`fetch('data.json')` when an HTML file is opened directly from disk.

The downloader uses a fixed window, June 15–September 4, 2026. It reuses the
final cache if it exists and saves intermediate batches so interrupted downloads
can resume. To deliberately change the window or refresh the snapshot, move the
old final cache and `cache_batches` folder aside first. Do not load untrusted
pickle files: pickle is a Python serialization format that can execute code.

GitHub Pages publishes the repository's `main` branch, root folder. Updating
`index.html`, `style.css`, `app.js`, and the exported data updates the same URL.
Only local Python reads the pickle; the published browser app reads JSON.
Credentials, the Python environment, and raw pickle caches stay out of GitHub.

## What the data contains

- 408 synthetic candidates on a $0.50 strike grid from $10.50 through $18.50.
- Friday expirations in the download window; not every generated Friday/strike
  represents a real listed contract.
- 334 contracts with at least one returned price: 168 calls and 166 puts.
- 11,834 contract/date rows, including missing observations.
- 50 individual request errors after batch fallback. Failed and all-empty
  candidates are unconfirmed; they are not classified as nonexistent contracts.
- Capital-change-adjusted stock closes matched unadjusted closes throughout the
  window. This screens for splits but is not a full adjusted-contract audit.

The sample is not a complete options chain. Strikes outside the underlying's
window-wide high/low band, later expirations, and non-Friday expirations are
outside the requested universe. Daily records are not intraday executions.

## RIC correction

For example, `UUUUT212601200.U^H26` is a UUUU August 21, 2026 $12 put.
The main month letter distinguishes calls (A–L) from puts (M–X), but the expired
suffix uses A–L for **both** types. The supplied description's instruction to
repeat the put letter in the suffix did not return put data. We corrected this
using LSEG documentation and verified the corrected identifiers with live data.

Source: https://community.developers.lseg.com/discussion/110410/expired-option-data-no-reponse

The old starter also requested `SETTLE`; this implementation requests `MID_PRICE`
and `TRDPRC_1` instead, as required by the updated assignment.

## Statistics and missing data

The date and call/put controls filter the chart and both statistics. Both price
fields are shown together. The page has one 3D chart and no extra dashboard panels.

A historical listing roster is not available from the generated RICs. We use an
explicit **observed-listed proxy**: contracts with a returned price on or before
the selected day and an expiry on or after that day. Once first observed, a
contract stays eligible through expiry even if both prices are missing later.
This can miss listed contracts before their first observed price or contracts
with no returned data at all; the percentage is not exchange-wide coverage.

- Midpoint without trade: `100 * count(mid exists and trade missing) / eligible count`.
- Median difference: median of `abs(mid - trade)` among eligible rows with both.
- Empty denominator or no matched pairs: N/A, not zero.
- A numeric zero remains a real observation. NaN is exported as JSON null.
- No interpolation, forward fill, or replacement of missing prices with zero.

The opening date is the day with the largest number of midpoint-only calls,
chosen to make the distinction visible, not to evaluate a trading strategy.

## Interpretation

The first sentence beneath the price plot identifies the densest expiration and
the exact missing strikes at the sparsest expiration for the selected date/type. The next two
sentences explain why a fine strike grid does not justify interpolation and why
MID_PRICE is the next assignment's mark while TRDPRC_1 is trade evidence.

MID_PRICE is the closing NBBO midpoint per the assignment and may be stale.
The last-trade field is not a settlement or necessarily a closing price. A daily
record alone does not verify the precise execution time or a realistic fill.

## Historical listing check

Workspace EquityDerivativeQuotes search returned no record for the expired put
checked, and TR.FirstTradeDate returned NaT for both the $12 August 21 put and
call. These checks do not provide a historical listing roster. The displayed
percentage therefore remains a clearly labeled sample estimate; exact compliance
with a requirement for verified historical listed-series counts remains unresolved.
