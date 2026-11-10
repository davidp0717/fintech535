"""Save a Plotly figure specification with recent LSEG daily last prices."""
import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path

import lseg.data as ld
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


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
            frame = ld.get_history(universe=ric, fields=["TRDPRC_1"], interval="daily",
                                   start=str(end - timedelta(days=89)), end=str(end))
            if frame is None or frame.empty or frame.iloc[:, 0].dropna().empty:
                raise ValueError(f"No daily prices for {ric}")
            prices = frame.iloc[:, 0]
            traces.append(dict(type="scatter", mode="lines", name=ric,
                               x=prices.index.strftime("%Y-%m-%d").tolist(),
                               y=[None if missing else float(value)
                                  for value, missing in zip(prices, prices.isna())]))
    finally:
        session.close()
    figure = {"data": traces, "layout": {
        "hovermode": "x unified", "xaxis": {"type": "date"},
        "yaxis": {"title": {"text": "Last price · instrument currency"}, "automargin": True},
        "legend": {"orientation": "h"}, "margin": {"t": 20, "r": 15},
    }}
    output = Path(__file__).with_name("prices.json")
    output.with_suffix(".tmp").write_text(json.dumps(figure, allow_nan=False) + "\n")
    output.with_suffix(".tmp").replace(output)


if __name__ == "__main__":
    main()
