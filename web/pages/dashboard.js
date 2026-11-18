/* The Dashboard and its own tabs: IB.page('dashboard', ...) and IB.dashboardTab(...). See docs/frontend-interfaces.md.
   Own tabs: plain (10), activity (20), people (30), apps (40), about (50). Others register brief, keyq and across. */
(() => {
  const IB = window.IB;
  if (!IB) return;
  const esc = (v) => IB.esc(v);
  const num = (n) => IB.fmt.num(Number(n) || 0);
  const arr = (v) => (Array.isArray(v) ? v : []);

  IB.css('ib-dashboard', `
    .db-hero { display: flex; flex-direction: column; gap: 14px; }
    .db-hero .db-l1 { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; min-width: 0; }
    .db-hero .db-name { font-size: var(--t-2xl, 28px); font-weight: 700; margin: 0; }
    .db-hero .db-about { display: flex; gap: 8px; align-items: baseline; min-width: 0; flex: 1 1 320px; }
    .db-hero .db-about p { margin: 0; opacity: .85; }
    .db-hero .db-about.open p { -webkit-line-clamp: unset; display: block; overflow: visible; white-space: normal; }
    .db-hero .db-l2 { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .db-hero .db-l2 .db-acts { margin-left: auto; display: flex; gap: 8px; }
    .db-hero a.db-chip { text-decoration: none; }
    .db-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
    .db-tabs .tab { flex: 1 1 0; white-space: normal; text-align: center; }
    .db-panel { min-height: 200px; }
    .db-sentences { display: flex; flex-direction: column; gap: 12px; margin: 0; padding: 0; list-style: none; }
    .db-sentences li { font-size: var(--t-l, 17px); line-height: 1.5; }
    .db-sentences a { color: inherit; text-decoration: underline; text-decoration-color: var(--border, rgba(127,127,127,.5)); text-underline-offset: 3px; }
    .db-sentences a:hover { text-decoration-color: currentColor; }
    .db-asks { display: flex; flex-wrap: wrap; gap: 8px; }
    .db-two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: stretch; }
    .db-two > .card { min-width: 0; }
    .db-days { display: flex; flex-direction: column; gap: 4px; }
    .db-day { display: flex; justify-content: space-between; gap: 12px; padding: 6px 8px; border-radius: 8px; color: inherit; text-decoration: none; }
    .db-day:hover, .db-day:focus-visible { background: var(--hover, rgba(127,127,127,.1)); }
    .db-apps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    @media (min-width: 1700px) { .db-apps { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    .db-app { display: flex; gap: 12px; align-items: flex-start; color: inherit; text-decoration: none; height: 100%; }
    .db-app:hover { border-color: var(--text-3, rgba(127,127,127,.5)); }
    .db-fp { display: inline-flex; align-items: center; gap: 6px; }
  `);

  const APP_NAMES = { whatsapp: 'WhatsApp', sms: 'SMS', calls: 'Calls', call: 'Calls', telegram: 'Telegram', signal: 'Signal',
    messages: 'Messages', imessage: 'Messages', photos: 'Photos', photo: 'Photos', voice: 'Voice notes', voice_notes: 'Voice notes',
    documents: 'Documents', document: 'Documents', bank: 'Bank messages', upi: 'UPI', location: 'Places', locations: 'Places',
    browser: 'Browser', contacts: 'Contacts', notes: 'Notes', video: 'Videos', videos: 'Videos', email: 'Email', instagram: 'Instagram' };
  const APP_ICONS = { whatsapp: 'chat', sms: 'mail', calls: 'phone', call: 'phone', telegram: 'chat', signal: 'chat', messages: 'chat',
    imessage: 'chat', photos: 'image', photo: 'image', voice: 'mic', voice_notes: 'mic', documents: 'file', document: 'file',
    bank: 'rupee', upi: 'rupee', location: 'pin', locations: 'pin', video: 'film', videos: 'film', email: 'mail', contacts: 'users', notes: 'notes' };
  const appName = (a) => APP_NAMES[String(a || '').toLowerCase()] || (a ? String(a).charAt(0).toUpperCase() + String(a).slice(1) : 'Other');
  const appIcon = (a, kind) => APP_ICONS[String(a || '').toLowerCase()] || APP_ICONS[String(kind || '').toLowerCase()] || 'list';

  /* Case stats: always fetched fresh, falling back to what the shell already has. */
  async function getStats(ctx) {
    try { return (await ctx.capi('/stats')) || {}; } catch (e) { if (IB.state.stats) return IB.state.stats; throw e; }
  }

  /* ---------- Hero ---------- */
  function heroHtml(c, phones) {
    const chips = arr(phones).map((p) => {
      const sid = p && typeof p === 'object' ? p.source_id : p;
      const href = IB.link('sources', sid != null ? { source: sid } : {});
      return `<a class="db-chip" href="${esc(href)}" data-tip="Open Evidence added">${IB.phoneChip(p && typeof p === 'object' ? (p.label ? { phone_no: p.phone_no, label: p.label } : p.source_id) : p)}</a>`;
    }).join('');
    return `<section class="card hero db-hero" aria-label="This case">
      <div class="db-l1">
        <h2 class="db-name">${esc(c.name || 'This case')}</h2>
        ${c.number ? `<span class="caps small">Case ${esc(c.number)}</span>` : ''}
        ${c.about ? `<div class="db-about" id="db-about"><p class="clamp-1">${esc(c.about)}</p><button type="button" class="link small" id="db-more" aria-expanded="false">More</button></div>` : ''}
      </div>
      <div class="db-l2">
        ${chips || '<span class="small">No phones added yet</span>'}
        <div class="db-acts">
          <a class="btn primary" href="${esc(IB.link('sources'))}">${IB.icon('plus', 16)} Add a phone or file</a>
          <button type="button" class="btn" id="db-edit">${IB.icon('pencil', 16)} Edit case details</button>
        </div>
      </div>
    </section>`;
  }

  async function editCase(ctx) {
    const c = IB.state.case || {};
    const v = await IB.dialog({
      title: 'Edit case details',
      body: `<div class="stack">
        <label class="field"><span>Case name</span><input class="input" name="name" required value="${esc(c.name || '')}"></label>
        <label class="field"><span>Case number</span><input class="input" name="number" value="${esc(c.number || '')}"></label>
        <label class="field"><span>What is this case about?</span><textarea class="textarea" name="about" rows="4" required>${esc(c.about || '')}</textarea>
          <span class="tiny muted">The AI reads this first. Say what you suspect: goods, people, money, places.</span></label>
      </div>`,
      actions: [{ label: 'Cancel', value: null }, { label: 'Save the details', kind: 'primary', value: 'save', busy: 'Saving…' }],
      async onAction(val, el) {
        if (val !== 'save') return;
        const f = IB.formValues(el);
        await IB.api('/api/cases/' + encodeURIComponent(ctx.cid), { method: 'PATCH', body: { name: (f.name || '').trim(), number: (f.number || '').trim(), about: (f.about || '').trim() } });
        return true;
      },
    });
    if (v === 'save') {
      IB.status('Case details saved.');
      try { await IB.refreshCase(); } catch (e) { /* the shell shows its own error */ }
      IB.reload();
    }
  }

  /* ---------- Progress strip for phones still being prepared ---------- */
  let progressEl = null;
  function drawProgress(jobs) {
    if (!progressEl || !progressEl.isConnected) return;
    const running = arr(jobs).filter((j) => j && (j.status === 'running' || j.status === 'waiting' || !j.status) && (!j.case_id || j.case_id === IB.state.cid));
    progressEl.innerHTML = running.map((j) => IB.progress(j, (j.label ? j.label.replace(/^Adding/, 'Getting') + ' ready' : 'Getting a phone ready'))).join('');
    if (running.length) progressEl.insertAdjacentHTML('beforeend', '<p class="small muted" style="margin:4px 0 0">You can use the pages now.</p>');
    progressEl.hidden = !running.length;
  }
  IB.on('jobs', drawProgress);

  /* ---------- Main numbers ---------- */
  function tilesHtml(s) {
    const L = s.links || {};
    const to = (key, page, params) => (L[key] ? sentenceHref(L[key]) : IB.link(page, params));
    const deleted = Number(s.deleted) || 0;
    const missed = Number(s.missed != null ? s.missed : (s.calls_missed != null ? s.calls_missed : 0)) || 0;
    return `<div class="db-tiles">
      ${IB.statTile({ n: num(s.records), label: 'Records', href: to('records', 'timeline') })}
      ${IB.statTile({ n: num(s.messages), label: 'Messages', sub: deleted ? `of which ${num(deleted)} deleted, recovered` : '', href: to('messages', 'timeline', { kind: 'message' }) })}
      ${IB.statTile({ n: num(s.calls), label: 'Calls', sub: missed ? `of which ${num(missed)} missed` : '', href: to('calls', 'calls') })}
      ${IB.statTile({ n: num(s.people_in_touch), label: 'People in touch', href: to('people_in_touch', 'people', { group: 'in-touch' }) })}
    </div>`;
  }

  /* ---------- The page ---------- */
  IB.page('dashboard', {
    title: (ctx) => (IB.state.case && IB.state.case.name) || 'Dashboard',
    async render(view, ctx) {
      ctx.bar('');
      const c = IB.state.case || {};
      view.innerHTML = `<div class="page stack">
        <div id="db-hero">${heroHtml(c, IB.state.phones || [])}</div>
        <div id="db-progress" class="stack" role="status" aria-live="polite" hidden></div>
        <div id="db-tiles">${IB.skeleton('cards', 4)}</div>
        <div class="tabs db-tabs" id="db-tabs"></div>
        <div class="db-panel" id="db-panel" role="tabpanel"></div>
      </div>`;
      wireHero(view, ctx);
      progressEl = IB.$('#db-progress', view);
      IB.refreshJobs && Promise.resolve(IB.refreshJobs()).catch(() => {});

      const tilesEl = IB.$('#db-tiles', view);
      const loadTiles = async () => {
        try {
          const s = await getStats(ctx);
          if (!ctx.alive()) return;
          tilesEl.innerHTML = tilesHtml(s);
        } catch (err) { IB.fail(tilesEl, err, loadTiles); }
      };
      const tilesP = loadTiles();

      const tabs = IB.dashboardTabs(ctx) || [];
      const panel = IB.$('#db-panel', view);
      let active = ctx.query.tab || (ctx.keep && ctx.keep.tab) || 'plain';
      if (!tabs.some((t) => t.key === active)) active = tabs.length ? tabs[0].key : 'plain';
      const drawTab = async (key) => {
        const t = tabs.find((x) => x.key === key);
        panel.setAttribute('aria-label', t ? t.label : 'Tab');
        if (!t) { panel.innerHTML = IB.empty('This tab is still being built.'); return; }
        panel.innerHTML = IB.skeleton('page');
        try { await t.render(panel, ctx); } catch (err) { IB.fail(panel, err, () => drawTab(key)); }
      };
      IB.tabs(IB.$('#db-tabs', view), {
        tabs: tabs.map((t) => ({ key: t.key, label: t.label })),
        active,
        label: 'Dashboard',
        onChange(key) {
          active = key;
          if (ctx.keep) ctx.keep.tab = key;
          ctx.setQuery({ tab: key === 'plain' ? '' : key });
          drawTab(key);
        },
      });
      return Promise.all([tilesP, drawTab(active)]);
    },
  });

  function wireHero(view, ctx) {
    const more = IB.$('#db-more', view);
    if (more) more.addEventListener('click', () => {
      const box = IB.$('#db-about', view);
      const open = box.classList.toggle('open');
      more.textContent = open ? 'Less' : 'More';
      more.setAttribute('aria-expanded', String(open));
    });
    const edit = IB.$('#db-edit', view);
    if (edit) edit.addEventListener('click', () => editCase(ctx));
  }

  /* Redraw the hero when the shell loads the case, and the numbers when a job finishes. */
  IB.on('case', () => {
    const hero = document.getElementById('db-hero');
    if (!hero || !hero.isConnected) return;
    hero.innerHTML = heroHtml(IB.state.case || {}, IB.state.phones || []);
    wireHero(hero, { cid: IB.state.cid });
  });
  IB.on('jobs:done', async () => {
    const tilesEl = document.getElementById('db-tiles');
    if (!tilesEl || !tilesEl.isConnected || !IB.state.cid) return;
    try {
      const s = await IB.capi('/stats');
      if (tilesEl.isConnected) tilesEl.innerHTML = tilesHtml(s || {});
    } catch (e) { /* keep the old numbers */ }
  });

  /* ---------- Tab 1: In plain words ---------- */
  const ASKS = ['Paisa kisne kisko bheja?', 'Who did they talk to most at night?', 'Which messages were deleted, and from which chats?', 'Were any of the phones at the same place at the same time?'];
  function sentenceHref(link) {
    if (!link) return '';
    if (typeof link === 'string') return link.startsWith('#') ? link : IB.link(link);
    const page = link.page === 'dashboard' ? '' : (link.page || '');
    const params = link.params || {};
    // person/{pid} and record/{eid} are paths, not query.
    if (page === 'person' && params.pid != null) return IB.link('person/' + params.pid);
    if (page === 'record' && params.eid != null) return IB.link('record/' + params.eid);
    return IB.link(page, params);
  }

  IB.dashboardTab('plain', {
    label: 'In plain words',
    order: 10,
    async render(el, ctx) {
      el.innerHTML = IB.skeleton('rows', 5);
      const story = await ctx.capi('/story');
      const sentences = arr(story && story.sentences).filter((s) => s && s.text);
      const list = sentences.length
        ? `<ul class="db-sentences">${sentences.map((s) => {
            const href = sentenceHref(s.link);
            return `<li>${href ? `<a href="${esc(href)}">${esc(s.text)}</a>` : esc(s.text)}</li>`;
          }).join('')}</ul>`
        : IB.empty('Nothing to say yet. Add a phone, and the main facts appear here.', { icon: 'notes' });
      el.innerHTML = `<div class="stack">
        ${story && story.updating ? IB.updating(true) : ''}
        <div class="card">${list}</div>
        <div class="card stack">
          <div class="card-title">Questions you could ask</div>
          <div class="db-asks">${(arr(story && story.questions).length ? arr(story.questions) : ASKS).slice(0, 4).map((q) => `<button type="button" class="chip" data-ask="${esc(q)}">${esc(q)}</button>`).join('')}</div>
        </div>
      </div>`;
    },
  });

  /* ---------- Tab 2: Activity ---------- */
  IB.dashboardTab('activity', {
    label: 'Activity',
    order: 20,
    async render(el, ctx) {
      el.innerHTML = IB.skeleton('cards', 2);
      const [act, stats] = await Promise.all([ctx.capi('/activity'), getStats(ctx).catch(() => ({}))]);
      const a = act || {};
      const days = arr(a.busiest_days).slice(0, 5);
      const byApp = arr(stats && stats.by_app).slice().sort((x, y) => (Number(y.n) || 0) - (Number(x.n) || 0));
      el.innerHTML = `<div class="stack">
        ${a.updating ? IB.updating(true) : ''}
        <div class="db-two">
          <div class="card stack"><div class="card-head"><div class="card-title">Messages and calls per month <span class="tiny muted">India time</span></div></div><div id="db-month"></div></div>
          <div class="card stack"><div class="card-head"><div class="card-title">When activity happens <span class="tiny muted">India time</span></div></div><div id="db-heat"></div></div>
        </div>
        <div class="db-two">
          <div class="card stack"><div class="card-title">Busiest days</div>
            ${days.length ? `<div class="db-days">${days.map((d) => {
              const key = d.day || d.date || (d.ts ? IB.fmt.dayKey(d.ts) : '');
              const n = Number(d.n != null ? d.n : d.count) || 0;
              const label = key ? IB.fmt.day(key + 'T12:00:00+05:30') : '';
              return `<a class="db-day" href="${esc(d.link ? sentenceHref(d.link) : IB.link('timeline', { day: key }))}"><span>${esc(label || key)}</span><span class="num muted">${esc(IB.plural(n, 'record', 'records'))}</span></a>`;
            }).join('')}</div>` : IB.empty('No busy days yet.')}
          </div>
          <div class="card stack"><div class="card-title">By app</div>
            ${IB.charts.hbars(byApp.map((r) => ({ label: (r.name || appName(r.app)) + (byApp.filter((x) => x.app === r.app).length > 1 && r.kind ? ', ' + r.kind + 's' : ''), n: r.n, icon: appIcon(r.app, r.kind), href: r.link ? sentenceHref(r.link) : IB.link('timeline', { app: r.app }) })))}
          </div>
        </div>
      </div>`;
      IB.charts.monthly(IB.$('#db-month', el), a.monthly);
      IB.charts.heat(IB.$('#db-heat', el), a.heat);
    },
  });

  /* ---------- Tab 3: People ---------- */
  const pm = (p) => Number(p.messages != null ? p.messages : p.n_messages) || 0;
  const pc = (p) => Number(p.calls != null ? p.calls : p.n_calls) || 0;
  IB.dashboardTab('people', {
    label: 'People',
    order: 30,
    async render(el, ctx) {
      el.innerHTML = IB.skeleton('rows', 8);
      const res = await ctx.capi('/people', { query: { group: 'in-touch' } });
      const rows = arr(res && (res.rows || res.people || (Array.isArray(res) ? res : [])))
        .filter((p) => !p.is_owner)
        .slice()
        .sort((x, y) => (pm(y) + pc(y)) - (pm(x) + pc(x)))
        .slice(0, 10);
      if (!rows.length) { el.innerHTML = IB.empty('No people in touch yet.', { icon: 'users' }); return; }
      const maxM = Math.max(1, ...rows.map(pm));
      const maxC = Math.max(1, ...rows.map(pc));
      el.innerHTML = `<div class="card stack">
        <div class="card-head"><div class="card-title">Top 10 people by two-way contact</div><a class="btn small" href="${esc(IB.link('people'))}">See everyone</a></div>
        <div class="table-wrap"><table class="table">
          <thead><tr><th>Name</th><th>Messages</th><th>Calls</th><th>Last contact</th><th>Phones</th></tr></thead>
          <tbody>${rows.map((p) => {
            const names = arr(p.also && p.also.length ? p.also : p.names).map((n) => (typeof n === 'object' && n ? n.name || n.text : n)).filter((n) => n && n !== p.name);
            const m = pm(p), cl = pc(p);
            const last = p.last_ts || p.last_contact;
            const phones = arr(p.phones || p.sources || p.phone_labels);
            const href = IB.link('person/' + p.person_id);
            return `<tr class="clickable" tabindex="0" data-href="${esc(href)}">
              <td><div><b>${esc(p.name || p.display || 'Unknown')}</b></div>${names.length ? `<div class="tiny muted clamp-1">saved as ${esc(names.slice(0, 3).join(', '))}</div>` : ''}</td>
              <td class="num"><span class="row" style="gap:8px">${IB.charts.miniBars([{ n: m }], { max: maxM, label: IB.plural(m, 'message', 'messages') })}${esc(num(m))}</span></td>
              <td class="num"><span class="row" style="gap:8px">${IB.charts.miniBars([{ n: cl }], { max: maxC, tone: 'green', label: IB.plural(cl, 'call', 'calls') })}${esc(num(cl))}</span></td>
              <td class="small">${last ? esc(IB.fmt.time(last)) : '<span class="muted">Not known</span>'}</td>
              <td>${phones.length ? IB.phoneChips(phones) : ''}</td>
            </tr>`;
          }).join('')}</tbody>
        </table></div>
      </div>`;
    },
  });

  /* ---------- Tab 4: Apps ---------- */
  IB.dashboardTab('apps', {
    label: 'Apps',
    order: 40,
    async render(el, ctx) {
      el.innerHTML = IB.skeleton('cards', 6);
      const s = await getStats(ctx);
      const byApp = arr(s && s.by_app);
      // Several kinds can share one app: group them into one card.
      const groups = new Map();
      byApp.forEach((r) => {
        const key = String(r.app || r.kind || 'other');
        const g = groups.get(key) || { app: key, name: r.name, link: r.link, kinds: [], n: 0, first: null, last: null };
        g.n += Number(r.n) || 0;
        if (r.kind) g.kinds.push({ kind: r.kind, n: Number(r.n) || 0 });
        if (r.first_ts && (!g.first || r.first_ts < g.first)) g.first = r.first_ts;
        if (r.last_ts && (!g.last || r.last_ts > g.last)) g.last = r.last_ts;
        groups.set(key, g);
      });
      const list = [...groups.values()].sort((a, b) => b.n - a.n);
      if (!list.length) { el.innerHTML = IB.empty('No apps yet. Add a phone first.', { icon: 'grid' }); return; }
      const tones = ['blue', 'green', 'violet', 'orange', 'teal'];
      el.innerHTML = `<div class="db-apps">${list.map((g, i) => {
        const range = g.first && g.last ? `${IB.fmt.date(g.first)} to ${IB.fmt.date(g.last)}` : '';
        const kinds = g.kinds.length > 1 ? g.kinds.map((k) => IB.plural(k.n, k.kind, k.kind + 's')).join(', ') : '';
        const href = g.kinds.length === 1 && g.link ? sentenceHref(g.link) : IB.link('timeline', { app: g.app });
        return `<a class="card db-app" href="${esc(href)}">
          ${IB.tile(appIcon(g.app, g.kinds[0] && g.kinds[0].kind), tones[i % tones.length])}
          <div class="stack" style="gap:4px;min-width:0">
            <div class="card-title">${esc(g.name || appName(g.app))}</div>
            <div class="num">${esc(IB.plural(g.n, 'record', 'records'))}</div>
            ${kinds ? `<div class="tiny muted clamp-2">${esc(kinds)}</div>` : ''}
            ${range ? `<div class="tiny muted">${esc(range)}</div>` : ''}
          </div>
        </a>`;
      }).join('')}</div>`;
    },
  });

  /* ---------- Tab 5: About the case ---------- */
  IB.dashboardTab('about', {
    label: 'About the case',
    order: 50,
    async render(el, ctx) {
      el.innerHTML = IB.skeleton('cards', 2);
      const c = IB.state.case || {};
      let sources = [];
      try { sources = arr(await ctx.capi('/sources')); } catch (e) { sources = arr(IB.state.phones); }
      const officers = arr(c.officers || c.access).map((o) => (typeof o === 'object' && o ? o.name : o)).filter(Boolean);
      const madeBy = c.created_by_name || (typeof c.created_by === 'string' && !/^\d+$/.test(c.created_by) ? c.created_by : '');
      el.innerHTML = `<div class="stack">
        <div class="card stack">
          <div class="card-head"><div class="card-title">The case</div><button type="button" class="btn small" id="db-edit2">${IB.icon('pencil', 14)} Edit case details</button></div>
          <div class="kv">
            <span class="muted">Case number</span><span>${esc(c.number || 'Not given')}</span>
            <span class="muted">What it's about</span><span>${esc(c.about || 'Not given')}</span>
            <span class="muted">Made</span><span>${c.created_at ? esc(IB.fmt.time(c.created_at)) : 'Not known'}${madeBy ? ' by ' + esc(madeBy) : ''}</span>
            ${officers.length ? `<span class="muted">Officers with access</span><span>${esc(officers.join(', '))}</span>` : ''}
          </div>
        </div>
        <div class="card stack">
          <div class="card-title">${esc(IB.plural(sources.length, 'phone', 'phones'))}</div>
          ${sources.length ? `<div class="table-wrap"><table class="table">
            <thead><tr><th>Phone</th><th>Device</th><th>Kind of file</th><th>Fingerprint</th><th>Dates</th><th>Records</th></tr></thead>
            <tbody>${sources.map((s) => {
              const fp = String(s.sha256 || '');
              const file = String(s.file_name || '');
              const ext = file.includes('.') ? file.split('.').pop().toUpperCase() + ' export' : (s.kind || '');
              const dates = s.first_ts && s.last_ts ? `${IB.fmt.date(s.first_ts)} to ${IB.fmt.date(s.last_ts)}` : '';
              return `<tr class="clickable" tabindex="0" data-href="${esc(IB.link('phone', { source: s.source_id }))}">
                <td>${IB.phoneChip(s.label ? { phone_no: s.phone_no, label: s.label } : s.source_id)}${s.status && s.status !== 'done' ? ' ' + IB.pill(s.status === 'reading' ? 'Being read' : 'Could not be read', s.status === 'reading' ? 'blue' : 'orange') : ''}</td>
                <td>${esc(s.device || s.platform || '')}${s.os ? `<div class="tiny muted">${esc(s.os)}</div>` : ''}</td>
                <td>${esc(ext)}</td>
                <td>${fp ? `<span class="db-fp"><span class="code">${esc(fp.slice(0, 12))}</span><button type="button" class="btn icon ghost small" data-copy="${esc(fp)}" aria-label="Copy the fingerprint" data-tip="Copy the whole fingerprint">${IB.icon('copy', 14)}</button></span>` : ''}</td>
                <td class="small">${esc(dates)}</td>
                <td class="num">${esc(num(s.n_events))}</td>
              </tr>`;
            }).join('')}</tbody>
          </table></div>` : IB.empty('No phones added yet.', { icon: 'smartphone' })}
        </div>
      </div>`;
      const b = IB.$('#db-edit2', el);
      if (b) b.addEventListener('click', () => editCase(ctx));
    },
  });
})();
