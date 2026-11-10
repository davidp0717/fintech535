"""Save a Plotly figure specification with recent LSEG daily candlesticks."""
import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path

import lseg.data as ld
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


FIELDS = {"open": "OPEN_PRC", "high": "HIGH_1", "low": "LOW_1", "close": "TRDPRC_1"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rics", nargs="+", help="LSEG instrument codes")
    rics = list(dict.fromkeys(parser.parse_args().rics))
    load_dotenv(ROOT / ".env", interpolate=False)
    session = ld.session.platform.Definition(
        app_key=os.environ["LSEG_APP_KEY"],
        grant=ld.session.platform.GrantPassword(
            username=os.environ["LSEG_USERNAME"], password=os.environ["LSEG_PASSWORD"]
        ),
    ).get_session()
    end = date.today() - timedelta(days=1)
    try:
        session.open()
        ld.session.set_default(session)
        traces = []
        for ric in rics:
            frame = ld.get_history(universe=ric, fields=list(FIELDS.values()), interval="daily",
                                   start=str(end - timedelta(days=89)), end=str(end))
            if frame is None:
                raise ValueError(f"No daily prices for {ric}")
            bars = frame.reindex(columns=list(FIELDS.values())).dropna().sort_index()
            if bars.empty:
                raise ValueError(f"No complete daily OHLC bars for {ric}")
            traces.append({
                "type": "candlestick", "name": ric,
                "x": bars.index.strftime("%Y-%m-%d").tolist(),
                **{key: bars[field].astype(float).tolist() for key, field in FIELDS.items()},
            })
    finally:
        session.close()
    figure = {"data": traces, "layout": {
        "xaxis": {"type": "date", "rangeslider": {"visible": False}},
        "yaxis": {"title": {"text": "Price · instrument currency"}, "automargin": True},
        "showlegend": False, "margin": {"t": 20, "r": 15},
    }}
    output = Path(__file__).with_name("prices.json")
    output.with_suffix(".tmp").write_text(json.dumps(figure, allow_nan=False) + "\n")
    output.with_suffix(".tmp").replace(output)


if __name__ == "__main__":
    main()
