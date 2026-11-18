/* People and a person: IB.page('people', ...) and IB.page('person', ...). See docs/frontend-interfaces.md. */
(() => {
  const E = v => IB.esc(v);
  const list = v => {
    if (Array.isArray(v)) return v;
    if (v && typeof v === 'object') for (const k of ['rows', 'items', 'list']) if (Array.isArray(v[k])) return v[k];
    return [];
  };
  const pick = (o, ...keys) => {
    if (!o) return undefined;
    for (const k of keys) if (o[k] !== undefined && o[k] !== null && o[k] !== '') return o[k];
    return undefined;
  };
  const n = v => Number(v) || 0;

  const GROUPS = [
    ['in-touch', 'In touch', 'A one-to-one chat or a connected call both ways'],
    ['same-groups', 'Only in the same groups', 'They share a group chat and nothing else'],
    ['lists-only', 'Only names on lists', 'Saved in contacts, with no chat or call'],
    ['apps', 'Apps and automatic senders', 'Banks, shops, delivery and other automatic messages'],
  ];

  const aliasesOf = p => {
    const main = pick(p, 'name') || '';
    return list(p.names || p.aliases || p.also).map(a => typeof a === 'string' ? a : pick(a, 'name', 'saved_as'))
      .filter(a => a && a !== main);
  };
  const numbersOf = p => list(p.numbers || p.idents || p.identifiers || p.phones_no)
    .map(i => typeof i === 'string' ? i : pick(i, 'display', 'ident', 'number')).filter(Boolean);
  const phonesOf = p => list(p.phones || p.sources || p.source_ids || p.on_phones)
    .map(s => typeof s === 'object' ? pick(s, 'source_id', 'label') : s).filter(Boolean);

  function bars(values) {
    const v = list(values).map(x => typeof x === 'object' ? n(pick(x, 'n', 'value', 'count')) : n(x)).slice(0, 24);
    if (!v.length) return '';
    const max = Math.max(1, ...v);
    return `<div class="ppl-bars" aria-hidden="true">${v.map(x => `<i style="height:${Math.max(2, Math.round(x / max * 28))}px"></i>`).join('')}</div>`;
  }

  function spark(points) {
    const v = list(points).map(x => typeof x === 'object' ? n(pick(x, 'n', 'value', 'count')) : n(x));
    if (v.length < 2) return '';
    const max = Math.max(1, ...v), w = 160, h = 32;
    const d = v.map((y, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - 2 - y / max * (h - 4)).toFixed(1)}`).join(' ');
    return `<svg class="ppl-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="Contact per week"><polyline fill="none" stroke="currentColor" stroke-width="1.5" points="${d}"/></svg>`;
  }

  IB.css('people', `
    .ppl-groups .stat { cursor: pointer; text-align: left; width: 100%; }
    .ppl-groups .stat[aria-pressed="true"] { outline: 2px solid currentColor; outline-offset: -2px; }
    .ppl-bars { display: flex; align-items: flex-end; gap: 2px; height: 30px; margin-top: 8px; }
    .ppl-bars i { display: block; width: 6px; border-radius: 2px; background: currentColor; opacity: .45; }
    .ppl-spark { color: inherit; opacity: .8; margin-top: 6px; }
    .ppl-head { align-items: center; flex-wrap: wrap; }
    .ppl-name { font-size: var(--t-2xl, 28px); margin: 0; }
    .ppl-names li { margin: 4px 0; }
  `);

  /* ---------- People ---------- */
  IB.page('people', {
    title: 'People',
    render(view, ctx) {
      const q = ctx.query;
      const group = q.group || '';
      const phones = IB.state.phones || [];
      view.innerHTML = `<div class="page stack">
        <div class="cols cols-4 ppl-groups" id="ppl-groups">${GROUPS.map(([k, label, tip]) => `
          <button type="button" class="stat card" data-group="${k}" aria-pressed="${group === k}" data-tip="${E(tip)}">
            <div class="small muted">${E(label)}</div><div class="num ppl-n">…</div><div class="ppl-b"></div>
          </button>`).join('')}</div>
        <div class="card">
          <div class="card-head">
            <div class="row grow">
              <input class="input" id="ppl-q" type="search" placeholder="Name or number" aria-label="Find a person by name or number" value="${E(q.q || '')}">
              <div id="ppl-filters"></div>
            </div>
            <label class="row small">Sort
              <select class="select" id="ppl-sort" aria-label="Sort people">
                ${[['contact', 'Most contact'], ['messages', 'Most messages'], ['calls', 'Most calls'], ['last', 'Last contact'], ['name', 'Name']]
                  .map(([v, l]) => `<option value="${v}"${(q.sort || 'contact') === v ? ' selected' : ''}>${l}</option>`).join('')}
              </select></label>
          </div>
          <div id="ppl-list"></div>
        </div>
      </div>`;
      ctx.exportable('people', () => ({ group: ctx.query.group, q: ctx.query.q, sort: ctx.query.sort, phone: ctx.query.phone }));

      const drawGroups = groups => {
        const byKey = {};
        list(groups).forEach(g => { byKey[g.key] = g; });
        IB.$$('[data-group]', view).forEach(b => {
          const g = byKey[b.dataset.group];
          if (g && g.label) IB.$('.small', b).textContent = g.label;
          IB.$('.ppl-n', b).textContent = g ? IB.fmt.num(g.n || 0) : '0';
          IB.$('.ppl-b', b).innerHTML = g ? bars(g.bars) : '';
        });
      };

      const row = p => {
        const pid = pick(p, 'person_id', 'pid', 'id');
        const al = aliasesOf(p), nums = numbersOf(p);
        return `<tr class="clickable" tabindex="0" data-href="${E(IB.link('person/' + pid))}">
          <td><b>${E(p.name || nums[0] || 'Unknown')}</b>${al.length ? `<div class="tiny muted clamp-1">also saved as ${E(al.slice(0, 3).join(', '))}</div>` : ''}</td>
          <td class="small">${nums.slice(0, 2).map(E).join('<br>')}</td>
          <td class="num">${E(IB.fmt.num(n(pick(p, 'n_messages', 'messages'))))}</td>
          <td class="num">${E(IB.fmt.num(n(pick(p, 'n_calls', 'calls'))))}</td>
          <td class="small">${p.first_ts ? E(IB.fmt.date(p.first_ts)) : ''}</td>
          <td class="small">${p.last_ts ? E(IB.fmt.date(p.last_ts)) : ''}</td>
          <td>${IB.phoneChips(phonesOf(p))}</td></tr>`;
      };

      let groupsDrawn = false;
      const more = IB.moreList(IB.$('#ppl-list', view), {
        alive: ctx.alive,
        noun: ['person', 'people'],
        empty: ctx.query.q ? 'No one matches that name or number.' : 'No people in this group.',
        head: '<tr><th>Name</th><th>Numbers</th><th>Messages</th><th>Calls</th><th>First contact</th><th>Last contact</th><th>Phones</th></tr>',
        row,
        async load(offset) {
          const d = await ctx.capi('/people', { query: {
            group: ctx.query.group, q: ctx.query.q, sort: ctx.query.sort, phone: ctx.query.phone, offset } });
          if (!groupsDrawn || offset === 0) { drawGroups(d && d.groups); groupsDrawn = true; }
          const rows = list(d && d.rows);
          const g = list(d && d.groups).find(x => x.key === ctx.query.group);
          const total = d && d.total != null ? d.total : (g && !ctx.query.q ? g.n : offset + rows.length);
          return { rows, total };
        },
      });

      if (phones.length > 1) {
        IB.filters(IB.$('#ppl-filters', view), {
          fields: [{ key: 'phone', label: 'Phone', type: 'select', options: [['', 'Every phone'], ...phones.map(p => [p.source_id, p.label])], words: 'on' }],
          values: { phone: q.phone || '' },
          onChange: v => { ctx.setQuery({ phone: v.phone }); more.reload(); },
        });
      }

      IB.$$('[data-group]', view).forEach(b => b.addEventListener('click', () => {
        const k = ctx.query.group === b.dataset.group ? '' : b.dataset.group;
        ctx.setQuery({ group: k }, { push: true });
        IB.$$('[data-group]', view).forEach(x => x.setAttribute('aria-pressed', String(x.dataset.group === k)));
        more.reload();
      }));
      let t = null;
      IB.$('#ppl-q', view).addEventListener('input', e => {
        clearTimeout(t);
        t = setTimeout(() => { ctx.setQuery({ q: e.target.value.trim() }); more.reload(); }, 300);
      });
      IB.$('#ppl-sort', view).addEventListener('change', e => { ctx.setQuery({ sort: e.target.value === 'contact' ? '' : e.target.value }); more.reload(); });
    },
  });

  /* ---------- A person ---------- */
  const cardHtml = (title, body, empty, extra) => `<section class="card">
    <div class="card-head"><h3 class="card-title">${E(title)}</h3>${extra || ''}</div>
    ${body || `<p class="muted small">${E(empty)}</p>`}</section>`;

  const recs = rows => rows.length ? `<div class="rec-list">${rows.map(r => IB.recordRow(r, { phone: true })).join('')}</div>` : '';

  IB.page('person', {
    title: 'Person',
    async render(view, ctx) {
      const pid = ctx.params.pid;
      view.innerHTML = `<div class="page">${IB.skeleton('page')}</div>`;
      let p;
      try { p = await ctx.capi('/people/' + encodeURIComponent(pid)); }
      catch (err) { IB.fail(IB.$('.page', view), err, () => IB.reload()); return; }
      p = (p && (p.person || p)) || {};
      const name = p.name || numbersOf(p)[0] || 'Unknown';
      ctx.title(name);
      const owner = pick(p, 'owner_source_id', 'owner_of');
      const counts = p.counts || {};
      const nMsg = n(pick(counts, 'messages', 'n_messages') ?? pick(p, 'n_messages', 'messages'));
      const nCall = n(pick(counts, 'calls', 'n_calls') ?? pick(p, 'n_calls'));
      const first = pick(counts, 'first_ts') || p.first_ts, last = pick(counts, 'last_ts') || p.last_ts;

      const names = list(p.names_evidence || p.names || p.aliases).map(a => typeof a === 'string' ? { name: a } : a);
      const idents = list(p.idents || p.identifiers || p.numbers).map(i => typeof i === 'string' ? { display: i } : i);
      const chats = list(p.chats);
      const calls = list(p.calls).slice(0, 10);
      const money = p.money || {};
      const moneyRows = list(money.rows || money);
      const together = list(p.together || p.places_together || p.places);
      const docs = list(p.documents || p.media || p.files);
      const across = p.across || {};
      const acrossSaved = list(across.saved || across.names || across);
      const acrossMoney = list(across.money);

      const anyEid = [moneyRows, calls, chats, docs].map(l => l.find(r => r && r.event_id)).find(Boolean);
      const sent = money.sent != null ? money.sent : moneyRows.filter(r => r.direction === 'debit').reduce((s, r) => s + n(r.amount), 0);
      const got = money.received != null ? money.received : moneyRows.filter(r => r.direction === 'credit').reduce((s, r) => s + n(r.amount), 0);

      const nameItem = a => {
        const how = pick(a, 'how', 'evidence', 'found');
        const src = pick(a, 'source_id', 'phone', 'label');
        const where = how || (src ? `Saved on ${IB.across ? IB.across.phoneOf(src).label : src}` : '');
        return `<li${a.event_id ? ` class="clickable" tabindex="0" data-eid="${E(a.event_id)}"` : ''}><b>${E(a.name)}</b> <span class="small muted">${E(where)}</span></li>`;
      };

      view.innerHTML = `<div class="page stack">
        <div class="row ppl-head">
          <h2 class="ppl-name grow">${E(name)} ${owner ? `<span class="small muted">owner of</span> ${IB.phoneChip(owner)}` : ''}</h2>
          <button type="button" class="btn primary" data-ask="${E(`What do the records say about ${name}?`)}">${IB.icon('spark')} Ask about this person</button>
          <button type="button" class="btn" id="ppl-save"${anyEid ? '' : ' disabled data-tip="No record to save yet"'}>${IB.icon('flag')} Save as finding</button>
        </div>
        <div class="cols cols-4">
          ${IB.statTile({ n: IB.fmt.num(nMsg), label: 'Messages', href: IB.link('timeline', { person: pid, kind: 'message' }) })}
          ${IB.statTile({ n: IB.fmt.num(nCall), label: 'Calls', href: IB.link('calls', { person: pid }) })}
          ${IB.statTile({ n: first ? IB.fmt.date(first) : 'Not found', label: 'First contact' })}
          ${IB.statTile({ n: last ? IB.fmt.date(last) : 'Not found', label: 'Last contact', sub: spark(p.weekly || p.per_week || p.spark) })}
        </div>
        <div class="cols cols-2">
          ${cardHtml('Names on these phones', names.length ? `<ul class="ppl-names">${names.map(nameItem).join('')}</ul>` : '', 'No other names found.')}
          ${cardHtml('Numbers and IDs', idents.length ? `<div class="kv">${idents.map(i => {
            const v = pick(i, 'display', 'ident', 'number');
            return `<span class="small muted">${E(pick(i, 'kind', 'type') || 'Number')}</span><span class="row"><span class="code">${E(v)}</span><button type="button" class="btn icon ghost small" data-copy="${E(v)}" aria-label="Copy ${E(v)}" data-tip="Copy">${IB.icon('copy', 14)}</button></span>`;
          }).join('')}</div>` : '', 'No numbers found.')}
        </div>
        <div class="cols cols-2">
          ${cardHtml('Chats with them', chats.length ? `<div class="rec-list">${chats.map(c => `
            <div class="rec clickable" tabindex="0" data-href="${E(IB.link('chats', { conv: c.conv_id }))}">
              <div class="row"><b class="grow clamp-1">${E(c.title || name)}</b>${c.app ? IB.appChip(c.app) : ''}${c.source_id ? IB.phoneChip(c.source_id) : ''}</div>
              <div class="small muted">${E(IB.plural(n(pick(c, 'n_messages', 'n')), 'message', 'messages'))}${c.n_deleted ? ', ' + E(c.n_deleted) + ' deleted' : ''}${c.last_ts ? ', last ' + E(IB.fmt.time(c.last_ts)) : ''}</div>
            </div>`).join('')}</div>` : '', 'No chats with them.')}
          ${cardHtml('Calls', recs(calls), 'No calls with them.', calls.length ? `<a class="link small" href="${E(IB.link('calls', { person: pid }))}">See every call</a>` : '')}
        </div>
        <div class="cols cols-2">
          ${cardHtml('Money with them', moneyRows.length ? `<div class="row small"><span class="pill tone-orange">Sent to them ${E(IB.fmt.money(sent))}</span><span class="pill tone-green">Received from them ${E(IB.fmt.money(got))}</span></div>${recs(moneyRows.slice(0, 10))}` : '', 'No money with them found.')}
          ${cardHtml('Places together', together.length ? `<div class="rec-list">${together.map(t => {
            const ids = list(t.event_ids);
            return `<div class="rec clickable" tabindex="0"${ids[0] || t.event_id ? ` data-eid="${E(ids[0] || t.event_id)}"` : ''}><b>${E(t.place || 'Same place')}</b> <span class="small muted">${E(IB.fmt.time(t.ts || (t.a && t.a.ts)))}</span></div>`;
          }).join('')}</div>` : '', owner ? 'Not found together with another phone.' : 'Shown only for people who own a phone in this case.')}
        </div>
        <div class="cols cols-2">
          ${cardHtml('Their documents and photos', recs(docs.slice(0, 10)), 'No documents or photos from them.')}
          ${cardHtml('Across phones', (acrossSaved.length || acrossMoney.length) ? `
            ${acrossSaved.length ? `<div class="row">${acrossSaved.map(s => typeof s === 'string' ? `<span class="pill">${E(s)}</span>` : `<span class="pill tone-teal"${s.event_id ? ` data-eid="${E(s.event_id)}" tabindex="0"` : ''}>"${E(pick(s, 'name', 'saved_as'))}" on ${E(IB.across ? IB.across.phoneOf(pick(s, 'source_id', 'phone')).short : pick(s, 'source_id', 'phone'))}</span>`).join(' ')}</div>` : ''}
            ${acrossMoney.length ? `<div class="rec-list">${acrossMoney.map(m => `<div class="rec clickable" tabindex="0"${m.event_id || list(m.event_ids)[0] ? ` data-eid="${E(m.event_id || list(m.event_ids)[0])}"` : ''}>${E(m.text || `${IB.fmt.money(n(m.amount))} with ${m.with || m.name || 'another owner'}`)}</div>`).join('')}</div>` : ''}` : '',
            'No other phone in this case knows them.')}
        </div>
      </div>`;

      const save = IB.$('#ppl-save', view);
      if (save && anyEid) save.addEventListener('click', () => IB.saveFinding({ event_id: anyEid.event_id, title: `About ${name}` }));
    },
  });
})();
