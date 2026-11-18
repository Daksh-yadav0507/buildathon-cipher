/* Key questions and Case brief tabs: IB.dashboardTab('keyq'|'brief', ...). See docs/frontend-interfaces.md. */
(() => {
  const esc = (v) => IB.esc(v);

  IB.css('pg-keyq', `
    .kq-list .kq-q { display: flex; gap: 12px; align-items: flex-start; padding: 12px 0; border-top: 1px solid var(--line, rgba(127,127,127,.2)); }
    .kq-list .kq-q:first-of-type { border-top: 0; }
    .kq-q .kq-n { min-width: 24px; color: var(--muted, #777); }
    .kq-q .kq-body { flex: 1; min-width: 0; }
    .kq-q .kq-text { font-weight: 600; margin-bottom: 4px; }
    .kq-line { margin: 4px 0; line-height: 1.5; }
    .kq-line .cite { margin-left: 4px; }
    .kq-why { margin-top: 4px; }
    .kq-off { opacity: .72; }
    .kq-add .textarea { min-height: 120px; }
    .br-sec { margin-bottom: 4px; }
    .br-sec ol { margin: 8px 0 0; padding-left: 20px; }
    .br-sec li { margin: 6px 0; line-height: 1.55; }
  `);

  // One line of an answer: its text plus a numbered citation chip per record.
  function lineHtml(line, start) {
    if (line == null) return '';
    if (typeof line === 'string') return `<div class="kq-line">${esc(line)}</div>`;
    const recs = Array.isArray(line.records) ? line.records : [];
    let n = start;
    const cites = recs.map((r) => {
      const eid = typeof r === 'string' ? r : (r && r.event_id);
      if (!eid) return '';
      n += 1;
      return IB.cite(n, eid, 'Open record ' + eid);
    }).join('');
    return { html: `<div class="kq-line">${esc(line.text || '')}${cites}</div>`, next: n };
  }

  function linesHtml(lines) {
    let n = 0;
    return (lines || []).map((l) => {
      const r = lineHtml(l, n);
      if (typeof r === 'string') return r;
      n = r.next;
      return r.html;
    }).join('');
  }

  const STATUS = {
    answered: ['Answered', 'green'],
    'not found': ['Not found', 'violet'],
    not_found: ['Not found', 'violet'],
    waiting: ['Waiting', 'blue'],
    running: ['Working on it', 'blue'],
    failed: ['Could not answer', 'orange'],
  };

  function resultHtml(q) {
    const res = q.result;
    if (!res) {
      if (q.status === 'waiting' || q.status === 'running') return '<p class="muted small">This question is answered after the phone is read.</p>';
      if (q.status === 'failed') return '<p class="muted small">This question could not be answered this time. Try running the questions again.</p>';
      return '';
    }
    if (typeof res === 'string') return `<div class="kq-line">${esc(res)}</div>`;
    let html = linesHtml(res.lines);
    const nf = Array.isArray(res.not_found) ? res.not_found : [];
    if (nf.length) html += nf.map((t) => `<div class="kq-line muted">${esc(t)}</div>`).join('');
    if (!html && res.text) html = `<div class="kq-line">${esc(res.text)}</div>`;
    return html;
  }

  function questionHtml(q, i) {
    const text = typeof q === 'string' ? q : (q.q || q.question || '');
    const st = STATUS[(q && q.status) || ''] || null;
    return `<div class="kq-q">
      <span class="kq-n num">${i + 1}.</span>
      <div class="kq-body">
        <div class="kq-text">${esc(text)}</div>
        ${typeof q === 'object' ? resultHtml(q) : ''}
      </div>
      <div class="row">
        ${st ? IB.pill(st[0], st[1]) : ''}
        <button type="button" class="btn small ghost" data-ask="${esc(text)}" data-tip="Ask this in Ask a question">Ask it again</button>
      </div>
    </div>`;
  }

  function listCard(list, i) {
    const qs = Array.isArray(list.questions) ? list.questions : [];
    const on = !!list.used;
    const answered = qs.filter((q) => q && q.status === 'answered').length;
    const head = `<div class="card-head">
        <div>
          <div class="card-title">${esc(list.name || 'Questions')}</div>
          <div class="muted small">${on ? 'On for this case' : 'Off for this case'} · ${IB.plural(qs.length, 'question', 'questions')}${on ? ' · ' + IB.fmt.num(answered) + ' answered' : ''}</div>
        </div>
        <div class="row">
          <button type="button" class="btn small" data-kq-use="${esc(list.id)}" data-use="${on ? '0' : '1'}" aria-pressed="${on}">${on ? 'Switch off for this case' : 'Switch on for this case'}</button>
        </div>
      </div>`;
    const when = list.when ? `<p class="muted small">When it applies: ${esc(list.when)}</p>` : '<p class="muted small">Runs on every phone.</p>';
    const why = list.why ? `<p class="small kq-why">What pointed to it: ${esc(list.why)}</p>` : '';
    const body = on
      ? `<div class="kq-list">${qs.map(questionHtml).join('')}</div>`
      : `<details class="fold"><summary>See the ${IB.plural(qs.length, 'question', 'questions')}</summary><div class="kq-list">${qs.map(questionHtml).join('')}</div></details>`;
    return `<section class="card stack ${on ? '' : 'kq-off'}" data-kq-index="${i}">${head}${when}${why}${body}</section>`;
  }

  async function addListDialog(ctx, reload) {
    const val = await IB.dialog({
      title: 'Add your own list of questions',
      wide: true,
      body: `<div class="stack kq-add">
        <label class="field"><span>Name of the list</span><input class="input" name="name" required placeholder="For example: Land deals"></label>
        <label class="field"><span>When it applies (leave blank for every phone)</span><input class="input" name="when" placeholder="The phone shows land being bought or sold in other people's names"></label>
        <label class="field"><span>Questions, one on each line</span><textarea class="textarea" name="questions" required placeholder="Who are the buyers and sellers?&#10;Which plots or survey numbers are named?"></textarea></label>
        <p class="muted small">Lists you add belong to the whole unit, so other officers can use them too.</p>
      </div>`,
      actions: [{ label: 'Cancel', value: null }, { label: 'Add the list', kind: 'primary', value: 'add', busy: 'Adding…' }],
      onAction: async (value, el) => {
        if (value !== 'add') return;
        const f = IB.formValues(el);
        const questions = String(f.questions || '').split('\n').map((s) => s.trim()).filter(Boolean);
        if (!questions.length) throw new Error('Write at least one question.');
        await IB.api('/question-lists', { method: 'POST', body: { name: String(f.name || '').trim(), when: String(f.when || '').trim(), questions } });
      },
    });
    if (val === 'add') {
      IB.status('List added. Its questions are answered next time they run.');
      reload();
    }
  }

  let kqView = null;

  async function drawKeyq(el, ctx) {
    kqView = { el, ctx };
    el.innerHTML = IB.skeleton('cards', 3);
    let data;
    try {
      data = await ctx.capi('/key-questions');
    } catch (err) {
      if (!ctx.alive()) return;
      IB.fail(el, err, () => drawKeyq(el, ctx));
      return;
    }
    if (!ctx.alive()) return;
    const lists = Array.isArray(data && data.lists) ? data.lists : [];
    const onLists = lists.filter((l) => l.used);
    const offLists = lists.filter((l) => !l.used);
    const waiting = data && data.waiting;
    const intro = `<div class="card-head">
        <div>
          <h2 class="section-title">Key questions</h2>
          <p class="muted small">Asked by themselves as soon as a phone is read. Each answer opens the records it rests on.${data && data.auto === false ? '' : ' Lists switch on by what the phone shows; you can switch any list on or off.'}</p>
        </div>
        <div class="row">
          <button type="button" class="btn small" data-kq-add>Add your own list</button>
          <button type="button" class="btn small" data-kq-run>Run the questions again</button>
        </div>
      </div>`;
    const wait = waiting ? `<p class="updating" role="status">${typeof waiting === 'number' ? IB.plural(waiting, 'question is', 'questions are') + ' still being answered.' : 'Some questions are still being answered.'}</p>` : '';
    let body;
    if (!lists.length) {
      body = IB.empty('No question lists yet. Add a phone to the case and its key questions are answered by themselves.', { icon: 'list' });
    } else {
      body = onLists.map(listCard).join('') +
        (offLists.length ? `<h3 class="section-title">Other lists, off for this case</h3>` + offLists.map(listCard).join('') : '');
    }
    el.innerHTML = `<div class="stack">${intro}${wait}${body}</div>`;

    IB.$$('[data-kq-use]', el).forEach((b) => b.addEventListener('click', async () => {
      const done = IB.busy(b, 'Saving…');
      try {
        await ctx.capi('/key-questions/use', { method: 'POST', body: { list_id: b.dataset.kqUse, use: b.dataset.use === '1' } });
        IB.status(b.dataset.use === '1' ? 'List switched on. Its questions are being answered.' : 'List switched off for this case.');
        drawKeyq(el, ctx);
      } catch (err) {
        done();
        IB.status(err.message, { error: true });
      }
    }));
    const run = IB.$('[data-kq-run]', el);
    if (run) run.addEventListener('click', async () => {
      const done = IB.busy(run, 'Starting…');
      try {
        await ctx.capi('/key-questions/run', { method: 'POST' });
        IB.status('Answering the key questions again. This page updates when it is done.');
        IB.refreshJobs();
      } catch (err) {
        IB.status(err.message, { error: true });
      }
      done();
    });
    const add = IB.$('[data-kq-add]', el);
    if (add) add.addEventListener('click', () => addListDialog(ctx, () => drawKeyq(el, ctx)));
  }

  /* ---------- Case brief ---------- */

  const BRIEF_TITLES = [
    'Whose phones these are',
    'The people who matter, and what each does',
    'What the case seems to be about',
    'Money',
    'Places and travel',
    'What was hidden or deleted',
    'Open questions to follow up',
  ];

  let briefView = null;

  async function drawBrief(el, ctx) {
    briefView = { el, ctx };
    el.innerHTML = IB.skeleton('page', 1);
    let data;
    try {
      data = await ctx.capi('/brief');
    } catch (err) {
      if (!ctx.alive()) return;
      IB.fail(el, err, () => drawBrief(el, ctx));
      return;
    }
    if (!ctx.alive()) return;
    data = data || {};
    let sections = Array.isArray(data.sections) ? data.sections : [];
    if (!sections.length && data.brief && Array.isArray(data.brief.sections)) sections = data.brief.sections;
    const made = data.made_at || data.written_at || data.ts;
    const by = data.ai ? `Written with the AI ${esc(data.ai)}` : (data.by ? esc(data.by) : '');
    const head = `<div class="card-head">
        <div>
          <h2 class="section-title">Case brief</h2>
          <p class="muted small">${made ? 'Written ' + esc(IB.fmt.time(made)) + '. ' : ''}${by ? by + '. ' : ''}Every line opens the records it rests on.</p>
        </div>
        <button type="button" class="btn small" data-br-again>Write the case brief again</button>
      </div>`;
    const upd = data.updating || data.writing ? '<p class="updating" role="status">The case brief is being written. This page updates when it is done.</p>' : '';
    let body;
    if (!sections.length) {
      body = IB.empty(data.updating ? 'The case brief is being written.' : 'No case brief yet. It is written by itself after the first phone is read.', { icon: 'file' });
    } else {
      let n = 0;
      body = sections.map((s, i) => {
        const title = s.title || s.name || BRIEF_TITLES[i] || 'Section ' + (i + 1);
        const lines = Array.isArray(s.lines) ? s.lines : [];
        const items = lines.map((l) => {
          const r = lineHtml(l, n);
          if (typeof r === 'string') return `<li>${r}</li>`;
          n = r.next;
          return `<li>${r.html}</li>`;
        }).join('');
        return `<section class="card br-sec">
          <div class="card-title">${i + 1}. ${esc(title)}</div>
          ${items ? `<ol>${items}</ol>` : '<p class="muted small">Nothing in the records for this section.</p>'}
        </section>`;
      }).join('');
    }
    el.innerHTML = `<div class="stack">${head}${upd}${body}</div>`;
    const again = IB.$('[data-br-again]', el);
    if (again) again.addEventListener('click', async () => {
      const done = IB.busy(again, 'Starting…');
      try {
        await ctx.capi('/brief', { method: 'POST' });
        IB.status('Writing the case brief again. This page updates when it is done.');
        IB.refreshJobs();
      } catch (err) {
        IB.status(err.message, { error: true });
      }
      done();
    });
  }

  IB.dashboardTab('brief', { label: 'Case brief', order: 60, render: drawBrief });
  IB.dashboardTab('keyq', { label: 'Key questions', order: 70, render: drawKeyq });

  // A finished job (a phone read, the brief written, questions answered): refresh in place.
  IB.on('jobs:done', () => {
    if (kqView && kqView.el.isConnected && kqView.ctx.alive()) drawKeyq(kqView.el, kqView.ctx);
    if (briefView && briefView.el.isConnected && briefView.ctx.alive()) drawBrief(briefView.el, briefView.ctx);
  });
})();
