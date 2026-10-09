"""Download historical quotes; never calculate returns or optimize parameters here.
Run from the project root: .venv/bin/python assignment3/download.py
"""
import datetime as dt
import hashlib
import json
import math
import warnings
from pathlib import Path

import lseg.data as ld
import pandas as pd
from lseg.data.content.historical_pricing import summaries
from config import START, END, LONG_EXPIRY, LONG_MONEYNESS, SHORT_MONEYNESS, LONG_GRID, SHORT_GRID, TZ

ROOT = Path(__file__).parent
CACHE = ROOT / 'cache'
FIELDS = ['BID', 'ASK', 'TRDPRC_1', 'ACVOL_UNS']


def fetch(ric, monday, friday):
    """Use one-minute bars ending at 09:59 (signal) and 10:00 (execution/mark)."""
    key = hashlib.sha256(f'{ric}|{monday}|{friday}|PT1M|endPeriod'.encode()).hexdigest()[:20]
    path = CACHE / f'{key}.pkl'
    if path.exists():
        return pd.read_pickle(path)
    start = pd.Timestamp(monday + ' 09:57', tz=TZ).tz_convert('UTC').isoformat()
    end = pd.Timestamp(friday + ' 10:00', tz=TZ).tz_convert('UTC').isoformat()
    try:
        response = summaries.Definition(universe=ric, fields=FIELDS, interval='PT1M',
            start=start, end=end, count=10000, adjustments='exchangeCorrection',
            extended_params={'summaryTimestampLabel': 'endPeriod'}).get_data()
        df = response.data.df
        if df is None or df.empty:
            return pd.DataFrame(columns=FIELDS)
    except ld.errors.LDError as error:
        print(f'Unavailable {ric}: {str(error)[:110]}', flush=True)
        return pd.DataFrame(columns=FIELDS)
    df = df.reindex(columns=FIELDS).apply(pd.to_numeric, errors='coerce')
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(TZ)
    for timestamp, group in df[df.index.duplicated(False)].groupby(level=0):
        if len(group.drop_duplicates()) > 1:
            raise ValueError(f'Conflicting duplicate bars: {ric} {timestamp}')
    df = df[~df.index.duplicated()].sort_index()
    times = df.index.strftime('%H:%M')
    df = df[(df.index.dayofweek < 5) & ((times == '09:59') | (times == '10:00'))]
    pd.to_pickle(df, path)
    return df


def candidates(expiry, strike):
    expiry = pd.Timestamp(expiry)
    month = chr(64 + expiry.month)
    for day in dict.fromkeys([f'{expiry.day:02d}', str(expiry.day)]):
        base = f'AAPL{month}{day}{expiry:%y}{round(strike * 100):05d}.U'
        if expiry.date() < dt.date(2026, 10, 9):
            yield base + f'^{month}{expiry:%y}'
        yield base


def option(expiry, strike, monday, friday, preferred=None):
    rics = list(dict.fromkeys(([preferred] if preferred else []) + list(candidates(expiry, strike))))
    signal = pd.Timestamp(monday + ' 09:59', tz=TZ)
    available = []
    for ric in rics:
        bars = fetch(ric, monday, friday)
        available.append({'ric': ric, 'rows': len(bars)})
        # Choose an identifier using only the signal-time quote, never future coverage.
        if signal in bars.index and bars.loc[signal, ['BID','ASK']].notna().all():
            return {'ric': ric, 'strike': strike, 'expiry': expiry, 'bars': bars, 'lookups': available}
    return {'ric': None, 'strike': strike, 'expiry': expiry,
            'bars': pd.DataFrame(columns=FIELDS), 'lookups': available}


def main():
    CACHE.mkdir(exist_ok=True)
    warnings.filterwarnings('ignore', category=FutureWarning)
    ld.open_session(name='desktop.workspace')
    try:
        dividends = ld.get_data('AAPL.O', ['TR.DivExDate', 'TR.DivPayDate',
            'TR.DivUnadjustedGross', 'TR.DivAnnouncementDate'],
            parameters={'SDate': START, 'EDate': END})
        dividends.to_pickle(CACHE / 'dividends.pkl')
        pd.to_pickle({
            'raw': ld.get_history('AAPL.O', fields=['TRDPRC_1'], interval='daily', start=START, end=END, adjustments='unadjusted'),
            'adjusted': ld.get_history('AAPL.O', fields=['TRDPRC_1'], interval='daily', start=START, end=END, adjustments='CCH')
        }, CACHE / 'split_check.pkl')
        long_strike, long_ric = None, None
        for m in pd.date_range(START, END, freq='W-MON'):
            monday, friday = str(m.date()), str((m + pd.Timedelta(days=4)).date())
            stock = fetch('AAPL.O', monday, friday)
            signal = pd.Timestamp(monday + ' 09:59', tz=TZ)
            result = {'monday': monday, 'friday': friday, 'stock': stock, 'short': None}
            if signal in stock.index and pd.notna(stock.at[signal, 'TRDPRC_1']):
                spot = float(stock.at[signal, 'TRDPRC_1'])
                if long_strike is None:
                    long_strike = math.floor(LONG_MONEYNESS * spot / LONG_GRID) * LONG_GRID
                strike = math.ceil(SHORT_MONEYNESS * spot / SHORT_GRID) * SHORT_GRID
                result['short'] = option(friday, strike, monday, friday)
            if long_strike is None:
                raise RuntimeError('No initial signal: cannot choose the long call')
            if long_ric is None:
                contract = option(LONG_EXPIRY, long_strike, monday, friday)
                if contract['ric'] is None:
                    raise RuntimeError('Predetermined long call has no signal quote; do not substitute using future performance')
                long_ric = contract['ric']
            else:
                # Holiday Monday does not prevent valuing the long on later days.
                contract = {'ric': long_ric, 'strike': long_strike, 'expiry': LONG_EXPIRY,
                            'bars': fetch(long_ric, monday, friday)}
            result['long'] = contract
            result['fetched_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            pd.to_pickle(result, CACHE / f'week-{monday}.pkl')
            print(f'{monday}: stock {len(stock)}, long {len(contract["bars"])}, short {result["short"]["ric"] if result["short"] else "holiday/missing signal"}', flush=True)
        manifest = {'provider': 'LSEG Workspace', 'start': START, 'end': END,
                    'interval': 'PT1M', 'timestamp_label': 'endPeriod', 'timezone': TZ,
                    'long_ric': long_ric, 'long_strike': long_strike, 'long_expiry': LONG_EXPIRY,
                    'completed_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        (ROOT / 'data_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    finally:
        ld.close_session()

if __name__ == '__main__':
    main()
