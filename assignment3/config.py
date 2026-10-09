"""Strategy choices fixed before calculating the backtest results."""
START = '2026-07-13'
END = '2026-10-02'
INITIAL_CASH = 40000.0
LONG_EXPIRY = '2027-01-15'  # Next standard January expiry with at least 180 days at entry.
LONG_MONEYNESS = .75
SHORT_MONEYNESS = 1.03
LONG_GRID = 5.0
SHORT_GRID = 2.5
FEE = .65                 # Assumed dollars per option contract, each side.
TZ = 'America/New_York'
