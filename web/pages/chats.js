/* Chats: IB.page('chats', ...), styled by chat-looks.css. See docs/frontend-interfaces.md. */
(() => {
  const esc = (v) => IB.esc(v);
  const APPS = [['', 'All'], ['whatsapp', 'WhatsApp'], ['sms', 'SMS'], ['telegram', 'Telegram'], ['signal', 'Signal'], ['imessage', 'Messages']];
  const LOOKS = { whatsapp: 'whatsapp', sms: 'sms', imessage: 'imessage', messages: 'imessage', telegram: 'telegram', signal: 'signal' };

  const lookOf = (app) => LOOKS[String(app || '').toLowerCase()] || 'sms';
  const listOf = (r, ...keys) => {
    if (Array.isArray(r)) return r;
    if (!r) return [];
    for (const k of keys) if (Array.isArray(r[k])) return r[k];
    return [];
  };
  const tsOf = (v) => (typeof v === 'number' ? v : Date.parse(v) || 0);
  const hash = (s) => { let h = 0; s = String(s || ''); for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); };
  const initials = (name) => {
    const parts = String(name || '?').replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '#';
    return ((parts[0][0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
  };
  const names = (v) => {
    if (!v) return [];
    if (typeof v === 'string') { try { v = JSON.parse(v); } catch (e) { return [v]; } }
    if (!Array.isArray(v)) return [];
    return v.map((p) => (typeof p === 'string' ? p : (p && (p.name || p.display || p.ident)) || '')).filter(Boolean);
  };
  const phoneList = (v) => {
    if (v == null || v === '' || v === false) return [];
    if (Array.isArray(v)) return v;
    return [v];
  };
  const phoneName = (p) => {
    if (p == null) return '';
    if (typeof p === 'object') return p.label || p.phone_label || (p.source_id != null ? 'Phone ' + p.source_id : '');
    if (typeof p === 'number' || /^\d+$/.test(String(p))) return 'Phone ' + p;
    return String(p).split('|')[0].trim();
  };
  const phoneFull = (p) => {
    if (p == null) return '';
    if (typeof p === 'object' && (p.label || p.phone_label)) return p.label || p.phone_label;
    const id = typeof p === 'object' ? p.source_id : p;
    const ph = (IB.state.phones || []).find((x) => String(x.source_id) === String(id));
    return ph ? ph.label : phoneName(p);
  };

  /* ---------- The chat list ---------- */

  function chatRow(c, activeId) {
    const title = c.title || names(c.participants).join(', ') || 'Unnamed chat';
    const last = c.last || c.last_message || {};
    const lastText = (typeof last === 'string' ? last : (last.preview || last.body || last.transcript || last.media_name || '')) || c.last_body || c.snippet || '';
    const lastTs = c.last_ts || last.ts;
    const n = c.n_messages != null ? c.n_messages : c.messages;
    const del = c.n_deleted || c.deleted || 0;
    const also = phoneList(c.also_on || c.other_phones);
    const app = String(c.app || '').toLowerCase();
    return `<div class="cv-row${String(c.conv_id) === String(activeId) ? ' on' : ''}" role="option" tabindex="0"
        aria-selected="${String(c.conv_id) === String(activeId)}" data-conv="${esc(c.conv_id)}">
      <span class="cv-av t${hash(title) % 6}" aria-hidden="true">${esc(initials(title))}</span>
      <div class="cv-main">
        <div class="cv-top"><span class="cv-title clamp-1">${esc(title)}</span>
          <span class="cv-time tiny muted">${lastTs ? esc(IB.fmt.time(lastTs)) : ''}</span></div>
        <div class="cv-last small muted clamp-1">${IB.icon('app-' + (app === 'messages' ? 'imessage' : app || 'sms'), 14)} ${esc(lastText)}</div>
        <div class="cv-meta tiny">
          ${n != null ? `<span class="muted">${esc(IB.plural(n, 'message', 'messages'))}</span>` : ''}
          ${del ? `<span class="chip status critical">${esc(IB.fmt.num(del))} deleted</span>` : ''}
          ${also.length ? `<span class="pill tone-violet">Also on ${esc(also.map(phoneName).join(', '))}</span>` : ''}
          ${(IB.state.phones || []).length > 1 && (c.source_id != null || c.phone_label) ? IB.phoneChip(c.phone_label || c.source_id) : ''}
        </div>
      </div>
    </div>`;
  }

  /* ---------- Bubbles ---------- */

  function bars(seed) {
    let h = hash(seed) || 7, out = '';
    for (let i = 0; i < 30; i++) { h = (h * 1103515245 + 12345) & 0x7fffffff; out += `<i style="height:${4 + (h % 17)}px"></i>`; }
    return out;
  }

  function media(m) {
    const kind = String(m.kind || '').toLowerCase();
    const name = m.media_name || '';
    if (kind === 'photo' || kind === 'image' || kind === 'video') {
      const words = m.ocr_text ? `<span class="cb-ocr tiny clamp-2">${esc(m.ocr_text)}</span>` : '';
      return `<div class="cb-photo">${IB.icon(kind === 'video' ? 'film' : 'image', 28)}
        <span class="tiny clamp-1">${esc(name || (kind === 'video' ? 'Video' : 'Photo'))}</span>${words}</div>`;
    }
    if (kind === 'voice' || kind === 'audio') {
      return `<div class="cb-voice"><span class="cb-play" aria-hidden="true">${IB.icon('play', 16)}</span>
        <span class="cb-wave" aria-hidden="true">${bars(m.event_id || name)}</span>
        <span class="tiny num">${m.duration_s ? esc(IB.fmt.duration(m.duration_s)) : ''}</span></div>
        ${m.transcript ? `<div class="cb-said"><span class="tiny caps muted">What was said</span><i>${esc(m.transcript)}</i></div>` : ''}`;
    }
    if (kind === 'document' || kind === 'file') {
      return `<span class="cb-doc">${IB.icon('file', 16)} <span class="clamp-1">${esc(name || 'Document')}</span>
        ${m.media_size ? `<span class="tiny muted">${esc(IB.fmt.size(m.media_size))}</span>` : ''}</span>`;
    }
    if (name) return `<span class="cb-doc">${IB.icon('file', 16)} <span class="clamp-1">${esc(name)}</span></span>`;
    return '';
  }

  function sideNote(m) {
    const t = m.side_note || m.marker || m.sides_text;
    if (t) return t;
    const del = phoneList(m.deleted_on);
    if (del.length) return 'Deleted on ' + del.map(phoneName).join(' and ');
    if (Array.isArray(m.also_on)) {
      const all = [m.phone_label || m.source_id].concat(m.also_on.map((o) => o.phone_label || o.source_id));
      if (m.also_on.length) return 'On ' + all.map(phoneName).join(' and ');
      if (all[0] != null && all[0] !== '') return 'Only on ' + phoneName(all[0]);
    }
    const on = phoneList(m.on || m.on_phones || m.sources || m.copies);
    if (on.length > 1) return 'On ' + on.map(phoneName).join(' and ');
    if (on.length === 1) return 'Only on ' + phoneName(on[0]);
    const only = m.only_on;
    if (only != null && only !== '') return 'Only on ' + phoneName(only);
    if (m.phone_label || m.source_id != null) return 'Only on ' + phoneName(m.phone_label || m.source_id);
    return '';
  }

  function bubble(m, ctx2) {
    const out = m.mine != null ? !!m.mine : m.direction === 'out';
    const status = String(m.status || '');
    const sender = m.sender_name || m.sender || '';
    const body = m.body || '';
    const chips = [];
    if (status === 'deleted') chips.push(IB.statusChip('deleted'));
    else if (status === 'edited') chips.push('<span class="chip">Edited</span>');
    else if (status === 'unsent') chips.push('<span class="chip">Unsent</span>');
    const note = ctx2.both ? sideNote(m) : '';
    const tick = out && ctx2.look === 'whatsapp' ? `<span class="cb-tick" aria-label="Read">${IB.icon('ticks', 14)}</span>` : '';
    const flagged = IB.isFlagged && IB.isFlagged(m.event_id) ? ' flag-on' : '';
    return `<div class="cb-line ${out ? 'out' : 'in'}${ctx2.first ? ' first' : ''}">
      <div class="bubble cb ${out ? 'out' : 'in'}${ctx2.first ? ' tail' : ''}${status === 'deleted' ? ' deleted' : ''}${flagged}"
          tabindex="0" data-eid="${esc(m.event_id)}" id="m-${esc(m.event_id)}">
        ${ctx2.first && ctx2.group && !out && sender ? `<div class="cb-from c${hash(sender) % 6}">${esc(sender)}</div>` : ''}
        ${media(m)}
        ${body ? `<div class="cb-text">${esc(body)}</div>` : ''}
        <div class="cb-foot">${chips.join('')}<span class="cb-time">${esc(IB.fmt.clock(m.ts))}</span>${tick}</div>
      </div>
      ${note ? `<div class="cb-side tiny">${esc(note)}</div>` : ''}
    </div>`;
  }

  /* ---------- The page ---------- */

  IB.page('chats', {
    title: 'Chats',
    render(view, ctx) {
      ctx.bar('');
      const q = ctx.query;
      const multi = (IB.state.phones || []).length > 1;
      view.innerHTML = `<div class="chats-wrap">
        <section class="cv-pane" aria-label="Chats">
          <div class="cv-controls">
            <input class="input" type="search" id="cv-find" placeholder="Find a chat" aria-label="Find a chat" value="${esc(q.q || '')}">
            <div class="cv-apps" role="group" aria-label="App">${APPS.map(([k, l]) =>
              `<button type="button" class="btn small${(q.app || '') === k ? ' on' : ''}" aria-pressed="${(q.app || '') === k}" data-app="${k}">${esc(l)}</button>`).join('')}</div>
            ${multi ? `<select class="select" id="cv-phone" aria-label="Phone"><option value="">Every phone</option>${(IB.state.phones || []).map((p) =>
              `<option value="${esc(p.source_id)}"${String(q.phone || '') === String(p.source_id) ? ' selected' : ''}>${esc(p.label)}</option>`).join('')}</select>` : ''}
          </div>
          <div class="cv-list" id="cv-list" role="listbox" aria-label="Chats, newest first"></div>
        </section>
        <section class="th-pane" id="th-pane" aria-label="Messages"></section>
      </div>`;

      const convs = new Map();
      const listEl = IB.$('#cv-list', view);
      const pane = IB.$('#th-pane', view);
      let active = q.conv || '';

      const list = IB.moreList(listEl, {
        noun: ['chat', 'chats'],
        empty: 'No chats match. Try another word, or show every app.',
        alive: ctx.alive,
        async load(offset) {
          const r = await ctx.capi('/chats', { query: { q: ctx.query.q, app: ctx.query.app, phone: ctx.query.phone, offset } });
          const rows = listOf(r, 'rows', 'chats', 'conversations');
          rows.forEach((c) => convs.set(String(c.conv_id), c));
          if (!active && offset === 0 && rows.length) { active = String(rows[0].conv_id); openThread(rows[0].conv_id, false); }
          return { rows, total: (r && r.total != null) ? r.total : rows.length };
        },
        row: (c) => chatRow(c, active),
      });

      let findTimer;
      IB.$('#cv-find', view).addEventListener('input', (e) => {
        clearTimeout(findTimer);
        findTimer = setTimeout(() => { ctx.setQuery({ q: e.target.value.trim() }); list.reload(); }, 250);
      });
      IB.$$('[data-app]', view).forEach((b) => b.addEventListener('click', () => {
        IB.$$('[data-app]', view).forEach((x) => { const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on); });
        ctx.setQuery({ app: b.dataset.app }); list.reload();
      }));
      const ph = IB.$('#cv-phone', view);
      if (ph) ph.addEventListener('change', () => { ctx.setQuery({ phone: ph.value }); list.reload(); });

      const pick = (row) => {
        if (!row) return;
        IB.$$('.cv-row', listEl).forEach((x) => { const on = x === row; x.classList.toggle('on', on); x.setAttribute('aria-selected', on); });
        active = row.dataset.conv;
        ctx.setQuery({ conv: active, around: '', find: '', both: '' }, { push: true });
        openThread(active, true);
      };
      listEl.addEventListener('click', (e) => pick(e.target.closest('.cv-row')));
      listEl.addEventListener('keydown', (e) => {
        const row = e.target.closest('.cv-row');
        if (!row) return;
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(row); }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          const rows = IB.$$('.cv-row', listEl), i = rows.indexOf(row);
          const next = rows[i + (e.key === 'ArrowDown' ? 1 : -1)];
          if (next) next.focus();
        }
      });

      /* ---------- One thread ---------- */
      let thAlive = () => true;
      async function openThread(convId, fresh) {
        thAlive = IB.latest('chat-thread');
        const mine = thAlive;
        const around = fresh ? '' : (ctx.query.around || '');
        const both = !fresh && (ctx.query.both === '1' || ctx.query.both === 1);
        const st = { convId, both, around, msgs: [], conv: convs.get(String(convId)) || {}, moreBefore: false, moreAfter: false, loading: false, hits: [], hit: -1 };
        pane.innerHTML = `<div class="th-skel">${IB.skeleton('rows', 8)}</div>`;
        let r;
        try {
          r = await ctx.capi('/chats/' + encodeURIComponent(convId), { query: { around, both: both ? 1 : '' } });
        } catch (err) {
          if (!mine()) return;
          IB.fail(pane, err, () => openThread(convId, fresh));
          return;
        }
        if (!mine()) return;
        absorb(st, r, 'set');
        drawThread(st);
        if (!fresh && ctx.query.find) { const f = IB.$('#th-find', pane); if (f) { f.value = ctx.query.find; runFind(st); } }
      }

      function absorb(st, r, mode) {
        const msgs = listOf(r, 'messages', 'rows', 'records');
        if (r && !Array.isArray(r)) {
          st.conv = Object.assign({}, st.conv, r.conv || r.conversation || {});
          st.bothInfo = r.both && r.both.on ? r.both : null;
          if (r.can_show_both != null) st.canBoth = !!r.can_show_both;
          if (r.also_on) st.conv.also_on = r.also_on;
        }
        const flag = (keys, dflt) => { for (const k of keys) if (r && r[k] != null) return !!r[k]; return dflt; };
        const full = msgs.length >= 100;
        if (mode === 'set') {
          st.msgs = msgs;
          st.moreBefore = flag(['has_before', 'more_before', 'has_more_before', 'has_older'], full);
          st.moreAfter = flag(['has_after', 'more_after', 'has_more_after', 'has_newer'], !!st.around && full);
        } else if (mode === 'before') {
          const seen = new Set(st.msgs.map((m) => m.event_id));
          st.msgs = msgs.filter((m) => !seen.has(m.event_id)).concat(st.msgs);
          st.moreBefore = flag(['has_before', 'more_before', 'has_more_before', 'has_older'], full);
        } else {
          const seen = new Set(st.msgs.map((m) => m.event_id));
          st.msgs = st.msgs.concat(msgs.filter((m) => !seen.has(m.event_id)));
          st.moreAfter = flag(['has_after', 'more_after', 'has_more_after', 'has_newer'], full);
        }
        st.msgs.sort((a, b) => tsOf(a.ts) - tsOf(b.ts));
      }

      function msgsHtml(st) {
        const look = lookOf(st.conv.app || (st.msgs[0] && st.msgs[0].app));
        const group = !!st.conv.is_group || names(st.conv.participants).length > 2;
        let html = '', day = '', prev = null;
        if (st.moreBefore) html += `<div class="th-more tiny muted" role="status">Scroll up for older messages</div>`;
        else if (st.msgs.length) html += `<div class="th-more tiny muted">The start of this chat</div>`;
        for (const m of st.msgs) {
          const d = IB.fmt.dayKey(m.ts);
          if (d !== day) { day = d; prev = null; html += `<div class="th-day"><span>${esc(IB.fmt.date(m.ts))}</span></div>`; }
          const who = (m.mine != null ? (m.mine ? 'out' : 'in') : (m.direction || '')) + '|' + (m.sender_name || m.sender || '');
          html += bubble(m, { look, group, both: st.both, first: who !== prev });
          prev = who;
        }
        if (st.moreAfter) html += `<div class="th-more tiny muted" role="status">Scroll down for newer messages</div>`;
        return html;
      }

      function drawThread(st) {
        const c = st.conv;
        const look = lookOf(c.app || (st.msgs[0] && st.msgs[0].app));
        const title = c.title || names(c.participants).join(', ') || 'Chat';
        const parts = names(c.participant_names && c.participant_names.length ? c.participant_names : c.participants);
        const n = c.n_messages != null ? c.n_messages : st.msgs.length;
        const first = c.first_ts || (st.msgs[0] && st.msgs[0].ts);
        const last = c.last_ts || (st.msgs.length && st.msgs[st.msgs.length - 1].ts);
        const also = phoneList(c.also_on || c.other_phones);
        const canBoth = st.canBoth != null ? st.canBoth : (also.length > 0 || (IB.state.phones || []).length > 1);
        const here = c.phone_label || c.source_id;
        const otherLabels = also.length ? also.map(phoneFull) : (IB.state.phones || []).filter((p) => String(p.source_id) !== String(c.source_id)).map((p) => p.label);
        pane.innerHTML = `
          <header class="th-head">
            <div class="th-id">
              <span class="cv-av t${hash(title) % 6}" aria-hidden="true">${esc(initials(title))}</span>
              <div class="grow">
                <h2 class="th-title clamp-1">${esc(title)}</h2>
                <div class="tiny muted clamp-1">${esc(parts.join(', '))}</div>
              </div>
            </div>
            <div class="th-meta row small">
              ${c.app ? IB.appChip(c.app) : ''}
              ${here != null && here !== '' ? IB.phoneChip(here) : ''}
              <span class="muted">${esc(IB.plural(n, 'message', 'messages'))}</span>
              ${first ? `<span class="muted">${esc(IB.fmt.date(first))} to ${esc(IB.fmt.date(last))}</span>` : ''}
            </div>
            <div class="th-tools row">
              <div class="th-findbox" role="search">
                <input class="input" type="search" id="th-find" placeholder="Find in this chat" aria-label="Find in this chat">
                <span class="tiny muted num" id="th-count" aria-live="polite"></span>
                <button type="button" class="btn icon ghost small" id="th-up" aria-label="Previous match" data-tip="Previous match">${IB.icon('chevron-up', 16)}</button>
                <button type="button" class="btn icon ghost small" id="th-down" aria-label="Next match" data-tip="Next match">${IB.icon('chevron-down', 16)}</button>
              </div>
              ${canBoth && !st.both ? `<button type="button" class="btn small primary" id="th-both">${IB.icon('arrows-left-right', 16)} Show both sides</button>` : ''}
            </div>
          </header>
          ${st.both ? `<div class="th-banner" role="status">${IB.icon('arrows-left-right', 16)}
            <span class="grow">${esc((st.bothInfo && st.bothInfo.banner) || ('Showing both sides: ' + [phoneFull(here)].concat(otherLabels).filter(Boolean).join(' and ') + '. Each message is shown once.'))}${c.n_deleted && otherLabels.length ? ` <b>${esc(IB.plural(c.n_deleted, 'message', 'messages'))} deleted on ${esc(c.phone_label || phoneFull(here))} ${c.n_deleted === 1 ? 'is' : 'are'} still on ${esc(otherLabels.join(' and '))}.</b>` : ''}</span>
            <button type="button" class="btn small" id="th-one">Back to this phone's copy</button></div>` : ''}
          <div class="th-scroll" id="th-scroll" data-look="${look}" tabindex="-1">
            <div class="th-msgs" id="th-msgs">${st.msgs.length ? msgsHtml(st) : ''}</div>
          </div>`;
        const scroller = IB.$('#th-scroll', pane);
        if (!st.msgs.length) IB.$('#th-msgs', pane).innerHTML = IB.empty('No messages in this chat to show.', { icon: 'chat' });

        const target = st.around && document.getElementById('m-' + st.around);
        if (target) {
          target.scrollIntoView({ block: 'center' });
          target.classList.add('hl');
          setTimeout(() => target.classList.remove('hl'), 2000);
        } else scroller.scrollTop = scroller.scrollHeight;

        scroller.addEventListener('scroll', () => {
          if (st.loading) return;
          if (st.moreBefore && scroller.scrollTop < 120) loadMore(st, 'before');
          else if (st.moreAfter && scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120) loadMore(st, 'after');
        });

        const bothBtn = IB.$('#th-both', pane);
        if (bothBtn) bothBtn.addEventListener('click', () => { ctx.setQuery({ both: 1, around: '' }, { push: true }); reopen(st, true); });
        const oneBtn = IB.$('#th-one', pane);
        if (oneBtn) oneBtn.addEventListener('click', () => { ctx.setQuery({ both: '' }, { push: true }); reopen(st, false); });

        const f = IB.$('#th-find', pane);
        let ft;
        f.addEventListener('input', () => { clearTimeout(ft); ft = setTimeout(() => { ctx.setQuery({ find: f.value.trim() }); runFind(st); }, 200); });
        f.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); step(st, e.shiftKey ? -1 : 1); } });
        IB.$('#th-up', pane).addEventListener('click', () => step(st, -1));
        IB.$('#th-down', pane).addEventListener('click', () => step(st, 1));
      }

      async function reopen(st, both) {
        thAlive = IB.latest('chat-thread');
        const mine = thAlive;
        st.both = both; st.around = '';
        const scroller = IB.$('#th-scroll', pane);
        if (scroller) scroller.classList.add('updating');
        try {
          const r = await ctx.capi('/chats/' + encodeURIComponent(st.convId), { query: { both: both ? 1 : '' } });
          if (!mine()) return;
          absorb(st, r, 'set');
          drawThread(st);
        } catch (err) {
          if (!mine()) return;
          if (scroller) scroller.classList.remove('updating');
          IB.status(err.message, { error: true });
        }
      }

      async function loadMore(st, dir) {
        const mine = thAlive;
        st.loading = true;
        const edge = dir === 'before' ? st.msgs[0] : st.msgs[st.msgs.length - 1];
        const query = { both: st.both ? 1 : '' };
        query[dir] = edge ? edge.event_id : '';
        try {
          const r = await ctx.capi('/chats/' + encodeURIComponent(st.convId), { query });
          if (!mine()) return;
          const before = st.msgs.length;
          absorb(st, r, dir);
          if (st.msgs.length === before) { if (dir === 'before') st.moreBefore = false; else st.moreAfter = false; }
          const scroller = IB.$('#th-scroll', pane);
          const oldH = scroller.scrollHeight, oldTop = scroller.scrollTop;
          IB.$('#th-msgs', pane).innerHTML = msgsHtml(st);
          if (dir === 'before') scroller.scrollTop = scroller.scrollHeight - oldH + oldTop;
          const f = IB.$('#th-find', pane);
          if (f && f.value.trim()) runFind(st, true);
        } catch (err) {
          if (mine()) IB.status(err.message, { error: true });
        } finally {
          st.loading = false;
        }
      }

      function runFind(st, keep) {
        const f = IB.$('#th-find', pane);
        const word = (f ? f.value : '').trim().toLowerCase();
        IB.$$('.cb.found, .cb.found-now', pane).forEach((b) => b.classList.remove('found', 'found-now'));
        const count = IB.$('#th-count', pane);
        if (!word) { st.hits = []; st.hit = -1; count.textContent = ''; return; }
        st.hits = st.msgs.filter((m) => [m.body, m.transcript, m.ocr_text, m.media_name].some((t) => t && String(t).toLowerCase().includes(word))).map((m) => m.event_id);
        st.hits.forEach((id) => { const b = document.getElementById('m-' + id); if (b) b.classList.add('found'); });
        if (!st.hits.length) { st.hit = -1; count.textContent = 'Not found in what is loaded'; return; }
        if (!keep || st.hit < 0 || st.hit >= st.hits.length) st.hit = st.hits.length - 1;
        show(st);
      }
      function step(st, d) {
        if (!st.hits.length) { runFind(st); return; }
        st.hit = (st.hit + d + st.hits.length) % st.hits.length;
        show(st);
      }
      function show(st) {
        IB.$$('.cb.found-now', pane).forEach((b) => b.classList.remove('found-now'));
        const b = document.getElementById('m-' + st.hits[st.hit]);
        if (b) { b.classList.add('found-now'); b.scrollIntoView({ block: 'center' }); }
        IB.$('#th-count', pane).textContent = `${st.hit + 1} of ${st.hits.length}`;
      }

      if (active) openThread(active, false);
      else pane.innerHTML = IB.empty('Pick a chat on the left to read it.', { icon: 'chat' });
    },
  });
})();
