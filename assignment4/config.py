"""Fixed Wheel choices. No parameter search is used."""
START = '2026-05-04'
END = '2026-10-30'
SYMBOL = 'AAPL.O'
TZ = 'America/New_York'
INITIAL_CASH = 40000.0
PUT_MONEYNESS = 0.99
CALL_MONEYNESS = 1.01
STRIKE_GRID = 2.5
OPTION_FEE = 0.65
ASSIGNMENT_FEE = 0.0
MAX_ENTRY_SPREAD = 0.20
MAX_QUOTE_AGE_SECONDS = 60
# Cash earns zero in both accounts; Sharpe uses the same zero reference rate.
CASH_RATE = 0.0
HOLIDAYS = {'2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07'}
OBSERVATIONS = ['09:59', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '15:59', '16:00']
