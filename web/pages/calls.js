/* Calls: IB.page('calls', ...). See docs/frontend-interfaces.md. */
(() => {
  const esc = (v) => IB.esc(v);
  const TYPES = [['all', 'All'], ['in', 'Incoming'], ['out', 'Outgoing'], ['missed', 'Missed']];

  IB.css('page-calls', `
    .calls-tools { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
    .calls-tools .input { width: 260px; }
    .call-dir { display: inline-flex; align-items: center; gap: 6px; }
    .call-dir.missed { color: var(--critical, #d93636); }
    .call-person b { font-weight: 600; }
    .call-marks { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
  `);

  const phoneName = (p) => {
    if (p == null || p === '') return '';
    if (typeof p === 'object') return p.label || (p.source_id != null ? 'Phone ' + p.source_id : '');
    if (/^\d+$/.test(String(p))) return 'Phone ' + p;
    return String(p).split('|')[0].trim();
  };

  function marks(r) {
    const out = [];
    const list = Array.isArray(r.marks) ? r.marks : (Array.isArray(r.across) ? r.across : []);
    list.forEach((m) => {
      if (typeof m === 'string') out.push({ text: m, tone: 'orange' });
      else if (m && m.text) out.push(m);
    });
    if (r.missing_on) {
      const ph = phoneName(r.missing_on);
      out.push({ text: `Missing on ${ph}'s log`, tone: 'orange',
        tip: `This call is on this phone's log but not on ${ph}'s. It may have been deleted from ${ph}.` });
    }
    if (r.other_duration_s != null && r.other_phone) {
      out.push({ text: `Different length on ${phoneName(r.other_phone)}: ${IB.fmt.duration(r.other_duration_s)}`, tone: 'orange' });
    }
    return out.map((m) => `<span class="chip status serious"${m.tip ? ` data-tip="${esc(m.tip)}"` : ''}>${esc(m.text)}</span>`).join('');
  }

  function dirCell(r) {
    const missed = r.status === 'missed' || r.status === 'rejected' || r.type === 'missed';
    if (missed) return `<span class="call-dir missed">${IB.icon('missed', 16)} ${r.status === 'rejected' ? 'Rejected' : 'Missed'}</span>`;
    if (r.direction === 'out') return `<span class="call-dir">${IB.icon('arrow-out', 16)} Outgoing</span>`;
    return `<span class="call-dir">${IB.icon('arrow-in', 16)} Incoming</span>`;
  }

  function row(r) {
    const name = r.person_name || r.name || (r.direction === 'out' ? (r.recipient_names || r.conv_title) : r.sender_name) || '';
    const nameText = Array.isArray(name) ? name.join(', ') : name;
    const number = r.number || r.phone_no || r.ident || (r.direction === 'out' ? (Array.isArray(r.recipients) ? r.recipients[0] : '') : r.sender) || '';
    const status = r.status && r.status !== 'missed' ? IB.statusChip(r.status) : '';
    const phone = r.phone_label || r.source_id;
    return `<tr class="clickable" tabindex="0" data-eid="${esc(r.event_id)}">
      <td class="num">${esc(IB.fmt.time(r.ts))}</td>
      <td>${dirCell(r)}</td>
      <td class="call-person"><b>${esc(nameText || number || 'Unknown')}</b>${nameText && number && number !== nameText ? `<div class="tiny muted num">${esc(number)}</div>` : ''}
        ${(() => { const m = marks(r); return m ? `<div class="call-marks">${m}</div>` : ''; })()}</td>
      <td>${r.app ? IB.appChip(r.app) : ''}</td>
      <td class="num">${r.duration_s ? esc(IB.fmt.duration(r.duration_s)) : '<span class="muted">0 s</span>'}</td>
      <td>${status}</td>
      <td>${phone != null && phone !== '' ? IB.phoneChip(phone) : ''}</td>
    </tr>`;
  }

  IB.page('calls', {
    title: 'Calls',
    render(view, ctx) {
      const q = ctx.query;
      if (!TYPES.some(([k]) => k === q.type)) q.type = 'all';
      let counts = null;
      view.innerHTML = `<div class="page stack">
        <div class="calls-tools">
          <div id="calls-seg"></div>
          <input class="input" type="search" id="calls-person" placeholder="Person or number" aria-label="Person or number" value="${esc(q.person || '')}">
          <div id="calls-filters" class="grow"></div>
        </div>
        <div id="calls-list"></div>
      </div>`;

      const seg = IB.$('#calls-seg', view);
      const drawSeg = () => IB.tabs(seg, {
        look: 'seg', label: 'Which calls', active: ctx.query.type || 'all',
        tabs: TYPES.map(([key, label]) => ({ key, label, count: counts && counts[key] != null ? counts[key] : undefined })),
        onChange(key) { ctx.setQuery({ type: key === 'all' ? '' : key }, { push: true }); ctx.query.type = key; list.reload(); },
      });

      ctx.exportable('calls', () => Object.assign({}, ctx.query));

      IB.filters(IB.$('#calls-filters', view), {
        fields: [
          { key: 'app', label: 'App', type: 'select', options: [['', 'Any app'], ['phone', 'Phone'], ['whatsapp', 'WhatsApp'], ['telegram', 'Telegram'], ['signal', 'Signal']] },
          { key: 'country', label: 'Country code', type: 'text', words: 'from' },
          { key: 'from', label: 'From', type: 'date' },
          { key: 'to', label: 'To', type: 'date' },
        ],
        values: { app: q.app || '', country: q.country || '', from: q.from || '', to: q.to || '' },
        onChange(values) { ctx.setQuery(values, { push: true }); list.reload(); },
      });

      let t;
      IB.$('#calls-person', view).addEventListener('input', (e) => {
        clearTimeout(t);
        t = setTimeout(() => { ctx.setQuery({ person: e.target.value.trim() }); list.reload(); }, 300);
      });

      const list = IB.moreList(IB.$('#calls-list', view), {
        noun: ['call', 'calls'],
        empty: 'No calls match. Try another person, or clear the filters.',
        alive: ctx.alive,
        head: '<tr><th>Time</th><th>Direction</th><th>Person</th><th>App</th><th>Length</th><th>Status</th><th>Phone</th></tr>',
        async load(offset) {
          const cq = ctx.query;
          const r = await ctx.capi('/calls', { query: {
            type: cq.type && cq.type !== 'all' ? cq.type : 'all', person: cq.person, app: cq.app, country: cq.country, from: cq.from, to: cq.to, offset } });
          const rows = Array.isArray(r) ? r : (r && (r.rows || r.calls)) || [];
          if (offset === 0 && r && r.counts) { counts = r.counts; drawSeg(); }
          const type = cq.type || 'all';
          const total = r && r.total != null ? r.total : (counts && counts[type] != null ? counts[type] : rows.length);
          return { rows, total };
        },
        row,
      });
      drawSeg();
    },
  });
})();
