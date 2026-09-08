"""Step 1: download daily prices from Workspace and save a local pickle cache.
Run: .venv/bin/python download_data.py
Keep Workspace open and signed in. Reruns reuse completed request batches.
"""
import datetime as dt
import math
import pickle
import warnings
from pathlib import Path

import lseg.data as ld
import pandas as pd

ROOT = Path(__file__).parent
CACHE = ROOT / "option_pipeline_data.pkl"
BATCH_FOLDER = ROOT / "cache_batches"
START = "2026-06-15"
END = "2026-09-04"
FIELDS = ["MID_PRICE", "TRDPRC_1"]


def make_ric(expiry, strike, option_type):
    """The suffix uses A-L for BOTH puts and calls (LSEG's actual scheme)."""
    month = chr(64 + expiry.month)
    code = month if option_type == "Call" else chr(76 + expiry.month)
    return f"UUUU{code}{expiry:%d%y}{round(strike * 100):05d}.U^{month}{expiry:%y}"


def fetch(rics, fields):
    return ld.get_history(universe=rics, fields=fields, interval="daily",
                          start=START, end=END, adjustments="unadjusted")


def split_frame(frame, rics):
    """Store a separate two-column DataFrame for each requested contract."""
    result = {}
    for ric in rics:
        if frame is None or frame.empty:
            continue
        if isinstance(frame.columns, pd.MultiIndex):
            if ric not in frame.columns.get_level_values(0):
                continue
            contract = frame[ric].copy()
        elif len(rics) == 1:
            contract = frame.copy()
        else:
            raise ValueError("Unexpected multi-contract response; retry individually")
        contract = contract.reindex(columns=FIELDS)
        # Keep NaN values. An all-empty candidate is not proof of a listing.
        if contract.notna().any().any():
            result[ric] = contract
    return result


def main():
    if CACHE.exists():
        print(f"Using existing cache: {CACHE.name}")
        return
    BATCH_FOLDER.mkdir(exist_ok=True)
    warnings.filterwarnings("ignore", category=FutureWarning, module="lseg.data")
    ld.open_session(name="desktop.workspace")
    try:
        stock = fetch(["UUUU.K"], ["OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1"])
        if stock.empty:
            raise RuntimeError("No stock history returned")
        # Compare capital-change-adjusted and raw prices to flag possible splits.
        adjusted = ld.get_history(universe="UUUU.K", fields=["TRDPRC_1"],
                                 interval="daily", start=START, end=END, adjustments="CCH")
        comparison = pd.concat([stock["TRDPRC_1"], adjusted["TRDPRC_1"]], axis=1).dropna()
        if comparison.empty:
            raise RuntimeError("Could not check capital-change adjustments")
        if not (comparison.iloc[:, 0] - comparison.iloc[:, 1]).abs().lt(0.00001).all():
            raise RuntimeError("Capital-change adjustments found: investigate splits before downloading options")
        low = math.floor(float(stock["LOW_1"].min()) * 2) / 2
        high = math.ceil(float(stock["HIGH_1"].max()) * 2) / 2
        strikes = [n / 2 for n in range(round(low * 2), round(high * 2) + 1)]
        expiries = pd.date_range(START, END, freq="W-FRI")
        candidates = [make_ric(expiry, strike, kind) for expiry in expiries
                      for strike in strikes for kind in ["Call", "Put"]]
        print(f"UUUU range ${low}-${high}; {len(candidates)} candidates", flush=True)
        options = {}
        failures = []
        for offset in range(0, len(candidates), 25):
            batch = candidates[offset:offset + 25]
            batch_file = BATCH_FOLDER / f"batch_{offset:04d}.pkl"
            if batch_file.exists():
                saved = pd.read_pickle(batch_file)
                if saved["rics"] != batch or saved["start"] != START or saved["end"] != END:
                    raise ValueError("Batch cache settings changed; use a new cache folder")
                found, errors = saved["options"], saved["failures"]
            else:
                found, errors = {}, []
                try:
                    found = split_frame(fetch(batch, FIELDS), batch)
                except Exception:
                    # Synthetic identifiers can be invalid; one failure must not lose a batch.
                    for ric in batch:
                        try:
                            found.update(split_frame(fetch([ric], FIELDS), [ric]))
                        except Exception as error:
                            errors.append({"ric": ric, "error_type": type(error).__name__})
                pd.to_pickle({"rics": batch, "start": START, "end": END,
                              "options": found, "failures": errors}, batch_file)
            options.update(found)
            failures.extend(errors)
            print(f"{min(offset + 25, len(candidates))}/{len(candidates)} requested; "
                  f"{len(options)} contracts with data", flush=True)
        if not options:
            raise RuntimeError("No options returned; refusing to save an empty final cache")
        payload = {"stock": stock, "options": options, "candidates": candidates,
                   "failures": failures, "ticker": "UUUU", "start": START, "end": END,
                   "strikes": strikes, "expiries": [str(d.date()) for d in expiries],
                   "split_check": "CCH-adjusted and unadjusted stock closes match throughout the window",
                   "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        with CACHE.open("wb") as file:
            pickle.dump(payload, file)
        print(f"Saved {len(options)} contracts to {CACHE.name}")
    finally:
        ld.close_session()


if __name__ == "__main__":
    main()
