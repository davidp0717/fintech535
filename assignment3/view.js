// The browser displays saved results; the strategy itself is in backtest.py.
let book;
const names = {pmcc:'PMCC', covered_call:'Covered call', buy_hold:'Buy and hold', long_call:'Long call only', assignment_stress:'Assignment stress'};
const money = v => v == null ? '—' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(v);
const price = v => v == null ? '—' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:4}).format(v);
const percent = v => `${v.toFixed(2)}%`;
const localTime = v => v ? v.slice(0,16).replace('T',' ') : '—';
const say = (id,value) => { document.getElementById(id).textContent=value; };
function row(body,values) {
  const tr=body.insertRow();
  for (const value of values) tr.insertCell().textContent=value;
  return tr;
}

function showResults() {
  const results=book.results, main=results.pmcc.summary, cc=results.covered_call.summary;
  const saving=100*(1-main.initial_debit/cc.initial_debit);
  say('pmcc-conclusion',`The PMCC used ${money(main.initial_debit)} initially, ${percent(saving)} less cash than the covered call. It earned ${money(main.pnl)} after quoted spreads and option fees. The matched covered call earned ${money(cc.pnl)}. Lower initial outlay did not produce the larger dollar profit in this sample.`);
  const body=document.querySelector('#comparison tbody');
  for (const key of ['pmcc','covered_call','buy_hold','long_call']) {
    const s=results[key].summary;
    row(body,[names[key],money(s.initial_debit),money(s.pnl),percent(s.account_return_pct),percent(s.return_on_initial_debit_pct),percent(s.max_drawdown_pct)]);
  }
  say('pmcc-attribution',`PMCC profit: ${money(main.long_pnl)} from the long call + ${money(main.short_pnl)} from the weekly calls = ${money(main.pnl)}. Weekly premiums were ${money(main.premium)}, buybacks cost ${money(main.buybacks)}, and total option fees were ${money(main.fees)}. Premium received is not profit.`);
  say('pmcc-capital',`Minimum PMCC cash balance: ${money(main.min_cash)}. Maximum net cash deployed: ${money(main.max_net_cash_deployed)}. Ending NAV: ${money(main.final_nav)}, entirely in cash. No new capital or borrowing was used.`);
  const scenarios=document.querySelector('#sensitivity tbody');
  for (const [key,label] of [['midpoint','Midpoint + fees'],['pmcc','Bid/ask + fees (main)'],['adverse','Beyond bid/ask + fees']]) {
    const s=results[key].summary;
    row(scenarios,[label,money(s.pnl),percent(s.account_return_pct)]);
  }
  say('pmcc-interpretation',`The PMCC earned ${money(main.pnl)} from two sources: ${money(main.long_pnl)} on the long call and ${money(main.short_pnl)} on the weekly calls, after spreads and fees. The weekly calls collected ${money(main.premium)} in premiums, but buybacks and fees reduced what was kept. The matched covered call earned the same ${money(cc.short_pnl)} on its short calls, plus ${money(cc.stock_pnl)} from its shares and ${money(cc.dividends)} in dividends. Its ${money(cc.pnl-main.pnl)} profit advantage therefore came from the backing position. The PMCC returned ${percent(main.return_on_initial_debit_pct)} on its smaller initial outlay, versus ${percent(cc.return_on_initial_debit_pct)} for the covered call; on equal $40,000 accounts, it returned ${percent(main.account_return_pct)} versus ${percent(cc.account_return_pct)}. The higher outlay return reflects a smaller denominator, not a larger dollar profit.`);
  say('pmcc-source',`${book.source.provider}; ${book.source.start}–${book.source.end}; ${book.source.quote_rows} saved signal/execution quote rows; ${main.observations} daily account observations. Long contract: ${book.source.long_ric}. Download completed ${book.source.completed_at}.`);
  say('pmcc-quality',`${main.entries} weekly calls opened; the September 7 holiday week was skipped. ${main.aged_fills} fill used a quote 60 seconds old (August 14 short buyback); ${main.stale_marks} end-of-observation position marks were carried. ${book.split_check}. This screens for splits, not every possible option adjustment. The exact-bar rule was amended to a disclosed 60-second limit after finding the missing bar and before the first completed performance run; strategy parameters were unchanged.`);
}

function showRecords() {
  const key=document.getElementById('pmcc-account').value;
  const account=book.results[key];
  say('pmcc-record-count',`${names[key]}: ${account.blotter.length} booked events and ${account.ledger.length} daily records.`);
  const blotter=document.querySelector('#pmcc-blotter tbody'); blotter.replaceChildren();
  for (const e of account.blotter) {
    const r=row(blotter,[localTime(e.time),e.instrument,e.side,e.qty,
      e.bid==null?'—':`${price(e.bid)} / ${price(e.ask)}`,price(e.fill),e.quote_age_seconds==null?'—':e.quote_age_seconds,
      money(e.fee),money(e.cash_delta),e.note]);
    r.cells[9].className='note-cell';
    r.cells[6].title=e.quote_time ? `Observed quote: ${localTime(e.quote_time)} New York` : '';
  }
  const ledger=document.querySelector('#pmcc-ledger tbody'); ledger.replaceChildren();
  for (const r of account.ledger) row(ledger,[r.time.slice(0,10),money(r.cash),r.shares,r.long_calls,
    r.long_calls?`${price(r.long_strike)} / ${r.long_expiry}`:'—',r.short_calls,
    r.short_calls?`${price(r.short_strike)} / ${r.short_expiry}`:'—',price(r.long_mark),price(r.short_mark),
    money(r.long_mv),money(r.short_mv),money(r.stock_mv),money(r.dividend_receivable),money(r.nav),money(r.liquidation_nav),r.oldest_mark_minutes]);
  const decisions=document.querySelector('#pmcc-decisions tbody'); decisions.replaceChildren();
  if (key==='long_call'||key==='buy_hold') {
    row(decisions,['—','—','—','Not applicable','This benchmark does not sell weekly calls.','—']);
  } else for (const d of account.decisions) {
    const tr=row(decisions,[d.week,price(d.strike),d.expiry,d.status,d.reason,d.exit?(/^\d{4}-/.test(d.exit)?localTime(d.exit):d.exit):'—']);
    tr.cells[4].className='note-cell';
  }
}

async function showChart() {
  if (typeof Plotly==='undefined') throw new Error('Plotly unavailable');
  const colors={pmcc:'#194e73',covered_call:'#af6419',buy_hold:'#63705b',long_call:'#886995'};
  const traces=['pmcc','covered_call','buy_hold','long_call'].map(key=>({
    x:book.results[key].ledger.map(r=>localTime(r.time)),y:book.results[key].ledger.map(r=>r.nav),
    name:names[key],mode:'lines',type:'scatter',line:{color:colors[key],width:2},
    visible:key==='pmcc'||key==='covered_call'?true:'legendonly',hovertemplate:`${names[key]}: $%{y:,.2f}<extra></extra>`
  }));
  traces.push({x:book.results.pmcc.ledger.map(r=>localTime(r.time)),y:book.results.pmcc.ledger.map(r=>r.liquidation_nav),
    name:'PMCC liquidation',mode:'lines',type:'scatter',line:{color:'#194e73',width:1,dash:'dot'},
    hovertemplate:'PMCC liquidation: $%{y:,.2f}<extra></extra>'});
  await Plotly.newPlot('pmcc-nav',traces,{margin:{l:66,r:15,t:15,b:100},
    font:{family:'Arial',size:12},hovermode:'x unified',legend:{orientation:'h',y:-.28},
    xaxis:{title:{text:'Date (10:00 a.m. New York)'},gridcolor:'#eee'},
    yaxis:{title:{text:'Account value (USD)'},tickprefix:'$',gridcolor:'#eee'},paper_bgcolor:'white',plot_bgcolor:'white'},
    {responsive:true,displaylogo:false,displayModeBar:false});
}

async function main() {
  try {
    const response=await fetch('assignment3/book.json');
    if (!response.ok) throw new Error(`Saved results returned ${response.status}`);
    book=await response.json();
    showResults(); showRecords();
    document.getElementById('pmcc-account').addEventListener('change',showRecords);
    document.getElementById('pmcc-status').hidden=true;
    try { await showChart(); }
    catch(error) { say('pmcc-nav','Chart unavailable. The results and account records remain available below.'); console.error(error); }
  } catch(error) {
    document.getElementById('pmcc-status').hidden=false;
    say('pmcc-status','The saved results could not load. Please refresh the page or use a local HTTP server.');
    console.error(error);
  }
}
main();
