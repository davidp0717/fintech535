async function loadOrders() {
  const status = document.getElementById("status");
  try {
    const response = await fetch("assignment6/status.json", {cache: "no-cache"});
    if (!response.ok) throw new Error("Status unavailable");
    const report = await response.json();
    status.textContent = report.reason;
    document.getElementById("dates").textContent =
      "Price session " + report.as_of + " · Order session " + report.for +
      " · Generated " + new Date(report.generated_at).toLocaleString();
    document.getElementById("orders").textContent = JSON.stringify(report.orders, null, 2);
    if (report.status === "blocked") return;
    document.getElementById("signal").textContent =
      "Latest close $" + report.close.toFixed(2) + " · 5-day average $" +
      report.sma5.toFixed(2) + " · 20-day average $" + report.sma20.toFixed(2);
    await Plotly.newPlot("signal-chart", [{
      x: report.series.map(row => row.date),
      y: report.series.map(row => row.close),
      type: "scatter", mode: "lines+markers", name: "GOOGL close"
    }], {
      margin: {t: 20, r: 20}, yaxis: {title: {text: "USD"}},
      shapes: [
        {type: "line", xref: "paper", x0: 0, x1: 1, y0: report.sma5, y1: report.sma5,
         line: {color: "#198754", dash: "dot"}},
        {type: "line", xref: "paper", x0: 0, x1: 1, y0: report.sma20, y1: report.sma20,
         line: {color: "#bc5b13", dash: "dash"}}
      ]
    }, {responsive: true, displaylogo: false});
  } catch {
    status.textContent = "Could not load the latest strategy output. Reload to try again.";
  }
}
loadOrders();
