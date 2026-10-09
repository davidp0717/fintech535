"""A chronological PMCC simulation with explicit cash and position accounting.
Run: .venv/bin/python assignment3/backtest.py
"""
import hashlib
import json
import math
import sys
from pathlib import Path
import pandas as pd
from config import START, END, INITIAL_CASH, FEE, TZ, SHORT_MONEYNESS, SHORT_GRID

ROOT = Path(__file__).parent


def finite(value):
    return value is not None and pd.notna(value) and math.isfinite(float(value))


def quote(bars, time):
    observed = time
    if time not in bars.index:
        # Explicit, bounded as-of quote rule; never look at the following minute.
        prior = time - pd.Timedelta(minutes=1)
        if time.strftime('%H:%M') != '10:00' or prior not in bars.index:
            return None
        observed = prior
    row = bars.loc[observed]
    bid, ask = row.get('BID'), row.get('ASK')
    if not finite(bid) or not finite(ask) or bid < 0 or ask <= 0 or bid > ask:
        return None
    return {'bid': float(bid), 'ask': float(ask), 'mid': float((bid + ask) / 2), 'observed': observed}


def entry_quote(q):
    return q is not None and q['bid'] > 0 and (q['ask'] - q['bid']) / q['mid'] <= .20 + 1e-10


def fill(q, side, scenario):
    if scenario == 'midpoint':
        return q['mid']
    base = q['ask'] if side == 'BUY' else q['bid']
    extra = .10 * (q['ask'] - q['bid']) if scenario == 'adverse' else 0
    return base + extra if side == 'BUY' else max(0, base - extra)


def early_exit_reason(time, spot, contract, signal_quote, dividends):
    """Only information available by 09:59 can trigger an unscheduled 10:00 exit."""
    if finite(spot) and signal_quote and spot > contract['strike']:
        if signal_quote['mid'] - max(spot - contract['strike'], 0) <= .10:
            return 'Close early: ITM short has at most $0.10 of midpoint time value at 09:59'
    next_business_day = (time + pd.offsets.BDay()).date().isoformat()
    for d in dividends:
        if d['announced'] < time.date().isoformat() and d['ex_date'] == next_business_day and d['ex_date'] <= contract['expiry']:
            return 'Close before an announced ex-dividend date'
    return ''


def simulate(weeks, dividends, kind='pmcc', scenario='bid_ask', stress=False):
    cash, shares, long_qty, short_qty, receivable = INITIAL_CASH, 0, 0, 0, 0.0
    blotter, ledger, decisions = [], [], []
    last_marks, claims = {}, {}
    stopped = False
    long_contract = weeks[0]['long']
    start = pd.Timestamp(START + ' 10:00', tz=TZ)
    end = pd.Timestamp(END + ' 10:00', tz=TZ)
    short_contract = None
    stress_detail = None

    def book(time, instrument, leg, side, qty, price, note, q=None, fee=0, multiplier=100, signal=None):
        nonlocal cash
        delta = (1 if side in ('SELL','DIVIDEND') else -1 if side == 'BUY' else 0) * qty * multiplier * price - fee
        cash += delta
        blotter.append({'time': time.isoformat(), 'signal_time': signal.isoformat() if signal is not None else '',
            'instrument': instrument, 'leg': leg, 'side': side, 'qty': qty,
            'bid': q['bid'] if q else None, 'ask': q['ask'] if q else None,
            'quote_time': q['observed'].isoformat() if q else '',
            'quote_age_seconds': (time-q['observed']).total_seconds() if q else None,
            'fill': price, 'fee': fee, 'cash_delta': delta, 'cash_after': cash, 'note': note})
        if cash < -1e-7:
            raise ValueError('Cash funding exhausted; cannot book an unfunded trade')

    def mark(leg, bars, time):
        q = quote(bars, time)
        if q:
            last_marks[leg] = (q, q['observed'])
        if leg not in last_marks:
            raise ValueError(f'No prior mark available: {leg} {time}')
        q, observed = last_marks[leg]
        return q, (time - observed).total_seconds() / 60

    for week in weeks:
        stock, long_bars = week['stock'], week['long']['bars']
        candidate = week['short']
        decision = {'week': week['monday'], 'expiry': week['friday'],
            'strike': candidate['strike'] if candidate else None,
            'ric': candidate['ric'] if candidate else None,
            'status': 'Skipped', 'reason': 'No Monday 09:59 signal (holiday or missing bar)', 'exit': ''}
        if stopped:
            decision['reason'] = 'Assignment stress already ended trading; hold cash'
        decisions.append(decision)
        times = stock.index[stock.index.strftime('%H:%M') == '10:00']
        for time in times:
            if time < start or time > end:
                continue
            signal = time - pd.Timedelta(minutes=1)
            stock_q = quote(stock, time)
            signal_spot = stock.at[signal, 'TRDPRC_1'] if signal in stock.index else None
            if time == start:
                if not entry_quote(quote(long_bars, signal)) or not entry_quote(quote(long_bars, time)):
                    raise ValueError('Initial long call fails the predeclared quote/spread screen')
                if not stock_q:
                    raise ValueError('Initial stock quote is missing')
                if kind in ('pmcc', 'long_call'):
                    q = quote(long_bars, time)
                    book(time, long_contract['ric'], 'long_call', 'BUY', 1, fill(q,'BUY',scenario),
                         'Buy fixed January call chosen from the initial 09:59 stock print', q, FEE, signal=signal)
                    long_qty = 1
                else:
                    book(time, 'AAPL.O', 'stock', 'BUY', 100, fill(stock_q,'BUY',scenario),
                         'Buy and retain 100 shares for the matched-period benchmark', stock_q, multiplier=1, signal=signal)
                    shares = 100
            # Stockholders earn a receivable on ex-date; cash arrives on payment date.
            for d in dividends:
                if time.date().isoformat() == d['ex_date'] and shares > 0 and d['ex_date'] not in claims:
                    amount = shares * d['amount']
                    receivable += amount
                    claims[d['ex_date']] = amount
                    book(time, 'AAPL.O', 'dividend', 'ACCRUE', shares, d['amount'], 'Ex-date dividend receivable; cash unchanged', multiplier=1)
                if time.date().isoformat() == d['pay_date'] and claims.get(d['ex_date'], 0):
                    amount = claims.pop(d['ex_date'])
                    receivable -= amount
                    book(time, 'AAPL.O', 'dividend', 'DIVIDEND', 1, amount, 'Pay the accrued dividend into cash', multiplier=1)

            # The stress scenario is separate from normal trading; it is not a fill assumption.
            if short_qty and stress and finite(signal_spot) and signal_spot > short_contract['strike']:
                long_q, age = mark('long_call', long_bars, time)
                stress_detail = {'time': time.isoformat(), 'short_strike': short_contract['strike'],
                    'long_strike': long_contract['strike'], 'long_time_value': max(0, long_q['mid'] - max((stock_q['mid'] if stock_q else signal_spot)-long_contract['strike'],0))*100,
                    'note': 'First observed ITM short: assume assignment and immediate long exercise, then hold cash. $10 fee per exercise/assignment.'}
                book(time, short_contract['ric'], 'short_call', 'ASSIGN', 1, 0, 'Stress: remove assigned short call', fee=10, signal=signal)
                short_qty = 0
                book(time, 'AAPL.O', 'stock', 'SELL', 100, short_contract['strike'], 'Stress: assignment creates 100 short shares', multiplier=1)
                shares -= 100
                book(time, long_contract['ric'], 'long_call', 'EXERCISE', 1, 0, 'Stress: exercise long; forfeit remaining time value', fee=10)
                long_qty = 0
                book(time, 'AAPL.O', 'stock', 'BUY', 100, long_contract['strike'], 'Stress: exercise supplies shares to cover delivery', multiplier=1)
                shares += 100
                short_contract = None
                stopped = True
                decision['exit'] = 'Assignment stress; stop trading'
            if short_qty:
                reason = early_exit_reason(time, signal_spot, short_contract, quote(short_contract['bars'], signal), dividends)
                if time.dayofweek == 4 or time == end:
                    reason = 'Scheduled Friday 10:00 buy-to-close before expiration'
                if reason:
                    q = quote(short_contract['bars'], time)
                    if not q:
                        raise ValueError(f'Missing mandatory short exit quote: {time}; cannot invent a fill')
                    book(time, short_contract['ric'], 'short_call', 'BUY', 1, fill(q,'BUY',scenario), reason, q, FEE, signal=signal)
                    short_qty, short_contract = 0, None
                    decision['exit'] = time.isoformat()
            if time.dayofweek == 0 and kind in ('pmcc','covered_call') and not stopped:
                if candidate and finite(signal_spot):
                    expected = math.ceil(SHORT_MONEYNESS * signal_spot / SHORT_GRID) * SHORT_GRID
                    assert candidate['strike'] == expected, 'Strike must use only 09:59 spot'
                    before, current = quote(candidate['bars'], signal), quote(candidate['bars'], time)
                    if not entry_quote(before) or not entry_quote(current):
                        decision['reason'] = 'Missing quote, zero bid, or spread above 20% at signal/execution'
                    elif candidate['strike'] <= long_contract['strike'] or candidate['expiry'] >= long_contract['expiry']:
                        decision['reason'] = 'Short strike/expiry does not form a protected diagonal'
                    elif cash < 100 * current['ask'] + FEE:
                        decision['reason'] = 'Insufficient cash reserve to buy back the short at its current ask'
                    else:
                        assert not short_qty
                        book(time, candidate['ric'], 'short_call', 'SELL', 1, fill(current,'SELL',scenario),
                             'Monday 10:00; strike selected from 09:59 stock print; current quote passes entry screen', current, FEE, signal=signal)
                        short_qty, short_contract = 1, candidate
                        decision.update(status='Entered', reason='Valid signal and execution quotes; fully paid backing position')
            if time == end:
                assert not short_qty, 'Cover the short before selling the backing position'
                if long_qty:
                    q = quote(long_bars, time)
                    if not q:
                        raise ValueError('Missing terminal long exit quote')
                    book(time, long_contract['ric'], 'long_call', 'SELL', 1, fill(q,'SELL',scenario), 'Sell long at the fixed end date; realize remaining value', q, FEE)
                    long_qty = 0
                if shares:
                    if not stock_q:
                        raise ValueError('Missing terminal stock quote')
                    book(time, 'AAPL.O', 'stock', 'SELL', shares, fill(stock_q,'SELL',scenario), 'Liquidate benchmark at the same terminal time', stock_q, multiplier=1)
                    shares = 0
            stock_mark = stock_q['mid'] if stock_q else None
            long_mark, short_mark, ages = None, None, []
            lmv = smv = stock_mv = liquidation = 0
            if long_qty:
                q, age = mark('long_call', long_bars, time)
                long_mark, lmv = q['mid'], 100*q['mid']
                liquidation += 100*q['bid'] - FEE
                ages.append(age)
            if short_qty:
                q, age = mark(short_contract['ric'], short_contract['bars'], time)
                short_mark, smv = q['mid'], -100*q['mid']
                liquidation -= 100*q['ask'] + FEE
                ages.append(age)
            if shares:
                q, age = mark('stock', stock, time)
                stock_mv = shares*q['mid']
                stock_mark = q['mid']
                liquidation += shares*q['bid']
                ages.append(age)
            nav = cash + lmv + smv + stock_mv + receivable
            ledger.append({'time': time.isoformat(), 'cash': cash, 'shares': shares,
                'long_calls': long_qty, 'long_ric': long_contract['ric'] if long_qty else '',
                'long_strike': long_contract['strike'] if long_qty else None,
                'long_expiry': long_contract['expiry'] if long_qty else '',
                'short_calls': short_qty, 'short_ric': short_contract['ric'] if short_qty else '',
                'short_strike': short_contract['strike'] if short_qty else None,
                'short_expiry': short_contract['expiry'] if short_qty else '',
                'stock_mark': stock_mark, 'long_mark': long_mark, 'short_mark': short_mark,
                'long_mv': lmv, 'short_mv': smv, 'stock_mv': stock_mv, 'dividend_receivable': receivable,
                'nav': nav, 'liquidation_nav': cash + liquidation + receivable,
                'oldest_mark_minutes': max(ages,default=0)})
        if short_qty:
            raise ValueError(f'Unclosed short at week end: {week["friday"]}')
    if not ledger or ledger[-1]['time'] != end.isoformat():
        raise ValueError('Terminal timestamp missing; do not report an unfinished backtest')
    assert not shares and not long_qty and not short_qty
    result = {'kind': kind, 'scenario': scenario, 'initial_cash': INITIAL_CASH,
              'blotter': blotter, 'ledger': ledger, 'decisions': decisions, 'stress': stress_detail}
    validate(result)
    result['summary'] = summarize(result)
    return result


def validate(result):
    cash, i = result['initial_cash'], 0
    for row in result['ledger']:
        while i < len(result['blotter']) and result['blotter'][i]['time'] <= row['time']:
            event = result['blotter'][i]
            cash += event['cash_delta']
            assert math.isclose(cash, event['cash_after'], abs_tol=1e-7)
            i += 1
        assert math.isclose(cash, row['cash'], abs_tol=1e-7)
        assert math.isclose(row['nav'], cash+row['long_mv']+row['short_mv']+row['stock_mv']+row['dividend_receivable'],abs_tol=1e-7)
        assert row['short_calls'] <= row['long_calls'] + row['shares']/100
        assert row['cash'] >= 0
    assert i == len(result['blotter'])


def summarize(result):
    ledger, trades = result['ledger'], result['blotter']
    peak, drawdown = INITIAL_CASH, 0
    for row in ledger:
        peak = max(peak,row['nav'])
        drawdown = min(drawdown,row['nav']/peak-1)
    pnl = ledger[-1]['nav']-INITIAL_CASH
    initial_debit = INITIAL_CASH-ledger[0]['cash']
    return {'final_nav': ledger[-1]['nav'], 'pnl': pnl, 'account_return_pct': 100*pnl/INITIAL_CASH,
        'initial_debit': initial_debit, 'return_on_initial_debit_pct': 100*pnl/initial_debit,
        'max_drawdown_pct': -100*drawdown, 'min_cash': min(r['cash'] for r in ledger),
        'max_net_cash_deployed': max(INITIAL_CASH-r['cash'] for r in ledger),
        'premium': sum(e['fill']*100 for e in trades if e['leg']=='short_call' and e['side']=='SELL'),
        'buybacks': sum(e['fill']*100 for e in trades if e['leg']=='short_call' and e['side']=='BUY'),
        'fees': sum(e['fee'] for e in trades),
        'long_pnl': sum(e['cash_delta'] for e in trades if e['leg']=='long_call'),
        'short_pnl': sum(e['cash_delta'] for e in trades if e['leg']=='short_call'),
        'stock_pnl': sum(e['cash_delta'] for e in trades if e['leg']=='stock'),
        'dividends': sum(e['cash_delta'] for e in trades if e['leg']=='dividend'),
        'entries': sum(d['status']=='Entered' for d in result['decisions']),
        'stale_marks': sum(r['oldest_mark_minutes']>0 for r in ledger),
        'aged_fills': sum((e['quote_age_seconds'] or 0)>0 for e in trades), 'observations': len(ledger)}


def load_inputs():
    """Public CSV snapshots allow a complete offline rerun without Workspace."""
    if (ROOT/'inputs.json').exists() and '--from-cache' not in sys.argv:
        info = json.loads((ROOT/'inputs.json').read_text())
        prices = pd.read_csv(ROOT/'quotes.csv')
        prices['time'] = pd.to_datetime(prices['time'], utc=True).dt.tz_convert(TZ)
        weeks = []
        for metadata in info['weeks']:
            week = dict(metadata)
            start = pd.Timestamp(week['monday'],tz=TZ)
            finish = pd.Timestamp(week['friday'],tz=TZ)+pd.Timedelta(days=1)
            subset = prices[(prices['time']>=start)&(prices['time']<finish)]
            week['stock'] = subset[subset['role']=='stock'].set_index('time')[['BID','ASK','TRDPRC_1','ACVOL_UNS']]
            for leg in ['long','short']:
                if week[leg]:
                    week[leg] = dict(week[leg])
                    week[leg]['bars'] = subset[subset['role']==leg].set_index('time')[['BID','ASK','TRDPRC_1','ACVOL_UNS']]
            weeks.append(week)
        return weeks, info['dividends'], info['split_check']
    weeks = [pd.read_pickle(p) for p in sorted((ROOT/'cache').glob('week-*.pkl'))]
    split = pd.read_pickle(ROOT/'cache/split_check.pkl')
    pair = pd.concat([split['raw'].iloc[:,0],split['adjusted'].iloc[:,0]],axis=1).dropna()
    if pair.empty or not ((pair.iloc[:,0]-pair.iloc[:,1]).abs()<.00001).all():
        raise ValueError('Capital-change screen failed')
    raw_dividends = pd.read_pickle(ROOT/'cache/dividends.pkl')
    dividends = [{'ex_date': str(pd.Timestamp(r['Dividend Ex Date']).date()),
        'pay_date': str(pd.Timestamp(r['Dividend Pay Date']).date()),
        'announced': str(pd.Timestamp(r['Dividend Announcement Date']).date()),
        'amount': float(r['Gross Dividend Amount'])} for _,r in raw_dividends.iterrows() if pd.notna(r['Dividend Ex Date'])]
    split_check = f'Raw and CCH-adjusted stock closes match on {len(pair)} dates'
    metadata = []
    for week in weeks:
        row = {'monday':week['monday'],'friday':week['friday']}
        for leg in ['long','short']:
            row[leg] = {k:v for k,v in week[leg].items() if k!='bars'} if week[leg] else None
        metadata.append(row)
    (ROOT/'inputs.json').write_text(json.dumps({'weeks':metadata,'dividends':dividends,'split_check':split_check},indent=2)+'\n')
    return weeks, dividends, split_check


def main():
    weeks, dividends, split_check = load_inputs()
    outputs = {kind: simulate(weeks,dividends,kind) for kind in ['pmcc','covered_call','buy_hold','long_call']}
    for scenario in ['midpoint','adverse']:
        outputs[scenario] = simulate(weeks,dividends,'pmcc',scenario)
    outputs['assignment_stress'] = simulate(weeks,dividends,'pmcc',stress=True)
    for name, result in outputs.items():
        print(f'{name}: P&L ${result["summary"]["pnl"]:,.2f}; final NAV ${result["summary"]["final_nav"]:,.2f}', flush=True)
    quotes = []
    for week in weeks:
        for role, contract in [('stock',{'ric':'AAPL.O','bars':week['stock']}),('long',week['long']),('short',week['short'])]:
            if not contract: continue
            for time, row in contract['bars'].iterrows():
                quotes.append({'time':time.isoformat(),'role':role,'ric':contract['ric'],
                    'strike':contract.get('strike'),'expiry':contract.get('expiry'),
                    **{f: float(row[f]) if finite(row[f]) else None for f in ['BID','ASK','TRDPRC_1','ACVOL_UNS']}})
    if '--from-cache' in sys.argv or not (ROOT/'quotes.csv').exists():
        pd.DataFrame(quotes).to_csv(ROOT/'quotes.csv',index=False)
        pd.DataFrame(dividends).to_csv(ROOT/'dividends.csv',index=False)
    result = {'source': json.loads((ROOT/'data_manifest.json').read_text()), 'dividends':dividends,
              'results': outputs, 'split_check': split_check}
    result['source']['quotes_sha256'] = hashlib.sha256((ROOT/'quotes.csv').read_bytes()).hexdigest()
    result['source']['config_sha256'] = hashlib.sha256((ROOT/'config.py').read_bytes()).hexdigest()
    result['source']['quote_rows'] = len(quotes)
    for key in ['blotter','ledger','decisions']:
        pd.DataFrame(outputs['pmcc'][key]).to_csv(ROOT/f'{key}.csv',index=False)
    # Include independent cash books so each benchmark and sensitivity can be audited.
    (ROOT/'book.json').write_text(json.dumps(result,allow_nan=False,separators=(',',':'))+'\n')
    print('Saved static results and audit CSV files.')

if __name__ == '__main__':
    main()
