/* Log in, All cases and About: IB.page('login'|'cases'|'about', ...). See docs/frontend-interfaces.md. */
(() => {
  const IB = window.IB;
  if (!IB) return;
  const esc = (v) => IB.esc(v);
  const WRONG = "That name and password don't match. Check the spelling and try again.";

  IB.css('ib-home', `
    .hm-login { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px; padding: 40px 16px;
      background: var(--hero-bg, #0f1b2e); color: var(--on-strong, #eef2f8); }
    .hm-login .card { width: 400px; max-width: 100%; display: flex; flex-direction: column; gap: 16px; padding: 28px; }
    .hm-login .hm-brand { display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center; }
    .hm-login .hm-brand h2 { margin: 0; font-size: var(--t-xl, 22px); }
    .hm-login .hm-err { color: var(--critical, #c0392b); font-size: 14px; }
    .hm-login .hm-err:empty { display: none; }
    .hm-login .btn.primary { width: 100%; justify-content: center; }
    .hm-foot { font-size: 13px; opacity: .8; }
    .hm-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    @media (min-width: 1700px) { .hm-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    .hm-case { display: flex; flex-direction: column; gap: 10px; height: 100%; }
    .hm-case .hm-name { font-weight: 700; font-size: var(--t-l, 17px); margin: 0; }
    .hm-case .hm-meta { margin-top: auto; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .hm-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .hm-about-keys { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; }
  `);

  /* Log in */
  IB.page('login', {
    title: 'Log in',
    bare: true,
    render(view) {
      view.innerHTML = `<div class="hm-login">
        <form class="card" id="hm-form" novalidate>
          <div class="hm-brand">
            ${IB.logo(64)}
            <h2>Insights Buddy</h2>
            <p class="muted small">Read a seized phone into a case on this computer: every chat, call, photo and place, found and asked about in plain words.</p>
          </div>
          <label class="field"><span>Officer</span><input class="input" name="name" autocomplete="username" required></label>
          <label class="field"><span>Password</span><input class="input" type="password" name="password" autocomplete="current-password" required></label>
          <div class="hm-err" id="hm-err" role="alert"></div>
          <button type="submit" class="btn primary">Log in</button>
          <p class="muted small" style="margin:0;text-align:center">Sample login: Arjun Rao / demo</p>
        </form>
        <div class="hm-foot">Offline, on this PC only</div>
      </div>`;
      const form = IB.$('#hm-form', view);
      const err = IB.$('#hm-err', view);
      const nameEl = form.elements.name;
      setTimeout(() => nameEl.focus(), 0);
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = form.elements.name.value.trim();
        const password = form.elements.password.value;
        if (!name || !password) { err.textContent = 'Type your name and password, then log in.'; return; }
        err.textContent = '';
        const done = IB.busy(IB.$('button[type=submit]', form), 'Logging in…');
        try {
          await IB.api('/api/auth/login', { method: 'POST', body: { name, password }, noLogin: true });
          done();
          IB.loggedIn();
        } catch (ex) {
          done();
          err.textContent = ex && ex.status === 401 ? (ex.message || WRONG) : ((ex && ex.message) || 'Could not log in. Try again.');
          form.elements.password.select();
        }
      });
    },
  });

  /* All cases */
  function caseCard(c) {
    const phones = Array.isArray(c.phones) ? c.phones : [];
    const href = '#/c/' + encodeURIComponent(c.case_id);
    const bits = [IB.plural(Number(c.records) || 0, 'record', 'records')];
    if (c.last_opened) bits.push('last opened ' + IB.fmt.time(c.last_opened));
    return `<div class="card hm-case">
      ${c.number ? `<div class="caps tiny muted">Case ${esc(c.number)}</div>` : ''}
      <h3 class="hm-name">${esc(c.name || 'Untitled case')}</h3>
      ${c.about ? `<p class="muted small clamp-2" style="margin:0">${esc(c.about)}</p>` : ''}
      <div class="row" style="flex-wrap:wrap">${phones.length ? IB.phoneChips(phones) : '<span class="muted small">No phones added yet</span>'}</div>
      <div class="hm-meta"><span class="small muted num">${esc(bits.join(' | '))}</span><a class="btn small" href="${esc(href)}">Open</a></div>
    </div>`;
  }

  async function newCase() {
    let made = null;
    const value = await IB.dialog({
      title: 'New case',
      body: `<div class="stack">
        <label class="field"><span>Case name</span><input class="input" name="name" required></label>
        <label class="field"><span>Case number</span><input class="input" name="number" placeholder="For example 41/2026"></label>
        <label class="field"><span>What is this case about?</span><textarea class="textarea" name="about" rows="3" required></textarea>
          <span class="tiny muted">The AI reads this first. Say what you suspect: goods, people, money, places.</span></label>
      </div>`,
      actions: [{ label: 'Cancel', value: null }, { label: 'Make the case', kind: 'primary', value: 'make', busy: 'Making the case…' }],
      async onAction(v, el) {
        if (v !== 'make') return;
        const f = IB.formValues(el);
        made = await IB.api('/api/cases', { method: 'POST', body: { name: (f.name || '').trim(), number: (f.number || '').trim(), about: (f.about || '').trim() } });
        return true;
      },
      onOpen(el) { const i = IB.$('input[name=name]', el); if (i) i.focus(); },
    });
    if (value === 'make') {
      const cid = made && (made.case_id || (made.case && made.case.case_id));
      if (cid) IB.go('#/c/' + encodeURIComponent(cid));
      else IB.reload();
    }
  }

  IB.page('cases', {
    title: 'Your cases',
    async render(view, ctx) {
      view.innerHTML = `<div class="page stack">
        <div class="hm-head"><h2 class="page-title">Your cases</h2><button type="button" class="btn primary" id="hm-new">${IB.icon('plus', 16)} New case</button></div>
        <div id="hm-list">${IB.skeleton('cards', 6)}</div>
        <div><a class="link small" href="#/about">About and credits</a></div>
      </div>`;
      IB.$('#hm-new', view).addEventListener('click', newCase);
      const list = IB.$('#hm-list', view);
      const load = async () => {
        list.innerHTML = IB.skeleton('cards', 6);
        try {
          const cases = await ctx.api('/api/cases');
          const rows = Array.isArray(cases) ? cases : (cases && cases.cases) || [];
          if (!rows.length) {
            list.innerHTML = IB.empty('No cases yet. Make one, then add a phone.', { icon: 'case' });
            return;
          }
          list.innerHTML = `<div class="hm-grid">${rows.map(caseCard).join('')}</div>`;
        } catch (err) {
          IB.fail(list, err, load);
        }
      };
      return load();
    },
  });

  /* About and credits */
  IB.page('about', {
    title: 'About and credits',
    render(view) {
      const keys = [
        ['/ or Ctrl+K', 'Find a name, number or word'],
        ['Esc', 'Close the drawer, dialog or popup'],
        ['Enter', 'Submit, or open the record in focus'],
        ['Arrow keys', 'Move between tabs and through lists'],
        ['g then d', 'Go to the Dashboard'],
        ['g then a', 'Go to Ask a question'],
        ['g then s', 'Go to Search'],
        ['g then c', 'Go to Chats'],
        ['g then t', 'Go to the Timeline'],
      ];
      view.innerHTML = `<div class="page stack">
        <h2 class="page-title">About and credits</h2>
        <div class="cols cols-2">
          <div class="card stack">
            <div class="row">${IB.logo(40)}<div><div class="card-title">Insights Buddy</div><div class="muted small">Seek deeper insights</div></div></div>
            <p>Insights Buddy helps an investigating officer understand seized phones. It reads a phone's extraction into one case, then lets you see the case at a glance, ask questions in English, Hindi or Hinglish, search every spelling of a word, read every chat the way the app showed it, and compare several people's phones.</p>
            <p>Every number and answer opens the records behind it. When something is not in the records, it says "not found".</p>
            <p class="muted small">It runs on this computer only. Nothing leaves it except questions to the AI, and only when an AI is set up elsewhere.</p>
            <p class="muted small">The sample case and its three phones are made up. Any likeness to real people, cases or agencies is chance.</p>
          </div>
          <div class="card stack">
            <div class="card-title">Keyboard</div>
            <div class="hm-about-keys small">${keys.map(([k, t]) => `<kbd>${esc(k)}</kbd><span>${esc(t)}</span>`).join('')}</div>
          </div>
        </div>
        <div><a class="link small" href="#/">Back to your cases</a></div>
      </div>`;
    },
  });
})();
