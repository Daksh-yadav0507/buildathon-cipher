/* Findings and the Notes panel: IB.page('findings', ...), IB.action('notes', ...). See docs/frontend-interfaces.md. */
(() => {
  const esc = (v) => IB.esc(v);

  IB.css('pg-findings', `
    .fd-list { display: flex; flex-direction: column; gap: 12px; }
    .fd-item .fd-what { min-width: 0; }
    .fd-item .rec { border: 0; padding-left: 0; padding-right: 0; }
    .fd-note { width: 100%; min-height: 64px; }
    .fd-meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .fd-tags { display: flex; flex-wrap: wrap; gap: 6px; }
    .fd-tagbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .fd-tagbar .chip[aria-pressed="true"] { outline: 2px solid currentColor; outline-offset: -2px; font-weight: 600; }
    .np-item { padding: 12px 0; border-top: 1px solid var(--line, rgba(127,127,127,.2)); }
    .np-item:first-child { border-top: 0; }
    .np-item .np-title { font-weight: 600; }
  `);

  const idOf = (f) => f.finding_id != null ? f.finding_id : (f.id != null ? f.id : f.fid);
  const tagsOf = (f) => {
    const t = f.tags;
    if (Array.isArray(t)) return t.filter(Boolean).map(String);
    if (typeof t === 'string' && t) {
      try { const j = JSON.parse(t); if (Array.isArray(j)) return j.map(String); } catch (e) { /* plain text */ }
      return t.split(',').map((s) => s.trim()).filter(Boolean);
    }
    return [];
  };
  const whenOf = (f) => f.created_at || f.ts || f.saved_at || f.updated_at;
  const rowsOf = (data) => Array.isArray(data) ? data : (data && (data.rows || data.findings)) || [];

  async function loadAll() {
    return rowsOf(await IB.capi('/findings'));
  }

  // The finding's subject: its record row, or the answer's first line.
  function whatHtml(f) {
    const rec = f.record || (f.event && typeof f.event === 'object' ? f.event : null);
    if (rec && rec.event_id) return `<div class="rec-list">${IB.recordRow(rec, { phone: true })}</div>`;
    const title = f.title || f.answer_line || f.text || (f.question ? 'Answer: ' + f.question : '');
    const eid = f.event_id;
    if (eid) {
      return `<div class="rec" tabindex="0" data-eid="${esc(eid)}"><span class="clamp-2">${esc(title || 'Record ' + eid)}</span></div>`;
    }
    if (f.ask_id != null) {
      return `<div class="clamp-2">${esc(title || 'A saved answer')}</div>`;
    }
    return `<div class="clamp-2">${esc(title || 'A saved finding')}</div>`;
  }

  function openHref(f) {
    if (f.event_id) return null;
    if (f.ask_id != null) {
      const q = f.question || f.title || '';
      return IB.link('ask', q ? { q } : {});
    }
    return null;
  }

  async function patchFinding(f, body) {
    const id = idOf(f);
    try {
      return await IB.capi('/findings/' + encodeURIComponent(id), { method: 'PATCH', body });
    } catch (err) {
      if (err.status === 404 || err.status === 405) return IB.capi('/findings', { method: 'PATCH', body: Object.assign({ finding_id: id, id }, body) });
      throw err;
    }
  }

  async function deleteFinding(f) {
    const id = idOf(f);
    try {
      return await IB.capi('/findings/' + encodeURIComponent(id), { method: 'DELETE' });
    } catch (err) {
      if (err.status === 404 || err.status === 405) return IB.capi('/findings', { method: 'DELETE', query: { finding_id: id, id } });
      throw err;
    }
  }

  function itemHtml(f, i) {
    const tags = tagsOf(f);
    const href = openHref(f);
    const openBtn = f.event_id
      ? `<button type="button" class="btn small" data-eid="${esc(f.event_id)}">Open</button>`
      : (href ? `<a class="btn small" href="${esc(href)}">Open</a>` : '');
    return `<article class="card fd-item stack" data-fd="${i}">
      <div class="fd-what">${whatHtml(f)}</div>
      <label class="field"><span class="small muted">Note</span>
        <textarea class="textarea fd-note" data-fd-note="${i}" aria-label="Note for this finding">${esc(f.note || '')}</textarea>
      </label>
      <div class="fd-meta">
        <div class="fd-tags">${tags.map((t) => `<span class="chip">${esc(t)}</span>`).join('')}</div>
        <span class="grow"></span>
        <span class="muted small">${esc(f.officer || f.officer_name || f.by || '')}${whenOf(f) ? ' · ' + esc(IB.fmt.time(whenOf(f))) : ''}</span>
        <button type="button" class="btn small ghost" data-fd-tags="${i}">Change tags</button>
        ${openBtn}
        <button type="button" class="btn small danger" data-fd-remove="${i}">Remove</button>
      </div>
    </article>`;
  }

  async function render(view, ctx) {
    ctx.bar('');
    view.innerHTML = `<div class="page stack">
      <div class="card-head">
        <div>
          <h2 class="page-title">Findings</h2>
          <p class="muted small">Records and answers saved by officers on this case, newest first.</p>
        </div>
      </div>
      <div id="fd-tagbar" class="fd-tagbar"></div>
      <div id="fd-body">${IB.skeleton('cards', 3)}</div>
    </div>`;
    ctx.exportable('findings', () => (ctx.query.tag ? { tag: ctx.query.tag } : {}));
    const body = IB.$('#fd-body', view);
    const tagbar = IB.$('#fd-tagbar', view);
    let all;
    try {
      all = await loadAll();
    } catch (err) {
      IB.fail(body, err, () => render(view, ctx));
      return;
    }
    if (!ctx.alive()) return;
    all.sort((a, b) => (new Date(whenOf(b) || 0)) - (new Date(whenOf(a) || 0)));

    const draw = () => {
      const tag = ctx.query.tag || '';
      const counts = {};
      all.forEach((f) => tagsOf(f).forEach((t) => { counts[t] = (counts[t] || 0) + 1; }));
      const tagNames = Object.keys(counts).sort();
      tagbar.innerHTML = tagNames.length
        ? `<span class="small muted">Tags</span>
           <button type="button" class="chip" data-tag="" aria-pressed="${!tag}">All (${IB.fmt.num(all.length)})</button>
           ${tagNames.map((t) => `<button type="button" class="chip" data-tag="${esc(t)}" aria-pressed="${t === tag}">${esc(t)} (${IB.fmt.num(counts[t])})</button>`).join('')}`
        : '';
      const shown = tag ? all.filter((f) => tagsOf(f).includes(tag)) : all;
      if (!all.length) {
        body.innerHTML = IB.empty('No findings yet. Use "Save as finding" on any record or answer to keep it here with a note.', { icon: 'flag' });
        return;
      }
      if (!shown.length) {
        body.innerHTML = IB.empty('No findings have this tag.', { icon: 'tag' });
        return;
      }
      body.innerHTML = `<p class="muted small">${IB.plural(shown.length, 'finding', 'findings')}</p>
        <div class="fd-list">${shown.map((f) => itemHtml(f, all.indexOf(f))).join('')}</div>`;
    };
    draw();

    tagbar.addEventListener('click', (e) => {
      const b = e.target.closest('[data-tag]');
      if (!b) return;
      ctx.setQuery({ tag: b.dataset.tag });
      draw();
    });

    body.addEventListener('change', async (e) => {
      const ta = e.target.closest('[data-fd-note]');
      if (!ta) return;
      const f = all[+ta.dataset.fdNote];
      try {
        await patchFinding(f, { note: ta.value });
        f.note = ta.value;
        IB.status('Note saved.');
      } catch (err) {
        IB.status(err.message, { error: true });
      }
    });

    body.addEventListener('click', async (e) => {
      const rm = e.target.closest('[data-fd-remove]');
      if (rm) {
        const f = all[+rm.dataset.fdRemove];
        const ok = await IB.confirm('Remove this finding? The record itself stays in the case.', { ok: 'Remove the finding', danger: true });
        if (!ok) return;
        try {
          await deleteFinding(f);
          all = all.filter((x) => x !== f);
          draw();
          IB.status('Finding removed.');
        } catch (err) {
          IB.status(err.message, { error: true });
        }
        return;
      }
      const tg = e.target.closest('[data-fd-tags]');
      if (tg) {
        const f = all[+tg.dataset.fdTags];
        const v = await IB.dialog({
          title: 'Change tags',
          body: `<label class="field"><span>Tags, separated by commas</span><input class="input" name="tags" value="${esc(tagsOf(f).join(', '))}"></label>`,
          actions: [{ label: 'Cancel', value: null }, { label: 'Save the tags', kind: 'primary', value: 'save', busy: 'Saving…' }],
          onAction: async (value, el) => {
            if (value !== 'save') return;
            const tags = String(IB.formValues(el).tags || '').split(',').map((s) => s.trim()).filter(Boolean);
            await patchFinding(f, { tags });
            f.tags = tags;
          },
        });
        if (v === 'save') { draw(); IB.status('Tags saved.'); }
      }
    });
  }

  IB.page('findings', { title: 'Findings', render });

  // "Show findings" in the top bar: a right-side Notes panel from any page.
  IB.action('notes', async () => {
    if (!IB.state.cid) return;
    IB.openPanel({ title: 'Findings', label: 'Findings on this case', html: IB.skeleton('rows', 4) });
    let rows;
    try {
      rows = await loadAll();
    } catch (err) {
      IB.openPanel({ title: 'Findings', label: 'Findings on this case', html: `<div class="error-box" role="alert">${esc(err.message)}</div>` });
      return;
    }
    rows.sort((a, b) => (new Date(whenOf(b) || 0)) - (new Date(whenOf(a) || 0)));
    const items = rows.map((f) => {
      const tags = tagsOf(f);
      const title = f.title || (f.record && (f.record.body || f.record.media_name)) || (f.event_id ? 'Record ' + f.event_id : 'A saved answer');
      return `<div class="np-item stack">
        <div class="np-title clamp-2">${esc(title)}</div>
        ${f.note ? `<div class="small">${esc(f.note)}</div>` : ''}
        <div class="row">
          ${tags.map((t) => `<span class="chip">${esc(t)}</span>`).join('')}
          <span class="grow"></span>
          ${f.event_id ? `<button type="button" class="btn small" data-eid="${esc(f.event_id)}">Open</button>` : ''}
        </div>
      </div>`;
    }).join('');
    IB.openPanel({
      title: 'Findings',
      label: 'Findings on this case',
      html: `<div class="stack">
        <p class="muted small">${IB.plural(rows.length, 'finding', 'findings')} saved on this case.</p>
        ${rows.length ? items : IB.empty('No findings yet.', { icon: 'flag' })}
        <a class="btn small" href="${esc(IB.link('findings'))}">Go to Findings</a>
      </div>`,
    });
  });

  IB.on('finding', () => {
    if (location.hash.indexOf('/findings') !== -1) IB.reload();
  });
})();
