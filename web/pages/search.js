/* Search: IB.page('search', ...). See docs/frontend-interfaces.md. */
(() => {
  const esc = (v) => IB.esc(v);

  const MODES = {
    auto: { link: '', said: '' },
    exact: { link: 'Only these exact words', said: 'Searched only these exact words.' },
    fuzzy: { link: 'Allow typing mistakes', said: 'Searched allowing typing mistakes.' },
    meaning: { link: 'Find by meaning', said: 'Searched by meaning.' },
  };
  const FILTER_KEYS = ['app', 'kind', 'person', 'phone', 'status', 'from', 'to'];

  IB.css('page-search', `
    .srch-box { display: flex; gap: 12px; align-items: center; }
    .srch-box .search-big { flex: 1; }
    .srch-head { display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
    .srch-modes { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
    .srch-modes .sep { color: var(--text-3, var(--text-2)); }
    .srch-tools { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .srch-chips { display: flex; gap: 8px; flex-wrap: wrap; }
    .srch-chips .chip { cursor: pointer; }
  `);

  const recentKey = (cid) => 'ib.search.recent.' + cid;
  function recent(cid) {
    try { const v = JSON.parse(localStorage.getItem(recentKey(cid)) || '[]'); return Array.isArray(v) ? v : []; } catch (e) { return []; }
  }
  function remember(cid, q) {
    try {
      const list = [q].concat(recent(cid).filter((x) => x.toLowerCase() !== q.toLowerCase())).slice(0, 8);
      localStorage.setItem(recentKey(cid), JSON.stringify(list));
    } catch (e) { /* storage may be blocked: recent searches just won't show */ }
  }

  function appOptions() {
    const seen = new Map();
    ((IB.state.stats || {}).by_app || []).forEach((a) => { if (a.app && !seen.has(a.app)) seen.set(a.app, a.app); });
    if (!seen.size) ['whatsapp', 'sms', 'telegram', 'signal', 'phone'].forEach((a) => seen.set(a, a));
    return [...seen.keys()].map((a) => [a, a.charAt(0).toUpperCase() + a.slice(1)]);
  }
  function phoneOptions() {
    return (IB.state.phones || []).map((p) => [String(p.source_id), p.label || p.phone_no || 'Phone ' + p.source_id]);
  }

  async function render(view, ctx) {
    const q = ctx.query || {};
    ctx.bar('');
    const text = String(q.q || '').trim();
    const mode = MODES[q.mode] ? q.mode : 'auto';

    view.innerHTML = `<div class="page stack">
      <form class="srch-box" id="srch-form" role="search">
        <input class="search-big" id="srch-q" type="search" placeholder="Any word, name or number" aria-label="Search every record"
               autocomplete="off" spellcheck="false" value="${esc(text)}">
        <button type="submit" class="btn primary">Search</button>
      </form>
      <div id="srch-body" class="stack"></div>
    </div>`;

    const input = IB.$('#srch-q', view);
    const body = IB.$('#srch-body', view);

    IB.$('#srch-form', view).addEventListener('submit', (e) => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) { input.focus(); return; }
      IB.go(IB.link('search', Object.assign({}, pick(ctx.query), { q: v, mode: ctx.query.mode || '' })));
    });

    if (!text) {
      const list = recent(ctx.cid);
      body.innerHTML = `${list.length ? `<section class="stack"><h3 class="section-title">Recent searches</h3>
        <div class="srch-chips">${list.map((s) => `<button type="button" class="chip" data-q="${esc(s)}">${esc(s)}</button>`).join('')}</div></section>` : ''}
        <div class="card stack">
          <p class="muted">Tip: search a number in any form: 98995 12640 or +91 9899512640</p>
          <p class="muted">Tip: one word finds every spelling, so "paisa" also finds "pese", "paise" and "पैसे".</p>
        </div>`;
      body.addEventListener('click', (e) => {
        const c = e.target.closest('[data-q]');
        if (c) IB.go(IB.link('search', { q: c.dataset.q }));
      });
      if (!ctx.back) input.focus();
      return;
    }

    remember(ctx.cid, text);
    ctx.exportable('search', () => Object.assign({ q: text, mode: mode === 'auto' ? '' : mode }, pick(ctx.query)));

    body.innerHTML = `<div class="srch-head">
        <div class="stack" style="gap:4px">
          <h2 class="page-title" id="srch-count" aria-live="polite">Searching for '${esc(text)}'…</h2>
          <p class="muted small" id="srch-how"></p>
          <div class="srch-modes small" id="srch-modes"></div>
        </div>
      </div>
      <div id="srch-filters"></div>
      <div id="srch-list"></div>`;

    // The other ways to search.
    const modes = IB.$('#srch-modes', view);
    if (mode === 'auto') {
      modes.innerHTML = ['exact', 'fuzzy', 'meaning'].map((m) =>
        `<a class="link" href="${esc(IB.link('search', Object.assign({}, pick(q), { q: text, mode: m })))}">${esc(MODES[m].link)}</a>`)
        .join('<span class="sep" aria-hidden="true">|</span>');
    } else {
      modes.innerHTML = `<span>${esc(MODES[mode].said)}</span>
        <a class="link" href="${esc(IB.link('search', Object.assign({}, pick(q), { q: text })))}">Back to every spelling</a>`;
    }


    const filters = IB.filters(IB.$('#srch-filters', view), {
      fields: [
        { key: 'app', label: 'App', type: 'select', options: appOptions() },
        { key: 'kind', label: 'Type', type: 'select', options: [['message', 'Messages'], ['call', 'Calls'], ['photo', 'Photos'], ['voice', 'Voice notes'], ['document', 'Documents'], ['location', 'Places']] },
        { key: 'phone', label: 'Phone', type: 'select', options: phoneOptions() },
        { key: 'person', label: 'Person', type: 'text' },
        { key: 'status', label: 'Status', type: 'select', options: [['deleted', 'Deleted, recovered']] },
        { key: 'from', label: 'From', type: 'date' },
        { key: 'to', label: 'To', type: 'date' },
      ],
      values: pick(q),
      onChange(values) {
        ctx.setQuery(Object.assign(blankFilters(), values), { push: true });
        list.reload();
      },
    });


    const count = IB.$('#srch-count', view);
    const how = IB.$('#srch-how', view);
    const list = IB.moreList(IB.$('#srch-list', view), {
      noun: ['result', 'results'],
      alive: ctx.alive,
      empty: `No records match '${text}'.` + (mode === 'exact' ? ' Try every spelling instead.' : ' Try fewer words or clear the filters.'),
      async load(offset) {
        const cur = Object.assign({}, filters.values ? filters.values() : pick(ctx.query));
        const r = await ctx.capi('/search', { query: Object.assign({ q: text, mode: mode === 'auto' ? '' : mode, offset }, cur) });
        const hits = (r && (r.hits || r.rows)) || [];
        const total = r && r.total != null ? r.total : hits.length;
        if (offset === 0) {
          count.textContent = IB.plural(total, 'result', 'results') + " for '" + text + "'";
          how.textContent = (r && r.how) || '';
        }
        return { rows: hits, total };
      },
      row: (h) => IB.recordRow(h, { phone: true }),
    });
  }

  function pick(query) {
    const out = {};
    FILTER_KEYS.forEach((k) => { if (query && query[k]) out[k] = query[k]; });
    return out;
  }
  function blankFilters() {
    const out = {};
    FILTER_KEYS.forEach((k) => { out[k] = ''; });
    return out;
  }

  IB.page('search', {
    title: (ctx) => (ctx && ctx.query && ctx.query.q ? "Search: '" + ctx.query.q + "'" : 'Search'),
    render,
  });
})();
