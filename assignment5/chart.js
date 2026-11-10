async function showPrices() {
  const status = document.getElementById("status");
  const instrument = document.getElementById("instrument");
  try {
    const response = await fetch("assignment5/prices.json", {cache: "no-cache"});
    if (!response.ok) throw new Error("Price file unavailable");
    const figure = await response.json();
    for (const trace of figure.data) instrument.add(new Option(trace.name));

    async function draw() {
      const trace = figure.data[instrument.selectedIndex];
      await Plotly.react("prices", [trace], figure.layout, {responsive: true, displaylogo: false});
      status.textContent = trace.x[0] + " through " + trace.x[trace.x.length - 1];
    }

    await draw();
    instrument.disabled = false;
    instrument.addEventListener("change", draw);
  } catch {
    status.textContent = "The price chart could not be loaded. Reload the page to try again.";
  }
}
showPrices();
