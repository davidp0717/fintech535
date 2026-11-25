"""Update the gold/corn trend study using completed common daily closes."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

MARKETS = {"Gold": "GC=F", "Corn": "ZC=F"}
COST = 0.0005
NY = ZoneInfo("America/New_York")


def history(symbol, now):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range=5y&interval=1d"
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
        data = json.load(response)["chart"]["result"][0]
    dates = pd.to_datetime(data["timestamp"], unit="s", utc=True).tz_convert(data["meta"]["exchangeTimezoneName"]).normalize().tz_localize(None)
    series = pd.Series(data["indicators"]["quote"][0]["close"], index=dates, dtype=float)
    # A manual run earlier in the day should never use an unfinished daily bar.
    cutoff = now.date() if now.hour >= 19 else now.date() - timedelta(days=1)
    series = series.loc[series.index.date <= cutoff].dropna().sort_index()
    series = series[~series.index.duplicated(keep="last")]
    if series.empty or (series <= 0).any() or (cutoff - series.index[-1].date()).days > 5:
        raise ValueError(f"Invalid or stale history for {symbol}")
    return series


def main():
    now = datetime.now(NY)
    prices = pd.concat({m: history(s, now) for m, s in MARKETS.items()}, axis=1).dropna()
    momentum = prices.pct_change(63)
    months = prices.index.to_period("M")
    rebalance = ~months.duplicated()
    decisions = momentum.shift(1).loc[rebalance].dropna()
    positions = decisions.apply(lambda col: (col > 0).astype(int) - (col < 0).astype(int))
    weights = positions.reindex(prices.index).ffill().dropna() / 2
    durations = []
    for market in MARKETS:
        held = weights[market]
        groups = held.ne(held.shift()).cumsum()
        finished = held[groups < groups.iloc[-1]]
        durations.extend(finished[finished != 0].groupby(groups).size().tolist())
    gross = (weights.shift(1) * prices.pct_change().reindex(weights.index)).sum(axis=1)
    turnover = weights.diff().fillna(weights.iloc[0]).abs().sum(axis=1)
    net = gross - COST * turnover
    passive = prices.pct_change().reindex(weights.index).mean(axis=1)
    passive.iloc[0] = 0
    active = net - passive
    days = momentum.dropna().tail(252)
    output = dict(as_of=str(prices.index[-1].date()), start=str(weights.index[0].date()),
                  average_hold=sum(durations) / len(durations) if durations else None,
                  dates=days.index.strftime("%Y-%m-%d").tolist(),
                  momentum={m:(days[m]*100).round(2).tolist() for m in MARKETS},
                  position=positions.iloc[-1].to_dict(), rebalance=str(positions.index[-1].date()),
                  gross_active=100*252*(gross-passive).mean(), net_active=100*252*active.mean(),
                  drag=100*252*COST*turnover.mean(), recent=100*active.tail(252).sum())
    path = Path(__file__).with_name("tracker.json")
    path.with_suffix(".tmp").write_text(json.dumps(output, allow_nan=False)+"\n")
    path.with_suffix(".tmp").replace(path)


if __name__ == "__main__":
    main()
