/* Places: IB.page('places', ...). See docs/frontend-interfaces.md. An offline map drawn in SVG: no tiles, no internet. */
(() => {
  const esc = (v) => IB.esc(v);
  const arr = (v, ...keys) => {
    if (Array.isArray(v)) return v;
    if (v && typeof v === 'object') for (const k of keys) if (Array.isArray(v[k])) return v[k];
    return [];
  };

  IB.css('pg-places', `
    .pl-layout { display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 16px; align-items: start; }
    .pl-map { width: 100%; height: auto; display: block; border-radius: 12px; background: var(--surface-2, #eef1f5); }
    .pl-map .grid { stroke: var(--line, rgba(127,127,127,.22)); stroke-width: 1; }
    .pl-map .lbl { font-size: 11px; fill: var(--muted, #6b7280); }
    .pl-map .lbl-dot { fill: var(--muted, #6b7280); opacity: .6; }
    .pl-map .pt { cursor: pointer; stroke: #fff; stroke-width: 2; opacity: .88; }
    .pl-map .pt:hover, .pl-map .pt:focus, .pl-map .pt.on { opacity: 1; stroke: var(--text, #111); outline: none; }
    .pl-map .pt-n { font-size: 11px; font-weight: 700; fill: #fff; pointer-events: none; }
    .pl-days { max-height: 520px; overflow: auto; display: flex; flex-direction: column; gap: 2px; }
    .pl-days button { text-align: left; display: flex; justify-content: space-between; gap: 8px; padding: 6px 10px; border-radius: 8px; border: 0; background: transparent; color: inherit; font: inherit; cursor: pointer; }
    .pl-days button:hover { background: var(--surface-2, rgba(127,127,127,.1)); }
    .pl-days button[aria-current="true"] { background: var(--surface-2, rgba(127,127,127,.16)); font-weight: 600; }
    .pl-wrap { position: relative; }
    .pl-off { position: absolute; left: 12px; top: 12px; }
    .pl-tog { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; padding: 10px 0; border-top: 1px solid var(--line, rgba(127,127,127,.2)); }
    .pl-tog:first-child { border-top: 0; }
    .pl-plist { margin: 0; padding-left: 18px; }
    @media (max-width: 1100px) { .pl-layout { grid-template-columns: 1fr; } }
  `);

  // Built-in place names drawn as small labels (made-up demo geography; positions approximate).
  const PLACES = [
    ['Connaught Place', 28.6315, 77.2167], ['Airport Cargo Terminal', 28.5535, 77.0960], ['Green Park', 28.5590, 77.2060],
    ['Karol Bagh', 28.6519, 77.1909], ['Gurugram', 28.4595, 77.0266], ['Noida', 28.5355, 77.3910],
    ['Chandni Chowk', 28.6506, 77.2303], ['Lajpat Nagar', 28.5677, 77.2433], ['Saket', 28.5245, 77.2066],
    ['Dwarka', 28.5921, 77.0460], ['Mahipalpur', 28.5440, 77.1230], ['Paharganj', 28.6448, 77.2130],
    ['Nehru Place', 28.5494, 77.2519], ['Rohini', 28.7495, 77.0565], ['Vasant Kunj', 28.5200, 77.1590],
    ['Janakpuri', 28.6219, 77.0878], ['Ghaziabad', 28.6692, 77.4538], ['Faridabad', 28.4089, 77.3178],
    ['Surat Ring Road', 21.1860, 72.8400], ['Varachha, Surat', 21.2100, 72.8650],
  ];
  const DUBAI = [25.2048, 55.2708];
  const TONE = { 1: '#2f5bd3', 2: '#1f8a4c', 3: '#c25a12' };
  const phoneN = (p) => {
    const m = String(p.phone || p.source_id || p.phone_label || '').match(/(\d+)/);
    return m ? +m[1] : 1;
  };

  function km(a, b) {
    const R = 6371, r = Math.PI / 180;
    const dLat = (b[0] - a[0]) * r, dLon = (b[1] - a[1]) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function mapSvg(points) {
    const W = 960, H = 560, M = 40;
    const pts = points.filter((p) => isFinite(+p.lat) && isFinite(+p.lon) && p.lat !== null && p.lon !== null);
    let minLat = Math.min(...pts.map((p) => +p.lat)), maxLat = Math.max(...pts.map((p) => +p.lat));
    let minLon = Math.min(...pts.map((p) => +p.lon)), maxLon = Math.max(...pts.map((p) => +p.lon));
    if (!pts.length) { minLat = 28.45; maxLat = 28.75; minLon = 77.0; maxLon = 77.45; }
    // Margin, and a minimum span so a single point still has a neighbourhood around it.
    const padLat = Math.max((maxLat - minLat) * 0.12, 0.02), padLon = Math.max((maxLon - minLon) * 0.12, 0.02);
    minLat -= padLat; maxLat += padLat; minLon -= padLon; maxLon += padLon;
    // Equirectangular: shrink longitude by cos(latitude), then fit the extent keeping the aspect.
    const k = Math.cos(((minLat + maxLat) / 2) * Math.PI / 180);
    const spanX = (maxLon - minLon) * k, spanY = maxLat - minLat;
    const s = Math.min((W - 2 * M) / spanX, (H - 2 * M) / spanY);
    const ox = (W - spanX * s) / 2, oy = (H - spanY * s) / 2;
    const X = (lon) => ox + (lon - minLon) * k * s;
    const Y = (lat) => oy + (maxLat - lat) * s;
    const inside = (lat, lon) => lat >= minLat && lat <= maxLat && lon >= minLon && lon <= maxLon;

    let grid = '';
    const step = 0.05;
    if ((maxLat - minLat) / step < 120 && (maxLon - minLon) / step < 120) {
      for (let a = Math.ceil(minLat / step) * step; a <= maxLat; a += step) grid += `<line class="grid" x1="0" x2="${W}" y1="${Y(a).toFixed(1)}" y2="${Y(a).toFixed(1)}"/>`;
      for (let o = Math.ceil(minLon / step) * step; o <= maxLon; o += step) grid += `<line class="grid" y1="0" y2="${H}" x1="${X(o).toFixed(1)}" x2="${X(o).toFixed(1)}"/>`;
    }
    const labels = PLACES.filter(([, la, lo]) => inside(la, lo)).map(([n, la, lo]) =>
      `<circle class="lbl-dot" cx="${X(lo).toFixed(1)}" cy="${Y(la).toFixed(1)}" r="2"/><text class="lbl" x="${(X(lo) + 5).toFixed(1)}" y="${(Y(la) - 4).toFixed(1)}">${esc(n)}</text>`).join('');
    const maxN = Math.max(1, ...pts.map((p) => +p.n || 1));
    const circles = pts.slice().sort((a, b) => (b.n || 1) - (a.n || 1)).map((p) => {
      const i = points.indexOf(p);
      const r = 7 + 13 * Math.sqrt((+p.n || 1) / maxN);
      const pn = phoneN(p);
      const cx = X(+p.lon).toFixed(1), cy = Y(+p.lat).toFixed(1);
      const tip = `${p.place || 'A place'}: ${IB.plural(+p.n || 1, 'record', 'records')}`;
      return `<g><circle class="pt" data-pt="${i}" tabindex="0" role="button" aria-label="${esc(tip)}, Phone ${pn}" data-tip="${esc(tip)}" cx="${cx}" cy="${cy}" r="${r.toFixed(1)}" fill="${TONE[pn] || TONE[1]}"/>
        <text class="pt-n" x="${cx}" y="${(+cy + 4).toFixed(1)}" text-anchor="middle">${pn}</text></g>`;
    }).join('');
    const center = [(minLat + maxLat) / 2, (minLon + maxLon) / 2];
    const dubai = inside(DUBAI[0], DUBAI[1]) ? null : Math.round(km(center, DUBAI) / 100) * 100;
    return {
      svg: `<svg class="pl-map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Map of the places in these records. The same places are listed in text beside it.">${grid}${labels}${circles}</svg>`,
      dubai,
    };
  }

  function togetherHtml(t) {
    const recs = [];
    const add = (x) => { if (x && x.event_id) recs.push(x); else if (typeof x === 'string') recs.push({ event_id: x }); };
    add(t.a); add(t.b);
    arr(t.records).forEach(add);
    arr(t.event_ids).forEach(add);
    const phones = arr(t.phones).length ? arr(t.phones) : recs.map((r) => r.phone_label || r.source_id).filter(Boolean);
    const dist = t.meters != null ? `${IB.fmt.num(Math.round(t.meters))} m apart` : (t.distance_m != null ? `${IB.fmt.num(Math.round(t.distance_m))} m apart` : '');
    const gap = t.minutes != null ? `${IB.plural(Math.round(t.minutes), 'minute', 'minutes')} apart` : (t.gap_min != null ? `${IB.plural(Math.round(t.gap_min), 'minute', 'minutes')} apart` : '');
    return `<div class="pl-tog">
      ${IB.phoneChips(phones)}
      <span>${esc(t.text || t.place || 'Same place')}</span>
      <span class="muted small">${esc([t.ts ? IB.fmt.time(t.ts) : '', dist, gap].filter(Boolean).join(' · '))}</span>
      <span class="grow"></span>
      ${recs.slice(0, 4).map((r, i) => `<button type="button" class="btn small" data-eid="${esc(r.event_id)}">Open record ${i + 1}</button>`).join('')}
    </div>`;
  }

  async function render(view, ctx) {
    ctx.bar('');
    const day = ctx.query.day || '';
    view.innerHTML = `<div class="page stack">
      <div><h2 class="page-title">Places</h2>
      <p class="muted small">Where the phones were, from location records. The map is drawn on this computer, with no internet.</p></div>
      <section class="card" id="pl-tog"><div class="card-title">Phones together</div>${IB.skeleton('rows', 2)}</section>
      <div class="pl-layout">
        <section class="card stack">
          <div class="card-head">
            <div class="row">
              <button type="button" class="btn icon ghost" id="pl-prev" aria-label="Previous day" data-tip="Previous day">${IB.icon('chevron-left')}</button>
              <input class="input" type="date" id="pl-day" value="${esc(day)}" aria-label="Day">
              <button type="button" class="btn icon ghost" id="pl-next" aria-label="Next day" data-tip="Next day">${IB.icon('chevron-right')}</button>
              <button type="button" class="btn small ghost" id="pl-all">All days</button>
            </div>
            <span class="muted small" id="pl-sum"></span>
          </div>
          <div class="pl-wrap" id="pl-map">${IB.skeleton('page', 1)}</div>
          <div id="pl-recs"></div>
          <details class="fold"><summary>The places in text</summary><div id="pl-text"></div></details>
        </section>
        <section class="card">
          <div class="card-title">Days with places</div>
          <div class="pl-days" id="pl-days"></div>
        </section>
      </div>
    </div>`;
    const $ = (s) => IB.$(s, view);
    let data;
    try {
      data = await ctx.capi('/places', { query: { day } });
    } catch (err) {
      IB.fail($('#pl-map'), err, () => render(view, ctx));
      $('#pl-tog').innerHTML = '<div class="card-title">Phones together</div>';
      return;
    }
    data = data || {};
    const days = arr(data.days).map((d) => (typeof d === 'string' ? { day: d, n: null } : { day: d.day || d.date, n: d.n != null ? d.n : d.count }));
    const points = arr(data.points);
    const together = arr(data.together);

    $('#pl-tog').innerHTML = `<div class="card-title">Phones together</div>
      <p class="muted small">Times two phones were within 500 m of each other within 30 minutes.</p>
      ${together.length ? together.map(togetherHtml).join('') : '<p class="muted">No two phones were at the same place at the same time' + (day ? ' on this day' : '') + '.</p>'}`;

    $('#pl-days').innerHTML = days.length
      ? days.map((d) => `<button type="button" data-day="${esc(d.day)}" aria-current="${d.day === day}"><span>${esc(IB.fmt.date(d.day))}</span>${d.n != null ? `<span class="muted num">${IB.fmt.num(d.n)}</span>` : ''}</button>`).join('')
      : '<p class="muted small">No days with places.</p>';

    const total = points.reduce((s, p) => s + (+p.n || 1), 0);
    $('#pl-sum').textContent = points.length ? `${IB.plural(total, 'record', 'records')} at ${IB.plural(points.length, 'place', 'places')}${day ? ' on ' + IB.fmt.date(day) : ''}` : '';

    if (!points.length) {
      $('#pl-map').innerHTML = IB.empty(day ? 'No places on this day. Choose another day from the list.' : 'No location records on these phones.', { icon: 'pin' });
    } else {
      const m = mapSvg(points);
      $('#pl-map').innerHTML = m.svg + (m.dubai ? `<span class="chip pl-off" data-tip="Records in Dubai are off this map">${IB.icon('arrow-left', 14)} Dubai, ${IB.fmt.num(m.dubai)} km west</span>` : '');
    }
    $('#pl-text').innerHTML = points.length
      ? `<ul class="pl-plist">${points.map((p, i) => `<li><button type="button" class="link" data-pt="${i}">${esc(p.place || 'A place')}</button> · Phone ${phoneN(p)} · ${IB.plural(+p.n || 1, 'record', 'records')}</li>`).join('')}</ul>`
      : '';

    const goDay = (d) => { ctx.setQuery({ day: d }, { push: true }); render(view, ctx); };
    $('#pl-day').addEventListener('change', (e) => goDay(e.target.value));
    $('#pl-all').addEventListener('click', () => goDay(''));
    const step = (dir) => {
      if (!days.length) return;
      const sorted = days.map((d) => d.day).sort();
      let i = sorted.indexOf(day);
      if (i === -1) i = dir > 0 ? -1 : sorted.length;
      const next = sorted[i + dir];
      if (next) goDay(next);
    };
    $('#pl-prev').addEventListener('click', () => step(-1));
    $('#pl-next').addEventListener('click', () => step(1));
    $('#pl-days').addEventListener('click', (e) => {
      const b = e.target.closest('[data-day]');
      if (b) goDay(b.dataset.day);
    });

    const showPoint = async (i) => {
      const p = points[i];
      if (!p) return;
      IB.$$('.pt', view).forEach((c) => c.classList.toggle('on', +c.dataset.pt === i));
      const box = $('#pl-recs');
      const ids = arr(p.event_ids).slice(0, 50);
      box.innerHTML = `<div class="section-title">${esc(p.place || 'A place')} · ${IB.plural(+p.n || ids.length, 'record', 'records')}</div>${IB.skeleton('rows', Math.min(ids.length || 1, 4))}`;
      let recs = arr(p.records);
      if (!recs.length && ids.length) {
        const got = await Promise.all(ids.slice(0, 20).map((id) => ctx.capi('/records/' + encodeURIComponent(id)).catch(() => null)));
        recs = got.map((g, k) => (g && (g.record || g)) || { event_id: ids[k], kind: 'location', place: p.place });
      }
      box.innerHTML = `<div class="section-title">${esc(p.place || 'A place')} · ${IB.plural(+p.n || ids.length, 'record', 'records')}</div>
        <div class="rec-list">${recs.map((r) => IB.recordRow(r, { phone: true })).join('')}</div>
        ${ids.length > 20 ? `<p class="muted small">Showing the first 20. Open the Timeline for this day to see them all.</p>` : ''}`;
    };
    const root = view.firstElementChild;
    root.addEventListener('click', (e) => {
      const c = e.target.closest('[data-pt]');
      if (c) showPoint(+c.dataset.pt);
    });
    root.addEventListener('keydown', (e) => {
      const c = e.target.closest && e.target.closest('circle[data-pt]');
      if (c && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); showPoint(+c.dataset.pt); }
    });
  }

  IB.page('places', { title: 'Places', render });
})();
