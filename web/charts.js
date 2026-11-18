/* The charts: monthly bars, day by hour heatmap, mini bars, sparkline and app bars.
   All hand-drawn in HTML, CSS and SVG, in India time. Registers IB.charts:

   IB.charts.monthly(el, monthly, {title})    monthly: [{month: '2026-09', n}]. Draws the card body into el.
   IB.charts.heat(el, heat, {title})          heat: 7 rows (Mon..Sun) of 24 hourly counts. Draws into el.
   IB.charts.miniBars(values, {max, tone, label})  values: [numbers] or [{n, tip}]. Returns an HTML string.
   IB.charts.spark(values, {width, height, label}) values: [numbers]. Returns an SVG string.
   IB.charts.hbars(rows, {max})               rows: [{label, n, icon, href}]. Returns an HTML string.
   IB.charts.monthLabel('2026-09')            gives "Sep 2026".
*/
(() => {
  const IB = window.IB;
  if (!IB) return;
  const esc = (v) => IB.esc(v);
  const num = (n) => (IB.fmt && IB.fmt.num ? IB.fmt.num(n) : String(n));
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const SHORT_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  IB.css('ib-charts', `
    .ch-box { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
    .ch-scroll { overflow-x: auto; overflow-y: hidden; padding-bottom: 4px; min-width: 0; }
    .ch-bars { display: flex; align-items: flex-end; gap: 2px; height: 136px; min-width: 100%; }
    .ch-col { flex: 1 0 6px; min-width: 6px; display: flex; flex-direction: column; justify-content: flex-end; height: 100%; position: relative; }
    .ch-bar { background: var(--series, #3b6fd8); border-radius: 4px 4px 0 0; min-height: 1px; width: 100%; cursor: default; }
    .ch-bar.zero { background: var(--empty, rgba(127,127,127,.18)); min-height: 2px; }
    .ch-col:focus-visible .ch-bar, .ch-col:hover .ch-bar { filter: brightness(1.15); }
    .ch-years { display: flex; gap: 2px; min-width: 100%; height: 16px; }
    .ch-years span { flex: 1 0 6px; min-width: 6px; font-size: 11px; white-space: nowrap; overflow: visible; color: var(--text-3, #777); }
    .ch-axis { display: flex; justify-content: space-between; gap: 8px; border-top: 1px solid var(--border, rgba(127,127,127,.35)); padding-top: 6px; font-size: 12px; color: var(--text-3, #777); }
    .ch-heat { display: grid; grid-template-columns: 34px repeat(24, minmax(0, 1fr)); gap: 3px; align-items: center; }
    .ch-heat .ch-dl { font-size: 12px; color: var(--text-3, #777); }
    .ch-cell { aspect-ratio: 1 / 1; border-radius: 4px; min-width: 6px; background: var(--empty, rgba(127,127,127,.14)); }
    .ch-cell:focus-visible { outline: 2px solid var(--accent, #3b6fd8); outline-offset: 1px; }
    .ch-hl { font-size: 12px; color: var(--text-3, #777); text-align: left; }
    .ch-legend { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-3, #777); }
    .ch-ramp { width: 120px; height: 10px; border-radius: 999px; background: linear-gradient(90deg, var(--seq-lo, #dbe6fb), var(--seq-hi, #1f4fb4)); }
    .ch-mini { display: inline-flex; align-items: flex-end; gap: 2px; height: 22px; vertical-align: middle; }
    .ch-mini i { display: block; width: 4px; border-radius: 2px 2px 0 0; background: var(--series, #3b6fd8); min-height: 1px; }
    .ch-mini.tone-green i { background: var(--good, #2f9e6a); }
    .ch-mini.tone-orange i { background: var(--serious, #d9822b); }
    .ch-hbar-list { display: flex; flex-direction: column; gap: 8px; }
    .ch-hbar { display: grid; grid-template-columns: 22px minmax(90px, 160px) 1fr 64px; gap: 10px; align-items: center; padding: 4px 6px; border-radius: 8px; color: inherit; text-decoration: none; }
    a.ch-hbar:hover, a.ch-hbar:focus-visible { background: var(--hover, rgba(127,127,127,.1)); }
    .ch-track { height: 10px; border-radius: 999px; background: var(--empty, rgba(127,127,127,.14)); overflow: hidden; }
    .ch-fill { height: 100%; border-radius: 999px; background: var(--series, #3b6fd8); }
    .ch-hbar .num { text-align: right; }
    .ch-spark { display: block; }
    .ch-spark path { fill: none; stroke: var(--series, #3b6fd8); stroke-width: 1.5; stroke-linejoin: round; stroke-linecap: round; }
  `);

  function monthLabel(key) {
    const [y, m] = String(key || '').split('-');
    const i = parseInt(m, 10) - 1;
    return (MONTHS[i] || '') + ' ' + (y || '');
  }

  /* Fill in empty months between the first and last, so the gaps are honest. */
  function fillMonths(list) {
    const rows = (list || []).filter((r) => r && r.month).slice().sort((a, b) => (a.month < b.month ? -1 : 1));
    if (!rows.length) return [];
    const have = new Map(rows.map((r) => [r.month, Number(r.n) || 0]));
    const out = [];
    let [y, m] = rows[0].month.split('-').map(Number);
    const last = rows[rows.length - 1].month;
    for (let guard = 0; guard < 600; guard++) {
      const key = y + '-' + String(m).padStart(2, '0');
      out.push({ month: key, n: have.get(key) || 0 });
      if (key >= last) break;
      m++; if (m > 12) { m = 1; y++; }
    }
    return out;
  }

  function monthly(el, list) {
    const rows = fillMonths(list);
    if (!rows.length) { el.innerHTML = IB.empty('No messages or calls with a date yet.'); return; }
    const peak = Math.max(1, ...rows.map((r) => r.n));
    const peakRow = rows.reduce((a, b) => (b.n > a.n ? b : a), rows[0]);
    const bars = rows.map((r) => {
      const h = r.n ? Math.max(2, Math.round((r.n / peak) * 136)) : 2;
      const tip = monthLabel(r.month) + ': ' + IB.plural(r.n, 'message and call', 'messages and calls');
      return `<div class="ch-col" tabindex="0" data-tip="${esc(tip)}" aria-label="${esc(tip)}"><div class="ch-bar${r.n ? '' : ' zero'}" style="height:${h}px"></div></div>`;
    }).join('');
    const years = rows.map((r, i) => {
      const mm = r.month.slice(5);
      return `<span>${i === 0 || mm === '01' ? esc(monthLabel(r.month)) : ''}</span>`;
    }).join('');
    const label = `Busiest in ${monthLabel(peakRow.month)}, with ${IB.plural(peakRow.n, 'message and call', 'messages and calls')}`;
    el.innerHTML = `<div class="ch-box" role="img" aria-label="${esc(label)}">
      <div class="ch-scroll"><div class="ch-bars">${bars}</div><div class="ch-years" aria-hidden="true">${years}</div></div>
      <div class="ch-axis"><span>${esc(monthLabel(rows[0].month))}</span><span>peak ${esc(num(peak))} in a month</span><span>${esc(monthLabel(rows[rows.length - 1].month))}</span></div>
    </div>`;
    const sc = el.querySelector('.ch-scroll');
    // Open scrolled to the newest month.
    requestAnimationFrame(() => { sc.scrollLeft = sc.scrollWidth; });
  }

  function hourWords(h) {
    if (h === 0) return '12 am';
    if (h === 12) return '12 pm';
    return h < 12 ? h + ' am' : (h - 12) + ' pm';
  }

  function heat(el, grid) {
    const rows = Array.from({ length: 7 }, (_, d) => Array.from({ length: 24 }, (_, h) => Number(((grid || [])[d] || [])[h]) || 0));
    let max = 0, bd = 0, bh = 0;
    rows.forEach((r, d) => r.forEach((n, h) => { if (n > max) { max = n; bd = d; bh = h; } }));
    if (!max) { el.innerHTML = IB.empty('No messages or calls with a time yet.'); return; }
    let cells = '<span></span>';
    for (let h = 0; h < 24; h++) cells += `<span class="ch-hl">${h % 3 === 0 ? h : ''}</span>`;
    rows.forEach((r, d) => {
      cells += `<span class="ch-dl">${SHORT_DAYS[d]}</span>`;
      r.forEach((n, h) => {
        const tip = `${DAYS[d]} ${hourWords(h)}: ${IB.plural(n, 'message and call', 'messages and calls')}`;
        const pct = Math.round((n / max) * 100);
        const bg = n ? `background: color-mix(in oklab, var(--seq-lo, #dbe6fb), var(--seq-hi, #1f4fb4) ${pct}%)` : '';
        cells += `<span class="ch-cell" tabindex="-1" data-tip="${esc(tip)}" style="${bg}"></span>`;
      });
    });
    const label = `Busiest hour ${DAYS[bd]} ${hourWords(bh)}, with ${IB.plural(max, 'message and call', 'messages and calls')}`;
    el.innerHTML = `<div class="ch-box">
      <div class="ch-heat" role="img" aria-label="${esc(label)}">${cells}</div>
      <div class="ch-legend"><span>fewer</span><span class="ch-ramp" aria-hidden="true"></span><span>more (busiest hour: ${esc(num(max))})</span></div>
    </div>`;
  }

  function miniBars(values, opts = {}) {
    const vals = (values || []).map((v) => (typeof v === 'object' && v ? v : { n: Number(v) || 0 }));
    const max = Math.max(1, opts.max || 0, ...vals.map((v) => Number(v.n) || 0));
    const bars = vals.map((v) => {
      const h = Math.max(1, Math.round(((Number(v.n) || 0) / max) * 22));
      return `<i style="height:${h}px"${v.tip ? ` data-tip="${esc(v.tip)}"` : ''}></i>`;
    }).join('');
    const tone = opts.tone ? ' tone-' + esc(opts.tone) : '';
    return `<span class="ch-mini${tone}" role="img" aria-label="${esc(opts.label || 'Bars')}">${bars}</span>`;
  }

  function spark(values, opts = {}) {
    const w = opts.width || 120, h = opts.height || 28;
    const vals = (values || []).map((v) => Number(v) || 0);
    if (vals.length < 2) return `<svg class="ch-spark" width="${w}" height="${h}" role="img" aria-label="${esc(opts.label || 'Not enough contact to draw')}"></svg>`;
    const max = Math.max(1, ...vals);
    const step = (w - 2) / (vals.length - 1);
    const d = vals.map((v, i) => `${i ? 'L' : 'M'}${(1 + i * step).toFixed(1)} ${(h - 2 - (v / max) * (h - 4)).toFixed(1)}`).join(' ');
    return `<svg class="ch-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(opts.label || 'Contact over time')}"><path d="${d}"/></svg>`;
  }

  function hbars(rows, opts = {}) {
    const list = (rows || []).filter(Boolean);
    if (!list.length) return IB.empty('Nothing to show yet.');
    const max = Math.max(1, opts.max || 0, ...list.map((r) => Number(r.n) || 0));
    return `<div class="ch-hbar-list">${list.map((r) => {
      const pct = Math.max(1, Math.round(((Number(r.n) || 0) / max) * 100));
      const tag = r.href ? 'a' : 'div';
      const href = r.href ? ` href="${esc(r.href)}"` : '';
      return `<${tag} class="ch-hbar"${href}>${r.icon ? IB.icon(r.icon, 18) : '<span></span>'}<span class="clamp-1">${esc(r.label)}</span><span class="ch-track" aria-hidden="true"><span class="ch-fill" style="display:block;width:${pct}%"></span></span><span class="num">${esc(num(r.n || 0))}</span></${tag}>`;
    }).join('')}</div>`;
  }

  IB.charts = { monthly, heat, miniBars, spark, hbars, monthLabel, hourWords };
})();
