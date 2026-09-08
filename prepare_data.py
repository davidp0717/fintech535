"""Step 2: load the LSEG pickle, parse RICs, and write browser-friendly JSON.
Run: .venv/bin/python prepare_data.py
Missing prices stay null; we never interpolate or carry prices forward.
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent


def parse_option_ric(ric):
    """Read a standard US option RIC, including its expired-contract suffix."""
    match = re.fullmatch(r"([A-Z]+)([A-X])(\d{2})(\d{2})(\d{5})\.U\^([A-X])(\d{2})", ric)
    if not match:
        raise ValueError(f"Unrecognized option RIC: {ric}")
    root, code, day, year, strike, suffix, suffix_year = match.groups()
    month = (ord(code) - ord("A")) % 12 + 1
    if (ord(suffix) - ord("A")) % 12 + 1 != month or suffix_year != year:
        raise ValueError(f"Expiry suffix does not match contract: {ric}")
    return {"underlying": root, "expiry": f"20{year}-{month:02d}-{day}",
            "type": "Call" if code <= "L" else "Put", "strike": int(strike) / 100}


def main():
    # Only load the trusted pickle created locally by download_data.py.
    cache = pd.read_pickle(ROOT / "option_pipeline_data.pkl")
    dates = cache["stock"].dropna(how="all").index
    pieces = []
    contracts = []
    for ric, prices in cache["options"].items():
        info = parse_option_ric(ric)
        observed = prices.dropna(how="all")
        first_seen = observed.index.min().strftime("%Y-%m-%d")
        contracts.append({"ric": ric, **info, "first_seen": first_seen})
        # Use stock trading dates, not a calendar with weekends and holidays.
        frame = prices.reindex(dates).copy()
        frame = frame.loc[frame.index <= pd.Timestamp(info["expiry"])]
        frame["date"] = frame.index.strftime("%Y-%m-%d")
        frame["ric"] = ric
        for name, value in info.items():
            frame[name] = value
        frame["eligible"] = frame["date"] >= first_seen
        pieces.append(frame.reset_index(drop=True))
    long = pd.concat(pieces, ignore_index=True)
    long = long[["date", "ric", "underlying", "expiry", "type", "strike",
                 "MID_PRICE", "TRDPRC_1", "eligible"]]
    long = long.sort_values(["date", "type", "expiry", "strike"])
    long.to_csv(ROOT / "options_long.csv", index=False)
    # Pandas serializes NaN as JSON null, rather than the invalid JSON value NaN.
    rows = json.loads(long.to_json(orient="records", double_precision=8))
    stock = {day.strftime("%Y-%m-%d"): float(row["TRDPRC_1"])
             for day, row in cache["stock"].iterrows() if pd.notna(row["TRDPRC_1"])}
    data = {"ticker": cache["ticker"], "start": cache["start"], "end": cache["end"],
            "fetched_at": cache["fetched_at"], "strikes": cache["strikes"],
            "expiries": cache["expiries"], "stock": stock, "contracts": contracts,
            "candidate_count": len(cache["candidates"]), "failure_count": len(cache["failures"]),
            "split_check": cache["split_check"], "rows": rows}
    (ROOT / "data.json").write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))
    print(f"Exported {len(long):,} rows for {len(contracts)} contracts")


if __name__ == "__main__":
    main()
