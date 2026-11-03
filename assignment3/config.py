"""Strategy choices fixed before calculating the backtest results."""
START = '2025-11-03'
END = '2026-10-30'
INITIAL_CASH = 40000.0
LONG_EXPIRY = '2027-01-15'  # Standard January expiry after the one-year test; chosen before computing results.
LONG_MONEYNESS = .75
SHORT_MONEYNESS = 1.03
LONG_GRID = 5.0
SHORT_GRID = 2.5
FEE = .65                 # Assumed dollars per option contract, each side.
TZ = 'America/New_York'
