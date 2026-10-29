const COLORS = ['#1f5a3a', '#e0a22c', '#d6452f', '#5d9b6e', '#8a6d3b', '#2f7f8f', '#a15c7a', '#7a8b99'];
const LAYOUT = {margin: {t: 10, r: 10, b: 40, l: 50}, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
  font: {family: 'Public Sans, system-ui, sans-serif', size: 12, color: '#33453a'}};
let REPORT = null, getMetric = () => 'revenue';

function loadReports(url, metricFn) {
  getMetric = metricFn;
  fetch(url).then(r => r.json()).then(d => { REPORT = d; redrawReports(); renderKpis(); renderTables(); });
}
function draw(id, traces, extra = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!traces[0] || !(traces[0].x || traces[0].values).length) { el.innerHTML = '<p class="empty">No sales in this period.</p>'; return; }
  Plotly.react(el, traces, {...LAYOUT, ...extra}, {displayModeBar: false, responsive: true});
}
function redrawReports() {
  if (!REPORT) return;
  const m = getMetric(), label = m === 'revenue' ? 'Revenue (₹)' : 'Units sold';
  draw('daily', [{type: 'scatter', mode: 'lines', fill: 'tozeroy', x: REPORT.daily.map(r => r.date),
    y: REPORT.daily.map(r => m === 'revenue' ? r.revenue : r.bills), line: {color: COLORS[0], width: 2},
    fillcolor: 'rgba(31,90,58,.12)'}], {yaxis: {title: m === 'revenue' ? label : 'Bills'}});
  draw('monthly', [{type: 'bar', x: REPORT.monthly.map(r => r.month),
    y: REPORT.monthly.map(r => m === 'revenue' ? r.revenue : r.bills), marker: {color: COLORS[0]}}]);
  const top = [...REPORT.top].reverse();
  draw('top', [{type: 'bar', orientation: 'h', y: top.map(r => r.name), x: top.map(r => r[m]), marker: {color: COLORS[1]}}],
    {margin: {t: 10, r: 10, b: 40, l: 150}, xaxis: {title: label}});
  draw('cats', [{type: 'pie', hole: .55, labels: REPORT.categories.map(r => r.category),
    values: REPORT.categories.map(r => r[m]), marker: {colors: COLORS}, textinfo: 'percent'}],
    {margin: {t: 10, r: 10, b: 10, l: 10}});
}
function renderKpis() {
  const el = document.getElementById('kpis'); if (!el) return;
  const k = REPORT.kpis, f = n => Number(n).toLocaleString('en-IN', {maximumFractionDigits: 0});
  el.innerHTML = `<div class="kpi lead"><span>Total revenue</span><strong>₹${f(k.total_revenue)}</strong><em>${k.bills} bills</em></div>
    <div class="kpi"><span>Average bill</span><strong>₹${f(k.avg_bill_value)}</strong></div>
    <div class="kpi"><span>Stock turnover</span><strong>${k.stock_turnover}</strong></div>
    <div class="kpi ${k.low_stock_count ? 'warn' : ''}"><span>Low-stock items</span><strong>${k.low_stock_count}</strong></div>
    <div class="kpi"><span>Top category</span><strong>${k.top_category_share}%</strong><em>${k.top_category}</em></div>`;
}
function table(id, rows, cols) {
  const el = document.getElementById(id); if (!el) return;
  if (!rows.length) { el.innerHTML = '<p class="empty">Nothing to show.</p>'; return; }
  el.innerHTML = '<table><thead><tr>' + cols.map(c => `<th>${c[1]}</th>`).join('') + '</tr></thead><tbody>' +
    rows.map(r => '<tr>' + cols.map(c => `<td>${r[c[0]]}</td>`).join('') + '</tr>').join('') + '</tbody></table>';
}
function renderTables() {
  table('t-low', REPORT.low_stock, [['name', 'Product'], ['stock_qty', 'Stock'], ['reorder_level', 'Reorder at']]);
  table('t-exp', REPORT.expiring, [['name', 'Product'], ['stock_qty', 'Stock'], ['expiry_date', 'Expires']]);
  table('t-slow', REPORT.slow, [['name', 'Product'], ['stock_qty', 'In stock'], ['units_sold', 'Sold (30d)']]);
}
