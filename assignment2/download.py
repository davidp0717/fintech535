"""Download the ten-week AAPL tape. Keep Workspace open and signed in.
Run from fintech535: .venv/bin/python assignment2/download.py
Each week's pickle is saved locally so an interrupted download can resume.
"""
import datetime as dt
import math
import warnings
from pathlib import Path

import lseg.data as ld
import pandas as pd
from lseg.data.content.historical_pricing import summaries

FOLDER = Path(__file__).parent / 'cache'
MONDAYS = pd.date_range('2026-07-13', periods=10, freq='W-MON')
FIELDS = ['BID', 'ASK', 'TRDPRC_1', 'ACVOL_UNS', 'NUM_MOVES']


def get_bars(ric, monday, friday):
    """Request end-labeled UTC hours, then keep regular-session US stock hours."""
    response = summaries.Definition(
        universe=ric, fields=FIELDS, interval='PT1H',
        start=f'{monday:%Y-%m-%d}T13:30:00Z', end=f'{friday:%Y-%m-%d}T20:00:00Z',
        adjustments='exchangeCorrection',
        extended_params={'summaryTimestampLabel': 'endPeriod'}).get_data()
    frame = response.data.df
    if frame is None or frame.empty:
        return pd.DataFrame(columns=FIELDS)
    frame = frame.reindex(columns=FIELDS).apply(pd.to_numeric, errors='coerce')
    frame.index = pd.to_datetime(frame.index, utc=True).tz_convert('America/New_York')
    # Some LSEG responses repeat the first timestamp. Conflicts require investigation.
    for timestamp, group in frame[frame.index.duplicated(False)].groupby(level=0):
        if len(group.drop_duplicates()) > 1:
            raise ValueError(f'Conflicting duplicate bars: {ric} {timestamp}')
    frame = frame.loc[~frame.index.duplicated()].sort_index()
    frame = frame.between_time('10:00', '16:00')
    return frame.loc[frame.index.dayofweek < 5]


def ric_candidates(expiry, strike):
    """Try the documented form, zero-padded day, and not-yet-archived form."""
    month = chr(64 + expiry.month)
    rics = []
    for day in [str(expiry.day), f'{expiry.day:02d}']:
        base = f'AAPL{month}{day}{expiry:%y}{round(strike * 100):05d}.U'
        for ric in [f'{base}^{month}{expiry:%y}', base]:
            if ric not in rics:
                rics.append(ric)
    return rics


def main():
    FOLDER.mkdir(exist_ok=True)
    warnings.filterwarnings('ignore', category=FutureWarning, module='lseg.data')
    ld.open_session(name='desktop.workspace')
    try:
        if not (FOLDER / 'split_check.pkl').exists():
            raw = ld.get_history('AAPL.O', fields=['TRDPRC_1'], interval='daily',
                                 start='2026-07-13', end='2026-09-18', adjustments='unadjusted')
            adjusted = ld.get_history('AAPL.O', fields=['TRDPRC_1'], interval='daily',
                                      start='2026-07-13', end='2026-09-18', adjustments='CCH')
            pair = pd.concat([raw.iloc[:, 0], adjusted.iloc[:, 0]], axis=1).dropna()
            if pair.empty or not (pair.iloc[:, 0] - pair.iloc[:, 1]).abs().lt(.00001).all():
                raise RuntimeError('Stock capital-change check failed; investigate before continuing')
            pd.to_pickle({'status': 'CCH-adjusted and raw closes match', 'dates': len(pair)}, FOLDER / 'split_check.pkl')
        for monday in MONDAYS:
            friday = monday + pd.Timedelta(days=4)
            filename = FOLDER / f'{monday:%Y-%m-%d}.pkl'
            if filename.exists():
                print(f'Reusing {filename.name}', flush=True)
                continue
            stock = get_bars('AAPL.O', monday, friday)
            entry = pd.Timestamp(f'{monday:%Y-%m-%d} 11:00', tz='America/New_York')
            result = {'monday': str(monday.date()), 'expiry': str(friday.date()),
                      'stock': stock, 'options': [], 'request_errors': [],
                      'fetched_at': dt.datetime.now(dt.timezone.utc).isoformat()}
            if entry not in stock.index or pd.isna(stock.at[entry, 'TRDPRC_1']):
                result['skip'] = 'No Monday 11:00 stock bar (holiday or missing data)'
            else:
                spot = float(stock.at[entry, 'TRDPRC_1'])
                selected = math.ceil(spot / 2.5) * 2.5
                result['selected_strike'] = selected
                for offset in range(-3, 4):
                    strike = selected + offset * 2.5
                    contract = {'strike': strike, 'expiry': str(friday.date()), 'ric': None, 'bars': pd.DataFrame()}
                    for ric in ric_candidates(friday, strike):
                        try:
                            bars = get_bars(ric, monday, friday)
                            if not bars[['BID', 'ASK', 'TRDPRC_1']].notna().any().any():
                                continue
                            contract.update({'ric': ric, 'bars': bars})
                            break
                        except ld.errors.LDError as error:
                            result['request_errors'].append({'ric': ric, 'reason': str(error)[:300]})
                    result['options'].append(contract)
                    print(f'{monday:%m-%d} strike {strike:g}: {contract["ric"] or "unavailable"}', flush=True)
            pd.to_pickle(result, filename)
            print(f'Saved {filename.name}', flush=True)
    finally:
        ld.close_session()


if __name__ == '__main__':
    main()
