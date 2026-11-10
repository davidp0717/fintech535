async function showPrices() {
  const status = document.getElementById("status");
  try {
    const response = await fetch("assignment5/prices.json", {cache: "no-cache"});
    if (!response.ok) throw new Error("Price file unavailable");
    const figure = await response.json();
    await Plotly.newPlot("prices", figure.data, figure.layout, {responsive: true, displaylogo: false});
    const dates = figure.data.flatMap(trace => trace.x.filter((date, i) => trace.y[i] !== null)).sort();
    status.textContent = dates[0] + " through " + dates[dates.length - 1];
  } catch {
    status.textContent = "The price chart could not be loaded. Reload the page to try again.";
  }
}
showPrices();
