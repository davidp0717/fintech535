"""Save LSEG quotes and metadata. No returns are calculated in this script."""
import datetime as dt
import hashlib
import json
import math
import signal
import time
import warnings
from pathlib import Path
import lseg.data as ld
import pandas as pd
from lseg.data.content.historical_pricing import summaries
from config import START, END, SYMBOL, TZ, PUT_MONEYNESS, CALL_MONEYNESS, STRIKE_GRID, HOLIDAYS, OBSERVATIONS

ROOT = Path(__file__).parent
CACHE = ROOT / 'cache'
FIELDS = ['BID', 'ASK', 'TRDPRC_1', 'ACVOL_UNS', 'NUM_MOVES']

def timed_out(*args):
    raise TimeoutError('LSEG request exceeded 90 seconds; cached progress is preserved')

def fetch(ric, monday, friday):
    key = hashlib.sha256(f'{ric}|{monday}|{friday}|PT1M|endPeriod'.encode()).hexdigest()[:24]
    path = CACHE / f'{key}.pkl'
    if path.exists():
        return pd.read_pickle(path)
    start = pd.Timestamp(monday+' 09:57', tz=TZ).tz_convert('UTC').isoformat()
    end = pd.Timestamp(friday+' 16:00', tz=TZ).tz_convert('UTC').isoformat()
    signal.alarm(90)
    try:
        response = summaries.Definition(universe=ric, fields=FIELDS, interval='PT1M',
            start=start, end=end, count=10000, adjustments='exchangeCorrection',
            extended_params={'summaryTimestampLabel':'endPeriod'}).get_data()
        df = response.data.df
    except ld.errors.LDError as error:
        # Nonexistent RIC aliases may return an error. Entitlement/connection
        # problems must stop instead of silently skipping the strategy.
        message = str(error)
        if any(x in message.lower() for x in ['not entitled', 'access denied', 'unauthorized', '403', '401', 'connection', 'session', 'timeout']):
            raise
        print(f'Alias unavailable {ric}: {message[:160]}', flush=True)
        return pd.DataFrame(columns=FIELDS)
    finally:
        signal.alarm(0)
    if df is None or df.empty:
        return pd.DataFrame(columns=FIELDS)
    df = df.reindex(columns=FIELDS).apply(pd.to_numeric, errors='coerce')
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(TZ)
    for timestamp, group in df[df.index.duplicated(False)].groupby(level=0):
        if len(group.drop_duplicates()) > 1:
            raise ValueError(f'Conflicting rows: {ric} {timestamp}')
    df = df[~df.index.duplicated()].sort_index()
    # Keep observations and their preceding minute for bounded as-of quotes.
    keep = set(OBSERVATIONS) | {f'{h:02}:59' for h in range(10,16)}
    df = df[(df.index.dayofweek<5) & df.index.strftime('%H:%M').isin(keep)]
    df.to_pickle(path)
    time.sleep(.2)
    return df

def candidates(expiry, strike, kind):
    expiry = pd.Timestamp(expiry)
    month = chr((64 if kind=='call' else 76)+expiry.month)
    for day in dict.fromkeys([f'{expiry.day:02}', str(expiry.day)]):
        base = f'AAPL{month}{day}{expiry:%y}{round(strike*100):05}.U'
        # The archive suffix is the calendar month A-L, also for puts M-X.
        yield base+f'^{chr(64+expiry.month)}{expiry:%y}'
        yield base

def option(expiry, strike, kind, monday, friday):
    lookups = []
    when = pd.Timestamp(monday+' 09:59', tz=TZ)
    for ric in candidates(expiry,strike,kind):
        bars = fetch(ric,monday,friday)
        found = when in bars.index and bars.loc[when,['BID','ASK']].notna().all()
        lookups.append({'ric':ric,'signal_quote_found':bool(found)})
        if found:
            return {'ric':ric,'kind':kind,'strike':strike,'expiry':expiry,'bars':bars,'lookups':lookups}
    return {'ric':None,'kind':kind,'strike':strike,'expiry':expiry,
            'bars':pd.DataFrame(columns=FIELDS),'lookups':lookups}

def main():
    CACHE.mkdir(exist_ok=True)
    signal.signal(signal.SIGALRM,timed_out)
    warnings.filterwarnings('ignore',category=FutureWarning)
    warnings.filterwarnings('ignore',category=DeprecationWarning)
    signal.alarm(90)
    ld.open_session(name='desktop.workspace')
    signal.alarm(0)
    try:
        if not (CACHE/f'daily-{START}-{END}.pkl').exists():
            signal.alarm(90)
            raw = ld.get_history(SYMBOL,fields=['TRDPRC_1'],interval='daily',start=str((pd.Timestamp(START)-pd.Timedelta(days=1)).date()),end=END,adjustments='unadjusted')
            adjusted = ld.get_history(SYMBOL,fields=['TRDPRC_1'],interval='daily',start=str((pd.Timestamp(START)-pd.Timedelta(days=1)).date()),end=END,adjustments='CCH')
            signal.alarm(0)
            pd.to_pickle({'raw':raw,'adjusted':adjusted},CACHE/f'daily-{START}-{END}.pkl')
        # Filter by ex-date explicitly: announcement-date filtering omits the
        # May dividend, which was announced before this backtest began.
        signal.alarm(90)
        dividends = ld.get_data(SYMBOL,['TR.DivExDate','TR.DivPayDate','TR.DivUnadjustedGross','TR.DivAnnouncementDate'],
            parameters={'SDate':START,'EDate':END,'DateType':'ED','CAEventType':'SDI'})
        signal.alarm(0)
        daily = pd.read_pickle(CACHE/f'daily-{START}-{END}.pkl')
        daily['dividends'] = dividends
        pd.to_pickle(daily,CACHE/f'daily-{START}-{END}.pkl')
        for m in pd.date_range(START,END,freq='W-MON'):
            monday, friday = str(m.date()),str((m+pd.Timedelta(days=4)).date())
            path = CACHE/f'week-{monday}.pkl'
            if path.exists():
                saved = pd.read_pickle(path)
                if monday in HOLIDAYS or (saved['put'] and saved['put']['ric']):
                    print(f'Reuse {monday}',flush=True)
                    continue
            expiry = str((m+pd.Timedelta(days=3 if friday in HOLIDAYS else 4)).date())
            stock = fetch(SYMBOL,monday,friday)
            when = pd.Timestamp(monday+' 09:59',tz=TZ)
            week = {'monday':monday,'friday':friday,'expiry':expiry,'stock':stock,'put':None,'call':None}
            if monday not in HOLIDAYS:
                if when not in stock.index or pd.isna(stock.at[when,'TRDPRC_1']):
                    raise ValueError(f'Missing nonholiday stock signal {monday}; investigate coverage')
                spot = float(stock.at[when,'TRDPRC_1'])
                for kind,strike in [('put',math.floor(PUT_MONEYNESS*spot/STRIKE_GRID)*STRIKE_GRID),('call',math.ceil(CALL_MONEYNESS*spot/STRIKE_GRID)*STRIKE_GRID)]:
                    week[kind] = option(expiry,strike,kind,monday,friday)
            week['fetched_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            pd.to_pickle(week,path)
            print(f'{monday}: stock {len(stock)}; put {week["put"]["ric"] if week["put"] else "holiday"}; call {week["call"]["ric"] if week["call"] else "holiday"}',flush=True)
        export()
    finally:
        ld.close_session()

def export():
    daily = pd.read_pickle(CACHE/f'daily-{START}-{END}.pkl')
    pair = pd.concat([daily['raw'].iloc[:,0],daily['adjusted'].iloc[:,0]],axis=1).dropna()
    if pair.empty or not (pair.iloc[:,0]-pair.iloc[:,1]).abs().lt(.00001).all():
        raise ValueError('Raw / CCH split screen failed')
    closes = {str(pd.Timestamp(t).date()):float(v) for t,v in daily['raw'].iloc[:,0].dropna().items()}
    dividends = [{'ex_date':str(pd.Timestamp(r['Dividend Ex Date']).date()),
        'pay_date':str(pd.Timestamp(r['Dividend Pay Date']).date()),
        'announced':str(pd.Timestamp(r['Dividend Announcement Date']).date()),
        'amount':float(r['Gross Dividend Amount'])} for _,r in daily['dividends'].iterrows() if pd.notna(r['Dividend Ex Date'])]
    metadata, quotes = [], []
    for path in sorted(CACHE.glob('week-*.pkl')):
        week = pd.read_pickle(path)
        if not START <= week['monday'] <= END: continue
        row = {k:week[k] for k in ['monday','friday','expiry','fetched_at']}
        for kind in ['put','call']:
            row[kind] = {k:v for k,v in week[kind].items() if k!='bars'} if week[kind] else None
        metadata.append(row)
        for role,contract in [('stock',{'ric':SYMBOL,'bars':week['stock']}),('put',week['put']),('call',week['call'])]:
            if not contract or not contract['ric']: continue
            for t,r in contract['bars'].iterrows():
                quotes.append({'time':t.isoformat(),'ric':contract['ric'],'role':role,
                    **{f:float(r[f]) if pd.notna(r[f]) else None for f in FIELDS}})
    pd.DataFrame(quotes).to_csv(ROOT/'quotes.csv',index=False)
    pd.DataFrame(dividends).to_csv(ROOT/'dividends.csv',index=False)
    (ROOT/'inputs.json').write_text(json.dumps({'weeks':metadata,'closes':closes,'dividends':dividends},indent=2)+'\n')
    manifest = {'provider':'LSEG Workspace','start':START,'end':END,'interval':'PT1M',
        'timestamp_label':'endPeriod','timezone':TZ,'quote_rows':len(quotes),
        'split_check':f'Raw and CCH stock closes match on {len(pair)} dates',
        'completed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    (ROOT/'data_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Exported quotes.csv, inputs.json, dividends.csv and manifest.',flush=True)

if __name__=='__main__':
    main()
