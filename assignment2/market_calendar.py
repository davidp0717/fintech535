"""US equity sessions for the fixed November 2025–October 2026 sample.
Source: NYSE 2025–2027 holiday / early-close calendar.
https://ir.theice.com/press/news-details/2024/NYSE-Group-Announces-2025-2026-and-2027-Holiday-and-Early-Closings-Calendar/default.aspx
"""
import pandas as pd
HOLIDAYS = {'2025-11-27', '2025-12-25', '2026-01-01', '2026-01-19',
    '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07'}
EARLY_CLOSES = {'2025-11-28', '2025-12-24'}
def close_clock(day):
    return '13:00' if str(day)[:10] in EARLY_CLOSES else '16:00'
def expiry_day(monday):
    day = pd.Timestamp(monday) + pd.Timedelta(days=4)
    while str(day.date()) in HOLIDAYS:
        day -= pd.Timedelta(days=1)
    return str(day.date())
def next_session(day):
    day = pd.Timestamp(day) + pd.Timedelta(days=1)
    while day.dayofweek > 4 or str(day.date()) in HOLIDAYS:
        day += pd.Timedelta(days=1)
    return day
