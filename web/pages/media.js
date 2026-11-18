/* Photos and files: IB.page('media', ...). See docs/frontend-interfaces.md. */
(() => {
  const esc = (v) => IB.esc(v);
  const arr = (v, ...keys) => {
    if (Array.isArray(v)) return v;
    if (v && typeof v === 'object') for (const k of keys) if (Array.isArray(v[k])) return v[k];
    return [];
  };

  IB.css('pg-media', `
    .md-actions { display: flex; flex-wrap: wrap; gap: 8px; }
    .md-photos .rec-list, .md-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }
    .md-card { display: flex; flex-direction: column; gap: 6px; padding: 8px; border-radius: 12px; cursor: pointer; background: var(--surface, transparent); border: 1px solid var(--line, rgba(127,127,127,.2)); text-align: left; font: inherit; color: inherit; }
    .md-card:hover, .md-card:focus-visible { border-color: var(--accent, #3b6cf6); }
    .md-card svg { width: 100%; height: auto; display: block; border-radius: 8px; }
    .md-row { display: flex; gap: 12px; align-items: flex-start; padding: 12px 0; border-top: 1px solid var(--line, rgba(127,127,127,.2)); }
    .md-row:first-child { border-top: 0; }
    .md-row .md-main { flex: 1; min-width: 0; }
    .md-wave { display: inline-flex; gap: 2px; align-items: center; height: 24px; vertical-align: middle; }
    .md-wave i { display: block; width: 3px; border-radius: 2px; background: currentColor; opacity: .45; }
    .md-big svg { width: 100%; max-width: 560px; height: auto; border-radius: 12px; }
    .md-fp { word-break: break-all; }
  `);

  const TONES = { 1: ['#dbe6ff', '#2f5bd3'], 2: ['#d9f2e3', '#1f8a4c'], 3: ['#ffe5cf', '#c25a12'] };
  const phoneNo = (r) => {
    const s = String(r.source_id || r.phone_label || '');
    const m = s.match(/(\d+)/);
    return m ? +m[1] : 1;
  };
  const words = (t, n) => String(t || '').split(/\s+/).filter(Boolean).slice(0, n).join(' ');

  // The photo thumbnail: a soft tone card with a camera and the first words in the photo, or its place.
  function photoSvg(r, w = 240, h = 180) {
    const [bg, fg] = TONES[phoneNo(r)] || TONES[1];
    const text = words(r.ocr_text, 8) || r.place || r.media_name || 'Photo';
    const lines = [];
    let cur = '';
    text.split(' ').forEach((wd) => {
      if ((cur + ' ' + wd).trim().length > 22 && cur) { lines.push(cur); cur = wd; } else cur = (cur + ' ' + wd).trim();
    });
    if (cur) lines.push(cur);
    const t = lines.slice(0, 3).map((l, i) => `<text x="${w / 2}" y="${h * 0.62 + i * 18}" text-anchor="middle" font-size="14" fill="${fg}" font-family="inherit">${esc(l)}</text>`).join('');
    const isVideo = r.kind === 'video';
    const cam = isVideo
      ? `<rect x="${w / 2 - 22}" y="${h * 0.2}" width="30" height="24" rx="4" fill="none" stroke="${fg}" stroke-width="2"/><path d="M${w / 2 + 10} ${h * 0.2 + 8} l12 -6 v24 l-12 -6z" fill="none" stroke="${fg}" stroke-width="2"/>`
      : `<rect x="${w / 2 - 18}" y="${h * 0.2 + 4}" width="36" height="26" rx="5" fill="none" stroke="${fg}" stroke-width="2"/><circle cx="${w / 2}" cy="${h * 0.2 + 17}" r="7" fill="none" stroke="${fg}" stroke-width="2"/><path d="M${w / 2 - 7} ${h * 0.2 + 4} l3 -5 h8 l3 5" fill="none" stroke="${fg}" stroke-width="2"/>`;
    return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(isVideo ? 'Video' : 'Photo')}: ${esc(text)}"><rect width="${w}" height="${h}" fill="${bg}"/>${cam}${t}</svg>`;
  }

  function wave(seed) {
    let x = 0;
    for (const c of String(seed)) x = (x * 31 + c.charCodeAt(0)) >>> 0;
    let bars = '';
    for (let i = 0; i < 28; i++) {
      x = (x * 1103515245 + 12345) >>> 0;
      bars += `<i style="height:${4 + (x % 20)}px"></i>`;
    }
    return `<span class="md-wave" aria-hidden="true">${bars}</span>`;
  }

  const who = (r) => r.sender_name || r.sender || (r.direction === 'out' ? 'Phone owner' : '');
  const toWho = (r) => r.conv_title || (Array.isArray(r.recipient_names) ? r.recipient_names.join(', ') : r.recipient_names) || '';
  const alsoOn = (r) => arr(r.also_on, 'phones').map((p) => (typeof p === 'string' ? p : p.label || p.phone_label || '')).filter(Boolean);

  function openPhoto(r) {
    const also = alsoOn(r);
    IB.dialog({
      title: r.media_name || (r.kind === 'video' ? 'Video' : 'Photo'),
      wide: true,
      body: `<div class="stack">
        <div class="md-big">${photoSvg(r, 560, 360)}</div>
        <div class="kv">
          <span class="muted">Phone</span><span>${IB.phoneChip(r.phone_label || r.source_id)}</span>
          <span class="muted">From</span><span>${esc(who(r))}</span>
          <span class="muted">To</span><span>${esc(toWho(r))}</span>
          <span class="muted">When</span><span>${r.ts ? esc(IB.fmt.time(r.ts)) : ''}</span>
          <span class="muted">Size</span><span>${r.media_size ? esc(IB.fmt.size(r.media_size)) : ''}</span>
          ${r.place ? `<span class="muted">Place</span><span>${esc(r.place)}</span>` : ''}
        </div>
        <div><div class="section-title">Words in the photo</div><p>${r.ocr_text ? esc(r.ocr_text) : '<span class="muted">No words read in this photo.</span>'}</p></div>
        <div><div class="section-title">Fingerprint</div><div class="row"><span class="code small md-fp grow">${esc(r.media_sha256 || 'Not recorded')}</span>
          ${r.media_sha256 ? `<button type="button" class="btn icon ghost" data-copy="${esc(r.media_sha256)}" aria-label="Copy the fingerprint" data-tip="Copy the fingerprint">${IB.icon('copy')}</button>` : ''}</div></div>
        ${also.length ? `<p><b>Also on</b> ${also.map((p) => IB.phoneChip(p)).join(' ')}</p>` : ''}
      </div>`,
      actions: [{ label: 'Open the record', value: 'open' }, { label: 'Close', kind: 'primary', value: null }],
    }).then((v) => { if (v === 'open' && r.event_id) IB.openRecord(r.event_id); });
  }

  const KINDS = [
    { key: 'photo', label: 'Photos & videos', noun: ['photo or video', 'photos and videos'] },
    { key: 'voice', label: 'Voice notes', noun: ['voice note', 'voice notes'] },
    { key: 'document', label: 'Documents', noun: ['document', 'documents'] },
  ];
  const READ_LABEL = { photo: 'Read words in photos', voice: 'Listen to voice notes', document: 'Read documents' };

  function countOf(data, k) {
    const c = data && (data.counts || data.by_kind) || {};
    if (k === 'photo') return (c.photo || 0) + (c.video || 0) || (c.photos || 0);
    return c[k] || 0;
  }

  async function render(view, ctx) {
    ctx.bar('');
    const kind = KINDS.some((k) => k.key === ctx.query.kind) ? ctx.query.kind : 'photo';
    view.innerHTML = `<div class="page stack">
      <div class="card-head"><div><h2 class="page-title">Photos and files</h2>
        <p class="muted small">Photos, videos, voice notes and documents on the phones in this case.</p></div>
        <div class="md-actions" id="md-actions"></div></div>
      <div id="md-tabs"></div>
      <div id="md-body"></div>
    </div>`;
    const body = IB.$('#md-body', view);
    const actions = IB.$('#md-actions', view);
    let first = null;

    const drawActions = (data) => {
      const read = (data && (data.read || data.done)) || {};
      actions.innerHTML = KINDS.map((k) => {
        const r = read[k.key] || {};
        const done = typeof r === 'number' ? r : (r.done || 0);
        const left = typeof r === 'object' ? (r.left || 0) : 0;
        return `<button type="button" class="btn small" data-md-read="${k.key}">${esc(READ_LABEL[k.key])} (${IB.fmt.num(done)} done${left ? ' | ' + IB.fmt.num(left) + ' left' : ''})</button>`;
      }).join('');
    };
    drawActions(null);

    const rowsById = {};
    let tabs;
    const show = (k) => {
      ctx.setQuery({ kind: k === 'photo' ? '' : k });
      ctx.exportable('media', { kind: k });
      const def = KINDS.find((x) => x.key === k);
      body.innerHTML = '';
      const holder = document.createElement('div');
      body.appendChild(holder);
      if (k === 'photo') holder.className = 'md-photos';
      IB.moreList(holder, {
        alive: ctx.alive,
        noun: def.noun,
        empty: `No ${def.noun[1]} on these phones.`,
        load: async (offset) => {
          const r = await ctx.capi('/media', { query: { kind: k, offset } });
          if (!first) {
            first = r;
            drawActions(r);
            if (tabs && r && (r.counts || r.by_kind)) {
              IB.$('#md-tabs', view).innerHTML = '';
              tabs = IB.tabs(IB.$('#md-tabs', view), { tabs: KINDS.map((x) => ({ key: x.key, label: x.label, count: countOf(r, x.key) })), active: k, onChange: show, label: 'Kinds of file' });
            }
          }
          const rows = arr(r, 'rows', 'items');
          return { rows, total: (r && r.total) != null ? r.total : rows.length };
        },
        row: (r) => rowHtml(k, r),
      });
    };

    tabs = IB.tabs(IB.$('#md-tabs', view), { tabs: KINDS.map((x) => ({ key: x.key, label: x.label })), active: kind, onChange: show, label: 'Kinds of file' });
    show(kind);

    function rowHtml(k, r) {
      rowsById[r.event_id] = r;
      if (k === 'photo') {
        return `<button type="button" class="md-card" data-md-photo="${esc(r.event_id)}" aria-label="Open ${esc(r.media_name || 'photo')}">
          ${photoSvg(r)}
          <span class="small clamp-1">${esc(r.media_name || '')}</span>
          <span class="tiny muted">${r.ts ? esc(IB.fmt.time(r.ts)) : ''}</span>
        </button>`;
      }
      if (k === 'voice') {
        return `<div class="md-row rec" tabindex="0" data-eid="${esc(r.event_id)}">
          ${IB.tile('play', 'blue')}
          <div class="md-main stack">
            <div class="row">${wave(r.event_id)}<span class="small num">${r.duration_s ? esc(IB.fmt.duration(r.duration_s)) : ''}</span>
              <span class="grow"></span>${IB.phoneChip(r.phone_label || r.source_id)}</div>
            <div class="small muted">${esc(who(r))}${toWho(r) ? ' to ' + esc(toWho(r)) : ''}${r.ts ? ' · ' + esc(IB.fmt.time(r.ts)) : ''}</div>
            <div class="clamp-2">${r.snippet_html ? IB.safe(r.snippet_html) : r.transcript ? esc(r.transcript) : '<span class="muted">Not listened to yet.</span>'}</div>
          </div>
        </div>`;
      }
      const text = r.ocr_text || r.body || r.text || '';
      return `<div class="md-row">
        ${IB.tile('file', 'violet')}
        <div class="md-main stack">
          <div class="row"><b class="clamp-1">${esc(r.media_name || 'Document')}</b><span class="small muted">${r.media_size ? esc(IB.fmt.size(r.media_size)) : ''}</span>
            <span class="grow"></span>${IB.phoneChip(r.phone_label || r.source_id)}</div>
          <div class="small muted">${esc(who(r))}${r.ts ? ' · ' + esc(IB.fmt.time(r.ts)) : ''}</div>
          ${text ? `<div class="clamp-2 small">${esc(text)}</div>` : '<div class="small muted">Not read yet.</div>'}
        </div>
        <div class="row"><button type="button" class="btn small" data-md-doc="${esc(r.event_id)}">Read it</button>
        <button type="button" class="btn small ghost" data-eid="${esc(r.event_id)}">Open the record</button></div>
      </div>`;
    }

    body.addEventListener('click', (e) => {
      const p = e.target.closest('[data-md-photo]');
      if (p) { const r = rowsById[p.dataset.mdPhoto]; if (r) openPhoto(r); return; }
      const d = e.target.closest('[data-md-doc]');
      if (d) {
        const r = rowsById[d.dataset.mdDoc] || {};
        const text = r.ocr_text || r.body || r.text || '';
        IB.openPanel({
          title: r.media_name || 'Document',
          label: 'Document text',
          html: `<div class="stack"><div class="small muted">${esc(who(r))}${r.ts ? ' · ' + esc(IB.fmt.time(r.ts)) : ''}</div>
            <div style="white-space:pre-wrap">${text ? esc(text) : '<span class="muted">No text read from this document yet.</span>'}</div>
            <button type="button" class="btn small" data-eid="${esc(r.event_id)}">Open the record</button></div>`,
        });
      }
    });

    actions.addEventListener('click', async (e) => {
      const b = e.target.closest('[data-md-read]');
      if (!b) return;
      const done = IB.busy(b, 'Starting…');
      try {
        await ctx.capi('/media/read', { method: 'POST', body: { kind: b.dataset.mdRead } });
        IB.status('Started. This page updates when it is done.');
        IB.refreshJobs();
      } catch (err) {
        IB.status(err.message, { error: true });
      }
      done();
    });
  }

  IB.page('media', { title: 'Photos and files', render });

  IB.on('jobs:done', () => {
    if (/\/media(\?|$)/.test(location.hash)) IB.reload();
  });
})();
