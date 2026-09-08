// Step 3: read the saved data, filter it, and redraw the page.
// Plain JavaScript: no framework, build tool, or live LSEG connection.
let dataset;
const dateInput = document.getElementById('date');
const typeInput = document.getElementById('type');
const chartConfig = { responsive: true, displaylogo: false };

function hasPrice(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function median(values) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function calculateStats(rows) {
  const eligible = rows.filter(row => row.eligible);
  const midOnly = eligible.filter(row => hasPrice(row.MID_PRICE) && !hasPrice(row.TRDPRC_1));
  const both = eligible.filter(row => hasPrice(row.MID_PRICE) && hasPrice(row.TRDPRC_1));
  return { count: eligible.length, midOnly: midOnly.length, both: both.length,
    percent: eligible.length ? 100 * midOnly.length / eligible.length : null,
    difference: median(both.map(row => Math.abs(row.MID_PRICE - row.TRDPRC_1))) };
}

function updateStats(rows) {
  const stats = calculateStats(rows);
  document.getElementById('midOnly').textContent = stats.percent === null ? 'N/A' : stats.percent.toFixed(1) + '%';
  document.getElementById('difference').textContent = stats.difference === null ? 'N/A' : '$' + stats.difference.toFixed(4);
  document.getElementById('midDetail').textContent = `(${stats.midOnly} of ${stats.count} sample series)`;
  document.getElementById('bothDetail').textContent = `(${stats.both} matched series)`;

}

function daysBetween(start, end) {
  return Math.round((Date.parse(end) - Date.parse(start)) / 86400000);
}

function drawCloud(rows, date) {
  const fields = ['MID_PRICE', 'TRDPRC_1'];
  const traces = fields.map(field => {
    const priced = rows.filter(row => hasPrice(row[field]));
    return { type: 'scatter3d', mode: 'markers', name: field,
      x: priced.map(row => row.strike), y: priced.map(row => daysBetween(date, row.expiry)),
      z: priced.map(row => row[field]),
      customdata: priced.map(row => [row.ric, row.expiry]),
      marker: { size: 4, opacity: 0.85, color: field === 'MID_PRICE' ? '#087f8c' : '#df6728',
        symbol: field === 'MID_PRICE' ? 'circle' : 'diamond' },
      hovertemplate: '<b>%{customdata[0]}</b><br>Strike $%{x:.2f}<br>Expiry %{customdata[1]}<br>' + field + ': $%{z:.4f}<extra></extra>' };
  });
  document.getElementById('cloudEmpty').hidden = traces.some(trace => trace.x.length > 0);
  return Plotly.react('cloud', traces, {
    margin: { l: 0, r: 0, b: 0, t: 10 }, paper_bgcolor: 'white',
    font: { family: 'system-ui, sans-serif', color: '#14263b', size: 14 },
    showlegend: true, legend: { orientation: 'h', x: 0, y: 1 },
    uirevision: 'keep-camera',
    scene: { xaxis: { title: { text: 'Strike ($)' } },
      yaxis: { title: { text: 'Days to expiration' } }, zaxis: { title: { text: 'Option price ($)' }, rangemode: 'tozero' },
      camera: { eye: { x: 1.5, y: 1.5, z: 1 } }, aspectmode: 'auto' }
  }, chartConfig);
}

function describeDensity(rows, date) {
  // Compare actual price availability at each expiry, then name the missing strikes.
  const expiries = dataset.expiries.filter(expiry => expiry >= date);
  const coverage = expiries.map(expiry => {
    const priced = rows.filter(row => row.expiry === expiry &&
      (hasPrice(row.MID_PRICE) || hasPrice(row.TRDPRC_1)));
    const strikes = new Set(priced.map(row => row.strike));
    return { expiry, count: strikes.size,
      missing: dataset.strikes.filter(strike => !strikes.has(strike)) };
  });
  coverage.sort((a, b) => b.count - a.count);
  const dense = coverage[0];
  const sparse = coverage[coverage.length - 1];
  if (!dense || dense.count === 0) {
    return `On ${date}, no prices are returned at any sampled strike or remaining expiration, so the whole requested grid is empty.`;
  }
  const denseText = `On ${date}, ${typeInput.value.toLowerCase()} prices are densest at the ${dense.expiry} expiration (${dense.count} of ${dataset.strikes.length} strikes)`;
  if (sparse.missing.length === 0) {
    return denseText + ', and every sampled strike–expiration cell has at least one price, though one of the two fields may still be missing.';
  }
  const strikesText = sparse.missing.map(strike => '$' + strike.toFixed(2)).join(', ');
  return denseText + `; the sparsest expiration is ${sparse.expiry}, with neither price at strikes ${strikesText}, including any unconfirmed listings.`;
}

async function updatePage() {
  const date = dateInput.value;
  const rows = dataset.rows.filter(row => row.date === date && row.type === typeInput.value);
  updateStats(rows);
  document.getElementById('spot').textContent = `UUUU close: $${dataset.stock[date].toFixed(2)}`;
  document.getElementById('sentence1').textContent = describeDensity(rows, date);
  await drawCloud(rows, date);
}

async function start() {
  try {
    if (typeof Plotly === 'undefined') throw new Error('The chart library did not load. Check your connection and reload.');
    const response = await fetch('data.json');
    if (!response.ok) throw new Error('The saved data could not be loaded. Please reload the page.');
    dataset = await response.json();
    const dates = Object.keys(dataset.stock).sort();
    for (const date of dates) dateInput.add(new Option(date, date));
    // Start at the day with the most midpoint-only calls; this exposes the assignment's key distinction.
    const ranked = dates.map(date => ({ date, stats: calculateStats(dataset.rows.filter(row => row.date === date && row.type === 'Call')) }));
    ranked.sort((a, b) => b.stats.midOnly - a.stats.midOnly || b.stats.count - a.stats.count);
    dateInput.value = ranked[0].date;
    for (const input of [dateInput, typeInput]) {
      input.disabled = false;
      input.addEventListener('change', () => updatePage().catch(showError));
    }
    document.getElementById('status').textContent = `${dataset.start} – ${dataset.end} · ${dataset.contracts.length} contracts with returned data · $0.50 strike grid`;
    document.getElementById('provenance').textContent = `Source: LSEG Workspace; fetched ${dataset.fetched_at}. ${dataset.candidate_count} identifiers requested; ${dataset.contracts.length} returned at least one price; ${dataset.failure_count} individual request errors. Split screening: ${dataset.split_check}.`;
    await updatePage();
  } catch (error) { showError(error); }
}

function showError(error) {
  document.getElementById('status').textContent = error.message;
  document.getElementById('status').style.color = '#a33120';
}

start();
