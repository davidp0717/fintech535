"""Generate next-session Sanji entry orders from completed GOOGL daily closes."""
import json
import math
from pathlib import Path
from datetime import datetime, timedelta, timezone

import exchange_calendars as xcals
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RIC = "GOOGL.O"
CONID = 208813720


def session_dates(now):
    calendar = xcals.get_calendar("XNYS")
    today = now.date().isoformat()
    latest = calendar.date_to_session(today, direction="previous")
    if calendar.session_close(latest) > pd.Timestamp(now):
        latest = calendar.previous_session(latest)
    return calendar, latest, calendar.next_session(latest)


def decide(closes, target):
    fast = closes.rolling(5).mean()
    slow = closes.rolling(20).mean()
    crossed = bool(fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1])
    orders = []
    if crossed:
        orders.append({
            "id": f"googl-sma5x20-entry-{target}",
            "for": target, "order_type": "lmt", "action": "BUY", "qty": 1,
            "underlying": CONID, "contract": "underlying", "ref": "open",
            "lmt_prc": round(float(closes.iloc[-1]), 2),
        })
    return orders, fast, slow


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def main():
    now = datetime.now(timezone.utc)
    calendar, latest, target = session_dates(now)
    target_date = target.date().isoformat()
    report = {
        "generated_at": now.isoformat(), "as_of": latest.date().isoformat(),
        "for": target_date, "ric": RIC, "conid": CONID,
        "status": "blocked", "reason": "", "orders": [], "series": [],
    }
    # If an old signal cannot be refreshed, publish an empty book rather than retain it.
    try:
        mapping = json.loads((ROOT / "price_history.json").read_text())
        if mapping[str(CONID)]["name"] != "ALPHABET INC":
            raise ValueError("The course conid mapping has changed.")
        history = mapping[str(CONID)]["price_history"]
        closes = pd.Series({day: bar["close"] for day, bar in history.items()}, dtype=float)
        closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
        closes = closes.sort_index()
        if closes.index.has_duplicates:
            raise ValueError("Duplicate session dates.")
        expected = calendar.sessions_window(latest, -21)
        closes = closes.reindex(expected)
        if len(closes) < 21 or any(not math.isfinite(x) or x <= 0 for x in closes):
            raise ValueError("Missing or invalid prices in the latest 21 completed sessions.")
        orders, fast, slow = decide(closes, target_date)
        report.update(
            status="order" if orders else "no_order",
            reason="The 5-day average crossed above the 20-day average." if orders
                   else "No new upward crossover on the latest completed session.",
            orders=orders, close=float(closes.iloc[-1]),
            sma5=float(fast.iloc[-1]), sma20=float(slow.iloc[-1]),
            previous_sma5=float(fast.iloc[-2]), previous_sma20=float(slow.iloc[-2]),
            series=[{"date": d.date().isoformat(), "close": float(c)}
                    for d, c in closes.items()],
        )
    except Exception as error:
        # Never publish service responses, tokens, or credential values.
        report["reason"] = f"Refresh failed ({type(error).__name__}). Orders cleared; inspect the workflow."
    save(ROOT / "open_orders.json", report["orders"])
    save(ROOT / "mkt/open_orders.json", report["orders"])
    save(ROOT / "assignment6/status.json", report)
    print(report["status"], report["reason"])
    if report["status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
