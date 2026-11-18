/* Ask a question: IB.page('ask', ...). See docs/frontend-interfaces.md. */
(() => {
  const esc = (v) => IB.esc(v);

  const SUGGESTED = [
    'Who are the main people in this case and what does each do?',
    'Paisa kisne kisko bheja?',
    'Was anyone told to delete chats?',
    'Which code words are used?',
    'Where was Raju on the night of 15 Sep?',
    'Kya kisi official ko paise diye gaye?',
  ];

  const DEPTHS = [
    ['auto', 'Choose for me', 'starts quick and reads further when it needs to'],
    ['quick', 'Quick look', 'fast, reads the most relevant records'],
    ['further', 'Look further', "reads in rounds until it's sure"],
    ['deep', 'Read every chat', 'reads everything in the scope you choose; slower, nothing missed'],
  ];

  const STEPS = [
    'Finding the records…',
    'The AI is reading the records…',
    'Checking each line against its records…',
  ];

  // Answers asked in this session, newest first, kept per case while the app is open.
  const session = {};

  IB.css('page-ask', `
    .ask-head { display: flex; gap: 14px; align-items: center; }
    .ask-head .page-title { margin: 0; }
    .ask-box { display: flex; gap: 12px; align-items: stretch; }
    .ask-box .textarea { flex: 1; min-height: 84px; resize: vertical; }
    .ask-box .btn.primary { align-self: flex-start; min-width: 96px; }
    .ask-under { margin-top: 8px; }
    .ask-chips { display: flex; flex-wrap: wrap; gap: 8px; }
    .ask-chips .chip { cursor: pointer; }
    .ask-opts { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-top: 12px; }
    .ask-depth label { display: flex; gap: 8px; align-items: flex-start; padding: 4px 0; cursor: pointer; }
    .ask-depth input { margin-top: 3px; }
    .ask-scope { display: flex; gap: 12px; flex-wrap: wrap; }
    .ask-scope .field { min-width: 150px; }
    .ask-q { font-weight: 600; font-size: 1.05em; }
    .ask-line { margin: 0 0 10px; line-height: 1.6; }
    .ask-line .cite { margin-left: 4px; }
    .ask-warn { display: inline-flex; vertical-align: -3px; margin-left: 4px; color: var(--warning); }
    .ask-nf { color: var(--text-2); }
    .ask-nf ul { margin: 4px 0 0; padding-left: 20px; }
    .ask-rel { display: flex; gap: 6px; align-items: center; color: var(--good); }
    .ask-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .ask-step { display: flex; gap: 10px; align-items: center; }
    .ask-earlier .rec { cursor: pointer; }
  `);

  function stat(n, one, many) {
    return n ? IB.plural(n, one, many) : '';
  }

  function underLine() {
    const st = IB.state.stats || {};
    const phones = (IB.state.phones || []).length || (st.phones || []).length || 0;
    const kinds = {};
    (st.by_app || []).forEach((a) => { kinds[a.kind] = (kinds[a.kind] || 0) + (a.n || 0); });
    const parts = [
      stat(st.messages, 'message', 'messages'),
      stat(st.calls, 'call', 'calls'),
      stat(kinds.voice, 'voice note', 'voice notes'),
      stat(kinds.document, 'document', 'documents'),
    ].filter(Boolean);
    const ai = (IB.state.health || {}).ai || {};
    let aiWords;
    if (!ai.configured) aiWords = 'No AI is set up, so answers come straight from the records';
    else if (ai.local === false) aiWords = 'The AI runs at ' + (ai.host || 'another computer');
    else aiWords = 'The AI runs on this computer';
    const lead = phones ? 'Ask searches ' + IB.plural(phones, 'phone', 'phones') + (parts.length ? ': ' + parts.join(', ') : '') : 'Ask searches every phone in this case';
    return esc(lead) + ' | ' + esc(aiWords);
  }

  function phoneOptions() {
    return (IB.state.phones || []).map((p) =>
      `<option value="${esc(p.source_id)}">${esc(p.label || p.phone_label || p.phone_no || 'Phone ' + p.source_id)}</option>`).join('');
  }

  // Number the cited records in order of first use across the answer.
  function citeMap(res) {
    const map = new Map();
    (res.lines || []).forEach((l) => (l.records || []).forEach((eid) => { if (!map.has(eid)) map.set(eid, map.size + 1); }));
    return map;
  }

  function firstLine(rec) {
    if (!rec) return '';
    const raw = rec.body || rec.transcript || rec.ocr_text || rec.media_name || '';
    const text = raw || String(rec.snippet_html || '').replace(/<[^>]*>/g, '');
    const who = rec.sender_name || rec.sender || '';
    const line = (who ? who + ': ' : '') + text;
    return line.length > 120 ? line.slice(0, 117) + '…' : line;
  }

  function howText(res) {
    const h = res.how || {};
    const bits = [];
    const words = h.words || [];
    if (words.length) {
      const sp = h.spellings || [];
      bits.push('Searched every spelling of ' + words.map((w, i) => (i === 0 && sp.length ? w + ' (' + sp.join(', ') + ')' : w)).join(' and '));
    }
    if (h.people && h.people.length) bits.push('looked for ' + h.people.map((x) => (x && x.name) || x).join(', '));
    if (h.dates) bits.push('kept to ' + (h.dates.words || ((h.dates.from || '') + ' to ' + (h.dates.to || ''))));
    if (h.records_read != null) {
      const phones = (IB.state.phones || []).length;
      bits.push('read ' + IB.plural(h.records_read, 'record', 'records') + (phones ? ' from ' + IB.plural(phones, 'phone', 'phones') : '') +
        (h.rounds ? ' in ' + IB.plural(h.rounds, 'round', 'rounds') : ''));
    }
    if (h.seconds != null) bits.push(Number(h.seconds).toFixed(1) + ' s');
    if (h.ai) bits.push(/code|none/i.test(String(h.ai)) ? 'answered from the records alone, no AI' : 'the AI ' + h.ai);
    if (res.depth_used) {
      const d = DEPTHS.find((x) => x[0] === res.depth_used);
      if (d) bits.push(d[1].toLowerCase());
    }
    if (!bits.length) return '';
    const s = bits.join('; ');
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  function copyText(res) {
    const map = citeMap(res);
    const out = [res.question || ''];
    (res.lines || []).forEach((l) => {
      out.push(l.text + ' ' + (l.records || []).map((e) => '[' + map.get(e) + ']').join(''));
    });
    if ((res.not_found || []).length) out.push('Not in these records: ' + res.not_found.join(' '));
    if (map.size) {
      out.push('');
      map.forEach((n, eid) => out.push('[' + n + '] ' + eid));
    }
    return out.join('\n');
  }

  function answerCard(res, when) {
    const recs = res.records || [];
    const byId = new Map(recs.map((r) => [r.event_id, r]));
    const map = citeMap(res);
    const lines = res.lines || [];
    const head = `<div class="card-head"><div class="ask-q">${esc(res.question || '')}</div>
      <span class="muted small">${esc(when ? IB.fmt.time(when) : '')}</span></div>`;

    let body;
    if (!lines.length) {
      const closest = recs.slice(0, 5);
      body = `<p>The records don't answer this.${closest.length ? ' Closest records below.' : ''}</p>` +
        (closest.length ? `<div class="rec-list">${closest.map((r) => IB.recordRow(r, { phone: true })).join('')}</div>` : '');
    } else {
      body = lines.map((l) => {
        const cites = (l.records || []).map((eid) => IB.cite(map.get(eid), eid, firstLine(byId.get(eid)) || 'Open this record')).join('');
        const warn = l.checked === false
          ? `<span class="ask-warn" data-tip="Couldn't confirm this from the records it cites" aria-label="Couldn't confirm this from the records it cites" tabindex="0">${IB.icon('alert', 16)}</span>`
          : '';
        return `<p class="ask-line">${esc(l.text)}${warn}${cites}</p>`;
      }).join('');
    }

    const nf = (res.not_found || []).length
      ? `<div class="ask-nf"><div class="small caps">Not in these records</div><ul>${res.not_found.map((t) => `<li>${esc(t)}</li>`).join('')}</ul></div>`
      : '';
    const rel = (res.reliability ? `<div class="ask-rel small">${IB.icon('check', 16)}<span>${esc(res.reliability)}</span></div>` : '') +
      (res.status ? `<p class="small muted">${esc(res.status)}</p>` : '') +
      (res.limit ? `<p class="small muted">${IB.icon('lock', 14)} ${esc(res.limit)}</p>` : '');
    const how = howText(res);
    const howFold = how ? `<details class="fold"><summary>How this was found</summary><p class="small muted">${esc(how)}</p></details>` : '';
    const cited = lines.length ? recs.filter((r) => map.has(r.event_id)) : [];
    const shown = cited.length ? cited : (lines.length ? recs : []);
    const recFold = shown.length
      ? `<details class="fold"><summary>The records it rests on (${esc(IB.fmt.num(shown.length))})</summary>
          <div class="rec-list">${shown.map((r) => IB.recordRow(r, { phone: true })).join('')}</div></details>`
      : '';
    const follow = (res.follow_ups || []).map((q) =>
      `<button type="button" class="chip" data-follow="${esc(q)}">${esc(q)}</button>`).join('');
    const actions = `<div class="ask-actions">
      ${lines.length ? `<button type="button" class="btn small" data-act="save">${IB.icon('flag', 16)} Save as finding</button>` : ''}
      <button type="button" class="btn small ghost" data-act="copy">${IB.icon('copy', 16)} Copy</button>
      ${res.offer_deep ? `<button type="button" class="btn small" data-act="deep">Read every chat for this</button>` : ''}
      ${follow}</div>`;

    const card = IB.el(`<article class="card stack" aria-label="Answer">${head}<div>${body}</div>${nf}${rel}${howFold}${recFold}${actions}</article>`);
    card.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b || !card.contains(b)) return;
      if (b.dataset.act === 'save') IB.saveFinding({ ask_id: res.ask_id, title: res.question });
      else if (b.dataset.act === 'copy') { IB.copy(copyText(res)); IB.status('Answer copied'); }
      else if (b.dataset.act === 'deep') card.dispatchEvent(new CustomEvent('ib-ask', { bubbles: true, detail: { q: res.question, depth: 'deep' } }));
      else if (b.dataset.follow) card.dispatchEvent(new CustomEvent('ib-ask', { bubbles: true, detail: b.dataset.follow }));
    });
    return card;
  }

  function pendingCard(question) {
    const card = IB.el(`<article class="card stack" aria-busy="true">
      <div class="card-head"><div class="ask-q">${esc(question)}</div><span class="muted small">${esc(IB.fmt.clock(Date.now()))}</span></div>
      <div class="ask-step" role="status" aria-live="polite"><span class="skel" style="width:16px;height:16px;border-radius:999px"></span><span class="muted" data-step>${esc(STEPS[0])}</span></div>
      ${IB.skeleton('rows', 3)}</article>`);
    let i = 0;
    const timer = setInterval(() => {
      i = Math.min(i + 1, STEPS.length - 1);
      const s = card.querySelector('[data-step]');
      if (s) s.textContent = STEPS[i];
      if (i === STEPS.length - 1) clearInterval(timer);
    }, 2200);
    card.stop = () => clearInterval(timer);
    return card;
  }

  function asksList(data) {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.asks)) return data.asks;
    if (data && Array.isArray(data.rows)) return data.rows;
    return [];
  }

  async function render(view, ctx) {
    const cid = ctx.cid;
    session[cid] = session[cid] || [];
    const q = ctx.query || {};
    const keep = ctx.keep || {};
    ctx.bar('');

    view.innerHTML = `<div class="page stack">
      <div class="ask-head">${IB.tile('spark', 'teal')}<div>
        <h2 class="page-title">Ask anything about this case</h2>
        <p class="muted">In English or Hinglish. Every answer shows the messages it rests on.</p></div></div>
      <section class="card stack" aria-label="Your question">
        <div>
          <div class="ask-box">
            <textarea class="textarea" id="ask-q" rows="3" placeholder="For example: paisa kisne kisko bheja?" aria-label="Your question"></textarea>
            <button type="button" class="btn primary" id="ask-go">Ask</button>
          </div>
          <p class="small muted ask-under">${underLine()}</p>
        </div>
        <div class="ask-chips" aria-label="Suggested questions">
          ${SUGGESTED.map((s) => `<button type="button" class="chip" data-suggest="${esc(s)}">${esc(s)}</button>`).join('')}
        </div>
        <details class="fold" id="ask-more"${keep.more ? ' open' : ''}><summary>More options</summary>
          <div class="ask-opts">
            <fieldset class="ask-depth" style="border:0;padding:0;margin:0"><legend class="small caps">How far to read</legend>
              ${DEPTHS.map(([v, l, d]) => `<label><input type="radio" name="ask-depth" value="${v}"${v === (keep.depth || 'auto') ? ' checked' : ''}>
                <span><b>${esc(l)}</b> <span class="muted small">${esc(d)}</span></span></label>`).join('')}
            </fieldset>
            <div class="stack"><div class="small caps">Scope</div>
              <div class="ask-scope">
                <label class="field"><span>Phones</span><select class="select" id="ask-phone"><option value="">All phones</option>${phoneOptions()}</select></label>
                <label class="field"><span>From</span><input class="input" type="date" id="ask-from"></label>
                <label class="field"><span>To</span><input class="input" type="date" id="ask-to"></label>
              </div>
              <p class="small muted" id="ask-est" role="status" aria-live="polite"></p>
            </div>
          </div>
        </details>
      </section>
      <section class="stack" id="ask-answers" aria-label="Answers" aria-live="polite"></section>
      <section class="stack ask-earlier" id="ask-earlier" aria-label="Earlier questions"></section>
    </div>`;

    const box = IB.$('#ask-q', view);
    const go = IB.$('#ask-go', view);
    const answers = IB.$('#ask-answers', view);
    const more = IB.$('#ask-more', view);
    const phoneSel = IB.$('#ask-phone', view);
    const fromIn = IB.$('#ask-from', view);
    const toIn = IB.$('#ask-to', view);
    const est = IB.$('#ask-est', view);
    if (keep.phone) phoneSel.value = keep.phone;
    if (keep.from) fromIn.value = keep.from;
    if (keep.to) toIn.value = keep.to;

    const depth = () => (IB.$('input[name="ask-depth"]:checked', view) || {}).value || 'auto';
    const scope = () => {
      const s = {};
      if (phoneSel.value) s.phone = phoneSel.value;
      if (fromIn.value) s.from = fromIn.value;
      if (toIn.value) s.to = toIn.value;
      return s;
    };
    const remember = () => { Object.assign(keep, { more: more.open, depth: depth(), phone: phoneSel.value, from: fromIn.value, to: toIn.value }); };

    async function estimate() {
      remember();
      const alive = IB.latest('ask-estimate');
      if (depth() !== 'deep') { est.textContent = ''; return; }
      est.textContent = 'Working out how long this takes…';
      try {
        const sc = scope();
        const r = await ctx.capi('/ask/estimate', { query: { depth: 'deep', phone: sc.phone, from: sc.from, to: sc.to } });
        if (!ctx.alive() || !alive()) return;
        const bits = [];
        if (r.records != null) bits.push(IB.plural(r.records, 'message', 'messages') + (r.parts ? ' in ' + IB.plural(r.parts, 'part', 'parts') : ''));
        if (r.minutes_words) bits.push(r.minutes_words);
        else if (r.minutes) bits.push('about ' + IB.plural(Math.round(r.minutes), 'minute', 'minutes'));
        if (r.cost_words) bits.push(r.cost_words);
        est.textContent = bits.join(' | ');
      } catch (err) {
        if (ctx.alive() && alive()) est.textContent = "Couldn't work out how long this takes.";
      }
    }
    view.addEventListener('change', (e) => { if (e.target.closest('#ask-more')) estimate(); });
    more.addEventListener('toggle', remember);

    function drawSession() {
      answers.innerHTML = '';
      session[cid].forEach((a) => answers.appendChild(answerCard(a.res, a.when)));
    }

    let asking = false;
    async function ask(question) {
      question = String(question || '').trim();
      if (!question) { box.focus(); IB.status('Type a question first.'); return; }
      if (asking) return;
      asking = true;
      box.value = question;
      ctx.setQuery({ q: question, go: '' });
      const done = IB.busy(go, 'Asking…');
      const card = pendingCard(question);
      answers.prepend(card);
      try {
        const res = await ctx.capi('/ask', { method: 'POST', body: { question, depth: depth(), scope: scope() } });
        card.stop();
        const item = { res: Object.assign({ question }, res || {}), when: Date.now() };
        session[cid].unshift(item);
        card.replaceWith(answerCard(item.res, item.when));
        loadEarlier();
      } catch (err) {
        card.stop();
        card.removeAttribute('aria-busy');
        card.innerHTML = `<div class="card-head"><div class="ask-q">${esc(question)}</div></div><div data-fail></div>`;
        IB.fail(IB.$('[data-fail]', card), err, () => { card.remove(); asking = false; ask(question); });
      } finally {
        asking = false;
        if (ctx.alive()) done();
      }
    }

    go.addEventListener('click', () => ask(box.value));
    box.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(box.value); }
    });
    view.addEventListener('click', (e) => {
      const s = e.target.closest('[data-suggest]');
      if (s) ask(s.dataset.suggest);
    });
    view.addEventListener('ib-ask', (e) => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      const d = e.detail;
      if (d && typeof d === 'object') {
        const r = IB.$(`input[name="ask-depth"][value="${d.depth}"]`, view);
        if (r) r.checked = true;
        estimate();
        ask(d.q);
      } else ask(d);
    });

    const earlier = IB.$('#ask-earlier', view);
    async function loadEarlier() {
      try {
        const data = await ctx.capi('/asks');
        const seen = new Set(session[cid].map((a) => a.res.ask_id).filter((x) => x != null));
        const list = asksList(data).filter((a) => !seen.has(a.ask_id));
        if (!list.length) { earlier.innerHTML = ''; return; }
        earlier.innerHTML = `<h3 class="section-title">Earlier questions</h3>`;
        list.forEach((a) => {
          const res = a.result || a.answer || a;
          const when = a.asked_at || a.ts || a.created_at || a.at;
          const question = a.question || res.question || '';
          if ((res.lines || []).length || (res.not_found || []).length) {
            const fold = IB.el(`<details class="fold card"><summary><b>${esc(question)}</b> <span class="muted small">${esc(when ? IB.fmt.time(when) : '')}</span></summary></details>`);
            fold.appendChild(answerCard(Object.assign({ question, ask_id: a.ask_id }, res), when));
            earlier.appendChild(fold);
          } else {
            earlier.appendChild(IB.el(`<div class="card row"><span class="grow"><b>${esc(question)}</b>
              ${when ? `<span class="muted small"> ${esc(IB.fmt.time(when))}</span>` : ''}</span>
              <button type="button" class="btn small" data-suggest="${esc(question)}">Ask again</button></div>`));
          }
        });
      } catch (err) {
        earlier.innerHTML = '';
      }
    }

    drawSession();
    if (depth() === 'deep') estimate();
    if (q.q) box.value = q.q;
    const first = loadEarlier();
    if (q.q && q.go === '1' && !ctx.back) ask(q.q);
    else if (!q.q && !ctx.back) box.focus();
    return first;
  }

  IB.page('ask', { title: 'Ask a question', render });
})();
