"""Small, readable tests for the trading and accounting rules."""
import copy
import unittest
import pandas as pd
from backtest import simulate, validate, midpoint, regression


def week(monday, entry_spot=99, expiry_spot=101, strike=100, bid=1, ask=3):
    start = pd.Timestamp(monday + ' 11:00', tz='America/New_York')
    end = (start + pd.Timedelta(days=4)).replace(hour=16)
    stock = pd.DataFrame({'TRDPRC_1': [entry_spot, expiry_spot], 'ACVOL_UNS': [100, 100]}, index=[start, end])
    bars = pd.DataFrame({'BID': [bid, .5], 'ASK': [ask, 1], 'TRDPRC_1': [2, .7],
                         'ACVOL_UNS': [10, 10]}, index=[start, end])
    contract = {'ric': 'TEST_CALL', 'strike': strike, 'expiry': str(end.date()), 'bars': bars}
    return {'monday': monday, 'expiry': str(end.date()), 'stock': stock,
            'options': [contract], 'selected_strike': strike}


class Rules(unittest.TestCase):
    def test_assignment_books_delivery_and_finishes_flat(self):
        result = simulate([week('2026-07-13')], initial_cash=10000)
        self.assertEqual([r['side'] for r in result['blotter']], ['BUY', 'SELL', 'ASSIGN', 'SELL'])
        self.assertEqual(result['ledger'][-1]['shares'], 0)
        self.assertEqual(result['ledger'][-1]['cash'], 10300)
        self.assertEqual(result['ledger'][0]['option_mv'], -200)
        validate(result)

    def test_expired_call_keeps_shares_without_rebuying(self):
        result = simulate([week('2026-07-13', expiry_spot=98), week('2026-07-20')], 10000)
        self.assertEqual(sum(e['side'] == 'BUY' for e in result['blotter']), 1)
        self.assertEqual(result['decisions'][0]['outcome'], 'Expired')
        self.assertEqual(result['ledger'][-1]['cash'], 10500)
        validate(result)

    def test_missing_quote_skips_both_legs(self):
        result = simulate([week('2026-07-13', ask=float('nan'))], 10000)
        self.assertEqual(result['blotter'], [])
        self.assertEqual(result['ledger'][-1]['cash'], 10000)

    def test_missing_quote_does_not_sell_existing_shares(self):
        result = simulate([week('2026-07-13', expiry_spot=98), week('2026-07-20', ask=float('nan'))], 10000)
        self.assertEqual(len(result['blotter']), 3)
        self.assertEqual(result['ledger'][-1]['shares'], 100)

    def test_insufficient_margin_rejects_combo(self):
        result = simulate([week('2026-07-13')], 1000)
        self.assertEqual(result['blotter'], [])
        self.assertIn('Insufficient', result['decisions'][0]['reason'])

    def test_atm_expires_by_declared_rule(self):
        result = simulate([week('2026-07-13', expiry_spot=100)], 10000)
        self.assertEqual(result['blotter'][-1]['side'], 'EXPIRE')

    def test_crossed_quote_rejected_zero_bid_valid(self):
        self.assertIsNone(midpoint({'BID': 3, 'ASK': 2}))
        self.assertEqual(midpoint({'BID': 0, 'ASK': 2}), 1)

    def test_missing_expiry_print_stops_instead_of_inventing_exit(self):
        sample = week('2026-07-13')
        sample['stock'] = sample['stock'].iloc[:1]
        with self.assertRaises(RuntimeError):
            simulate([sample], 10000)

    def test_missing_valuation_quote_is_flagged_without_a_trade(self):
        sample = week('2026-07-13')
        middle = pd.Timestamp('2026-07-14 11:00', tz='America/New_York')
        sample['stock'].loc[middle] = [99, 100]
        sample['stock'] = sample['stock'].sort_index()
        result = simulate([sample], 10000)
        self.assertTrue(result['ledger'][1]['stale_mark'])
        self.assertEqual(result['ledger'][1]['quote_age_hours'], 24)
        self.assertFalse(any(e['time'] == middle.isoformat() for e in result['blotter']))

    def test_regression_with_intercept(self):
        fit = regression([{'mid': x, 'trade': 2*x+1} for x in [1,2,3,4]])
        self.assertAlmostEqual(fit['slope'], 2)
        self.assertAlmostEqual(fit['intercept'], 1)
        self.assertAlmostEqual(fit['r2'], 1)
        self.assertIsNone(regression([]))


if __name__ == '__main__':
    unittest.main()
