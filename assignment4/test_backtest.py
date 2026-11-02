"""Small artificial edge cases; none of these prices feed the published page."""
import copy
import unittest
from unittest.mock import patch
import pandas as pd
import backtest as bt

def example():
    dates=[str(d.date()) for d in pd.bdate_range('2026-05-04','2026-05-15')]
    times=[bt.timestamp(d,t) for d in dates for t in ['09:59','10:00','11:00','12:00','13:00','14:00','15:00','16:00']]
    stock=pd.DataFrame({'BID':99.9,'ASK':100.1,'TRDPRC_1':100.,'ACVOL_UNS':100.,'NUM_MOVES':1.},index=times)
    closes={d:100. for d in dates}; closes['2026-05-08']=94.; closes['2026-05-15']=110.
    bars={bt.SYMBOL:stock}; weeks=[]
    for monday,expiry in [('2026-05-04','2026-05-08'),('2026-05-11','2026-05-15')]:
        w={'monday':monday,'friday':expiry,'expiry':expiry}
        for kind,strike in [('put',97.5),('call',102.5)]:
            ric=kind+'-'+monday
            w[kind]={'ric':ric,'kind':kind,'strike':strike,'expiry':expiry}
            bars[ric]=pd.DataFrame({'BID':2.,'ASK':2.1,'TRDPRC_1':2.05,'ACVOL_UNS':1.,'NUM_MOVES':1.},index=[t for t in times if monday<=str(t.date())<=expiry])
        weeks.append(w)
    return {'weeks':weeks,'closes':closes,'bars':bars,'dividends':[]}

class WheelTests(unittest.TestCase):
    def test_full_wheel_and_atomic_assignment(self):
        r=bt.simulate(example())
        assignments=[e for e in r['blotter'] if e['action']=='ASSIGN']
        self.assertEqual([e['kind'] for e in assignments],['put','call'])
        self.assertEqual(r['ledger'][-1]['shares'],0)
        self.assertAlmostEqual(r['summary']['pnl'],898.70)
        for e in assignments:
            pair=[s for s in r['ledger'] if s['group']==e['group']]
            self.assertEqual([s['phase'] for s in pair],['before','after'])
            self.assertAlmostEqual(pair[0]['nav'],pair[1]['nav'])

    def test_expiration_does_not_credit_premium_twice(self):
        data=example(); data['closes']={d:100. for d in data['closes']}
        r=bt.simulate(data)
        self.assertAlmostEqual(r['summary']['pnl'],398.70)
        self.assertTrue(all(e['cash_delta']==0 for e in r['blotter'] if e['action']=='EXPIRE'))

    def test_collateral_is_not_subtracted_from_nav(self):
        r=bt.simulate(example())
        s=next(s for s in r['ledger'] if s['phase']=='after')
        self.assertAlmostEqual(s['put_reserve'],9750)
        self.assertAlmostEqual(s['free_cash'],s['cash']-9750)
        self.assertAlmostEqual(s['nav'],39994.35)

    def test_insufficient_cash_skips_put(self):
        with patch.object(bt,'INITIAL_CASH',9700): r=bt.simulate(example())
        self.assertEqual(r['blotter'],[])
        self.assertIn('collateral',r['decisions'][0]['reason'])

    def test_missing_execution_quote_cannot_use_future(self):
        data=example(); ric=data['weeks'][0]['put']['ric']
        data['bars'][ric]=data['bars'][ric].loc[data['bars'][ric].index>bt.timestamp('2026-05-04','10:00')]
        r=bt.simulate(data)
        self.assertEqual(r['decisions'][0]['status'],'Skipped')

    def test_quote_age_and_crossed_mark(self):
        data=example(); frame=data['bars'][bt.SYMBOL].iloc[:1]
        self.assertIsNotNone(bt.quote(frame,bt.timestamp('2026-05-04','10:00'),60))
        self.assertIsNone(bt.quote(frame,bt.timestamp('2026-05-04','10:01'),60))
        frame=frame.copy(); frame['BID']=102
        self.assertIsNone(bt.quote(frame,bt.timestamp('2026-05-04','10:00'),60))

    def test_future_prices_do_not_change_earlier_events(self):
        data=example(); first=bt.simulate(data)
        future=bt.timestamp('2026-05-12','10:00')
        for frame in data['bars'].values():
            frame.loc[frame.index>=future,['BID','ASK','TRDPRC_1']]*=1.5
        second=bt.simulate(data)
        cut='2026-05-12'
        self.assertEqual([e for e in first['blotter'] if e['time'][:10]<cut],[e for e in second['blotter'] if e['time'][:10]<cut])

    def test_dividend_accrual_payment_and_ex_date_purchase(self):
        data=example(); data['dividends']=[{'ex_date':'2026-05-11','pay_date':'2026-05-14','announced':'2026-04-30','amount':.27}]
        r=bt.simulate(data)
        accrue=next(s for s in r['ledger'] if s['phase']=='after' and s['reason']=='Dividend entitlement')
        self.assertEqual(accrue['dividend_receivable'],27)
        self.assertEqual(r['summary']['dividends'],27)
        self.assertEqual(r['ledger'][-1]['dividend_receivable'],0)
        # A covered call assigned Friday buys again Monday after ex-date opens.
        data['closes']['2026-05-08']=110
        cc=bt.simulate(data,'covered_call')
        self.assertEqual(cc['summary']['dividends'],0)

    def test_cost_sensitivity_preserves_contracts(self):
        results=[bt.simulate(example(),scenario=s) for s in ['adverse','bid_ask','midpoint']]
        self.assertLess(results[0]['summary']['pnl'],results[1]['summary']['pnl'])
        self.assertLess(results[1]['summary']['pnl'],results[2]['summary']['pnl'])
        self.assertEqual(results[0]['decisions'],results[2]['decisions'])

    def test_call_below_acquisition_cost_is_not_hidden(self):
        data=example(); w=data['weeks'][1]; when=bt.timestamp(w['monday'],'09:59')
        data['bars'][bt.SYMBOL].loc[when,'TRDPRC_1']=90
        w['call']['strike']=92.5
        r=bt.simulate(data)
        self.assertEqual(r['decisions'][1]['strike'],92.5)
        self.assertLess(r['summary']['stock_pnl'],0)

    def test_early_assignment_uses_prior_signal(self):
        data=example(); when=bt.timestamp('2026-05-07','09:59')
        data['bars'][bt.SYMBOL].loc[when,'TRDPRC_1']=94
        ric=data['weeks'][0]['put']['ric']
        data['bars'][ric].loc[when,['BID','ASK']]=[3.5,3.6]
        r=bt.simulate(data,early_assignment=True)
        assignment=next(e for e in r['blotter'] if e['action']=='ASSIGN')
        self.assertEqual(assignment['time'],bt.timestamp('2026-05-07','10:00').isoformat())
        self.assertEqual(r['decisions'][1]['kind'],'call')

    def test_ledger_corruption_is_detected(self):
        r=bt.simulate(example()); r['ledger'][10]['cash']+=1
        with self.assertRaises(AssertionError): bt.validate(r)

    def test_holiday_week_has_no_entry(self):
        data=example()
        data['weeks'].append({'monday':'2026-05-25','friday':'2026-05-29','expiry':'2026-05-29','put':None,'call':None})
        r=bt.simulate(data)
        self.assertIn('holiday',r['decisions'][-1]['reason'])

    def test_terminal_shares_stay_marked_not_fake_sold(self):
        data=example(); data['closes']['2026-05-15']=100
        r=bt.simulate(data)
        self.assertEqual(r['ledger'][-1]['shares'],100)
        self.assertEqual(r['blotter'][-1]['action'],'EXPIRE')
        self.assertAlmostEqual(r['summary']['pnl'],r['summary']['option_pnl']+r['summary']['stock_pnl'])

if __name__=='__main__': unittest.main()
