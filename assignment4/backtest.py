"""Walk forward through saved observations; record every cash/position event.
Run without Workspace: .venv/bin/python assignment4/backtest.py
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from market_calendar import close_clock
from config import (START, END, SYMBOL, TZ, INITIAL_CASH, PUT_MONEYNESS,
    CALL_MONEYNESS, STRIKE_GRID, OPTION_FEE, ASSIGNMENT_FEE,
    MAX_ENTRY_SPREAD, MAX_QUOTE_AGE_SECONDS, HOLIDAYS)

ROOT = Path(__file__).parent

def timestamp(day, clock):
    return pd.Timestamp(day+' '+clock, tz=TZ)

def finite(x):
    return x is not None and pd.notna(x) and math.isfinite(float(x))

def quote(bars, time, max_age=None):
    """Latest valid observed quote, never a later observation."""
    prior = bars.loc[bars.index<=time]
    if prior.empty: return None
    valid = prior['BID'].notna() & prior['ASK'].notna()
    valid &= (prior['BID']>=0) & (prior['ASK']>0) & (prior['BID']<=prior['ASK'])
    prior = prior.loc[valid]
    if prior.empty: return None
    when, row = prior.index[-1], prior.iloc[-1]
    age = (time-when).total_seconds()
    if max_age is not None and age>max_age: return None
    return {'bid':float(row['BID']), 'ask':float(row['ASK']),
        'mid':float((row['BID']+row['ASK'])/2), 'time':when.isoformat(),
        'age_seconds':age, 'trade':float(row['TRDPRC_1']) if finite(row.get('TRDPRC_1')) else None}

def eligible(q):
    return q is not None and q['bid']>0 and (q['ask']-q['bid'])/q['mid']<=MAX_ENTRY_SPREAD+1e-10

def fill(q, side, scenario):
    if scenario=='midpoint': return q['mid']
    price = q['ask'] if side=='BUY' else q['bid']
    extra = .1*(q['ask']-q['bid']) if scenario=='adverse' else 0
    return price+extra if side=='BUY' else max(0,price-extra)

def intrinsic(contract, stock):
    return max((contract['strike']-stock) if contract['kind']=='put' else (stock-contract['strike']),0)

def load_inputs():
    info = json.loads((ROOT/'inputs.json').read_text())
    raw = pd.read_csv(ROOT/'quotes.csv')
    raw['time'] = pd.to_datetime(raw['time'],utc=True).dt.tz_convert(TZ)
    raw = raw.loc[[t.strftime('%H:%M') <= close_clock(t.date()) for t in raw['time']]]
    bars = {ric:group.set_index('time').drop(columns=['ric','role']).sort_index()
            for ric,group in raw.groupby('ric')}
    for ric, frame in bars.items():
        if frame.index.duplicated().any(): raise ValueError(f'Duplicate quote timestamps: {ric}')
    info['bars'] = bars
    expected = [str(d.date()) for d in pd.bdate_range(START,END) if str(d.date()) not in HOLIDAYS]
    if set(expected)!=set(info['closes']):
        raise ValueError('Daily closes do not cover the fixed exchange calendar')
    if len(info['weeks'])!=len(pd.date_range(START,END,freq='W-MON')):
        raise ValueError('Missing download weeks')
    return info

def simulate(data, strategy='wheel', scenario='bid_ask', early_assignment=False):
    cash, shares, position, receivable = INITIAL_CASH, 0, None, 0.0
    trades, ledger, decisions, claims = [], [], [], {}
    group_id = 0
    days = sorted(data['closes'])
    closes_at = {d:timestamp(d,close_clock(d)) for d in days}
    weeks = {w['monday']:w for w in data['weeks']}
    stocks = data['bars'][SYMBOL]

    def state(time, phase, reason, group=None):
        stock_q = quote(stocks,time)
        # The daily close is available only at/after that session's close.
        known_days = [d for d in days if closes_at[d]<=time]
        closing_day = known_days[-1] if known_days else None
        if closing_day and (stock_q is None or timestamp(closing_day,close_clock(closing_day))>=pd.Timestamp(stock_q['time'])):
            stock_mark = data['closes'][closing_day]
            stock_time = timestamp(closing_day,close_clock(closing_day)).isoformat()
            stock_source = 'Raw daily closing print'
            stock_bid = stock_q['bid'] if stock_q and stock_q['time']==stock_time else stock_mark
        else:
            stock_mark = stock_q['mid'] if stock_q else None
            stock_bid = stock_q['bid'] if stock_q else None
            stock_time = stock_q['time'] if stock_q else ''
            stock_source = 'Bid/ask midpoint'
        if shares and stock_mark is None: raise ValueError(f'No stock mark {time}')
        option, liability, liquidation_cost = None, 0.0, 0.0
        if position:
            option = {k:position[k] for k in ['ric','kind','strike','expiry']}
            option['quantity'] = -1
            if time>=timestamp(position['expiry'],close_clock(position['expiry'])):
                mark = intrinsic(position,data['closes'][position['expiry']])
                option.update(mark=mark,quote_time=timestamp(position['expiry'],close_clock(position['expiry'])).isoformat(),
                    mark_source='Expiry intrinsic value',quote_age_seconds=(time-timestamp(position['expiry'],close_clock(position['expiry']))).total_seconds())
                liquidation_cost = 100*mark
            else:
                q = quote(data['bars'][position['ric']],time)
                if q is None: raise ValueError(f'No option mark {position["ric"]} {time}')
                option.update(mark=q['mid'],quote_time=q['time'],mark_source='Bid/ask midpoint',quote_age_seconds=q['age_seconds'])
                liquidation_cost = 100*q['ask']+OPTION_FEE
            liability = option['mark']*100
        stock_mv = shares*(stock_mark or 0)
        reserve = 100*position['strike'] if position and position['kind']=='put' else 0.0
        nav = cash+stock_mv-liability+receivable
        snap = {'time':time.isoformat(),'phase':phase,'reason':reason,'group':group,
            'cash':cash,'shares':shares,'option':option,'short_puts':int(bool(position and position['kind']=='put')),
            'short_calls':int(bool(position and position['kind']=='call')),
            'put_reserve':reserve,'free_cash':cash-reserve,'dividend_receivable':receivable,
            'stock_mark':stock_mark,'stock_mark_time':stock_time,'stock_mark_source':stock_source,
            'stock_mv':stock_mv,'option_mv':-liability,'nav':nav,
            'liquidation_nav':cash+shares*(stock_bid or 0)-liquidation_cost+receivable}
        assert shares in (0,100)
        assert cash>=-1e-7 and cash-reserve>=-1e-7, 'Insufficient cash or collateral'
        assert not position or (position['kind']=='put' and shares==0) or (position['kind']=='call' and shares==100), 'Uncovered option'
        return snap

    def trade_row(instrument,kind,action,qty,price,fee=0,q=None,note='',contract=None):
        change = (qty*price*(100 if kind in ('put','call') else 1)) * (1 if action=='SELL' else -1 if action=='BUY' else 0)-fee
        return {'instrument':instrument,'kind':kind,'action':action,'quantity':qty,
            'strike':contract['strike'] if contract else None,'expiry':contract['expiry'] if contract else '',
            'fill':price,'fee':fee,'cash_delta':change,
            'bid':q['bid'] if q else None,'ask':q['ask'] if q else None,
            'quote_time':q['time'] if q else '', 'quote_age_seconds':q['age_seconds'] if q else None,
            'note':note}

    def transact(time, rows, new_shares, new_position, note, new_receivable=None):
        nonlocal cash,shares,position,receivable,group_id
        group_id += 1
        ledger.append(state(time,'before',note,group_id))
        for row in rows:
            cash += row['cash_delta']
            row.update(id=len(trades)+1,time=time.isoformat(),group=group_id,cash_after=cash)
            trades.append(row)
        shares, position = new_shares, copy.deepcopy(new_position)
        if new_receivable is not None: receivable = new_receivable
        ledger.append(state(time,'after',note,group_id))

    def settle(time, assign, early=False):
        contract = copy.deepcopy(position)
        text = ('Early-assignment sensitivity' if early else 'Expiry rule')
        if assign:
            rows = [trade_row(contract['ric'],contract['kind'],'ASSIGN',1,0,ASSIGNMENT_FEE,
                note=text+': remove short option; linked stock transfer in same atomic event',contract=contract)]
            is_put = contract['kind']=='put'
            rows.append(trade_row(SYMBOL,'stock','BUY' if is_put else 'SELL',100,contract['strike'],
                note=text+': physical delivery at strike',contract=contract))
            transact(time,rows,100 if is_put else 0,None,text+': '+contract['kind']+' assigned')
        else:
            row = trade_row(contract['ric'],contract['kind'],'EXPIRE',1,0,
                note='Below $0.01 ITM at expiry close; option removed; no premium collected twice',contract=contract)
            transact(time,[row],shares,None,'Option expires')

    ledger.append(state(timestamp(days[0],'09:59'),'initial','Initial funding'))
    for day in days:
        for d in data['dividends']:
            if day==d['ex_date'] and shares:
                amount = shares*d['amount']; claims[d['ex_date']] = amount
                row = trade_row(SYMBOL,'dividend','ACCRUE',shares,d['amount'],note='Shares held entering ex-date; accrue receivable')
                transact(timestamp(day,'09:30'),[row],shares,position,'Dividend entitlement',receivable+amount)
            if day==d['pay_date'] and d['ex_date'] in claims:
                amount = claims.pop(d['ex_date'])
                row = trade_row(SYMBOL,'dividend','DIVIDEND',1,amount,note='Pay existing dividend receivable')
                row['cash_delta'] = amount
                transact(timestamp(day,'09:30'),[row],shares,position,'Dividend payment',receivable-amount)
        order_time, signal_time = timestamp(day,'10:00'), timestamp(day,'09:59')
        if strategy=='buy_hold' and day==days[0]:
            q = quote(stocks,order_time,MAX_QUOTE_AGE_SECONDS)
            if q is None: raise ValueError('Missing benchmark initial stock quote')
            if cash<100*fill(q,'BUY',scenario): raise ValueError('Cannot fund benchmark')
            transact(order_time,[trade_row(SYMBOL,'stock','BUY',100,fill(q,'BUY',scenario),q=q,
                note='Buy 100 shares at the first 10:00 ask and hold')],100,None,'Buy-and-hold entry')
        if early_assignment and position and day<position['expiry']:
            q = quote(data['bars'][position['ric']],signal_time,MAX_QUOTE_AGE_SECONDS)
            spot = stocks.at[signal_time,'TRDPRC_1'] if signal_time in stocks.index else None
            if q and finite(spot) and intrinsic(position,spot)>0 and q['mid']-intrinsic(position,spot)<=.10:
                settle(order_time,True,early=True)
        if day in weeks and strategy!='buy_hold':
            week = weeks[day]
            kind = 'put' if strategy=='wheel' and shares==0 else 'call'
            c = week[kind]
            decision = {'week':day,'kind':kind,'strike':c['strike'] if c else None,'expiry':week['expiry'],
                'ric':c['ric'] if c else '', 'status':'Skipped','reason':''}
            decisions.append(decision)
            if position: raise ValueError('Previous weekly option unexpectedly remains open')
            if not c or not c['ric']:
                decision['reason'] = 'Predetermined contract has no signal-time quote after identifier checks'
            else:
                spot = stocks.at[signal_time,'TRDPRC_1']
                expected = (math.floor(PUT_MONEYNESS*spot/STRIKE_GRID) if kind=='put' else math.ceil(CALL_MONEYNESS*spot/STRIKE_GRID))*STRIKE_GRID
                assert expected==c['strike'], 'Strike used information beyond the prior stock print'
                before = quote(data['bars'][c['ric']],signal_time,MAX_QUOTE_AGE_SECONDS)
                q = quote(data['bars'][c['ric']],order_time,MAX_QUOTE_AGE_SECONDS)
                stock_q = quote(stocks,order_time,MAX_QUOTE_AGE_SECONDS)
                if not eligible(before) or not eligible(q):
                    decision['reason'] = 'Missing/stale quote, zero bid or relative spread above 20%'
                elif kind=='put' and cash<100*c['strike']+OPTION_FEE:
                    decision['reason'] = 'Insufficient existing cash for full strike collateral plus fee'
                elif kind=='call' and shares==0 and (not stock_q or cash<100*fill(stock_q,'BUY',scenario)+OPTION_FEE):
                    decision['reason'] = 'Cannot buy 100 shares and fund option fee'
                else:
                    if kind=='call' and shares==0:
                        transact(order_time,[trade_row(SYMBOL,'stock','BUY',100,fill(stock_q,'BUY',scenario),q=stock_q,
                            note='Covered-call benchmark: repurchase 100 shares when flat')],100,None,'Covered-call stock entry')
                    transact(order_time,[trade_row(c['ric'],kind,'SELL',1,fill(q,'SELL',scenario),OPTION_FEE,q,
                        note=f'Monday 10:00; {kind} strike from 09:59 stock print; hold to expiry',contract=c)],shares,c,'Sell '+kind)
                    decision.update(status='Entered',reason='Valid prior signal and execution quote; fully funded')
        for clock in ['10:00','11:00','12:00','13:00','14:00','15:00','16:00']:
            if clock > close_clock(day): continue
            ledger.append(state(timestamp(day,clock),'mark','Scheduled valuation'))
        if position and day==position['expiry']:
            value = intrinsic(position,data['closes'][day])
            settle(timestamp(day,close_clock(day))+pd.Timedelta(minutes=1),value>=.01-1e-9)
        ledger.append(state(timestamp(day,close_clock(day))+pd.Timedelta(minutes=1),'close','Daily close after modeled expiry events'))
    for week in data['weeks']:
        if week['monday'] in HOLIDAYS and strategy!='buy_hold':
            decisions.append({'week':week['monday'],'kind':'','strike':None,'expiry':week['expiry'],
                'ric':'','status':'Skipped','reason':'Monday exchange holiday; no Tuesday catch-up'})
    decisions.sort(key=lambda d:d['week'])
    result = {'blotter':trades,'ledger':ledger,'decisions':decisions}
    validate(result)
    result['summary'] = summarize(result)
    return result

def validate(result):
    cash = INITIAL_CASH
    for row in result['blotter']:
        cash += row['cash_delta']
        assert math.isclose(cash,row['cash_after'],abs_tol=1e-7)
        if row['quote_time']:
            assert pd.Timestamp(row['quote_time'])<=pd.Timestamp(row['time'])
            assert row['quote_age_seconds']<=MAX_QUOTE_AGE_SECONDS
    last_time = None
    expected_cash, expected_shares, expected_option, expected_receivable = INITIAL_CASH,0,None,0.0
    groups = {}
    for row in result['blotter']: groups.setdefault(row['group'],[]).append(row)
    for row in result['ledger']:
        t = pd.Timestamp(row['time'])
        assert last_time is None or t>=last_time, 'Ledger must be chronological'
        last_time = t
        if row['phase']=='after':
            for e in groups[row['group']]:
                expected_cash += e['cash_delta']
                if e['kind']=='stock': expected_shares += e['quantity']*(1 if e['action']=='BUY' else -1)
                if e['kind'] in ('put','call'):
                    if e['action']=='SELL': expected_option = e['instrument']
                    elif e['action'] in ('ASSIGN','EXPIRE','BUY'): expected_option = None
                if e['action']=='ACCRUE': expected_receivable += e['quantity']*e['fill']
                elif e['action']=='DIVIDEND': expected_receivable -= e['cash_delta']
        assert math.isclose(row['cash'],expected_cash,abs_tol=1e-7), 'Cash differs from event replay'
        assert row['shares']==expected_shares, 'Share position differs from event replay'
        assert (row['option']['ric'] if row['option'] else None)==expected_option
        assert math.isclose(row['dividend_receivable'],expected_receivable,abs_tol=1e-7)
        assert math.isclose(row['nav'],row['cash']+row['stock_mv']+row['option_mv']+row['dividend_receivable'],abs_tol=1e-7)
        assert row['free_cash']>=-1e-7
        assert row['short_calls']*100<=row['shares']
    assert math.isclose(cash,result['ledger'][-1]['cash'],abs_tol=1e-7)

def summarize(result):
    close = [r for r in result['ledger'] if r['phase']=='close']
    nav = np.array([INITIAL_CASH]+[r['nav'] for r in close])
    returns = nav[1:]/nav[:-1]-1
    std = float(np.std(returns,ddof=1)) if len(returns)>1 else 0
    trades, final = result['blotter'],close[-1]
    option_cash = sum(e['cash_delta'] for e in trades if e['kind'] in ('put','call'))
    stock_pnl = sum(e['cash_delta'] for e in trades if e['kind']=='stock')+final['stock_mv']
    dividend = sum(e['cash_delta'] for e in trades if e['action']=='DIVIDEND')+final['dividend_receivable']
    put_assign = sum(e['action']=='ASSIGN' and e['kind']=='put' for e in trades)
    call_assign = sum(e['action']=='ASSIGN' and e['kind']=='call' for e in trades)
    return {'pnl':final['nav']-INITIAL_CASH,'final_nav':final['nav'],'return_pct':100*(final['nav']/INITIAL_CASH-1),
        'drawdown_pct':100*float(np.max(1-nav/np.maximum.accumulate(nav))),
        'volatility_pct':100*std*math.sqrt(252),'sharpe':float(returns.mean()/std*math.sqrt(252)) if std else None,
        'option_pnl':option_cash+final['option_mv'],'stock_pnl':stock_pnl,'dividends':dividend,
        'fees':sum(e['fee'] for e in trades),'premium':sum(100*e['fill'] for e in trades if e['action']=='SELL' and e['kind'] in ('put','call')),
        'put_assignments':put_assign,'call_assignments':call_assign,'completed_cycles':min(put_assign,call_assign),
        'option_entries':sum(e['action']=='SELL' and e['kind'] in ('put','call') for e in trades),
        'share_days_pct':100*sum(r['shares']>0 for r in close)/len(close),
        'mean_committed_capital':float(np.mean([r['stock_mv']+r['put_reserve'] for r in close])),
        'min_free_cash':min(r['free_cash'] for r in result['ledger']),
        'stale_option_marks':sum(bool(r['option'] and r['option']['quote_age_seconds']>60) for r in close),
        'observations':len(close),'ending_shares':final['shares'],
        'aged_fills':sum((r['quote_age_seconds'] or 0)>0 for r in trades)}

def diagnostics(data, main):
    entries = [e for e in main['blotter'] if e['action']=='SELL' and e['kind'] in ('put','call')]
    points = []
    for e in entries:
        frame = data['bars'][e['instrument']]
        frame = frame[(frame.index>=pd.Timestamp(e['time'])) & (frame.index<=timestamp(e['expiry'],close_clock(e['expiry'])))]
        for time,row in frame.iterrows():
            if not all(finite(row.get(k)) for k in ['BID','ASK','TRDPRC_1','ACVOL_UNS']): continue
            if row['BID']<0 or row['ASK']<=0 or row['BID']>row['ASK'] or row['ACVOL_UNS']<=0: continue
            points.append({'time':time.isoformat(),'ric':e['instrument'],'mid':float((row['BID']+row['ASK'])/2),
                'trade':float(row['TRDPRC_1']),'bid':float(row['BID']),'ask':float(row['ASK'])})
    spreads = [e['ask']-e['bid'] for e in entries]
    result = {'entries':len(entries),'median_spread':float(np.median(spreads)) if spreads else None,
        'max_spread':max(spreads) if spreads else None,
        'midpoint_advantage':sum(50*(e['ask']-e['bid']) for e in entries),
        'observed_points':len(points),'points':points,'r2':None,'slope':None,'intercept':None}
    if len(points)>2:
        x=np.array([p['mid'] for p in points]); y=np.array([p['trade'] for p in points])
        if np.ptp(x)>0 and np.ptp(y)>0:
            slope,intercept=np.polyfit(x,y,1); residual=y-(slope*x+intercept)
            result.update(slope=float(slope),intercept=float(intercept),r2=float(1-sum(residual**2)/sum((y-y.mean())**2)))
        result['inside_spread_pct'] = 100*sum(p['bid']<=p['trade']<=p['ask'] for p in points)/len(points)
    return result

def csv_ledger(rows):
    out=[]
    for r in rows:
        flat={k:v for k,v in r.items() if k!='option'}
        for key,value in (r['option'] or {}).items(): flat['option_'+key]=value
        out.append(flat)
    return pd.DataFrame(out)

def main():
    data=load_inputs()
    results={key:simulate(data,key) for key in ['wheel','buy_hold','covered_call']}
    for scenario in ['midpoint','adverse']:
        results[scenario]=simulate(data,'wheel',scenario)
        assert [(d['week'],d['status'],d['ric']) for d in results[scenario]['decisions']]==[(d['week'],d['status'],d['ric']) for d in results['wheel']['decisions']], 'Cost scenarios changed entry eligibility'
    results['early_assignment']=simulate(data,early_assignment=True)
    for key,r in results.items():
        s=r['summary']
        assert math.isclose(s['pnl'],s['option_pnl']+s['stock_pnl']+s['dividends'],abs_tol=1e-6)
        print(f'{key}: P&L {s["pnl"]:.2f}; return {s["return_pct"]:.2f}%; Sharpe {s["sharpe"]}; puts assigned {s["put_assignments"]}; calls assigned {s["call_assignments"]}',flush=True)
    source=json.loads((ROOT/'data_manifest.json').read_text())
    source['hashes']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['quotes.csv','inputs.json','config.py','SPECIFICATION.md']}
    book={'source':source,'initial_cash':INITIAL_CASH,'results':results,'diagnostics':diagnostics(data,results['wheel'])}
    (ROOT/'book.json').write_text(json.dumps(book,allow_nan=False,separators=(',',':'))+'\n')
    pd.DataFrame(results['wheel']['blotter']).to_csv(ROOT/'blotter.csv',index=False)
    csv_ledger(results['wheel']['ledger']).to_csv(ROOT/'ledger.csv',index=False)
    pd.DataFrame(results['wheel']['decisions']).to_csv(ROOT/'decisions.csv',index=False)

if __name__=='__main__': main()
