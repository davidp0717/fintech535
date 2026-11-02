# Wheel specification

Fixed on November 1, 2026 before calculating results. Educational historical
simulation, not a claim that the rules were chosen before May. No optimization.

## Rules

- AAPL, May 4–October 30, 2026; 26 complete weeks; $40,000 starting cash.
- At most one standard option (100 shares), and either zero or 100 shares.
- Monday 09:59 New York stock print selects the contract. Order at 10:00.
  Flat: put strike = floor(0.99 * spot / 2.5) * 2.5. With shares:
  call strike = ceil(1.01 * spot / 2.5) * 2.5. A call can be below the stock's
  acquisition cost; losses are not hidden by refusing to sell below cost.
- Expiry is the last exchange session of the same week. Closed Fridays June 19
  and July 3 shift expiry to Thursday. Closed Mondays May 25 and September 7
  skip that week's entry. No Tuesday catch-up.
- Hold to expiry; no discretionary closes, stop losses or rolls. A missing or
  ineligible chosen contract skips the entry, with the reason recorded.
- Valid signal and execution bid/ask required; positive bid; relative spread
  <=20%; execution quote age <=60 seconds; no future quote or interpolation.
- Before a put sale cash must cover strike*100 plus the entry fee, without
  relying on the new premium. Reserve strike*100 while the put remains open.
  Covered calls require 100 shares. Reserved cash remains an asset.
- Main sale at bid; buy at ask if needed for a modeled close; $0.65 per option
  transaction, $0 stock and assignment fee. Sensitivities: midpoint, and an
  additional 10% of spread worse than bid/ask. Compare identical decisions;
  flag if funding differences change eligibility. Not a guarantee of fills.
- Expiry: use that session's raw daily stock closing print. At least $0.01 ITM
  means modeled assignment; otherwise expire. Put assignment buys 100 shares at
  strike; call assignment sells 100 at strike. Remove the option simultaneously.
  Log the option event and linked stock event with atomic before/after states.
  Effective book time 16:01 is a modeling convention, not an actual notice or
  settlement timestamp. No contrary exercise or after-hours pin-risk model.
- Main case has no early assignment. Separate sensitivity assigns a short
  before expiry at 10:00 when prior 09:59 intrinsic value >0 and midpoint time
  value <=$0.10. It then waits until the next Monday to resume the wheel.
  This tests a rule, not an estimated assignment probability or worst case.
- Retain end positions and mark at the common final close; no invented
  after-close liquidation. Report marked P&L and estimated liquidation NAV.
- Benchmarks: buy 100 AAPL at the first 10:00 ask and hold; and a conventional
  covered-call cycle which buys 100 shares when flat on an eligible Monday and
  writes the same call rule. Both use $40,000 and identical pricing/fee rules.
- Dividend entitlement uses shares held before ex-date; accrue a receivable at
  09:30, pay cash on payment date. Cash interest is zero for every account.

## Marks and performance

- Scheduled ledger: 10:00 and hourly through 16:00, plus every event. Portfolio
  viewer applies the last event at or before the requested timestamp, with
  before/after event selection. Quote timestamps are always shown separately.
- Marks use latest valid bid/ask at or before observation, explicitly flagging
  stale quotes. Stock at 16:00 uses its raw daily close. Option at expiry uses
  intrinsic value immediately before the modeled 16:01 assignment/expiration.
  No valid prior mark means stop, not a fabricated value.
- NAV = cash + stock MV - short option liability + dividend receivable.
  Free cash = cash - put collateral. Validate cash, coverage and NAV at every
  event and ledger observation. Quote and configuration hashes accompany output.
- Daily returns use post-expiry closing account values and initial $40,000.
  Report total return, dollar P&L, maximum daily drawdown, annualized daily
  volatility (sqrt(252)), and sample Sharpe (mean/std * sqrt(252), zero cash
  reference rate). Half-year estimates are descriptive, not forward forecasts.
- Thesis: premium may improve Sharpe and reduce volatility relative to 100
  shares plus idle cash, at a cost of missed upside. Test against actual results;
  lower exposure is not evidence of alpha. Show option, stock and dividend P&L,
  assignment/cycle counts, time in shares and cash utilization.

## Data and limits

Historical LSEG Workspace data, one-minute end-labeled bars. RIC aliases chosen
from signal-time availability only; not later coverage. Preserve candidate
quotes and skip reasons. Missing entry means skip; missing expiry stock close
stops the run. Screen raw versus CCH stock closes for splits; stop on differences.
One-minute bars do not establish available size or exact quote-change timing.
No market impact, taxes, stock fees, cash interest, financing or settlement-delay
model. Data access failures must not be disguised as economic no-trade decisions.

Sources: https://www.schwab.com/learn/story/three-things-to-know-about-wheel-strategy
https://www.optionseducation.org/referencelibrary/faq/options-assignment
https://www.nyse.com/trade/hours-calendars
