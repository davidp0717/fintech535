async function loadTracker() {
  const status = document.getElementById("asof");
  try {
    const response = await fetch("final-project/tracker.json", {cache: "no-cache"});
    if (!response.ok) throw new Error("Tracker unavailable");
    const d = await response.json();
    status.textContent = "Latest common close · " + d.as_of;
    if (d.average_hold != null) {
      document.getElementById("lifetime").textContent = "My estimate for an uninterrupted directional trade is " +
        Math.round(d.average_hold) + " trading days, the sample average across completed futures positions.";
    }
    for (const option of d.options) {
      const row = document.getElementById("hurdles").insertRow();
      for (const value of [option.market, option.months, option.hurdle == null ? "—" : option.hurdle.toFixed(2) + "%"]) {
        row.insertCell().textContent = value;
      }
    }
    const directions = ["short", "flat", "long"];
    document.getElementById("positions").textContent = "Monthly positions set " + d.rebalance + " · " +
      Object.entries(d.position).map(([name, sign]) => name + " " + directions[sign + 1]).join(" · ");
    document.getElementById("estimate").textContent =
      "From " + d.start + " to " + d.as_of + ", the gross advantage was " + d.gross_active.toFixed(2) +
      " percentage points per year. Estimated turnover costs took " + d.drag.toFixed(2) +
      " points, leaving " + d.net_active.toFixed(2) + " points per year after costs. " +
      (d.net_active > 0 ? "The sample supports a positive net edge." : "The sample has yet to show a positive net edge.");
    const traces = Object.entries(d.momentum).map(([name, y]) => ({name, x: d.dates, y, mode: "lines"}));
    await Plotly.newPlot("trend", traces, {hovermode: "x unified", margin: {t: 15, r: 15},
      yaxis: {ticksuffix: "%", zerolinewidth: 2}, legend: {orientation: "h"}}, {responsive: true});
  } catch {
    status.textContent = "Unable to load the daily tracker. Check the refresh history below.";
  }
}
loadTracker();
