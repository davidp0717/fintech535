// Display the saved Python backtest. All times below are New York wall time.
let book;
let scatterDrawn = false;
const names = {wheel:'Wheel',covered_call:'Covered call',buy_hold:'Buy and hold',midpoint:'Wheel — midpoint',adverse:'Wheel — adverse',early_assignment:'Wheel — early assignment'};
const money = n => n == null ? '—' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n);
const number = n => n == null ? '—' : n.toFixed(2);
const percent = n => `${number(n)}%`;
const time = s => s ? s.slice(0,16).replace('T',' ') : '—';
const el = id => document.getElementById(id);
const say = (id,text) => { el(id).textContent = text; };
const account = () => book.results[el('wheel-account').value];
function addRow(body,values) {
  const row = body.insertRow();
  for (const value of values) row.insertCell().textContent = value;
  return row;
}
function body(id) { const b=el(id).tBodies[0]; b.replaceChildren(); return b; }

function showResults() {
  const w=book.results.wheel.summary, b=book.results.buy_hold.summary;
  say('wheel-conclusion',`The wheel earned ${money(w.pnl)} (${percent(w.return_pct)}), versus ${percent(b.return_pct)} for buy and hold. Its volatility and drawdown were lower, but its Sharpe was ${number(w.sharpe)} versus ${number(b.sharpe)}.`);
  const table=body('comparison');
  for (const key of ['wheel','buy_hold','covered_call']) {
    const s=book.results[key].summary;
    addRow(table,[names[key],money(s.pnl),percent(s.return_pct),percent(s.drawdown_pct),percent(s.volatility_pct),number(s.sharpe)]);
  }
  say('wheel-attribution',`Wheel profit: ${money(w.option_pnl)} in option receipts after fees ${w.stock_pnl<0 ? "−" : "+"} ${money(Math.abs(w.stock_pnl))} stock P&L + ${money(w.dividends)} dividends = ${money(w.pnl)}. Stock P&L includes ending shares at market value. Premium received is not profit.`);
  say('wheel-capital',`${w.option_entries} option entries; ${w.put_assignments} put assignments; ${w.call_assignments} call assignments; ${w.completed_cycles} completed wheel cycles. Shares were held at ${percent(w.share_days_pct)} of daily closes. Minimum free cash: ${money(w.min_free_cash)}. Ending NAV: ${money(w.final_nav)}, including 100 AAPL shares.`);
  const costs=body('sensitivity');
  for (const [key,label] of [['wheel','Bid/ask + fees (main)'],['midpoint','Midpoint + fees'],['adverse','Beyond bid/ask + fees'],['early_assignment','Early-assignment sensitivity']]) {
    const s=book.results[key].summary;
    addRow(costs,[label,money(s.pnl),percent(s.return_pct)]);
  }
  const d=book.diagnostics;
  say('wheel-spreads',`At the ${d.entries} Wheel entries, the median quoted spread was ${money(d.median_spread)} per share and the largest was ${money(d.max_spread)}. Assuming midpoint sales would increase total P&L by ${money(d.midpoint_advantage)}. All three execution cases use the same contracts and entry dates.`);
  say('wheel-assignment','The main case assumes assignment only at expiry. A separate sensitivity assigns early at 10:00 when the 09:59 option is in the money with no more than $0.10 of midpoint time value, then waits until Monday to restart. It moves the June 12 put assignment to June 11, without changing final P&L here. This is one alternative timing rule, not an estimated probability or worst case.');
  say('scatter-stat',`${d.observed_points.toLocaleString()} matched observations; fitted trade = ${d.slope.toFixed(4)} × midpoint + ${d.intercept.toFixed(4)}; R² = ${d.r2.toFixed(5)}. ${percent(d.inside_spread_pct)} of reported trades fall inside the same bar's bid/ask.`);
  say('wheel-interpretation',`The thesis was that weekly premiums could reduce volatility and improve Sharpe relative to holding 100 shares plus idle cash. The wheel collected ${money(w.option_pnl)} after option fees, but lost ${money(-w.stock_pnl)} on the stock component. Two cycles sold shares $20 below their acquisition price, losing $2,000 each; the final shares had a $713 unrealized gain. Shares were held at only ${percent(w.share_days_pct)} of daily closes, missing much of AAPL's rise. Lower volatility did not offset the return shortfall: the improved-Sharpe thesis was not supported.`);
  say('wheel-source',`${book.source.provider}; ${book.source.start}–${book.source.end}; ${book.source.quote_rows.toLocaleString()} saved observations; ${w.observations} exchange sessions. Download completed ${book.source.completed_at.slice(0,19).replace('T',' ')} UTC.`);
  say('wheel-quality',`${book.source.split_check}. All 24 chosen entry weeks passed the quote rules; May 25 and September 7 were skipped for Monday holidays. ${w.aged_fills} entries used an older quote and ${w.stale_option_marks} daily closing option marks exceeded 60 seconds. Missing entries are skipped with a reason; missing expiry stock closes stop the run. Missing intraday marks may carry only an earlier quote, with its timestamp shown.`);
}

function showPortfolio(index,requested) {
  const records=account().ledger, r=records[index];
  el('portfolio-record').value=String(index);
  if (!requested) {
    el('portfolio-time').value=r.time.slice(0,16);
    el('portfolio-side').value=r.phase==='before' ? 'before' : 'after';
  }
  say('portfolio-status',`${names[el('wheel-account').value]} · requested ${time(requested || r.time)} · recorded state ${time(r.time)} (${r.phase}${r.group ? `, event ${r.group}` : ''}): ${r.reason}.`);
  const table=body('portfolio'), o=r.option;
  const contract=o ? `${o.ric} · ${money(o.strike)} · expires ${o.expiry}` : 'None';
  for (const values of [
    ['Cash',money(r.cash)],['Cash reserved for put',money(r.put_reserve)],['Free cash',money(r.free_cash)],
    ['AAPL shares',`${r.shares} · market value ${money(r.stock_mv)}`],
    ['Short puts',r.short_puts],['Covered calls',r.short_calls],['Option contract',contract],
    ['Short-option market value',money(r.option_mv)],['Dividend receivable',money(r.dividend_receivable)],
    ['Account NAV',money(r.nav)],['Estimated liquidation NAV',money(r.liquidation_nav)]
  ]) addRow(table,values);
  const stock=`Stock: ${money(r.stock_mark)} at ${time(r.stock_mark_time)} (${r.stock_mark_source}).`;
  const option=o ? ` Option: ${money(o.mark)} at ${time(o.quote_time)} (${o.mark_source}; age at recorded state ${o.quote_age_seconds} seconds).` : ' No open option.';
  say('portfolio-marks',stock+option+' All displayed times are New York time. Liquidation NAV estimates stock sales at bid and option purchases at ask plus exit fees; it is not a booked trade.');
}

// The ledger is ordered, including multiple events sharing a timestamp.
function findRecord(records,requested,before) {
  let index=-1;
  for (let i=0;i<records.length;i++) {
    const t=records[i].time.slice(0,16);
    if (t>requested) break;
    if (before && t===requested && records[i].phase==='before') return i;
    index=i;
  }
  return index;
}
function selectTime() {
  const requested=el('portfolio-time').value;
  if (!requested || !el('portfolio-time').checkValidity()) {
    say('portfolio-status','Choose a time between May 4 at 09:59 and October 30 at 16:01, 2026.'); return;
  }
  const index=findRecord(account().ledger,requested,el('portfolio-side').value==='before');
  if (index<0) { say('portfolio-status','No recorded state is available before this time.'); return; }
  showPortfolio(index,requested);
}

function showRecords() {
  const a=account(), key=el('wheel-account').value;
  say('wheel-record-count',`${names[key]}: ${a.blotter.length} booked rows and ${a.ledger.length.toLocaleString()} portfolio states. Assignment rows and their linked stock transfers share an event number. No rolls are used.`);
  const select=el('portfolio-record'); select.replaceChildren();
  for (let i=0;i<a.ledger.length;i++) {
    const r=a.ledger[i];
    select.add(new Option(`${time(r.time)} · ${r.phase}${r.group ? ` event ${r.group}` : ''} · ${r.reason}`,String(i)));
  }
  const table=body('wheel-blotter');
  for (const r of a.blotter) {
    const tr=addRow(table,['',time(r.time),r.instrument,r.action,r.quantity,
      r.strike==null?'—':`${money(r.strike)} / ${r.expiry}`,
      r.bid==null?'—':`${money(r.bid)} / ${money(r.ask)}`,money(r.fill),money(r.fee),money(r.cash_delta),money(r.cash_after),r.note]);
    tr.cells[11].className='note-cell';
    tr.cells[6].title=r.quote_time ? `Quote: ${time(r.quote_time)} NY; age ${r.quote_age_seconds} seconds` : 'Assignment/expiry uses the contract rule';
    const button=document.createElement('button'); button.type='button'; button.className='event-link'; button.textContent=String(r.group);
    button.setAttribute('aria-label',`View portfolio after event ${r.group}, ${r.action} ${r.instrument}`);
    button.addEventListener('click',()=>{
      const index=a.ledger.findIndex(s=>s.group===r.group && s.phase==='after');
      el('portfolio-details').open=true;
      showPortfolio(index); el('portfolio-title').scrollIntoView({block:'start'});
    });
    tr.cells[0].append(button);
  }
  const decisions=body('wheel-decisions');
  if (!a.decisions.length) addRow(decisions,['—','—','—','—','Not applicable','Buy 100 shares once and hold.']);
  for (const r of a.decisions) {
    const tr=addRow(decisions,[r.week,r.kind || '—',money(r.strike),r.expiry,r.status,r.reason]);
    tr.cells[5].className='note-cell';
  }
  if (el('ledger-details').open) showLedger();
  selectTime();
}

function showLedger() {
  const table=body('wheel-ledger');
  for (const r of account().ledger) {
    const o=r.option;
    const tr=addRow(table,[time(r.time),`${r.phase}${r.group ? ` #${r.group}` : ''}`,money(r.cash),r.shares,r.short_puts,r.short_calls,
      o ? `${o.ric} / ${money(o.strike)} / ${o.expiry}` : '—',money(r.put_reserve),money(r.free_cash),money(r.stock_mv),money(r.option_mv),money(r.dividend_receivable),money(r.nav),r.reason]);
    tr.cells[13].className='note-cell';
  }
}

const chartConfig={responsive:true,displaylogo:false,displayModeBar:false};
function layout(x,y) {
  return {margin:{l:70,r:15,t:15,b:90},font:{family:'Arial',size:12},paper_bgcolor:'white',plot_bgcolor:'white',
    xaxis:{title:{text:x},gridcolor:'#eee'},yaxis:{title:{text:y},gridcolor:'#eee'},legend:{orientation:'h',y:-.26}};
}
async function showNav() {
  const colors={wheel:'#194e73',buy_hold:'#63705b',covered_call:'#af6419'};
  const traces=['wheel','buy_hold','covered_call'].map(key=>{
    const daily=book.results[key].ledger.filter(r=>r.phase==='initial'||r.phase==='close');
    return {x:daily.map(r=>r.time.slice(0,10)),y:daily.map(r=>r.nav),name:names[key],type:'scatter',mode:'lines',
      line:{color:colors[key],width:2},hovertemplate:`${names[key]}: $%{y:,.2f}<extra></extra>`};
  });
  await Plotly.newPlot('wheel-nav',traces,{...layout('Date — daily close','Account value (USD)'),hovermode:'x unified'},chartConfig);
}
async function showScatter() {
  if (scatterDrawn || !el('scatter-details').open) return;
  try {
    const d=book.diagnostics, xs=d.points.map(p=>p.mid), endpoints=[Math.min(...xs),Math.max(...xs)];
    const dots={x:xs,y:d.points.map(p=>p.trade),mode:'markers',type:'scatter',name:'Observed bars',marker:{color:'#194e73',size:5,opacity:.45},
      text:d.points.map(p=>`${p.ric}<br>${time(p.time)} NY`),hovertemplate:'%{text}<br>Mid: $%{x:.3f}<br>Trade: $%{y:.3f}<extra></extra>'};
    const line={x:endpoints,y:endpoints.map(x=>d.slope*x+d.intercept),mode:'lines',name:'OLS fit',line:{color:'#af6419'}};
    await Plotly.newPlot('wheel-scatter',[dots,line],layout('Option midpoint ($ per share)','Reported trade ($ per share)'),chartConfig);
    scatterDrawn=true;
  } catch(error) { say('wheel-scatter','Chart unavailable. The fitted statistics remain above.'); console.error(error); }
}

async function main() {
  try {
    const response=await fetch('assignment4/book.json');
    if (!response.ok) throw new Error(`Saved results returned ${response.status}`);
    book=await response.json();
    showResults(); showRecords();
    el('wheel-account').addEventListener('change',showRecords);
    el('show-portfolio').addEventListener('click',selectTime);
    el('portfolio-side').addEventListener('change',selectTime);
    el('portfolio-record').addEventListener('change',()=>showPortfolio(Number(el('portfolio-record').value)));
    el('ledger-details').addEventListener('toggle',()=>{ if(el('ledger-details').open) showLedger(); });
    el('scatter-details').addEventListener('toggle',showScatter);
    el('wheel-status').hidden=true;
    try { await showNav(); } catch(error) { say('wheel-nav','Chart unavailable. Results and full records remain below.'); console.error(error); }
  } catch(error) {
    say('wheel-status','Saved results could not load. Refresh the page or use a local HTTP server.'); console.error(error);
  }
}
main();
