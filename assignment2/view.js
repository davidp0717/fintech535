// Read the saved Python results and display them. No live data connection is needed.
const money = value => value == null ? '—' : new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 2
}).format(value);
const price = value => value == null ? '—' : new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4
}).format(value);
const timeLabel = value => value.slice(0, 16).replace('T', ' ');
const text = (id, value) => { document.getElementById(id).textContent = value; };

function addRow(body, values) {
  const row = body.insertRow();
  for (const value of values) row.insertCell().textContent = value;
  return row;
}

function showTables() {
  const body = document.querySelector('#blotter tbody');
  for (const event of BOOK.blotter) {
    const row = addRow(body, [timeLabel(event.time), event.instrument, event.side,
      event.qty, price(event.limit), price(event.fill), money(event.cash_delta), event.note]);
    row.cells[7].className = 'note-cell';
    if (event.occ) {
      const subtitle = document.createElement('small');
      subtitle.textContent = event.occ;
      row.cells[1].appendChild(subtitle);
    }
  }
  const decisions = document.querySelector('#decisions tbody');
  for (const week of BOOK.decisions) {
    const row = addRow(decisions, [week.week, week.expiry, money(week.strike),
      week.outcome || week.status, week.reason]);
    row.cells[4].className = 'note-cell';
  }
  showLedger();
  document.getElementById('ledger-frequency').addEventListener('change', showLedger);
}

function showLedger() {
  const all = document.getElementById('ledger-frequency').value === 'all';
  // Each new row replaces the earlier row for its day, leaving the last one.
  const daily = new Map();
  for (const row of BOOK.ledger) daily.set(row.time.slice(0, 10), row);
  const rows = all ? BOOK.ledger : [...daily.values()];
  const body = document.querySelector('#ledger tbody');
  body.replaceChildren();
  document.querySelector('#ledger caption').textContent = `${rows.length} ${all ? 'hourly' : 'daily closing'} records`;
  for (const row of rows) {
    addRow(body, [timeLabel(row.time), row.shares, row.short_calls,
      row.short_calls ? `${money(row.strike)} / ${row.expiry}` : '—',
      money(row.cash), price(row.stock_mark), price(row.option_mark), money(row.stock_mv),
      money(row.option_mv), money(row.nav), money(row.initial), money(row.maintenance),
      money(row.available), money(row.excess), row.short_calls ? row.quote_age_hours : '—']);
  }
}

function showSummary() {
  const s = BOOK.summary;
  const profit = s.final_nav - BOOK.initial_cash;
  const results = document.getElementById('results');
  for (const [label, value] of [
    ['Ending NAV', money(s.final_nav)], ['Net change', `${money(profit)} (${s.return_pct.toFixed(2)}%)`],
    ['Premium collected', money(s.premium)], ['Maximum drawdown', `${Math.abs(s.max_drawdown_pct).toFixed(2)}%`]
  ]) {
    const p = document.createElement('p');
    p.textContent = `${label}: `;
    const strong = document.createElement('strong');
    strong.textContent = value;
    p.appendChild(strong);
    results.appendChild(p);
  }
  text('margin-check', `Minimum available funds: ${money(s.min_available)}. Minimum excess equity: ${money(s.min_excess)}. ` +
    `${s.negative_available} hourly records have negative available funds; ${s.negative_excess} have negative excess equity. ` +
    `${s.stale_marks} records use a carried option mark.`);
  text('outcomes', `${s.entered} calls were sold: ${s.assigned} ended in assignment and ${s.expired} expired with shares retained. ` +
    `The September 7 holiday week was skipped because there was no Monday entry bar. The final account is flat, with ${money(s.final_nav)} in cash.`);
  text('pnl-analysis', `The strategy collected ${money(s.premium)} in premiums, but premiums are not the same as profit. ` +
    `The stock purchases and assignment deliveries contributed ${money(profit - s.premium)}, leaving a net model gain of ${money(profit)}. ` +
    `This illustrates the downside that remains in a covered call even as the premium cushions the loss.`);
  const fit = BOOK.regression;
  text('fit', fit ? `Linear fit: trade = ${fit.slope.toFixed(4)} × mid ${fit.intercept < 0 ? '−' : '+'} ${Math.abs(fit.intercept).toFixed(4)}. ` +
    `R² = ${fit.r2.toFixed(4)}; ${fit.n.toLocaleString()} paired observations.` : 'Not enough paired observations for a regression.');
  text('fit-analysis', fit ? `The median absolute trade–midpoint gap is $${fit.median_gap.toFixed(3)} per share ` +
    `($${(100 * fit.median_gap).toFixed(2)} per contract). This supports using midpoint as a baseline price proxy, ` +
    `but the regression does not measure fill probability or remove intrabar timing differences.` : 'There are not enough observations to assess midpoint pricing.');
  const source = BOOK.source;
  text('source', `${source.provider}; ${source.ticker}; ${source.start} through ${source.end}; ${source.interval}. ` +
    `${source.contracts_with_data} call contracts returned data. Download completed ${source.fetched_at}. ` +
    `Capital-change screen: ${source.split_check}. This screen is not a full adjusted-contract audit.`);
}

async function showCharts() {
  const layout = {
    margin: {l: 65, r: 15, t: 20, b: 90}, font: {family: 'Arial', size: 12},
    paper_bgcolor: 'white', plot_bgcolor: 'white',
    legend: {orientation: 'h', y: -0.25},
    xaxis: {title: {text: 'Date / time (New York)'}, gridcolor: '#eee'},
    yaxis: {title: {text: 'USD'}, tickprefix: '$', gridcolor: '#eee'}
  };
  const config = {responsive: true, displaylogo: false, displayModeBar: false};
  const lines = [['nav', 'NAV', '#194e73'], ['initial', 'Initial margin', '#a55c10'],
    ['maintenance', 'Maintenance', '#6c7278'], ['available', 'Available funds', '#218052'],
    ['excess', 'Excess equity', '#75509a']].map(([field, name, color]) => ({
      x: BOOK.ledger.map(row => timeLabel(row.time)), y: BOOK.ledger.map(row => row[field]),
      name, type: 'scatter', mode: 'lines', line: {color, width: 2},
      visible: field === 'available' || field === 'excess' ? 'legendonly' : true,
      hovertemplate: `${name}: $%{y:,.2f}<extra></extra>`
    }));
  await Plotly.newPlot('nav-chart', lines, {...layout, hovermode: 'x unified'}, config);
  const points = BOOK.scatter;
  const traces = [{x: points.map(p => p.mid), y: points.map(p => p.trade),
    customdata: points.map(p => `${p.ric}<br>${timeLabel(p.time)} ET`),
    name: 'Hourly observations', type: 'scatter', mode: 'markers', marker: {size: 5, color: '#194e73', opacity: 0.45},
    hovertemplate: '%{customdata}<br>Mid: $%{x:.3f}<br>Trade: $%{y:.3f}<extra></extra>'}];
  const fit = BOOK.regression;
  if (fit) {
    const x = [fit.xmin, fit.xmax];
    traces.push({x, y: x.map(v => fit.slope * v + fit.intercept), type: 'scatter', mode: 'lines',
      name: 'Fitted line', line: {color: '#b65d0b', width: 2}});
    traces.push({x, y: x, type: 'scatter', mode: 'lines', name: 'Trade = mid',
      line: {color: '#666', width: 1, dash: 'dash'}});
  }
  await Plotly.newPlot('scatter-chart', traces, {...layout,
    xaxis: {title: {text: 'Option midpoint ($ / share)'}, gridcolor: '#eee'},
    yaxis: {title: {text: 'Last trade ($ / share)'}, gridcolor: '#eee'}}, config);
}

async function main() {
  try {
    showSummary();
    showTables();
    await showCharts();
    text('load-status', `Saved results loaded: ${BOOK.ledger.length} hourly records and ${BOOK.blotter.length} booked events.`);
  } catch (error) {
    text('load-status', 'Some results could not load. Refresh the page; charts require access to the Plotly CDN.');
    console.error(error);
  }
}
main();
