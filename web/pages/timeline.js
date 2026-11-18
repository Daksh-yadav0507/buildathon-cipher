/* Timeline: IB.page('timeline', ...), also drawn for #/c/{cid}/record/{eid}. See docs/frontend-interfaces.md. */
(() => {
  const esc = (v) => IB.esc(v);
  const KINDS = [['', 'Any kind'], ['message', 'Messages'], ['call', 'Calls'], ['photo', 'Photos'], ['video', 'Videos'],
    ['voice', 'Voice notes'], ['document', 'Documents'], ['location', 'Places'], ['contact', 'Contacts'], ['note', 'Notes']];
  const STATUSES = [['', 'Any status'], ['deleted', 'Deleted, recovered'], ['edited', 'Edited'], ['unsent', 'Unsent'], ['missed', 'Missed']];
  const APP_NAMES = { whatsapp: 'WhatsApp', sms: 'SMS', telegram: 'Telegram', signal: 'Signal', imessage: 'Messages', phone: 'Phone', calls: 'Phone' };

  IB.css('page-timeline', `
    .tl-tools { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
    .tl-total { font-weight: 600; }
    .tl-money { font-weight: 700; }
    .rec.tl-hl { box-shadow: inset 3px 0 0 var(--accent, #2563eb); background: var(--selected, rgba(37, 99, 235, 0.12)); }
  `);

  const FILTER_KEYS = ['app', 'kind', 'status', 'person', 'phone', 'money', 'from', 'to'];

  IB.page('timeline', {
    title: 'Timeline',
    async render(view, ctx) {
      const q = ctx.query;
      const eid = ctx.params && ctx.params.eid;
      if (q.day) { q.from = q.from || q.day; q.to = q.to || q.day; }

      /* Opening a record: start the list on that record's day. */
      if (eid && !q.to) {
        try {
          const r = await ctx.capi('/records/' + encodeURIComponent(eid));
          const rec = (r && (r.record || r)) || {};
          if (rec.ts) q.to = IB.fmt.dayKey(rec.ts);
        } catch (e) { /* the drawer shows its own error; draw the whole timeline */ }
      }

      const apps = ((IB.state.stats && IB.state.stats.by_app) || []).map((a) => a.app).filter((v, i, all) => v && all.indexOf(v) === i);
      const phones = IB.state.phones || [];
      const order = q.order === 'asc' ? 'asc' : 'desc';

      view.innerHTML = `<div class="page stack">
        <div class="tl-tools">
          <span class="tl-total num" id="tl-total" aria-live="polite"></span>
          <div id="tl-filters" class="grow"></div>
          <div class="seg" role="group" aria-label="Order">
            <button type="button" class="tab" data-order="desc" aria-pressed="${order === 'desc'}">Newest first</button>
            <button type="button" class="tab" data-order="asc" aria-pressed="${order === 'asc'}">Oldest first</button>
          </div>
        </div>
        <div class="rec-list" id="tl-list"></div>
      </div>`;

      const fields = [
        { key: 'app', label: 'App', type: 'select', options: [['', 'Any app']].concat(apps.map((a) => [a, APP_NAMES[a] || a])) },
        { key: 'kind', label: 'Kind', type: 'select', options: KINDS },
        { key: 'status', label: 'Status', type: 'select', options: STATUSES },
        { key: 'person', label: 'Person', type: 'text', words: 'with' },
      ];
      if (phones.length > 1) fields.push({ key: 'phone', label: 'Phone', type: 'select', options: [['', 'Every phone']].concat(phones.map((p) => [String(p.source_id), p.label])) });
      fields.push({ key: 'money', label: 'Money only', type: 'check' }, { key: 'from', label: 'From', type: 'date' }, { key: 'to', label: 'To', type: 'date' });

      const values = {};
      FILTER_KEYS.forEach((k) => { values[k] = q[k] || ''; });
      IB.filters(IB.$('#tl-filters', view), {
        fields, values,
        onChange(v) {
          const next = Object.assign({}, v, { day: '' });
          if (next.money === true) next.money = 1;
          if (next.money === false) next.money = '';
          ctx.setQuery(next, { push: true });
          list.reload();
        },
      });

      IB.$$('[data-order]', view).forEach((b) => b.addEventListener('click', () => {
        IB.$$('[data-order]', view).forEach((x) => x.setAttribute('aria-pressed', x === b));
        ctx.setQuery({ order: b.dataset.order === 'asc' ? 'asc' : '' }, { push: true });
        list.reload();
      }));

      ctx.exportable('timeline', () => {
        const o = {};
        FILTER_KEYS.concat(['order']).forEach((k) => { if (ctx.query[k]) o[k] = ctx.query[k]; });
        return o;
      });

      let lastDay = '';
      let dayCounts = {};
      let jumped = false;
      const totalEl = IB.$('#tl-total', view);

      const list = IB.moreList(IB.$('#tl-list', view), {
        noun: ['record', 'records'],
        empty: 'No records match. Clear the filters to see every record.',
        alive: ctx.alive,
        async load(offset) {
          const cq = ctx.query;
          const r = await ctx.capi('/timeline', { query: {
            app: cq.app, kind: cq.kind, status: cq.status, person: cq.person, phone: cq.phone,
            money: cq.money ? 1 : '', from: cq.from, to: cq.to, order: cq.order === 'asc' ? 'asc' : 'desc', offset } });
          const rows = Array.isArray(r) ? r : (r && (r.rows || r.records || r.events)) || [];
          if (offset === 0) {
            lastDay = '';
            dayCounts = {};
          }
          const days = r && (r.days || r.day_counts);
          if (Array.isArray(days)) days.forEach((d) => { if (d && d.day) dayCounts[d.day] = d.n; });
          else if (days && typeof days === 'object') Object.assign(dayCounts, days);
          const total = r && r.total != null ? r.total : rows.length;
          totalEl.textContent = IB.plural(total, 'record', 'records');
          if (eid && !jumped) setTimeout(jump, 0);
          return { rows, total };
        },
        row(rec) {
          const day = IB.fmt.dayKey(rec.ts);
          let head = '';
          if (day !== lastDay) {
            lastDay = day;
            const n = dayCounts[day];
            head = `<div class="day-head">${esc(IB.fmt.day(rec.ts))}${n != null ? ` | ${esc(IB.plural(n, 'record', 'records'))}` : ''}</div>`;
          }
          /* recordRow draws the amount in bold for money rows ("₹50,000 debited"). */
          return head + IB.recordRow(rec, { phone: true });
        },
      });

      function jump() {
        const el = view.querySelector(`[data-eid="${CSS.escape(eid)}"]`);
        if (!el) return;
        jumped = true;
        el.scrollIntoView({ block: 'center' });
        el.classList.add('tl-hl');
        setTimeout(() => el.classList.remove('tl-hl'), 2500);
      }
    },
  });
})();
