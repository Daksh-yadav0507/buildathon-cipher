/* The Across phones tab and its marks on other pages: IB.dashboardTab('across', ...). See docs/frontend-interfaces.md.
   Also IB.across: load(), callMark(row), chatMark(conv), used by the marks on Calls and Chats. */
(() => {
  const E = v => IB.esc(v);
  const list = v => {
    if (Array.isArray(v)) return v;
    if (v && typeof v === 'object') {
      for (const k of ['rows', 'items', 'matches', 'list', 'pairs']) if (Array.isArray(v[k])) return v[k];
    }
    return [];
  };
  const pick = (o, ...keys) => {
    if (!o) return undefined;
    for (const k of keys) if (o[k] !== undefined && o[k] !== null && o[k] !== '') return o[k];
    return undefined;
  };
  const toMs = ts => (ts == null || ts === '') ? null : (typeof ts === 'number' ? ts : Date.parse(ts));

  /* "Phone 2" from a source id, a label or an object. */
  function phoneOf(src) {
    if (src && typeof src === 'object' && src.phone && typeof src.phone === 'object') src = src.phone;
    let given = '';
    if (src && typeof src === 'object') { given = src.label || ''; src = pick(src, 'source_id', 'label', 'phone_label', 'phone_no'); }
    const phones = IB.state.phones || [];
    const p = phones.find(x => x.source_id === src || x.label === src || x.phone_no === src);
    const label = (p && p.label) || given || (typeof src === 'string' ? src : '');
    return { id: p ? p.source_id : src, label, short: (label.split('|')[0] || label).trim() || 'the other phone' };
  }
  const chip = src => { const p = phoneOf(src); return p.id != null && p.id !== '' ? IB.phoneChip(p.id) : (p.label ? IB.phoneChip(p.label) : ''); };

  function gapText(sec) {
    if (sec == null || isNaN(sec)) return '';
    sec = Math.abs(Math.round(sec));
    if (sec < 60) return IB.plural(sec, 'second', 'seconds');
    if (sec < 3600) return IB.plural(Math.round(sec / 60), 'minute', 'minutes');
    const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
    return IB.plural(h, 'hour', 'hours') + (m ? ' ' + IB.plural(m, 'minute', 'minutes') : '');
  }
  const gapOf = (r, a, b) => {
    const g = pick(r, 'gap_s', 'gap_seconds');
    if (g == null && r.gap_ms != null) return Number(r.gap_ms) / 1000;
    if (g != null) return Number(g);
    const gm = pick(r, 'gap_min', 'gap_minutes');
    if (gm != null) return Number(gm) * 60;
    const ta = toMs(a && a.ts), tb = toMs(b && b.ts);
    return (ta != null && tb != null) ? (tb - ta) / 1000 : null;
  };

  /* The two (or more) sides of a match, whatever shape the server gives. */
  function sides(r, names) {
    for (const k of ['sides', 'copies', 'records', 'phones_detail']) {
      if (Array.isArray(r[k]) && r[k].length && typeof r[k][0] === 'object') return r[k];
    }
    for (const [x, y] of names) if (r[x] && r[y] && typeof r[x] === 'object' && typeof r[y] === 'object') return [r[x], r[y]];
    const out = [];
    for (const s of ['a', 'b']) {
      const o = {
        source_id: pick(r, 'source_' + s, s + '_source', 'source_id_' + s, 'phone_' + s),
        ts: pick(r, 'ts_' + s, s + '_ts'),
        event_id: pick(r, 'event_' + s, 'eid_' + s, s + '_event_id', 'event_id_' + s),
        name: pick(r, 'name_' + s, s + '_name', 'counterparty_' + s),
      };
      if (o.source_id || o.event_id) out.push(o);
    }
    return out;
  }
  const eidsOf = r => {
    const ids = [].concat(r.event_ids || [], r.records_ids || []);
    for (const s of sides(r, [['a', 'b'], ['from', 'to']])) if (s && s.event_id) ids.push(s.event_id);
    if (r.event_id) ids.push(r.event_id);
    return [...new Set(ids.filter(Boolean))];
  };
  const cites = ids => ids.slice(0, 6).map((id, i) => IB.cite(i + 1, id, 'Open this record')).join(' ');
  const firstEid = ids => ids.length ? ` data-eid="${E(ids[0])}"` : '';

  let headers = {};
  function card(title, counts, body, emptyText, key) {
    const h = key && headers[key];
    if (h) { const bits = String(h).split(' | '); title = bits[0]; counts = bits.slice(1); }
    const c = counts.filter(Boolean).map(E).join(' | ');
    return `<section class="card across-card">
      <div class="card-head"><h3 class="card-title">${E(title)}${c ? ` <span class="muted small">| ${c}</span>` : ''}</h3></div>
      ${body || IB.empty(emptyText, { icon: 'arrows-left-right' })}
    </section>`;
  }
  const table = (head, rows) => rows.length
    ? `<div class="table-wrap"><table class="table"><thead><tr>${head.map(h => `<th>${E(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`
    : '';

  /* 3. Money between the phones */
  function moneyCard(part, totalsPart) {
    const rows = list(part);
    let total = 0;
    const html = rows.map(r => {
      const [from, to] = sides(r, [['from', 'to'], ['debit', 'credit'], ['a', 'b']]);
      const amt = Number(pick(r, 'amount', 'value') || pick(from, 'amount') || 0);
      total += amt;
      const ids = eidsOf(r);
      const gap = gapOf(r, from, to);
      const fromName = pick(from, 'counterparty', 'name', 'to_name');
      const toName = pick(to, 'counterparty', 'name', 'from_name');
      const fp = phoneOf(from), tp = phoneOf(to);
      const sentence = pick(r, 'text', 'sentence') ||
        `${IB.fmt.money(amt)} left ${fp.label}${fromName ? ` (${pick(from, 'method') || 'UPI'} to ${fromName})` : ''} and arrived on ${tp.label}${gap != null ? ' ' + gapText(gap) + ' later' : ''}${toName ? ` (from ${toName})` : ''}`;
      const said = list(r.talk || r.said || r.chat).map(s => typeof s === 'string' ? `<div class="small muted clamp-1">"${E(s)}"</div>`
        : `<div class="small muted clamp-1" data-eid="${E(s.event_id)}" tabindex="0">"${E(pick(s, 'body', 'text', 'snippet') || '')}"</div>`).join('');
      return `<tr class="clickable" tabindex="0"${firstEid(ids)}>
        <td class="num"><b>${E(IB.fmt.money(amt))}</b></td>
        <td>${E(sentence)}${said}</td>
        <td class="small">${E(IB.fmt.time(pick(from, 'ts') || r.ts))}</td>
        <td>${cites(ids)}</td></tr>`;
    });
    const totals = list(totalsPart || (part && part.totals)).map(t => `<span class="pill tone-orange"${list(t.event_ids)[0] ? ` data-eid="${E(t.event_ids[0])}" tabindex="0"` : ''}>${E(t.text || `${phoneOf(pick(t, 'from_phone', 'from')).short} to ${phoneOf(pick(t, 'to_phone', 'to')).short}: ${IB.fmt.money(t.total || 0)}`)}</span>`).join(' ');
    return card('Money between the phones', [rows.length ? IB.plural(rows.length, 'match', 'matches') : '', rows.length ? IB.fmt.money(total) : ''],
      (totals ? `<div class="row small">${totals}</div>` : '') + table(['Amount', 'What happened', 'When', 'Records'], html),
      'No payment on one phone matches a payment arriving on another.', 'money');
  }

  /* 5. Calls checked against each other */
  function callsCard(part) {
    const rows = list(part);
    let missing = 0;
    const html = rows.map(r => {
      const kind = pick(r, 'kind', 'type', 'issue') || (r.missing_on ? 'missing' : 'length');
      const has = phoneOf(pick(r, 'on_phone', 'source_id', 'on', 'found_on', 'has'));
      const other = phoneOf(pick(r, 'missing_on', 'other_phone', 'other_source_id', 'other', 'not_on'));
      const ts = pick(r, 'ts', 'when');
      const dur = pick(r, 'duration_s', 'duration');
      let what;
      if (String(kind).startsWith('miss')) {
        missing++;
        what = `<span class="chip status serious" data-tip="This call is on ${E(has.label)}'s log but not on ${E(other.label)}'s, although that phone has other calls that day">${E(r.mark || `Missing on ${other.short}'s log`)}</span> <span class="small muted">may have been deleted there</span>`;
      } else {
        const od = pick(r, 'other_duration_s', 'duration_other', 'other_duration');
        what = `<span class="pill tone-orange">${E(r.mark || `Different length on ${other.short}: ${IB.fmt.duration(od)}`)}</span>`;
      }
      const ids = eidsOf(r);
      const day = ts ? IB.fmt.dayKey(ts) : '';
      const href = day ? IB.link('timeline', { day, kind: 'call' }) : '';
      return `<tr class="clickable" tabindex="0"${href ? ` data-href="${E(href)}"` : firstEid(ids)} data-tip="Open both phones' records for that day">
        <td class="small">${E(IB.fmt.time(ts))}</td>
        <td>${chip(has.id != null ? has.id : has.label)}${r.text ? `<div class="small">${E(r.text)}</div>` : ''}${pick(r, 'person', 'name', 'with') ? ` <span class="small">with ${E(pick(r, 'person', 'name', 'with'))}</span>` : ''}</td>
        <td class="num">${dur != null ? E(IB.fmt.duration(dur)) : ''}</td>
        <td>${what}</td>
        <td>${cites(ids)}</td></tr>`;
    });
    return card('Calls checked against each other', [rows.length ? IB.plural(rows.length, 'call to check', 'calls to check') : '', missing ? missing + ' missing' : ''],
      table(['When', 'On the log of', 'Length', 'What to check', 'Records'], html),
      'Every call between these phones is on both logs, with the same length.', 'calls');
  }

  /* 2. Together at the same place and time */
  function togetherCard(part) {
    const rows = list(part);
    const html = rows.map(r => {
      const ss = sides(r, [['a', 'b'], ['first', 'second']]);
      const ids = eidsOf(r);
      const dist = pick(r, 'distance_m', 'distance', 'metres');
      const gap = gapOf(r, ss[0], ss[1]);
      return `<tr class="clickable" tabindex="0"${firstEid(ids)}>
        <td><b>${E(pick(r, 'place', 'name') || 'Same place')}</b></td>
        <td>${ss.map(s => `<div>${chip(s)} <span class="small">${E(IB.fmt.time(s.ts))}</span></div>`).join('')}</td>
        <td class="num">${dist != null ? E(Math.round(dist) + ' m') : ''}</td>
        <td class="small">${E(r.gap_words || (gap != null ? (gap < 60 ? 'same minute' : gapText(gap)) : ''))}</td>
        <td>${cites(ids)}</td></tr>`;
    });
    return card('Together at the same place and time', [rows.length ? IB.plural(rows.length, 'time', 'times') : ''],
      table(['Place', 'Phones and times', 'Apart', 'Gap', 'Records'], html),
      'No two phones were within about 500 m of each other within 30 minutes.', 'together');
  }

  /* 1. Both sides of the same chat */
  function chatsCard(part) {
    const rows = list(part);
    const html = rows.map(r => {
      const per = list(r.phones || r.per_phone || r.copies);
      const conv = pick(r, 'conv_id') || pick(per[0], 'conv_id');
      const one = pick(r, 'only_one', 'one_side', 'on_one_only', 'n_one_side');
      const del = pick(r, 'deleted_elsewhere', 'deleted_one_side', 'n_deleted_one_side', 'deleted_on_one');
      const notes = [];
      if (one) notes.push(`<span class="pill tone-pink">${E(IB.plural(Number(one), 'message', 'messages'))} on one phone only</span>`);
      if (del) notes.push(`<span class="chip status serious">${E(IB.plural(Number(del), 'message', 'messages'))} deleted on one phone, still on another</span>`);
      list(r.notes).forEach(n => notes.push(`<span class="small">${E(typeof n === 'string' ? n : n.text)}</span>`));
      const href = conv ? IB.link('chats', { conv, both: 1 }) : '';
      return `<tr${href ? ` class="clickable" tabindex="0" data-href="${E(href)}"` : ''}>
        <td><b>${E(pick(r, 'title', 'name') || 'Chat')}</b> ${r.app ? IB.appChip(r.app) : ''}</td>
        <td>${per.map(p => `<div>${chip(p)} <span class="small num">${p.n != null || p.n_messages != null ? E(IB.plural(Number(pick(p, 'n', 'n_messages')), 'message', 'messages')) : ''}</span></div>`).join('')}</td>
        <td>${notes.join(' ') || '<span class="small muted">Both copies match</span>'}</td>
        <td>${href ? `<button type="button" class="btn small" data-href="${E(href)}">Both sides</button>` : ''}</td></tr>`;
    });
    return card('Both sides of the same chat', [rows.length ? IB.plural(rows.length, 'chat', 'chats') : ''],
      table(['Chat', 'Messages on each phone', 'Worth a look', ''], html),
      'No chat is held on more than one phone.', 'chats');
  }

  /* 4. The same file on several phones */
  function filesCard(part) {
    const rows = list(part);
    const html = rows.map(r => {
      const copies = sides(r, [['a', 'b']]).slice().sort((x, y) => (toMs(x.ts) || 0) - (toMs(y.ts) || 0));
      const ids = eidsOf(r);
      const t0 = toMs(copies[0] && copies[0].ts);
      const path = copies.map((c, i) => `${chip(c)} <span class="small">${E(i === 0 ? 'first, ' + IB.fmt.time(c.ts) : (t0 != null && toMs(c.ts) != null ? gapText((toMs(c.ts) - t0) / 1000) + ' later' : IB.fmt.time(c.ts)))}</span>`).join(' <span class="muted">then</span> ');
      const fp = pick(r, 'sha256', 'fingerprint');
      return `<tr class="clickable" tabindex="0"${firstEid(ids)}>
        <td><b>${E(pick(r, 'name', 'media_name', 'file_name') || 'File')}</b>${fp ? `<div class="tiny muted code" data-tip="Fingerprint: the same on every copy">${E(String(fp).slice(0, 12))}</div>` : ''}</td>
        <td class="num small">${r.size != null || r.media_size != null ? E(IB.fmt.size(pick(r, 'size', 'media_size'))) : ''}</td>
        <td>${path}</td>
        <td>${cites(ids)}</td></tr>`;
    });
    return card('The same file on several phones', [rows.length ? IB.plural(rows.length, 'file', 'files') : ''],
      table(['File', 'Size', 'How it went from phone to phone', 'Records'], html),
      'No file of 10 KB or more is on more than one phone.', 'files');
  }

  /* 6. How each phone saved the others */
  function namesCard(part) {
    const rows = list(part);
    const html = rows.map(r => {
      const saved = list(r.saved || r.names || r.saved_as || r.by_phone);
      const pid = pick(r, 'person_id', 'pid');
      const owner = pick(r, 'owner_of', 'owner_source_id');
      return `<tr${pid ? ` class="clickable" tabindex="0" data-href="${E(IB.link('person/' + pid))}"` : ''}>
        <td><b>${E(pick(r, 'name', 'person', 'owner_name') || '')}</b>${owner ? ' <span class="small muted">owner of</span> ' + chip(owner) : ''}</td>
        <td>${saved.map(s => typeof s === 'string' ? `<span class="pill">${E(s)}</span>`
          : `<span class="pill tone-teal"${s.event_id ? ` data-eid="${E(s.event_id)}" tabindex="0"` : ''}>"${E(pick(s, 'name', 'saved_as'))}" on ${E(phoneOf(s.phone || pick(s, 'source_id', 'label')).short)}</span>`).join(' ')}</td>
        <td class="num">${saved.length > 1 || r.n_phones ? E(IB.plural(Number(r.n_phones || saved.length), 'phone', 'phones')) : ''}</td></tr>`;
    });
    return card('How each phone saved the others', [rows.length ? IB.plural(rows.length, 'person', 'people') : ''],
      table(['Person', 'Saved as', 'Known to'], html),
      'No person is saved in more than one phone\'s contacts.', 'names');
  }

  /* Loading, cached per case: worked out once by the server, never reloaded on a timer. */
  let cache = null, cacheCid = null;
  function load(force) {
    const cid = IB.state.cid;
    if (!cid) return Promise.reject(new Error('Open a case first.'));
    if (force || !cache || cacheCid !== cid) {
      cacheCid = cid;
      cache = IB.capi('/across').catch(e => { cache = null; throw e; });
    }
    return cache;
  }
  IB.on('jobs:done', () => { cache = null; });
  IB.on('limit', () => { cache = null; });

  async function render(el, ctx) {
    el.innerHTML = IB.skeleton('cards', 4);
    let data;
    try { data = await (ctx.alive ? load() : load()); }
    catch (err) { if (!ctx.alive || ctx.alive()) IB.fail(el, err, () => { cache = null; render(el, ctx); }); return; }
    if (ctx.alive && !ctx.alive()) return;
    data = data || {};
    headers = data.headers || {};
    if (data.enabled === false) { el.innerHTML = IB.empty(data.why_off || 'Across phones needs two or more people\'s phones in the case.', { icon: 'arrows-left-right' }); return; }
    el.innerHTML = `<div class="stack across">
      <p class="muted small">${E(data.note || 'Compared by code, with no AI. These are leads to check, not findings.')}${data.limited ? ' While the warrant limit is on, only records inside it are compared and nothing is called missing.' : ''}</p>
      ${data.updating ? IB.updating(true) : ''}
      ${moneyCard(data.money, data.money_totals)}
      ${callsCard(data.calls)}
      ${togetherCard(data.together)}
      ${chatsCard(data.chats)}
      ${filesCard(data.files)}
      ${namesCard(data.names)}
    </div>`;
  }

  IB.css('across', `
    .across-card .table td { vertical-align: top; }
    .across-card .table td .chip, .across-card .table td .pill { margin: 2px 0; }
    .across-mark { margin-left: 8px; white-space: nowrap; }
  `);

  IB.dashboardTab('across', {
    label: 'Across phones',
    order: 80,
    show: () => (IB.state.phones || []).length >= 2,
    render,
  });

  /* ---- Marks on Calls and Chats ---- */
  let marks = null;
  function index(data) {
    const calls = new Map(), chats = new Map();
    list(data && data.calls).forEach(r => { if (r.event_id) calls.set(r.event_id, r); });
    list(data && data.chats).forEach(r => {
      const per = list(r.phones || r.per_phone || r.copies);
      const convs = [r.conv_id, ...per.map(p => p && p.conv_id), ...list(r.conv_ids)].filter(Boolean);
      convs.forEach(c => chats.set(String(c), { row: r, per, conv: String(c) }));
    });
    return { calls, chats };
  }

  /* HTML for a call row's mark, or ''. */
  function callMark(row) {
    if (!marks || !row) return '';
    const r = marks.calls.get(row.event_id || row);
    if (!r) return '';
    const kind = String(pick(r, 'kind', 'type', 'issue') || (r.missing_on ? 'missing' : 'length'));
    const other = phoneOf(pick(r, 'missing_on', 'other_phone', 'other_source_id', 'other', 'not_on'));
    if (kind.startsWith('miss')) {
      return `<span class="chip status serious across-mark" data-tip="The other phone in this call has other calls that day, but not this one: it may have been deleted there">${E(r.mark || `Missing on ${other.short}'s log`)}</span>`;
    }
    const od = pick(r, 'other_duration_s', 'duration_other', 'other_duration');
    return `<span class="pill tone-orange across-mark" data-tip="Both logs have this call, with lengths more than 20% apart">${E(r.mark || `Different length on ${other.short}: ${IB.fmt.duration(od)}`)}</span>`;
  }

  /* HTML for a chat row's mark ("Also on Phone 2"), or ''. */
  function chatMark(conv) {
    if (!marks || conv == null) return '';
    const id = String(typeof conv === 'object' ? conv.conv_id : conv);
    const m = marks.chats.get(id);
    if (!m) return '';
    const mine = typeof conv === 'object' ? conv.source_id : null;
    const others = m.per.map(p => phoneOf(p)).filter(p => p.id !== mine && String(p.id) !== String(mine))
      .map(p => p.short);
    const names = [...new Set(others)];
    return `<span class="pill tone-blue across-mark">Also on ${E(names.length ? names.join(' and ') : 'another phone')}</span>`;
  }

  /* Decorates rows the Calls and Chats pages draw, once each, if they did not add a mark themselves. */
  function decorate(view, tab) {
    if (!marks) return;
    if (tab === 'calls') {
      IB.$$('[data-eid]', view).forEach(node => {
        if (node.dataset.acrossMarked || node.querySelector('.across-mark')) return;
        const html = callMark(node.dataset.eid);
        node.dataset.acrossMarked = '1';
        if (!html) return;
        const cell = node.tagName === 'TR' ? node.lastElementChild : node;
        if (cell) cell.insertAdjacentHTML('beforeend', html);
      });
    } else if (tab === 'chats') {
      IB.$$('[data-href*="conv="], a[href*="conv="], [data-conv]', view).forEach(node => {
        if (node.dataset.acrossMarked || node.querySelector('.across-mark') || node.closest('.across-mark')) return;
        if (node.closest('.thread, .bubble')) return;
        const ref = node.dataset.conv || node.dataset.href || node.getAttribute('href') || '';
        const m = /conv=([^&]+)/.exec(ref);
        const id = node.dataset.conv || (m && decodeURIComponent(m[1]));
        node.dataset.acrossMarked = '1';
        const html = id ? chatMark(id) : '';
        if (!html) return;
        const t = node.querySelector('.clamp-1, b, strong, .title') || node;
        t.insertAdjacentHTML('afterend', html);
      });
    }
  }

  let observer = null;
  IB.on('route', ctx => {
    if (observer) { observer.disconnect(); observer = null; }
    if (!ctx || (ctx.tab !== 'calls' && ctx.tab !== 'chats')) return;
    if ((IB.state.phones || []).length < 2) return;
    const view = document.getElementById('view');
    if (!view) return;
    const tab = ctx.tab;
    load().then(d => {
      marks = index(d);
      if (ctx.alive && !ctx.alive()) return;
      decorate(view, tab);
      if (observer) observer.disconnect();
      let queued = false;
      observer = new MutationObserver(() => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => { queued = false; decorate(view, tab); });
      });
      observer.observe(view, { childList: true, subtree: true });
    }).catch(() => {});
  });

  IB.across = {
    load: force => load(force).then(d => { marks = index(d); return d; }),
    callMark,
    chatMark,
    phoneOf,
  };
})();
