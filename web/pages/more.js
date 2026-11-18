/* More pages: Code words, Evidence added, Audit, Phone details, and the warrant limit dialog. See docs/frontend-interfaces.md. */
(() => {
  const esc = (v) => IB.esc(v);
  const arr = (v, ...keys) => {
    if (Array.isArray(v)) return v;
    if (v && typeof v === 'object') for (const k of keys) if (Array.isArray(v[k])) return v[k];
    return [];
  };

  IB.css('pg-more', `
    .cw-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
    .cw-ex { margin: 6px 0; padding: 8px 10px; border-radius: 8px; background: var(--surface-2, rgba(127,127,127,.08)); cursor: pointer; }
    .cw-word { font-size: 1.15em; font-weight: 600; }
    .ev-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 16px; }
    .ev-fp { word-break: break-all; }
    .pd-section { margin-bottom: 4px; }
  `);

  const label = (k) => String(k).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
  const plain = (v) => {
    if (v == null || v === '') return '';
    if (typeof v === 'boolean') return v ? 'Yes' : 'No';
    if (Array.isArray(v)) return v.map(plain).join(', ');
    if (typeof v === 'object') return Object.entries(v).map(([k, x]) => label(k) + ': ' + plain(x)).join('; ');
    return String(v);
  };

  /* ---------- Code words ---------- */

  async function codes(view, ctx) {
    ctx.bar('');
    view.innerHTML = `<div class="page stack">
      <div><h2 class="page-title">Code words</h2>
      <p class="muted small">Words used unusually often in these chats, often at night or near money. They are suggestions: an officer confirms what each one means.</p></div>
      <div id="cw-tabs"></div>
      <div id="cw-body">${IB.skeleton('cards', 4)}</div>
    </div>`;
    const body = IB.$('#cw-body', view);
    let data;
    try {
      data = await ctx.capi('/codes');
    } catch (err) {
      IB.fail(body, err, () => codes(view, ctx));
      return;
    }
    const sugg = arr(data, 'suggestions').filter((s) => !s.status || s.status === 'suggested');
    const book = arr(data && data.book != null ? data.book : (data && data.confirmed), 'rows')
      .concat(arr(data, 'suggestions').filter((s) => s.status === 'confirmed' && !arr(data && data.book).length));
    const active = ctx.keep.cwTab || ctx.query.view || 'suggestions';
    const draw = (key) => {
      ctx.keep.cwTab = key;
      if (key === 'book') {
        body.innerHTML = book.length
          ? `<div class="table-wrap"><table class="table"><thead><tr><th>Word</th><th>Meaning</th><th>Confirmed by</th><th>When</th><th class="num">Times used</th></tr></thead><tbody>
            ${book.map((c) => `<tr class="clickable" data-href="${esc(IB.link('search', { q: c.word }))}" tabindex="0">
              <td><b>${esc(c.word)}</b></td><td>${esc(c.meaning || '')}</td><td>${esc(c.by || c.confirmed_by || c.officer || '')}</td>
              <td>${c.at || c.confirmed_at ? esc(IB.fmt.time(c.at || c.confirmed_at)) : ''}</td><td class="num">${IB.fmt.num(c.n || c.count || 0)}</td></tr>`).join('')}
            </tbody></table></div>`
          : IB.empty('No code words confirmed yet. Confirm a suggestion to add it to the code book; search then finds its meaning too.', { icon: 'key' });
        return;
      }
      body.innerHTML = sugg.length
        ? `<div class="cw-grid">${sugg.map((s, i) => {
            const ex = arr(s.examples || s.lines, 'rows').slice(0, 3);
            return `<article class="card stack" data-cw="${i}">
              <div class="card-head"><span class="cw-word">${esc(s.word)}</span>
                <span class="muted small">${IB.plural(s.n || s.count || 0, 'use', 'uses')}${s.chats ? ' in ' + IB.plural(s.chats, 'chat', 'chats') : ''}</span></div>
              ${ex.map((e) => `<div class="cw-ex small" tabindex="0" ${e.event_id ? `data-eid="${esc(e.event_id)}"` : ''}>${e.snippet_html ? IB.safe(e.snippet_html) : esc(e.text || e.body || '')}</div>`).join('')}
              ${s.why ? `<p class="small muted">Why it stands out: ${esc(s.why)}</p>` : ''}
              ${s.meaning || s.suggested_meaning ? `<p class="small">Suggested meaning: <b>${esc(s.meaning || s.suggested_meaning)}</b>${s.meaning_from ? ` <span class="muted">(from ${esc(s.meaning_from)})</span>` : ''}</p>` : ''}
              <div class="row"><button type="button" class="btn small primary" data-cw-ok="${i}">Confirm</button>
              <button type="button" class="btn small" data-cw-no="${i}">Not a code</button>
              <button type="button" class="btn small ghost" data-href="${esc(IB.link('search', { q: s.word }))}">Search for it</button></div>
            </article>`;
          }).join('')}</div>`
        : IB.empty('No code words suggested in these records.', { icon: 'key' });
    };
    IB.tabs(IB.$('#cw-tabs', view), {
      tabs: [{ key: 'suggestions', label: 'Suggestions', count: sugg.length }, { key: 'book', label: 'Code book', count: book.length }],
      active, onChange: draw, label: 'Code words',
    });
    draw(active);

    body.addEventListener('click', async (e) => {
      const ok = e.target.closest('[data-cw-ok]');
      const no = e.target.closest('[data-cw-no]');
      if (!ok && !no) return;
      const s = sugg[+(ok || no).dataset[ok ? 'cwOk' : 'cwNo']];
      if (ok) {
        const v = await IB.dialog({
          title: `What does "${s.word}" mean?`,
          body: `<label class="field"><span>Meaning</span><input class="input" name="meaning" required value="${esc(s.meaning || s.suggested_meaning || '')}"></label>`,
          actions: [{ label: 'Cancel', value: null }, { label: 'Confirm the code word', kind: 'primary', value: 'ok', busy: 'Saving…' }],
          onAction: async (value, el) => {
            if (value !== 'ok') return;
            await ctx.capi('/codes', { method: 'POST', body: { word: s.word, meaning: String(IB.formValues(el).meaning || '').trim(), status: 'confirmed' } });
          },
        });
        if (v === 'ok') { IB.status(`"${s.word}" added to the code book.`); codes(view, ctx); }
      } else {
        try {
          await ctx.capi('/codes', { method: 'POST', body: { word: s.word, meaning: '', status: 'rejected' } });
          IB.status(`"${s.word}" marked as not a code.`);
          codes(view, ctx);
        } catch (err) { IB.status(err.message, { error: true }); }
      }
    });
  }

  /* ---------- Evidence added ---------- */

  async function sources(view, ctx) {
    ctx.bar('');
    view.innerHTML = `<div class="page stack">
      <div><h2 class="page-title">Evidence added</h2>
      <p class="muted small">Every phone and file read into this case, with its fingerprint, so anyone can check it hasn't changed.</p></div>
      <div id="ev-body">${IB.skeleton('cards', 3)}</div></div>`;
    const body = IB.$('#ev-body', view);
    let list;
    try {
      list = arr(await ctx.capi('/sources'), 'sources', 'rows');
    } catch (err) {
      IB.fail(body, err, () => sources(view, ctx));
      return;
    }
    if (!list.length) {
      body.innerHTML = IB.empty('No phones added to this case yet.', { icon: 'smartphone', action: `<a class="btn primary" href="${esc(IB.link(''))}">Go to the Dashboard</a>` });
      return;
    }
    body.innerHTML = `<div class="ev-grid">${list.map((s, i) => {
      const counts = s.counts || s.by_kind || {};
      const countText = Array.isArray(s.counts_words) && s.counts_words.length ? s.counts_words.join(', ') : Array.isArray(counts)
        ? counts.map((c) => IB.plural(c.n || 0, c.kind, c.kind + 's')).join(', ')
        : Object.entries(counts).map(([k, n]) => IB.fmt.num(n) + ' ' + k).join(', ');
      const status = s.status === 'done' ? 'Read' : s.status === 'reading' ? 'Being read' : s.status === 'failed' ? 'Could not be read' : (s.status || '');
      return `<article class="card stack">
        <div class="card-head"><div class="row">${IB.phoneChip(s)}<span class="muted small">${esc([s.device, s.os].filter(Boolean).join(', '))}</span></div>
          ${status ? IB.pill(status, s.status === 'failed' ? 'orange' : s.status === 'reading' ? 'blue' : 'green') : ''}</div>
        <div class="kv">
          <span class="muted">Owner</span><span>${esc(s.owner_name || 'Not certain')}</span>
          <span class="muted">Phone number</span><span class="num">${esc(s.phone_no || '')}</span>
          <span class="muted">File</span><span>${esc([s.platform ? s.platform + ' extraction' : '', s.file_name].filter(Boolean).join(': '))}</span>
          <span class="muted">Added</span><span>${esc([s.added_by, s.added_at ? IB.fmt.time(s.added_at) : ''].filter(Boolean).join(', '))}</span>
          <span class="muted">Records</span><span>${IB.fmt.num(s.n_events || 0)}${countText ? ' (' + esc(countText) + ')' : ''}</span>
          <span class="muted">Dates</span><span>${s.first_ts ? esc(IB.fmt.date(s.first_ts) + ' to ' + IB.fmt.date(s.last_ts)) : ''}</span>
        </div>
        <div class="field"><span class="small muted">Fingerprint</span>
          <div class="row"><span class="code small ev-fp grow">${esc(s.sha256 || 'Not recorded')}</span>
          ${s.sha256 ? `<button type="button" class="btn icon ghost" data-copy="${esc(s.sha256)}" aria-label="Copy the fingerprint" data-tip="Copy the fingerprint">${IB.icon('copy')}</button>` : ''}</div></div>
        <div class="row">
          <button type="button" class="btn small" data-ev-check="${i}">Check the fingerprint again</button>
          <a class="btn small ghost" href="${esc(IB.link('phone', { source: s.source_id }))}">Phone details</a>
          <span class="small muted" data-ev-out="${i}" role="status"></span>
        </div>
      </article>`;
    }).join('')}</div>`;
    body.addEventListener('click', async (e) => {
      const b = e.target.closest('[data-ev-check]');
      if (!b) return;
      const s = list[+b.dataset.evCheck];
      const out = IB.$(`[data-ev-out="${b.dataset.evCheck}"]`, body);
      const done = IB.busy(b, 'Checking…');
      try {
        const r = await ctx.capi('/sources/' + encodeURIComponent(s.source_id) + '/check', { method: 'POST' });
        const same = r && (r.matches === true || r.ok === true || (r.sha256 && r.sha256 === s.sha256));
        out.textContent = r && r.text ? r.text : same ? 'Matches what was recorded when it was added.' : 'Does not match what was recorded when it was added.';
      } catch (err) {
        out.textContent = err.message;
      }
      done();
    });
  }

  /* ---------- Audit ---------- */

  async function audit(view, ctx) {
    ctx.bar('<div class="row grow" id="au-filters"></div>');
    view.innerHTML = `<div class="page stack">
      <div><h2 class="page-title">Audit</h2>
      <p class="muted small">Every login, search, question, record opened, finding saved and export on this case. Times are India time.</p></div>
      <div id="au-body"></div></div>`;
    ctx.exportable('audit', () => pick(ctx.query));
    const body = IB.$('#au-body', view);
    const pick = (q) => ({ officer: q.officer || '', action: q.action || '', from: q.from || '', to: q.to || '' });
    let opts = { officers: [], actions: [] };
    const filterEl = IB.$('#au-filters') || IB.$('#au-filters', view);
    let list;
    const startFilters = () => {
      if (!filterEl) return;
      IB.filters(filterEl, {
        fields: [
          { key: 'officer', label: 'Officer', type: 'select', options: [['', 'Any officer']].concat(opts.officers.map((o) => [o, o])) },
          { key: 'action', label: 'What happened', type: 'select', options: [['', 'Anything']].concat(opts.actions.map((a) => [a, label(a)])) },
          { key: 'from', label: 'From', type: 'date' },
          { key: 'to', label: 'To', type: 'date' },
        ],
        values: pick(ctx.query),
        onChange: (v) => { ctx.setQuery(v, { push: true }); list.reload(); },
      });
    };
    let filtersDrawn = false;
    list = IB.moreList(body, {
      alive: ctx.alive,
      noun: ['line', 'lines'],
      empty: 'Nothing in the audit log matches these filters.',
      head: '<tr><th>When</th><th>Officer</th><th>What happened</th></tr>',
      load: async (offset) => {
        const r = await ctx.capi('/audit', { query: Object.assign({ offset }, pick(ctx.query)) });
        if (!filtersDrawn) {
          filtersDrawn = true;
          opts = { officers: arr(r && r.officers).map((o) => (typeof o === 'string' ? o : o.name)), actions: arr(r && r.actions).map((a) => (typeof a === 'string' ? a : a.action)) };
          startFilters();
        }
        return { rows: arr(r, 'rows'), total: (r && r.total) || 0 };
      },
      row: (a) => `<tr><td class="num">${esc(a.when || (a.ts ? IB.fmt.time(a.ts) : ''))}</td><td>${esc(a.officer || '')}</td><td>${esc(a.text || a.action || '')}</td></tr>`,
    });
  }

  /* ---------- Phone details ---------- */

  function tableOf(rows) {
    if (!rows.length) return '<p class="muted small">None found on this phone.</p>';
    if (rows.every((r) => r == null || typeof r !== 'object')) return `<p>${rows.map((r) => esc(r)).join(', ')}</p>`;
    const keys = [];
    rows.forEach((r) => Object.keys(r || {}).forEach((k) => { if (!keys.includes(k)) keys.push(k); }));
    const cell = (k, v) => /(_at|_ts|^ts|last_joined|installed|when)$/.test(k) && v ? esc(IB.fmt.time(v)) : esc(plain(v));
    return `<div class="table-wrap"><table class="table"><thead><tr>${keys.map((k) => `<th>${esc(label(k))}</th>`).join('')}</tr></thead>
      <tbody>${rows.map((r) => `<tr>${keys.map((k) => `<td>${cell(k, (r || {})[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  function phoneHtml(d) {
    if (!d || typeof d !== 'object') return IB.empty('No details recorded for this phone.', { icon: 'smartphone' });
    const info = (d.device_info && typeof d.device_info === 'object') ? d.device_info : {};
    const parts = [];
    let details = arr(d.details);
    if (!details.length) {
      details = [['Owner', info.owner_name || d.owner_name], ['Phone', info.model || d.device], ['Software', info.os || d.os],
        ['IMEI', info.imei], ['Serial', info.serial], ['File added', d.file_name], ['Fingerprint', d.sha256]]
        .filter(([, v]) => v).map(([label, value]) => ({ label, value }));
    }
    if (info.serial && !details.some((x) => x.label === 'Serial')) details.push({ label: 'Serial', value: info.serial });
    parts.push(`<section class="card pd-section"><div class="card-head"><div class="card-title">Device</div>${IB.phoneChip(d)}</div>
      <div class="kv">${details.map((x) => `<span class="muted">${esc(x.label)}</span><span class="${x.label === 'Fingerprint' ? 'code small ev-fp' : ''}">${esc(plain(x.value))}</span>`).join('')}</div></section>`);
    const nums = arr(info.owner_numbers);
    const sims = arr(d.sims).length ? arr(d.sims) : arr(info.sims);
    parts.push(`<section class="card pd-section"><div class="card-title">SIMs and numbers</div>${tableOf(sims.length ? sims : nums)}</section>`);
    [['Accounts', 'accounts'], ['Wi-Fi networks', 'wifi'], ['Installed apps', 'apps']].forEach(([t, k]) => {
      const rows = arr(d[k]).length ? arr(d[k]) : arr(info[k]);
      parts.push(`<section class="card pd-section"><div class="card-title">${esc(t)}</div>${tableOf(rows)}</section>`);
    });
    const pw = info.saved_passwords != null ? info.saved_passwords : (info.passwords != null ? info.passwords : info.n_passwords);
    if (pw != null) {
      const n = typeof pw === 'number' ? pw : Array.isArray(pw) ? pw.length : (pw && pw.n) || 0;
      parts.push(`<section class="card pd-section"><div class="card-title">Saved passwords</div>
        <p>${IB.plural(n, 'saved password', 'saved passwords')} (hidden, never sent to the AI).</p></section>`);
    }
    return parts.join('');
  }

  async function phone(view, ctx) {
    ctx.bar('');
    view.innerHTML = `<div class="page stack"><div><h2 class="page-title">Phone details</h2>
      <p class="muted small">What the extraction says about each phone itself.</p></div>
      <div id="pd-tabs"></div><div id="pd-body" class="stack">${IB.skeleton('cards', 3)}</div></div>`;
    const body = IB.$('#pd-body', view);
    let list = arr(IB.state.phones, 'sources', 'rows');
    if (!list.length) {
      try { list = arr(await ctx.capi('/sources'), 'sources', 'rows'); } catch (err) { IB.fail(body, err, () => phone(view, ctx)); return; }
    }
    if (!list.length) { body.innerHTML = IB.empty('No phones added to this case yet.', { icon: 'smartphone' }); return; }
    const active = String(ctx.query.source || list[0].source_id);
    const show = async (sid) => {
      ctx.setQuery({ source: sid });
      body.innerHTML = IB.skeleton('cards', 3);
      try {
        const d = await ctx.capi('/phone/' + encodeURIComponent(sid));
        body.innerHTML = phoneHtml(d);
      } catch (err) {
        IB.fail(body, err, () => show(sid));
      }
    };
    IB.tabs(IB.$('#pd-tabs', view), {
      tabs: list.map((s) => ({ key: String(s.source_id), label: s.label || 'Phone ' + s.source_id })),
      active, onChange: show, label: 'Phones',
    });
    return show(active);
  }

  /* ---------- Warrant limit dialog ---------- */

  IB.action('limit', async () => {
    if (!IB.state.cid) return;
    let cur = {};
    let people = [];
    try {
      const [l, p] = await Promise.all([IB.capi('/limit'), IB.capi('/people', { query: { group: 'in-touch' } }).catch(() => ({}))]);
      cur = l || {};
      people = arr(p, 'rows', 'people');
    } catch (err) {
      IB.status(err.message, { error: true });
      return;
    }
    const chosen = new Set(arr(cur.people).map((x) => String(x.person_id != null ? x.person_id : x)));
    arr(cur.people).forEach((x) => { if (x && x.person_id != null && !people.some((p) => String(p.person_id) === String(x.person_id))) people.unshift(x); });
    const apps = [];
    arr(IB.state.stats && IB.state.stats.by_app).forEach((a) => { if (a.app && !apps.includes(a.app)) apps.push(a.app); });
    if (!apps.includes('calls')) apps.push('calls');
    const curApps = new Set(arr(cur.apps));
    const on = cur && (cur.from || cur.to || arr(cur.people).length || arr(cur.apps).length);
    const v = await IB.dialog({
      title: 'Warrant limit',
      wide: true,
      body: `<div class="stack">
        <p class="muted small">Limit this case to the people, dates and apps the warrant allows. Records outside it aren't shown or read by the AI.</p>
        <div class="field"><span>People</span>
          <select class="select" name="people" multiple size="6" aria-label="People">${people.slice(0, 200).map((p) => `<option value="${esc(p.person_id)}" ${chosen.has(String(p.person_id)) ? 'selected' : ''}>${esc(p.name || p.display || p.person_id)}</option>`).join('')}</select>
          <span class="tiny muted">Hold Ctrl to choose more than one. Choose none for everyone.</span></div>
        <div class="row">
          <label class="field grow"><span>From</span><input class="input" type="date" name="from" value="${esc(cur.from_day || '')}"></label>
          <label class="field grow"><span>To</span><input class="input" type="date" name="to" value="${esc(cur.to_day || '')}"></label>
        </div>
        <div class="field"><span>Apps</span><div class="row">${apps.map((a) => `<label class="check"><input type="checkbox" name="app" value="${esc(a)}" ${curApps.has(a) ? 'checked' : ''}> ${esc(label(a))}</label>`).join('')}</div></div>
      </div>`,
      actions: [{ label: 'Cancel', value: null }].concat(on ? [{ label: 'Remove the limit', kind: 'danger', value: 'off', busy: 'Removing…' }] : [])
        .concat([{ label: 'Apply the limit', kind: 'primary', value: 'on', busy: 'Applying…' }]),
      onAction: async (value, el) => {
        if (value === 'off') { await IB.capi('/limit', { method: 'POST', body: {} }); return; }
        if (value !== 'on') return;
        const sel = IB.$('select[name="people"]', el);
        const body = {
          people: sel ? Array.from(sel.selectedOptions).map((o) => o.value) : [],
          from: IB.$('input[name="from"]', el).value || '',
          to: IB.$('input[name="to"]', el).value || '',
          apps: IB.$$('input[name="app"]:checked', el).map((c) => c.value),
        };
        if (!body.people.length && !body.from && !body.to && !body.apps.length) throw new Error('Choose at least one person, date or app, or use Remove the limit.');
        await IB.capi('/limit', { method: 'POST', body });
      },
    });
    if (v === 'on' || v === 'off') {
      IB.status(v === 'on' ? 'Warrant limit applied.' : 'Warrant limit removed.');
      IB.emit('limit', {});
      IB.refreshLimit();
      IB.reload();
    }
  });

  IB.page('codes', { title: 'Code words', render: codes });
  IB.page('sources', { title: 'Evidence added', render: sources });
  IB.page('audit', { title: 'Audit', render: audit });
  IB.page('phone', { title: 'Phone details', render: phone });
})();
