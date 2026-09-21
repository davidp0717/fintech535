"""Run the covered-call strategy and export the static website's results.
Run: .venv/bin/python assignment2/backtest.py
All trades below are simulated. The cached prices come from LSEG.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
INITIAL_CASH = 40000.0
MULTIPLIER = 100


def number(value):
    return pd.notna(value) and math.isfinite(float(value))


def midpoint(row):
    """A valid two-sided quote is required. Never fill from a stale prior bar."""
    if row is None:
        return None
    bid, ask = row.get('BID'), row.get('ASK')
    if not number(bid) or not number(ask) or bid < 0 or ask <= 0 or bid > ask:
        return None
    return float((bid + ask) / 2)


def has_trade(row):
    if row is None or not number(row.get('TRDPRC_1')) or row['TRDPRC_1'] <= 0:
        return False
    # Where volume exists, require activity rather than a carried trade field.
    volume = row.get('ACVOL_UNS')
    return not number(volume) or volume > 0


def occ_symbol(expiry, strike):
    return f'AAPL {pd.Timestamp(expiry):%y%m%d}C{round(strike * 1000):08d}'


def simulate(weeks, initial_cash=INITIAL_CASH):
    cash, shares = float(initial_cash), 0
    short_call = None
    last_mid, last_quote_time = None, None
    blotter, ledger, decisions, scatter = [], [], [], []

    def book(time, instrument, side, qty, fill, cash_delta, note, limit=None, occ=''):
        nonlocal cash
        cash += cash_delta
        blotter.append({'time': time.isoformat(), 'instrument': instrument, 'occ': occ,
                        'side': side, 'qty': qty, 'limit': limit, 'fill': fill,
                        'cash_delta': cash_delta, 'cash_after': cash, 'note': note})

    for week in weeks:
        entry = pd.Timestamp(week['monday'] + ' 11:00', tz='America/New_York')
        expiry_time = pd.Timestamp(week['expiry'] + ' 16:00', tz='America/New_York')
        stock = week['stock']
        options = week['options']
        # A failed call request stays a missing candidate, not a zero-price option.
        selected = next((c for c in options if c['strike'] == week.get('selected_strike')), None)
        decision = {'week': week['monday'], 'expiry': week['expiry'],
                    'strike': week.get('selected_strike'), 'ric': selected['ric'] if selected else None,
                    'status': 'Skipped', 'reason': week.get('skip', 'Missing Monday entry bar')}
        decisions.append(decision)

        for time, stock_row in stock.iterrows():
            if not has_trade(stock_row):
                continue
            spot = float(stock_row['TRDPRC_1'])
            # Diagnostic: use all nearby requested calls, not only traded calls.
            for contract in options:
                bars = contract['bars']
                if time not in bars.index or abs(contract['strike'] / spot - 1) > .05:
                    continue
                row = bars.loc[time]
                mid = midpoint(row)
                if mid is not None and has_trade(row):
                    scatter.append({'time': time.isoformat(), 'ric': contract['ric'],
                                    'strike': contract['strike'], 'mid': mid,
                                    'trade': float(row['TRDPRC_1'])})

            if time == entry:
                if short_call is not None:
                    raise RuntimeError('Cannot open a second short call before expiry')
                bars = selected['bars'] if selected else pd.DataFrame()
                quote = bars.loc[time] if time in bars.index else None
                mid = midpoint(quote)
                if mid is None:
                    decision['reason'] = 'No valid bid and ask on the selected contract at Monday 11:00'
                elif mid > spot:
                    decision['reason'] = 'Option midpoint exceeds stock price; quote rejected'
                else:
                    # Test the complete proposed position before booking either leg.
                    proposed_cash = cash - (100 * spot if shares == 0 else 0) + 100 * mid
                    proposed_nav = proposed_cash + 100 * spot - 100 * mid
                    initial_margin = .50 * 100 * spot
                    if proposed_nav < initial_margin:
                        decision['reason'] = 'Insufficient Reg T available funds; neither leg booked'
                    else:
                        if shares == 0:
                            book(time, 'AAPL.O', 'BUY', 100, spot, -100 * spot,
                                 'Monday 11:00: buy 100 shares because flat; same-bar stock print')
                            shares = 100
                        short_call = selected
                        last_mid, last_quote_time = mid, time
                        book(time, selected['ric'], 'SELL', 1, mid, 100 * mid,
                             'Monday 11:00: sell covered call at same-bar midpoint; wait through expiry',
                             limit=mid, occ=occ_symbol(week['expiry'], selected['strike']))
                        decision.update(status='Entered', reason='Both prices available and Reg T initial margin satisfied')

            if short_call is not None:
                bars = short_call['bars']
                current_mid = midpoint(bars.loc[time]) if time in bars.index else None
                if current_mid is not None:
                    last_mid, last_quote_time = current_mid, time
                if time == expiry_time:
                    strike = short_call['strike']
                    symbol = occ_symbol(week['expiry'], strike)
                    if spot > strike:
                        book(time, short_call['ric'], 'ASSIGN', 1, 0, 0,
                             f'Friday close {spot:.4f} > strike {strike:g}; physically settle call', occ=symbol)
                        book(time, 'AAPL.O', 'SELL', 100, strike, 100 * strike,
                             'Deliver the 100 covered shares at strike; account is now flat')
                        shares = 0
                        decision['outcome'] = 'Assigned'
                    else:
                        book(time, short_call['ric'], 'EXPIRE', 1, 0, 0,
                             f'Friday close {spot:.4f} <= strike {strike:g}; retain shares', occ=symbol)
                        decision['outcome'] = 'Expired'
                    short_call, last_mid, last_quote_time = None, None, None

            lmv = shares * spot
            option_mv = -100 * last_mid if short_call else 0.0
            nav = cash + lmv + option_mv
            quote_age = (time - last_quote_time).total_seconds() / 3600 if short_call else 0
            ledger.append({'time': time.isoformat(), 'cash': cash, 'shares': shares,
                           'short_calls': 1 if short_call else 0,
                           'ric': short_call['ric'] if short_call else '',
                           'strike': short_call['strike'] if short_call else None,
                           'expiry': short_call['expiry'] if short_call else '',
                           'stock_mark': spot, 'option_mark': last_mid if short_call else None,
                           'quote_age_hours': quote_age, 'stale_mark': quote_age > 0,
                           'stock_mv': lmv, 'option_mv': option_mv, 'nav': nav,
                           'initial': .50 * lmv, 'maintenance': .25 * lmv,
                           'available': nav - .50 * lmv, 'excess': nav - .25 * lmv})
        if short_call is not None:
            raise RuntimeError(f'Missing expiry stock print for {week["expiry"]}; cannot invent settlement')
    return {'initial_cash': initial_cash, 'blotter': blotter, 'ledger': ledger,
            'decisions': decisions, 'scatter': scatter}


def regression(points):
    if len(points) < 3:
        return None
    x = np.array([p['mid'] for p in points])
    y = np.array([p['trade'] for p in points])
    if np.var(x) == 0 or np.var(y) == 0:
        return None
    slope, intercept = np.polyfit(x, y, 1)
    residuals = y - (slope * x + intercept)
    return {'n': len(x), 'slope': float(slope), 'intercept': float(intercept),
            'r2': float(1 - (residuals ** 2).sum() / ((y - y.mean()) ** 2).sum()),
            'median_gap': float(np.median(np.abs(y - x))),
            'xmin': float(x.min()), 'xmax': float(x.max())}


def validate(result):
    """Accounting identities must hold for every ledger row and cash event."""
    running_cash = result['initial_cash']
    for event in result['blotter']:
        running_cash += event['cash_delta']
        assert math.isclose(running_cash, event['cash_after'], abs_tol=1e-7)
    for row in result['ledger']:
        assert row['shares'] in (0, 100)
        assert row['short_calls'] in (0, 1)
        assert row['shares'] >= 100 * row['short_calls'], 'Uncovered short call'
        assert math.isclose(row['nav'], row['cash'] + row['stock_mv'] + row['option_mv'], abs_tol=1e-7)
        assert math.isclose(row['initial'], .5 * row['stock_mv'], abs_tol=1e-7)
        assert math.isclose(row['maintenance'], .25 * row['stock_mv'], abs_tol=1e-7)
        assert math.isclose(row['available'], row['nav'] - row['initial'], abs_tol=1e-7)
        assert math.isclose(row['excess'], row['nav'] - row['maintenance'], abs_tol=1e-7)
    if result['ledger']:
        assert math.isclose(running_cash, result['ledger'][-1]['cash'], abs_tol=1e-7)


def main():
    mondays = pd.date_range('2026-07-13', periods=10, freq='W-MON')
    weeks = [pd.read_pickle(ROOT / 'cache' / f'{m:%Y-%m-%d}.pkl') for m in mondays]
    result = simulate(weeks)
    validate(result)
    result['regression'] = regression(result['scatter'])
    result['source'] = {'provider': 'LSEG Workspace', 'ticker': 'AAPL.O',
                        'start': '2026-07-13', 'end': '2026-09-18',
                        'fetched_at': max(w['fetched_at'] for w in weeks),
                        'interval': 'hourly; explicitly end-labeled; New York time',
                        'contracts_with_data': sum(bool(c['ric']) for w in weeks for c in w['options']),
                        'split_check': pd.read_pickle(ROOT / 'cache' / 'split_check.pkl')['status']}
    result['summary'] = {
        'final_nav': result['ledger'][-1]['nav'],
        'return_pct': 100 * (result['ledger'][-1]['nav'] / INITIAL_CASH - 1),
        'premium': sum(e['cash_delta'] for e in result['blotter'] if e['side'] == 'SELL' and e['qty'] == 1),
        'entered': sum(d['status'] == 'Entered' for d in result['decisions']),
        'assigned': sum(d.get('outcome') == 'Assigned' for d in result['decisions']),
        'expired': sum(d.get('outcome') == 'Expired' for d in result['decisions']),
        'stale_marks': sum(r['stale_mark'] for r in result['ledger']),
        'negative_available': sum(r['available'] < 0 for r in result['ledger']),
        'negative_excess': sum(r['excess'] < 0 for r in result['ledger']),
        'min_available': min(r['available'] for r in result['ledger']),
        'min_excess': min(r['excess'] for r in result['ledger'])}
    navs = np.array([INITIAL_CASH] + [r['nav'] for r in result['ledger']])
    result['summary']['max_drawdown_pct'] = float(100 * (navs / np.maximum.accumulate(navs) - 1).min())
    # Static snapshot: no Workspace credentials or connection are used on GitHub Pages.
    (ROOT / 'book.js').write_text('const BOOK = ' + json.dumps(result, allow_nan=False) + ';\n')
    for table in ['blotter', 'ledger', 'decisions']:
        pd.DataFrame(result[table]).to_csv(ROOT / f'{table}.csv', index=False)
    print(json.dumps(result['summary'], indent=2))
    print('Regression:', result['regression'])
    print('Validated and exported book.js, blotter.csv, ledger.csv, decisions.csv')


if __name__ == '__main__':
    main()
