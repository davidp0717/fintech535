"""Small invented paths test the rules; none of these prices appear on the website."""
import copy
import unittest
from unittest.mock import patch
import pandas as pd
import backtest as bt


def fixture():
    index = pd.DatetimeIndex([pd.Timestamp(f'2026-07-{day} {hour}',tz=bt.TZ)
        for day in range(13,18) for hour in ['09:59','10:00']])
    stock = pd.DataFrame({'BID':99.99,'ASK':100.01,'TRDPRC_1':100.,'ACVOL_UNS':100},index=index)
    long = pd.DataFrame({'BID':30.,'ASK':32.,'TRDPRC_1':31.,'ACVOL_UNS':1},index=index)
    short = pd.DataFrame({'BID':1.,'ASK':1.1,'TRDPRC_1':1.05,'ACVOL_UNS':1},index=index)
    long.loc[index[-2:],['BID','ASK']] = [35.,37.]
    short.loc[index[-2:],['BID','ASK']] = [.1,.2]
    return [{'monday':'2026-07-13','friday':'2026-07-17','stock':stock,
        'long':{'ric':'LONG','strike':75.,'expiry':'2027-01-15','bars':long},
        'short':{'ric':'SHORT','strike':105.,'expiry':'2026-07-17','bars':short}}]


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.end = patch.object(bt,'END','2026-07-17'); self.end.start()
        self.capital = patch.object(bt,'INITIAL_CASH',20000.); self.capital.start()
        self.addCleanup(self.end.stop); self.addCleanup(self.capital.stop)

    def test_profit_and_cash_identity(self):
        r=bt.simulate(fixture(),[])
        self.assertAlmostEqual(r['summary']['pnl'],377.4)
        self.assertEqual(r['ledger'][-1]['long_calls'],0)
        self.assertEqual(r['ledger'][-1]['short_calls'],0)
        bt.validate(r)

    def test_strike_uses_prior_minute_not_execution_stock(self):
        w=fixture(); w[0]['stock'].loc[w[0]['stock'].index[1],'TRDPRC_1']=110
        r=bt.simulate(w,[])
        self.assertEqual(r['decisions'][0]['strike'],105)
        self.assertEqual(r['decisions'][0]['status'],'Entered')

    def test_future_prices_do_not_change_prior_trades(self):
        w=fixture(); original=bt.simulate(w,[])
        w[0]['long']['bars'].iloc[-2:,0:2]=[60,62]
        changed=bt.simulate(w,[])
        self.assertEqual(original['blotter'][:2],changed['blotter'][:2])
        self.assertNotEqual(original['summary']['pnl'],changed['summary']['pnl'])

    def test_missing_entry_skips_without_changing_backing_position(self):
        w=fixture(); w[0]['short']['bars']=w[0]['short']['bars'].iloc[2:]
        r=bt.simulate(w,[])
        self.assertEqual(r['summary']['entries'],0)
        self.assertEqual(r['ledger'][0]['long_calls'],1)
        self.assertEqual(len(r['blotter']),2)

    def test_one_minute_old_fill_is_disclosed(self):
        w=fixture(); w[0]['short']['bars']=w[0]['short']['bars'].iloc[:-1]
        r=bt.simulate(w,[])
        close=[e for e in r['blotter'] if e['leg']=='short_call' and e['side']=='BUY'][0]
        self.assertEqual(close['quote_age_seconds'],60)
        self.assertEqual(close['fill'],.2)

    def test_exit_never_uses_future_or_old_quote(self):
        w=fixture(); bars=w[0]['short']['bars'].iloc[:-2].copy()
        bars.loc[pd.Timestamp('2026-07-17 10:01',tz=bt.TZ)]=[.1,.2,.15,1]
        w[0]['short']['bars']=bars
        with self.assertRaisesRegex(ValueError,'Missing mandatory short exit'):
            bt.simulate(w,[])

    def test_crossed_quote_is_not_replaced_with_prior_quote(self):
        w=fixture(); bars=w[0]['short']['bars']; bars.iloc[1,0:2]=[2,1]
        self.assertIsNone(bt.quote(bars,bars.index[1]))
        self.assertEqual(bt.simulate(w,[])['summary']['entries'],0)

    def test_zero_bid_allowed_for_exit_but_not_entry(self):
        w=fixture(); bars=w[0]['short']['bars']; bars.iloc[-1,0:2]=[0,.01]
        r=bt.simulate(w,[])
        self.assertEqual(r['blotter'][-2]['fill'],.01)
        self.assertFalse(bt.entry_quote({'bid':0,'ask':.01,'mid':.005}))

    def test_dividend_receivable_is_not_double_counted(self):
        div=[{'ex_date':'2026-07-14','pay_date':'2026-07-16','announced':'2026-07-01','amount':.27}]
        r=bt.simulate(fixture(),div,kind='buy_hold')
        self.assertAlmostEqual(r['summary']['dividends'],27)
        self.assertEqual(r['ledger'][1]['dividend_receivable'],27)
        self.assertEqual(r['ledger'][3]['dividend_receivable'],0)
        self.assertAlmostEqual(r['summary']['pnl'],25)

    def test_future_announcement_cannot_trigger_exit(self):
        w=fixture(); time=pd.Timestamp('2026-07-13 10:00',tz=bt.TZ)
        d={'ex_date':'2026-07-14','pay_date':'2026-07-16','announced':'2026-07-13','amount':.27}
        self.assertEqual(bt.early_exit_reason(time,100,w[0]['short'],{'mid':1},[d]),'')
        d['announced']='2026-07-12'
        self.assertIn('ex-dividend',bt.early_exit_reason(time,100,w[0]['short'],{'mid':1},[d]))

    def test_assignment_stress_closes_both_options_and_stock(self):
        w=fixture(); w[0]['stock'].iloc[2,2]=106
        r=bt.simulate(w,[],stress=True)
        self.assertIsNotNone(r['stress'])
        self.assertEqual([e['side'] for e in r['blotter']][-4:],['ASSIGN','SELL','EXERCISE','BUY'])
        self.assertEqual(r['ledger'][-1]['shares'],0)
        self.assertEqual(r['ledger'][-1]['long_calls'],0)
        self.assertAlmostEqual(r['summary']['pnl'],-121.3)

    def test_early_itm_close_uses_signal(self):
        w=fixture(); w[0]['stock'].iloc[2,2]=106
        w[0]['short']['bars'].iloc[2,0:2]=[1,1.1]
        r=bt.simulate(w,[])
        self.assertIn('Close early',r['blotter'][2]['note'])
        self.assertIn('2026-07-14',r['blotter'][2]['time'])

    def test_insufficient_cash_stops(self):
        with patch.object(bt,'INITIAL_CASH',1000):
            with self.assertRaisesRegex(ValueError,'funding exhausted'):
                bt.simulate(fixture(),[])

    def test_execution_cost_sensitivity(self):
        r=[bt.simulate(fixture(),[],scenario=x)['summary']['pnl'] for x in ['midpoint','bid_ask','adverse']]
        self.assertGreater(r[0],r[1]); self.assertGreater(r[1],r[2])

if __name__=='__main__': unittest.main()
