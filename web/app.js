/* Insights Buddy shell: the IB global, the hash router, api(), the side menu and top bar,
   and the shared components every page uses. The contract is docs/frontend-interfaces.md. */
(() => {
  'use strict';
  const IB = (window.IB = window.IB || {});
  const D = document;

  /* ------------------------------------------------------------------ basics */

  const $ = (sel, root) => (root || D).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || D).querySelectorAll(sel));
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (v) => (v === null || v === undefined ? '' : String(v).replace(/[&<>"']/g, (c) => ESC[c]));
  const icon = (name, size = 18) => (IB.icon ? IB.icon(name, size) : '');

  /* Keeps only <mark>, <b>, <i> and <br> from server HTML such as snippet_html. */
  function safe(html) {
    if (html === null || html === undefined) return '';
    const s = esc(html);
    return s
      .replace(/&lt;(\/?)(mark|b|i)&gt;/gi, '<$1$2>')
      .replace(/&lt;br\s*\/?&gt;/gi, '<br>');
  }

  function el(html) {
    const t = D.createElement('template');
    t.innerHTML = String(html).trim();
    return t.content.firstElementChild;
  }

  function css(id, text) {
    if (D.getElementById(id)) return;
    const s = D.createElement('style');
    s.id = id;
    s.textContent = text;
    D.head.appendChild(s);
  }

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } },
    sget(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    sset(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* ignore */ } },
  };

  const state = {
    cid: null, case: null, stats: null, phones: [], me: null,
    theme: D.documentElement.getAttribute('data-theme') || 'light',
    textsize: D.documentElement.getAttribute('data-textsize') === 'large' ? 'large' : 'normal',
    health: null, limit: {}, jobs: [], flagged: new Set(),
  };

  /* ------------------------------------------------------------------ events and actions */

  const listeners = {};
  function on(event, fn) { (listeners[event] = listeners[event] || []).push(fn); return () => off(event, fn); }
  function off(event, fn) { listeners[event] = (listeners[event] || []).filter((f) => f !== fn); }
  function emit(event, data) {
    (listeners[event] || []).slice().forEach((fn) => {
      try { fn(data); } catch (e) { console.error('IB event ' + event, e); }
    });
  }

  const actions = {};
  function action(name, fn) { actions[name] = fn; }
  function run(name, ...args) {
    const fn = actions[name];
    if (!fn) { status('That part is still being built.'); return undefined; }
    return fn(...args);
  }

  /* ------------------------------------------------------------------ formatting (India time) */

  const TZ = 'Asia/Kolkata';
  const nf = new Intl.NumberFormat('en-IN');
  function toDate(ts) {
    if (ts === null || ts === undefined || ts === '') return null;
    if (ts instanceof Date) return ts;
    if (typeof ts === 'number' || /^\d+$/.test(String(ts))) {
      let n = Number(ts);
      if (n < 1e11) n *= 1000; /* seconds */
      return new Date(n);
    }
    const d = new Date(ts);
    return isNaN(d) ? null : d;
  }
  function parts(ts, opts) {
    const d = toDate(ts);
    if (!d) return null;
    const o = {};
    new Intl.DateTimeFormat('en-GB', Object.assign({ timeZone: TZ }, opts)).formatToParts(d)
      .forEach((p) => { o[p.type] = p.value; });
    return o;
  }
  const thisYear = () => parts(Date.now(), { year: 'numeric' }).year;
  function clock(ts) {
    const p = parts(ts, { hour: 'numeric', minute: '2-digit', hour12: true });
    if (!p) return '';
    return `${Number(p.hour)}:${p.minute} ${String(p.dayPeriod || '').toLowerCase().replace(/\./g, '')}`;
  }
  function date(ts) {
    const p = parts(ts, { day: 'numeric', month: 'short', year: 'numeric' });
    return p ? `${Number(p.day)} ${p.month.replace('Sept', 'Sep')} ${p.year}` : '';
  }
  function time(ts) {
    const p = parts(ts, { day: 'numeric', month: 'short', year: 'numeric' });
    if (!p) return '';
    const y = p.year === thisYear() ? '' : ' ' + p.year;
    return `${Number(p.day)} ${p.month.replace('Sept', 'Sep')}${y}, ${clock(ts)}`;
  }
  function day(ts) {
    const p = parts(ts, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    return p ? `${p.weekday}, ${Number(p.day)} ${p.month} ${p.year}` : '';
  }
  function dayKey(ts) {
    const p = parts(ts, { year: 'numeric', month: '2-digit', day: '2-digit' });
    return p ? `${p.year}-${p.month}-${p.day}` : '';
  }
  function num(n) { return n === null || n === undefined || n === '' || isNaN(n) ? '' : nf.format(Number(n)); }
  function money(n) {
    if (n === null || n === undefined || n === '' || isNaN(n)) return '';
    const v = Number(n);
    const f = new Intl.NumberFormat('en-IN', { maximumFractionDigits: Number.isInteger(v) ? 0 : 2 });
    return (v < 0 ? '-₹' : '₹') + f.format(Math.abs(v));
  }
  function lakh(n) {
    if (n === null || n === undefined || n === '' || isNaN(n)) return '';
    const v = Math.abs(Number(n));
    const sign = Number(n) < 0 ? '-' : '';
    const one = (x) => String(Math.round(x * 10) / 10);
    if (v >= 1e7) return `${sign}₹${one(v / 1e7)} crore`;
    if (v >= 1e5) return `${sign}₹${one(v / 1e5)} lakh`;
    return money(n);
  }
  function duration(s) {
    s = Math.round(Number(s) || 0);
    if (s < 60) return `${s} s`;
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    if (h) return m ? `${h} h ${m} min` : `${h} h`;
    return r ? `${m} min ${r} s` : `${m} min`;
  }
  function size(b) {
    b = Number(b) || 0;
    if (b < 1024) return `${b} bytes`;
    const u = ['KB', 'MB', 'GB', 'TB'];
    let i = -1;
    do { b /= 1024; i++; } while (b >= 1024 && i < u.length - 1);
    return `${b >= 10 ? Math.round(b) : Math.round(b * 10) / 10} ${u[i]}`;
  }
  const fmt = { num, money, lakh, time, date, clock, day, dayKey, duration, size };
  function plural(n, one, many) {
    const v = Number(n) || 0;
    return `${num(v)} ${v === 1 ? one : (many || one + 's')}`;
  }

  /* ------------------------------------------------------------------ api */

  function apiUrl(path, query) {
    let p = String(path || '');
    if (!/^\/api(\/|$)/.test(p)) p = '/api' + (p.startsWith('/') ? '' : '/') + p;
    if (query) {
      const q = new URLSearchParams();
      Object.keys(query).forEach((k) => {
        const v = query[k];
        if (v === null || v === undefined || v === '' || v === false) return;
        if (Array.isArray(v)) { if (v.length) q.set(k, v.join(',')); return; }
        q.set(k, v === true ? '1' : String(v));
      });
      const s = q.toString();
      if (s) p += (p.includes('?') ? '&' : '?') + s;
    }
    return p;
  }

  let loadingCount = 0;
  function loadline(delta) {
    loadingCount = Math.max(0, loadingCount + delta);
    const l = $('#loadline');
    if (l) l.hidden = loadingCount === 0;
  }

  async function api(path, opts) {
    opts = opts || {};
    const init = { method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'), headers: {}, credentials: 'same-origin' };
    if (opts.body !== undefined) {
      if (opts.body instanceof FormData || opts.body instanceof Blob) init.body = opts.body;
      else { init.body = JSON.stringify(opts.body); init.headers['Content-Type'] = 'application/json'; }
    }
    let res;
    loadline(1);
    try {
      res = await fetch(apiUrl(path, opts.query), init);
    } catch (e) {
      const err = new Error('Insights Buddy is not answering. Check that it is still running on this computer, then try again.');
      err.status = 0;
      throw err;
    } finally {
      loadline(-1);
    }
    let data = null;
    const text = await res.text();
    if (text) { try { data = JSON.parse(text); } catch (e) { data = text; } }
    if (!res.ok) {
      const msg = (data && typeof data === 'object' && (data.error || (typeof data.detail === 'string' && data.detail)))
        || (res.status === 404 ? 'That was not found.' : res.status === 401 ? 'Please log in again.' : 'Something went wrong. Try again.');
      const err = new Error(msg);
      err.status = res.status;
      err.data = data;
      if (res.status === 401 && !opts.noLogin) needLogin();
      throw err;
    }
    return data;
  }
  function capi(path, opts) {
    if (!state.cid) return Promise.reject(Object.assign(new Error('Open a case first.'), { status: 0 }));
    return api('/cases/' + encodeURIComponent(state.cid) + (String(path).startsWith('/') ? '' : '/') + path, opts);
  }

  const latestSeq = {};
  function latest(name) {
    const n = (latestSeq[name] = (latestSeq[name] || 0) + 1);
    return () => latestSeq[name] === n;
  }

  /* ------------------------------------------------------------------ status line and copy */

  let statTimer = null;
  function status(text, opts) {
    const err = opts && opts.error;
    const line = $(err ? '#alertline' : '#statline');
    const other = $(err ? '#statline' : '#alertline');
    if (other) { other.textContent = ''; other.classList.remove('on'); }
    if (!line) return;
    line.textContent = text;
    line.classList.add('on');
    clearTimeout(statTimer);
    statTimer = setTimeout(() => { line.textContent = ''; line.classList.remove('on'); }, 3000);
  }
  async function copy(text) {
    text = String(text === null || text === undefined ? '' : text);
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const t = D.createElement('textarea');
      t.value = text; t.setAttribute('readonly', ''); t.style.position = 'fixed'; t.style.opacity = '0';
      D.body.appendChild(t); t.select();
      try { D.execCommand('copy'); } catch (e2) { /* ignore */ }
      t.remove();
    }
    status('Copied');
  }

  /* ------------------------------------------------------------------ registries */

  const pages = {};
  function page(tab, def) { pages[tab] = def || {}; }
  const dashTabs = {};
  function dashboardTab(key, def) { dashTabs[key] = Object.assign({ key, order: 100 }, def || {}); }
  function dashboardTabs(ctx) {
    return Object.values(dashTabs)
      .filter((t) => { try { return !t.show || t.show(ctx || current.ctx || {}) !== false; } catch (e) { return false; } })
      .sort((a, b) => (a.order || 0) - (b.order || 0));
  }

  /* ------------------------------------------------------------------ the menu */

  const NAV = [
    { tab: 'dashboard', label: 'Dashboard', icon: 'grid', tip: 'The whole case at a glance' },
    { tab: 'ask', label: 'Ask a question', icon: 'spark', tip: 'Ask in your own words, and get an answer with the records behind it' },
    { tab: 'search', label: 'Search', icon: 'search', tip: 'Find any word, name or number in every record' },
    { tab: 'chats', label: 'Chats', icon: 'chat', tip: 'Every chat, in every app' },
    { tab: 'calls', label: 'Calls', icon: 'phone', tip: 'The call log: incoming, outgoing and missed', when: 'calls' },
    { tab: 'media', label: 'Photos & files', icon: 'image', tip: 'Photos, videos, voice notes and documents' },
    { tab: 'timeline', label: 'Timeline', icon: 'clock', tip: 'Everything in order of time' },
    { tab: 'places', label: 'Places', icon: 'pin', tip: 'Where the phone was, on a map', when: 'places' },
    { tab: 'people', label: 'People', icon: 'users', tip: 'Everyone the phone was in touch with' },
    { tab: 'findings', label: 'Findings', icon: 'flag', tip: "What you've saved from this case, with your notes" },
  ];
  const MORE = [
    { tab: 'faces', label: 'Faces', icon: 'face', tip: 'Faces found in photos, grouped by person' },
    { tab: 'board', label: 'Link board', icon: 'link', tip: 'Your own map of who and what connects' },
    { tab: 'codes', label: 'Code words', icon: 'key', tip: 'Words that may mean something else in these chats' },
    { tab: 'sources', label: 'Evidence added', icon: 'database', tip: 'The phones and files added to this case, and how they were read' },
    { tab: 'audit', label: 'Audit', icon: 'shield', tip: 'Who did what in this case, and when' },
    { tab: 'phone', label: 'Phone details', icon: 'smartphone', tip: 'The phone itself, its apps, accounts, Wi-Fi and SIMs' },
    { action: 'limit', label: 'Warrant limit', icon: 'lock', tip: 'Limit what this case shows to what the warrant allows' },
  ];
  const NAMES = { cases: 'All cases', about: 'About and credits', login: 'Log in', person: 'Person', record: 'Record' };
  NAV.concat(MORE).forEach((n) => { if (n.tab) NAMES[n.tab] = n.label; });

  function hasNav(item) {
    const s = state.stats;
    if (!item.when) return true;
    if (!s) return false;
    if (item.when === 'calls') return Number(s.calls) > 0;
    if (item.when === 'places') {
      return (s.by_app || []).some((a) => /locat|place/i.test(String(a.kind || '')) && Number(a.n || 1) > 0)
        || Number(s.locations || s.places || 0) > 0;
    }
    return true;
  }

  function navItem(item, activeTab) {
    const on = item.tab && item.tab === activeTab;
    const attrs = item.action
      ? `href="#" data-action="${esc(item.action)}" role="button"`
      : `href="${esc(link(item.tab === 'dashboard' ? '' : item.tab))}"`;
    return `<a class="side-item${on ? ' on' : ''}" ${attrs} data-tip="${esc(item.tip)}"${on ? ' aria-current="page"' : ''}>`
      + `${icon(item.icon, 18)}<span>${esc(item.label)}</span></a>`;
  }

  function drawSide() {
    const sc = $('#side-case'), nav = $('#side-nav');
    if (!sc || !nav) return;
    const tab = current.ctx ? (current.ctx.tab === 'record' ? 'timeline' : current.ctx.tab) : '';
    if (!state.cid) {
      sc.innerHTML = `<a class="side-all${tab === 'cases' ? ' on' : ''}" href="#/">${icon('case', 16)}<span>All cases</span></a>`;
      nav.innerHTML = '';
      return;
    }
    const name = (state.case && state.case.name) || 'This case';
    sc.innerHTML = `<a class="side-case-name name clamp-2" href="${esc(link(''))}" data-tip="Open this case's Dashboard">${esc(name)}</a>`
      + `<a class="side-all small" href="#/">${icon('arrow-left', 14)}<span>All cases</span></a>`;
    const activeTab = tab === 'person' ? 'people' : tab;
    const moreOn = MORE.some((m) => m.tab === activeTab);
    const keepOpen = moreOn || store.sget('ib.more') === '1';
    nav.innerHTML = `<div class="side-label caps tiny">This case</div>`
      + NAV.filter(hasNav).map((n) => navItem(n, activeTab)).join('')
      + `<details class="side-more"${keepOpen ? ' open' : ''}><summary class="side-item">${icon('more', 18)}<span>More</span>${icon('chevron-down', 14)}</summary>`
      + MORE.map((n) => navItem(n, activeTab)).join('') + `</details>`;
    const det = $('.side-more', nav);
    if (det) det.addEventListener('toggle', () => store.sset('ib.more', det.open ? '1' : '0'));
  }

  function drawJobs() {
    const box = $('#side-jobs');
    if (!box) return;
    const running = (state.jobs || []).filter(isRunning);
    box.innerHTML = running.map((j) => progress(j)).join('');
  }

  function drawLimit() {
    const bar = $('#limitbar');
    if (!bar) return;
    const l = state.limit || {};
    const onNow = state.cid && l && Object.keys(l).length > 0;
    bar.hidden = !onNow;
    if (!onNow) { bar.innerHTML = ''; return; }
    const text = l.banner || limitWords(l);
    bar.innerHTML = `${icon('lock', 16)}<span class="grow">Warrant limit on: ${esc(text)}. Only these records are shown.</span>`
      + `<button type="button" class="btn small" data-action="limit">Change</button>`;
  }
  function limitWords(l) {
    const bits = [];
    if (l.people && l.people.length) bits.push(l.people.map((p) => p.name || p).join(', '));
    if (l.from_day || l.from) bits.push('from ' + (l.from_day ? date(l.from_day) : date(l.from)));
    if (l.to_day || l.to) bits.push('to ' + (l.to_day ? date(l.to_day) : date(l.to)));
    if (l.apps && l.apps.length) bits.push(l.apps.map(appName).join(', '));
    return bits.join(', ') || 'some records only';
  }

  function drawTop(ctx, def) {
    const bare = !!(def && def.bare);
    const side = $('#side'), top = $('#top');
    D.body.classList.toggle('is-bare', bare);
    if (side) side.hidden = bare;
    if (top) top.hidden = bare;
    const back = $('#back');
    if (back) {
      const st = history.state || {};
      back.hidden = bare || !(st.ibd > 0);
      back.innerHTML = `${icon('arrow-left', 16)}<span>Back</span>`;
    }
    const qf = $('#qf');
    if (qf) qf.hidden = bare || !state.cid;
    const nb = $('#notes-btn');
    if (nb) {
      nb.hidden = bare || !state.cid;
      nb.innerHTML = `${icon('flag', 16)}<span>Show findings</span>`;
    }
    const exp = $('#export-btn');
    if (exp) { exp.hidden = true; exp.innerHTML = `${icon('download', 16)}<span>Export</span>`; }
    current.exportable = null;
    closeMenus();
    const me = $('#me');
    if (me) {
      me.hidden = bare || !state.me;
      const mb = $('#me-btn');
      if (mb && state.me) {
        mb.textContent = state.me.initials || initials(state.me.name);
        mb.setAttribute('aria-label', `${state.me.name || 'Officer'}: menu`);
        mb.setAttribute('data-tip', state.me.name || '');
      }
    }
    drawSide();
    drawLimit();
    drawJobs();
    const bar = $('#pagebar');
    if (bar) { bar.hidden = true; bar.innerHTML = ''; }
  }
  function initials(name) {
    return String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
  }

  function setTitle(text) {
    const t = $('#top-title');
    if (t) t.textContent = text || 'Insights Buddy';
    D.title = text && text !== 'Insights Buddy' ? `${text} · Insights Buddy` : 'Insights Buddy';
  }

  /* ------------------------------------------------------------------ the case */

  function asList(x, key) {
    if (Array.isArray(x)) return x;
    if (x && Array.isArray(x[key])) return x[key];
    if (x && Array.isArray(x.rows)) return x.rows;
    if (x && Array.isArray(x.items)) return x.items;
    return [];
  }

  let caseLoading = null;
  async function loadCase(cid) {
    const mine = latest('case');
    const [cases, stats, phones, limit, findings] = await Promise.all([
      api('/cases').catch(() => null),
      api(`/cases/${encodeURIComponent(cid)}/stats`).catch(() => null),
      api(`/cases/${encodeURIComponent(cid)}/sources`).catch(() => null),
      api(`/cases/${encodeURIComponent(cid)}/limit`).catch(() => null),
      api(`/cases/${encodeURIComponent(cid)}/findings`).catch(() => null),
    ]);
    if (!mine() || state.cid !== cid) return;
    const c = asList(cases, 'cases').find((x) => String(x.case_id) === String(cid));
    state.case = c || state.case || { case_id: cid, name: 'This case' };
    if (stats) state.stats = stats;
    if (phones) state.phones = asList(phones, 'sources');
    state.limit = limit || {};
    if (findings) state.flagged = new Set(asList(findings, 'findings').map((f) => f.event_id).filter(Boolean));
    drawSide();
    drawLimit();
    emit('case', { case: state.case, stats: state.stats, phones: state.phones });
  }
  function refreshCase() {
    if (!state.cid) return Promise.resolve();
    caseLoading = loadCase(state.cid);
    return caseLoading;
  }
  async function refreshLimit() {
    if (!state.cid) return;
    const cid = state.cid;
    try {
      const l = await api(`/cases/${encodeURIComponent(cid)}/limit`);
      if (state.cid !== cid) return;
      state.limit = l || {};
    } catch (e) { return; }
    drawLimit();
    emit('limit', state.limit);
  }

  /* ------------------------------------------------------------------ jobs */

  const isRunning = (j) => !!j && (j.status ? /^(waiting|running|queued)$/i.test(String(j.status)) : Number(j.progress || 0) < 1);
  let jobTimer = null;
  let lastRunning = new Set();
  async function refreshJobs() {
    clearTimeout(jobTimer);
    if (!state.cid || !state.me) { state.jobs = []; drawJobs(); return; }
    const cid = state.cid;
    let jobs = [];
    try { jobs = asList(await api(`/cases/${encodeURIComponent(cid)}/jobs`, { noLogin: true }), 'jobs'); } catch (e) { jobs = []; }
    if (state.cid !== cid) return;
    state.jobs = jobs;
    const running = jobs.filter(isRunning);
    const nowIds = new Set(running.map((j) => String(j.id)));
    const finished = [...lastRunning].filter((id) => !nowIds.has(id));
    lastRunning = nowIds;
    drawJobs();
    emit('jobs', running);
    if (finished.length) {
      finished.forEach((id) => {
        const j = jobs.find((x) => String(x.id) === id) || { id };
        emit('jobs:done', j);
      });
      refreshCase();
    }
    if (running.length) jobTimer = setTimeout(refreshJobs, 10000);
  }

  /* ------------------------------------------------------------------ the router */

  const current = { ctx: null, key: null, def: null };
  let seq = 0;
  let keyCounter = Number(store.sget('ib.key') || 0);
  const memory = new Map(); /* history key -> {scroll, keep}; the last 10 */

  function remember(key, data) {
    if (key === null || key === undefined) return;
    memory.delete(key);
    memory.set(key, data);
    while (memory.size > 10) memory.delete(memory.keys().next().value);
  }
  function scrollPos() {
    const v = $('#view');
    return { y: window.scrollY || D.documentElement.scrollTop || 0, v: v ? v.scrollTop : 0 };
  }
  function saveCurrent() {
    if (!current.ctx || current.key === null) return;
    remember(current.key, { scroll: scrollPos(), keep: current.ctx.keep });
  }
  function newKey() { keyCounter += 1; store.sset('ib.key', String(keyCounter)); return keyCounter; }

  function parseHash(hash) {
    let h = String(hash || '').replace(/^#/, '');
    let qs = '';
    const qi = h.indexOf('?');
    if (qi >= 0) { qs = h.slice(qi + 1); h = h.slice(0, qi); }
    const query = {};
    new URLSearchParams(qs).forEach((v, k) => { query[k] = v; });
    const segs = h.split('/').filter(Boolean).map((s) => { try { return decodeURIComponent(s); } catch (e) { return s; } });
    const r = { tab: 'cases', cid: null, params: {}, query };
    if (!segs.length) return r;
    if (segs[0] === 'login') { r.tab = 'login'; return r; }
    if (segs[0] === 'about') { r.tab = 'about'; return r; }
    if (segs[0] === 'c' && segs[1]) {
      r.cid = segs[1];
      const t = segs[2] || 'dashboard';
      if (t === 'person' && segs[3]) { r.tab = 'person'; r.params.pid = segs[3]; return r; }
      if (t === 'record' && segs[3]) { r.tab = 'timeline'; r.params.eid = segs[3]; r.record = true; return r; }
      r.tab = t;
      if (segs[3]) r.params.id = segs[3];
      return r;
    }
    r.tab = 'missing';
    return r;
  }

  function queryString(q) {
    const u = new URLSearchParams();
    Object.keys(q || {}).forEach((k) => {
      const v = q[k];
      if (v === null || v === undefined || v === '' || v === false) return;
      if (Array.isArray(v)) { if (v.length) u.set(k, v.join(',')); return; }
      u.set(k, v === true ? '1' : String(v));
    });
    const s = u.toString();
    return s ? '?' + s : '';
  }

  function link(path, query, cid) {
    const c = cid || state.cid;
    let p = String(path || '').replace(/^\/+/, '');
    if (p === 'dashboard') p = '';
    const base = c ? `#/c/${encodeURIComponent(c)}${p ? '/' + p : ''}` : `#/${p}`;
    return base + queryString(query);
  }

  function go(hash) {
    if (!hash) return;
    let h = String(hash);
    if (!h.startsWith('#')) h = '#' + (h.startsWith('/') ? '' : '/') + h;
    if (h === location.hash) { reload(); return; }
    location.hash = h;
  }

  function reload() { route({ again: true }); }

  function needLogin() {
    const h = location.hash || '#/';
    if (!/^#\/login/.test(h)) store.sset('ib.return', h);
    state.me = null;
    if (!/^#\/login/.test(h)) location.hash = '#/login';
    else route({ again: true });
  }

  async function route(opts) {
    opts = opts || {};
    saveCurrent();
    const my = ++seq;
    const r = parseHash(location.hash);

    /* history bookkeeping: each entry gets a key, and a depth for the Back button */
    let st = history.state && typeof history.state === 'object' ? history.state : null;
    let back = false;
    if (st && st.ibk !== undefined) {
      back = !opts.again && memory.has(st.ibk) && st.ibk !== current.key;
    } else {
      const prevDepth = current.ctx ? ((current.depth || 0) + 1) : 0;
      st = Object.assign({}, st || {}, { ibk: newKey(), ibd: prevDepth });
      try { history.replaceState(st, '', location.href); } catch (e) { /* ignore */ }
    }
    const key = st.ibk;
    const saved = memory.get(key);

    /* who is logged in */
    if (r.tab !== 'login' && !state.me) {
      try {
        state.me = await api('/me', { noLogin: true });
      } catch (e) {
        if (my !== seq) return;
        if (e.status === 401) { needLogin(); return; }
        showFatal(e);
        return;
      }
      if (my !== seq) return;
      loadPrefs();
    }

    /* the case */
    if (r.cid !== state.cid) {
      clearTimeout(jobTimer);
      lastRunning = new Set();
      state.cid = r.cid;
      state.case = null; state.stats = null; state.phones = []; state.limit = {}; state.jobs = []; state.flagged = new Set();
      if (r.cid) { refreshCase(); refreshJobs(); }
    }
    /* Pages read IB.state.phones and stats (tabs, chips, marks): wait for the case once, at most 5 s. */
    if (r.cid && caseLoading && !state.stats) {
      loadline(1);
      try { await Promise.race([caseLoading.catch(() => {}), new Promise((ok) => setTimeout(ok, 5000))]); } finally { loadline(-1); }
      if (my !== seq) return;
    }

    closeDrawer(true);
    closePop();
    hideTip();

    const def = pages[r.tab];
    const ctx = {
      tab: r.tab, cid: r.cid, params: r.params, query: Object.assign({}, r.query),
      keep: saved && saved.keep ? saved.keep : {},
      back: !!back,
      alive: () => my === seq,
    };
    ctx.api = (path, o) => guard(ctx, api(path, o));
    ctx.capi = (path, o) => guard(ctx, capi(path, o));
    ctx.setQuery = (obj, o) => setQuery(ctx, obj, o);
    ctx.bar = (html) => {
      const b = $('#pagebar');
      if (!b || !ctx.alive()) return b;
      b.innerHTML = html || '';
      b.hidden = !html;
      return b;
    };
    ctx.title = (text) => { if (ctx.alive()) setTitle(text); };
    ctx.exportable = (pageName, query) => { if (ctx.alive()) exportable(pageName, query); };
    let restored = false;
    ctx.restoreScroll = () => {
      if (restored || !ctx.alive()) return;
      restored = true;
      if (back && saved && saved.scroll) {
        const s = saved.scroll;
        const put = () => {
          if (!ctx.alive()) return;
          window.scrollTo(0, s.y);
          const v = $('#view'); if (v) v.scrollTop = s.v;
        };
        put();
        requestAnimationFrame(put);
        setTimeout(put, 60);
      }
    };

    current.ctx = ctx; current.key = key; current.def = def; current.depth = st.ibd || 0;
    drawTop(ctx, def);

    let title = NAMES[r.tab] || 'Insights Buddy';
    if (def && def.title) {
      try { title = typeof def.title === 'function' ? def.title(ctx) : def.title; } catch (e) { /* keep the default */ }
    }
    setTitle(title);

    const view = $('#view');
    if (!view) return;
    if (!back) { window.scrollTo(0, 0); view.scrollTop = 0; }
    view.innerHTML = '';
    emit('route', ctx);

    if (r.tab === 'missing') {
      view.innerHTML = `<div class="page">${empty("This page doesn't exist.", { icon: 'info', action: { label: 'Go to all cases', href: '#/' } })}</div>`;
      ctx.restoreScroll();
      return;
    }
    if (!def || typeof def.render !== 'function') {
      view.innerHTML = notBuilt(NAMES[r.tab] || r.tab);
      ctx.restoreScroll();
      if (r.record) openRecord(r.params.eid);
      return;
    }
    let out;
    loadline(1);
    try {
      out = def.render(view, ctx);
      if (out && typeof out.then === 'function') await out;
    } catch (e) {
      console.error(e);
      if (ctx.alive()) {
        view.innerHTML = '<div class="page"></div>';
        fail(view.firstElementChild, e, () => reload());
      }
    } finally {
      loadline(-1);
    }
    if (!ctx.alive()) return;
    ctx.restoreScroll();
    if (r.record && r.params.eid) openRecord(r.params.eid);
  }

  function guard(ctx, p) {
    return new Promise((resolve, reject) => {
      p.then((v) => { if (ctx.alive()) resolve(v); }, (e) => { if (ctx.alive()) reject(e); });
    });
  }

  function setQuery(ctx, obj, o) {
    if (!ctx.alive()) return;
    const q = Object.assign({}, ctx.query, obj || {});
    Object.keys(q).forEach((k) => { const v = q[k]; if (v === null || v === undefined || v === '' || v === false || (Array.isArray(v) && !v.length)) delete q[k]; });
    ctx.query = q;
    const hash = location.hash.replace(/\?.*$/, '') + queryString(q);
    const url = location.pathname + location.search + hash;
    if (o && o.push) {
      saveCurrent();
      const key = newKey();
      const depth = (current.depth || 0) + 1;
      ctx.keep = Object.assign({}, ctx.keep);
      history.pushState({ ibk: key, ibd: depth }, '', url);
      current.key = key; current.depth = depth;
      const b = $('#back'); if (b) b.hidden = false;
    } else {
      const st = Object.assign({}, history.state || {}, { ibk: current.key, ibd: current.depth || 0 });
      history.replaceState(st, '', url);
    }
  }

  function showFatal(e) {
    const view = $('#view');
    if (!view) return;
    drawTop({ tab: 'cases' }, { bare: true });
    view.innerHTML = '<div class="page"></div>';
    fail(view.firstElementChild, e, () => reload());
  }

  /* ------------------------------------------------------------------ login, prefs, theme, text size */

  async function loadPrefs() {
    try {
      const p = await api('/prefs', { noLogin: true });
      if (p && (p.theme === 'light' || p.theme === 'dark')) applyTheme(p.theme, false);
      if (p && (p.textsize === 'normal' || p.textsize === 'large')) applySize(p.textsize, false);
    } catch (e) { /* keep what this browser remembers */ }
  }
  function savePrefs() {
    if (!state.me) return;
    api('/prefs', { method: 'POST', body: { theme: state.theme, textsize: state.textsize }, noLogin: true }).catch(() => {});
  }
  function applyTheme(t, save) {
    if (t !== 'light' && t !== 'dark') return;
    const changed = t !== state.theme;
    state.theme = t;
    D.documentElement.setAttribute('data-theme', t);
    store.set('ib.theme', t);
    $$('[data-theme-set]').forEach((b) => b.setAttribute('aria-pressed', String(b.getAttribute('data-theme-set') === t)));
    if (save !== false) savePrefs();
    if (changed) emit('theme', t);
  }
  function applySize(s, save) {
    if (s !== 'normal' && s !== 'large') return;
    state.textsize = s;
    if (s === 'large') D.documentElement.setAttribute('data-textsize', 'large');
    else D.documentElement.removeAttribute('data-textsize');
    store.set('ib.textsize', s);
    $$('[data-size-set]').forEach((b) => b.setAttribute('aria-pressed', String(b.getAttribute('data-size-set') === s)));
    if (save !== false) savePrefs();
  }

  async function loggedIn(me) {
    if (me && me.name) state.me = me;
    else { try { state.me = await api('/me', { noLogin: true }); } catch (e) { state.me = null; } }
    await loadPrefs();
    const back = store.sget('ib.return');
    store.sset('ib.return', '');
    go(back && !/^#\/login/.test(back) ? back : '#/');
  }
  async function logout() {
    try { await api('/auth/logout', { method: 'POST', noLogin: true }); } catch (e) { /* already out */ }
    state.me = null; state.cid = null; state.case = null; state.stats = null; state.phones = []; state.limit = {};
    store.sset('ib.return', '');
    go('#/login');
  }

  async function loadHealth() {
    try {
      state.health = await api('/health', { noLogin: true });
    } catch (e) { return; }
    const b = $('#badge');
    const ai = (state.health && state.health.ai) || {};
    if (b && ai.configured && ai.local === false) {
      const host = ai.host || ai.where || 'another computer';
      b.textContent = 'On this PC, AI elsewhere';
      b.setAttribute('data-tip', `Everything stays on this computer, except questions to the AI, which go to ${host}`);
      b.classList.add('ai-away');
    }
  }

  /* ------------------------------------------------------------------ chips and small parts */

  const TONES = ['blue', 'green', 'orange', 'violet', 'teal'];
  function phoneInfo(p) {
    const phones = state.phones || [];
    let src = null, label = '', n = 0, phoneNo = '';
    if (p && typeof p === 'object') {
      phoneNo = p.phone_no || '';
      label = p.label || p.phone_label || '';
      src = phones.find((x) => (p.source_id && x.source_id === p.source_id) || (phoneNo && x.phone_no === phoneNo)) || null;
    } else if (p !== null && p !== undefined) {
      const s = String(p);
      src = phones.find((x) => String(x.source_id) === s || x.phone_no === s || x.label === s
        || (x.phone_label && x.phone_label === s)) || null;
      if (!src) label = s;
    }
    if (src) {
      label = label || src.phone_label || src.label || src.device || '';
      phoneNo = phoneNo || src.phone_no || '';
      n = Number(src.number || src.n || src.index) || (phones.indexOf(src) + 1);
      const m = String(src.source_id || '').match(/(\d+)/);
      if (!src.number && m) n = Number(m[1]);
    }
    const m2 = String(label).match(/^\s*Phone\s+(\d+)\s*\|\s*(.*)$/i);
    let name = label;
    if (m2) { n = n || Number(m2[1]); name = m2[2]; }
    if (!n && p && typeof p !== 'object') { const m3 = String(p).match(/^P(\d+)/i); if (m3) n = Number(m3[1]); }
    if (src && name === label && /^Phone\s+\d+$/i.test(String(name))) name = src.device || src.owner || '';
    return { n, name: name || phoneNo, phoneNo };
  }
  function phoneChip(p) {
    if (p === null || p === undefined || p === '') return '';
    const i = phoneInfo(p);
    const tone = i.n ? ` p${((i.n - 1) % 3) + 1}` : '';
    const lead = i.n ? `Phone ${i.n}` : 'Phone';
    const tail = i.name && i.name !== lead ? `<span class="chip-l">${esc(i.name)}</span>` : '';
    return `<span class="chip phone${tone}"${i.phoneNo ? ` data-tip="${esc(i.phoneNo)}"` : ''}><span class="chip-n">${esc(lead)}</span>${tail}</span>`;
  }
  function phoneChips(list) { return (list || []).map(phoneChip).join(' '); }

  function statusChip(s) {
    const k = String(s || '').toLowerCase();
    if (!k || k === 'normal' || k === 'ok' || k === 'live' || k === 'intact') return '';
    if (k === 'deleted' || k === 'recovered') return `<span class="chip status critical">Deleted, recovered</span>`;
    const words = { unsent: 'Unsent', edited: 'Edited', missed: 'Missed', rejected: 'Rejected', unread: 'Unread' };
    return `<span class="chip status serious">${esc(words[k] || (k[0].toUpperCase() + k.slice(1)))}</span>`;
  }

  const APPS = {
    whatsapp: 'WhatsApp', sms: 'Messages', telegram: 'Telegram', signal: 'Signal', imessage: 'iMessage',
    phone: 'Phone', calls: 'Phone', call: 'Phone', gallery: 'Photos', photos: 'Photos', camera: 'Camera', upi: 'UPI',
    gpay: 'Google Pay', phonepe: 'PhonePe', paytm: 'Paytm', maps: 'Maps', location: 'Locations', contacts: 'Contacts',
    files: 'Files', notes: 'Notes', instagram: 'Instagram', email: 'Email', mail: 'Mail', browser: 'Browser',
  };
  function appName(a) {
    const k = String(a || '').toLowerCase();
    if (APPS[k]) return APPS[k];
    return k ? k.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '';
  }
  function appIcon(a) {
    const k = String(a || '').toLowerCase();
    if (IB.ICONS && IB.ICONS['app-' + k]) return 'app-' + k;
    const m = { phone: 'phone', calls: 'phone', call: 'phone', gallery: 'image', photos: 'image', camera: 'camera',
      upi: 'rupee', gpay: 'rupee', phonepe: 'rupee', paytm: 'rupee', maps: 'pin', location: 'pin', contacts: 'users',
      files: 'file', notes: 'notes', email: 'mail', mail: 'mail' };
    return m[k] || 'chat';
  }
  function appChip(app) {
    if (!app) return '';
    return `<span class="chip app">${icon(appIcon(app), 14)}<span>${esc(appName(app))}</span></span>`;
  }
  function pill(text, tone) { return `<span class="pill${tone ? ' tone-' + esc(tone) : ''}">${esc(text)}</span>`; }
  function cite(n, eid, tip) {
    return `<button type="button" class="cite" data-eid="${esc(eid)}"${tip ? ` data-tip="${esc(tip)}"` : ''} aria-label="Record ${esc(n)}${tip ? ': ' + esc(tip) : ''}">${esc(n)}</button>`;
  }
  function tile(name, tone) { return `<span class="tile${tone ? ' tone-' + esc(tone) : ''}">${icon(name, 18)}</span>`; }
  function logo(sz) { sz = sz || 28; return `<img class="logo" src="/static/brand/logo.svg" width="${sz}" height="${sz}" alt="">`; }

  function statTile(o) {
    o = o || {};
    const n = typeof o.n === 'number' ? num(o.n) : esc(o.n === undefined ? '' : o.n);
    const inner = `<span class="stat-n num">${n}</span><span class="stat-label">${esc(o.label)}</span>`
      + (o.sub ? `<span class="stat-sub small muted">${esc(o.sub)}</span>` : '');
    return o.href
      ? `<a class="stat card" href="${esc(o.href)}">${inner}</a>`
      : `<div class="stat card">${inner}</div>`;
  }

  const KIND_ICON = { message: 'chat', call: 'phone', photo: 'image', image: 'image', video: 'film', voice: 'mic', audio: 'mic',
    document: 'file', file: 'file', location: 'pin', contact: 'user', note: 'notes', payment: 'rupee', money: 'rupee',
    email: 'mail', calendar: 'calendar', wifi: 'wifi', sim: 'sim' };
  const kindIcon = (k) => KIND_ICON[String(k || '').toLowerCase()] || 'file';
  function recText(rec) {
    if (rec.snippet_html) return safe(rec.snippet_html);
    const t = rec.body || rec.transcript || rec.ocr_text || rec.media_name || rec.place || '';
    if (t) return esc(t);
    if (String(rec.kind) === 'call') return esc(callWords(rec));
    return '';
  }
  function callWords(rec) {
    const dir = String(rec.direction || '').toLowerCase();
    const w = dir === 'missed' || rec.status === 'missed' ? 'Missed call' : dir === 'in' || dir === 'incoming' ? 'Incoming call' : dir === 'out' || dir === 'outgoing' ? 'Outgoing call' : 'Call';
    return rec.duration_s ? `${w}, ${duration(rec.duration_s)}` : w;
  }
  function who(rec) {
    const from = rec.sender_name || rec.sender || '';
    const to = rec.recipient_names || rec.conv_title || '';
    const toText = Array.isArray(to) ? to.join(', ') : to;
    if (from && toText) return `${esc(from)} <span class="who-to" role="img" aria-label="to">${icon('arrow-right', 14)}</span> ${esc(toText)}`;
    return esc(from || toText);
  }
  function recordRow(rec, o) {
    rec = rec || {};
    o = o || {};
    const money_ = rec.amount ? `<span class="rec-amount num">${esc(money(rec.amount))}</span>` : '';
    const ph = o.phone === false ? '' : phoneChip(rec.phone_label || rec.source_id);
    return `<div class="rec" tabindex="0" role="button" data-eid="${esc(rec.event_id)}"${state.flagged.has(rec.event_id) ? ' data-flagged="1"' : ''}>`
      + `<span class="rec-time num muted small">${esc(time(rec.ts))}</span>`
      + `<span class="rec-kind" aria-hidden="true">${icon(kindIcon(rec.kind), 16)}</span>`
      + `<span class="rec-app">${appChip(rec.app)}</span>`
      + `<span class="rec-main grow"><span class="rec-who">${who(rec)}</span><span class="rec-text clamp-2">${recText(rec)}</span></span>`
      + `<span class="rec-tags">${money_}${statusChip(rec.status)}${state.flagged.has(rec.event_id) ? `<span class="flag-on" data-tip="Saved as a finding">${icon('flag-on', 14)}</span>` : ''}${ph}</span>`
      + `</div>`;
  }

  /* ------------------------------------------------------------------ states */

  function empty(text, o) {
    o = o || {};
    let act = '';
    if (o.action) {
      if (typeof o.action === 'string') act = o.action;
      else if (o.action.href) act = `<a class="btn${o.action.primary ? ' primary' : ''}" href="${esc(o.action.href)}">${esc(o.action.label)}</a>`;
      else if (o.action.ask) act = `<button type="button" class="btn" data-ask="${esc(o.action.ask)}">${esc(o.action.label)}</button>`;
      else if (o.action.action) act = `<button type="button" class="btn" data-action="${esc(o.action.action)}">${esc(o.action.label)}</button>`;
    }
    return `<div class="empty">${o.icon ? `<span class="empty-icon">${icon(o.icon, 28)}</span>` : ''}<p>${esc(text)}</p>${act ? `<div class="row">${act}</div>` : ''}</div>`;
  }
  function skeleton(kind, n) {
    n = n || (kind === 'cards' ? 4 : kind === 'page' ? 3 : 6);
    if (kind === 'cards') {
      return `<div class="cols cols-${Math.min(n, 4)}" aria-hidden="true">${'<div class="skel skel-card"></div>'.repeat(n)}</div>`;
    }
    if (kind === 'page') {
      return `<div class="page stack" aria-busy="true" aria-label="Loading"><div class="skel skel-title"></div>`
        + `<div class="cols cols-4">${'<div class="skel skel-card"></div>'.repeat(4)}</div>`
        + `${'<div class="skel skel-block"></div>'.repeat(Math.max(1, n - 1))}</div>`;
    }
    return `<div class="stack skel-rows" aria-busy="true" aria-label="Loading">${'<div class="skel skel-row"></div>'.repeat(n)}</div>`;
  }
  function fail(target, err, retry) {
    const msg = (err && err.message) || 'Something went wrong. Try again.';
    const html = `<div class="error-box" role="alert"><span class="error-icon">${icon('alert', 18)}</span><p class="grow">${esc(msg)}</p>`
      + (retry ? `<button type="button" class="btn small" data-retry>${icon('refresh', 14)}<span>Try again</span></button>` : '') + `</div>`;
    if (!target) return html;
    target.innerHTML = html;
    const b = $('[data-retry]', target);
    if (b && retry) b.addEventListener('click', () => retry());
    return html;
  }
  function notBuilt(name) {
    return `<div class="page"><div class="empty">${icon('settings', 28)}<p>This page is still being built.</p>`
      + `<p class="muted small">${esc(name || 'This page')} will appear here soon.</p></div></div>`;
  }
  function progress(job, lead) {
    job = job || {};
    let p = Number(job.progress) || 0;
    if (p <= 1) p *= 100;
    p = Math.max(0, Math.min(100, Math.round(p)));
    const main = job.label || job.step || 'Working';
    const sub = job.label && job.step && job.step !== job.label ? job.step : '';
    const s = Number(job.time_left_s);
    const left = job.time_left_s !== null && job.time_left_s !== undefined && s > 0
      ? ` · about ${s < 90 ? 'a minute' : Math.round(s / 60) + ' min'} left` : '';
    return `<div class="progress" role="status">`
      + `<div class="progress-text small">${lead ? `<b>${esc(lead)}</b> ` : ''}${esc(main)}… ${p}%${esc(left)}</div>`
      + (sub ? `<div class="progress-step tiny muted">${esc(sub)}</div>` : '')
      + `<div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${p}"><span style="width:${p}%"></span></div></div>`;
  }
  function updating(onNow) {
    return onNow === false ? '' : `<div class="updating small muted" role="status"><span class="spin" aria-hidden="true"></span>Updating these numbers…</div>`;
  }
  function busy(button, label) {
    if (!button) return () => {};
    const old = button.innerHTML;
    button.setAttribute('aria-busy', 'true');
    button.disabled = true;
    if (label) button.textContent = label;
    return () => {
      button.removeAttribute('aria-busy');
      button.disabled = false;
      button.innerHTML = old;
    };
  }

  /* ------------------------------------------------------------------ tabs */

  function tabs(target, o) {
    o = o || {};
    let active = o.active || (o.tabs && o.tabs[0] && o.tabs[0].key);
    const seg = o.look === 'seg';
    function draw() {
      target.innerHTML = `<div class="${seg ? 'seg' : 'tabs'}" role="tablist"${o.label ? ` aria-label="${esc(o.label)}"` : ''}>`
        + (o.tabs || []).map((t) => {
          const on = t.key === active;
          return `<button type="button" class="tab${on ? ' on' : ''}" role="tab" aria-selected="${on}" tabindex="${on ? 0 : -1}" data-key="${esc(t.key)}">`
            + `${esc(t.label)}${t.count !== undefined && t.count !== null ? ` <span class="tab-count num">${esc(num(t.count))}</span>` : ''}</button>`;
        }).join('') + `</div>`;
    }
    draw();
    function set(key, fire) {
      if (!(o.tabs || []).some((t) => t.key === key)) return;
      active = key;
      $$('[role=tab]', target).forEach((b) => {
        const on = b.getAttribute('data-key') === key;
        b.classList.toggle('on', on);
        b.setAttribute('aria-selected', String(on));
        b.tabIndex = on ? 0 : -1;
      });
      if (fire && o.onChange) o.onChange(key);
    }
    target.addEventListener('click', (e) => {
      const b = e.target.closest('[role=tab]');
      if (b && target.contains(b)) set(b.getAttribute('data-key'), true);
    });
    target.addEventListener('keydown', (e) => {
      const b = e.target.closest('[role=tab]');
      if (!b) return;
      const all = $$('[role=tab]', target);
      let i = all.indexOf(b);
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') i = (i + 1) % all.length;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') i = (i - 1 + all.length) % all.length;
      else if (e.key === 'Home') i = 0;
      else if (e.key === 'End') i = all.length - 1;
      else return;
      e.preventDefault();
      all[i].focus();
      set(all[i].getAttribute('data-key'), true);
    });
    return { set: (key) => set(key, false) };
  }

  /* ------------------------------------------------------------------ "Show 50 more" */

  function moreList(target, o) {
    o = o || {};
    const noun = o.noun || ['record', 'records'];
    let rows = [], total = 0, run_ = 0;
    const alive = o.alive || (() => true);
    target.innerHTML = `<div class="more-list stack"><div class="more-count small muted" role="status"></div><div class="more-body"></div>`
      + `<div class="more-foot row"><button type="button" class="btn more-btn" hidden>Show 50 more</button></div></div>`;
    const countEl = $('.more-count', target), body = $('.more-body', target), btn = $('.more-btn', target);
    function drawCount() {
      countEl.textContent = rows.length ? (rows.length >= total ? `Showing ${plural(total, noun[0], noun[1])}` : `Showing ${num(rows.length)} of ${plural(total, noun[0], noun[1])}`) : '';
      btn.hidden = rows.length >= total;
    }
    function frame() {
      if (o.head) {
        body.innerHTML = `<div class="table-wrap"><table class="table"><thead>${o.head}</thead><tbody></tbody></table></div>`;
        return $('tbody', body);
      }
      body.innerHTML = `<div class="rec-list"></div>`;
      return $('.rec-list', body);
    }
    let holder = null;
    async function loadMore(first) {
      const my = ++run_;
      if (first) { body.innerHTML = skeleton('rows', 6); countEl.textContent = ''; btn.hidden = true; }
      const done = first ? () => {} : busy(btn, 'Loading…');
      let res;
      try {
        res = await o.load(first ? 0 : rows.length);
      } catch (e) {
        done();
        if (my !== run_ || !alive()) return;
        if (first) fail(body, e, () => loadMore(true));
        else status(e.message || 'Could not load more. Try again.', { error: true });
        return;
      }
      done();
      if (my !== run_ || !alive() || !res) return;
      const got = asList(res, 'rows');
      total = Number(res.total !== undefined ? res.total : (first ? got.length : rows.length + got.length)) || 0;
      if (first) {
        rows = [];
        if (!got.length) { body.innerHTML = empty(o.empty || `No ${noun[1]} here.`); drawCount(); countEl.textContent = ''; return; }
        holder = frame();
      }
      rows = rows.concat(got);
      if (total < rows.length) total = rows.length;
      holder.insertAdjacentHTML('beforeend', got.map((r) => o.row(r)).join(''));
      drawCount();
    }
    btn.addEventListener('click', () => loadMore(false));
    loadMore(true);
    return { reload: () => loadMore(true), rows: () => rows.slice() };
  }

  /* ------------------------------------------------------------------ filters */

  function filters(target, o) {
    o = o || {};
    const fields = o.fields || [];
    let values = Object.assign({}, o.values || {});
    let open = false;
    const uid = 'f' + Math.random().toString(36).slice(2, 8);
    const isOn = (f) => { const v = values[f.key]; return !(v === undefined || v === null || v === '' || v === false || v === '0'); };
    function word(f) {
      const v = values[f.key];
      if (typeof f.words === 'function') return f.words(v, values);
      if (typeof f.words === 'string') return f.words.replace('{v}', v);
      if (f.type === 'select') { const op = (f.options || []).find((x) => String(x[0]) === String(v)); return op ? op[1] : String(v); }
      if (f.type === 'date') return `${String(f.label || '').toLowerCase()} ${date(v)}`.trim();
      if (f.type === 'check') return f.label;
      return `${f.label}: “${v}”`;
    }
    function fieldHtml(f) {
      const id = `${uid}-${f.key}`;
      const v = values[f.key];
      if (f.type === 'check') {
        return `<label class="check"><input type="checkbox" id="${id}" data-fkey="${esc(f.key)}"${isOn(f) ? ' checked' : ''}> ${esc(f.label)}</label>`;
      }
      let input;
      if (f.type === 'select') {
        input = `<select class="select" id="${id}" data-fkey="${esc(f.key)}"><option value="">Any</option>`
          + (f.options || []).map((op) => `<option value="${esc(op[0])}"${String(op[0]) === String(v === undefined ? '' : v) ? ' selected' : ''}>${esc(op[1])}</option>`).join('')
          + `</select>`;
      } else if (f.type === 'date') {
        input = `<input class="input" type="date" id="${id}" data-fkey="${esc(f.key)}" value="${esc(v || '')}">`;
      } else {
        input = `<input class="input" type="text" id="${id}" data-fkey="${esc(f.key)}" value="${esc(v || '')}" autocomplete="off">`;
      }
      return `<div class="field"><label for="${id}">${esc(f.label)}</label>${input}</div>`;
    }
    target.innerHTML = `<div class="filters"><div class="filters-head row"><button type="button" class="btn small filters-btn" aria-expanded="false" aria-controls="${uid}-fold"></button>`
      + `<span class="filters-words small grow"></span></div><div class="filters-fold" id="${uid}-fold" hidden><div class="row filters-fields">${fields.map(fieldHtml).join('')}</div></div></div>`;
    const btn = $('.filters-btn', target), fold = $('.filters-fold', target), words = $('.filters-words', target);
    function drawHead() {
      const onList = fields.filter(isOn);
      btn.innerHTML = `${icon('sliders', 16)}<span>Filters${onList.length ? ' · ' + onList.length : ''}</span>`;
      btn.setAttribute('aria-expanded', String(open));
      words.innerHTML = onList.length
        ? `<span>${esc(onList.map(word).join(', '))}</span> <button type="button" class="link filters-clear">Clear</button>`
        : '';
    }
    function syncInputs() {
      fields.forEach((f) => {
        const inp = $(`[data-fkey="${CSS.escape(f.key)}"]`, fold);
        if (!inp) return;
        if (f.type === 'check') inp.checked = isOn(f);
        else inp.value = values[f.key] === undefined || values[f.key] === null ? '' : values[f.key];
      });
    }
    btn.addEventListener('click', () => { open = !open; fold.hidden = !open; drawHead(); });
    let tTimer = null;
    fold.addEventListener('input', (e) => {
      const inp = e.target.closest('[data-fkey]');
      if (!inp) return;
      const k = inp.getAttribute('data-fkey');
      const f = fields.find((x) => x.key === k);
      values[k] = f && f.type === 'check' ? (inp.checked ? '1' : '') : inp.value;
      if (!values[k]) delete values[k];
      drawHead();
      clearTimeout(tTimer);
      const fire = () => o.onChange && o.onChange(Object.assign({}, values));
      if (f && f.type === 'text') tTimer = setTimeout(fire, 350); else fire();
    });
    target.addEventListener('click', (e) => {
      if (!e.target.closest('.filters-clear')) return;
      fields.forEach((f) => { delete values[f.key]; });
      syncInputs();
      drawHead();
      if (o.onChange) o.onChange(Object.assign({}, values));
    });
    drawHead();
    return {
      set(v) { values = Object.assign({}, v || {}); syncInputs(); drawHead(); },
      values() { return Object.assign({}, values); },
    };
  }

  /* ------------------------------------------------------------------ dialog */

  let dialogOpen = null;
  function formValues(root) {
    const out = {};
    $$('input[name], select[name], textarea[name]', root).forEach((f) => {
      const k = f.name;
      if (f.type === 'checkbox') {
        const same = $$(`input[type=checkbox][name="${CSS.escape(k)}"]`, root);
        if (same.length > 1) { out[k] = out[k] || []; if (f.checked) out[k].push(f.value); }
        else out[k] = f.checked;
      } else if (f.type === 'radio') {
        if (f.checked) out[k] = f.value; else if (!(k in out)) out[k] = '';
      } else if (f.tagName === 'SELECT' && f.multiple) {
        out[k] = Array.from(f.selectedOptions).map((x) => x.value);
      } else if (f.type === 'file') {
        out[k] = f.files;
      } else {
        out[k] = f.value;
      }
    });
    return out;
  }

  function dialog(o) {
    o = o || {};
    const dlg = $('#dialog');
    if (!dlg) return Promise.resolve(null);
    if (dialogOpen) dialogOpen(null);
    const opener = D.activeElement;
    return new Promise((resolve) => {
      const acts = o.actions && o.actions.length ? o.actions : [{ label: 'Close', value: null }];
      dlg.className = o.wide ? 'wide' : '';
      dlg.innerHTML = `<form method="dialog" class="dlg" novalidate>`
        + `<div class="dlg-head"><h2 id="dlg-title" class="section-title">${esc(o.title || '')}</h2>`
        + `<button type="button" class="btn icon ghost dlg-x" aria-label="Close" data-tip="Close">${icon('x', 18)}</button></div>`
        + `<div class="dlg-body stack">${o.body || ''}</div>`
        + `<div class="dlg-msg error-box" role="alert" hidden></div>`
        + `<div class="dlg-foot row">${acts.map((a, i) => `<button type="${a.kind === 'primary' ? 'submit' : 'button'}" class="btn${a.kind ? ' ' + esc(a.kind) : ''}" data-i="${i}">${esc(a.label)}</button>`).join('')}</div>`
        + `</form>`;
      const form = $('form', dlg), msg = $('.dlg-msg', dlg);
      let finished = false;
      function finish(v) {
        if (finished) return;
        finished = true;
        dialogOpen = null;
        try { if (dlg.open) dlg.close(); } catch (e) { /* ignore */ }
        dlg.innerHTML = '';
        if (opener && opener.focus && D.contains(opener)) opener.focus();
        resolve(v === undefined ? null : v);
      }
      dialogOpen = finish;
      async function pick(a, btn) {
        msg.hidden = true;
        const cancel = a.value === null || a.value === undefined || a.value === false || a.value === 'cancel';
        if (!cancel) {
          const missing = $$('[required]', form).find((f) => (f.type === 'checkbox' ? !f.checked : !String(f.value || '').trim()));
          if (missing) {
            const lab = missing.id ? $(`label[for="${CSS.escape(missing.id)}"]`, form) : null;
            msg.textContent = `Fill in ${lab ? '“' + lab.textContent.trim() + '”' : 'this'} first.`;
            msg.hidden = false;
            missing.focus();
            return;
          }
        }
        if (o.onAction && !cancel) {
          const done = busy(btn, a.busy || null);
          try {
            const r = await o.onAction(a.value, dlg);
            done();
            if (r === false) return;
          } catch (e) {
            done();
            msg.textContent = (e && e.message) || 'Something went wrong. Try again.';
            msg.hidden = false;
            return;
          }
        }
        finish(a.value);
      }
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const i = acts.findIndex((a) => a.kind === 'primary');
        if (i >= 0) pick(acts[i], $(`[data-i="${i}"]`, form));
      });
      form.addEventListener('click', (e) => {
        if (e.target.closest('.dlg-x')) { finish(null); return; }
        const b = e.target.closest('button[data-i]');
        if (!b || b.type === 'submit') return;
        pick(acts[Number(b.getAttribute('data-i'))], b);
      });
      dlg.oncancel = (e) => { e.preventDefault(); finish(null); };
      dlg.onclick = (e) => { if (e.target === dlg) finish(null); };
      try { dlg.showModal(); } catch (e) { dlg.setAttribute('open', ''); }
      if (o.onOpen) { try { o.onOpen(dlg); } catch (e) { console.error(e); } }
      const first = $('.dlg-body input:not([type=hidden]), .dlg-body select, .dlg-body textarea', dlg)
        || $('.dlg-foot .primary', dlg) || $('.dlg-foot button', dlg);
      if (first) first.focus();
    });
  }
  function confirm_(text, o) {
    o = o || {};
    return dialog({
      title: o.title || 'Are you sure?',
      body: `<p>${esc(text)}</p>`,
      actions: [{ label: 'Cancel', value: false }, { label: o.ok || 'Yes', kind: o.danger ? 'danger' : 'primary', value: true }],
    }).then((v) => v === true);
  }

  /* ------------------------------------------------------------------ findings */

  function isFlagged(eid) { return state.flagged.has(eid); }
  async function saveFinding(o) {
    o = o || {};
    const v = await dialog({
      title: 'Save as finding',
      body: `<div class="field"><label for="sf-title">Title</label><input class="input" id="sf-title" name="title" value="${esc(o.title || '')}" required></div>`
        + `<div class="field"><label for="sf-note">Your note</label><textarea class="textarea" id="sf-note" name="note" rows="4" placeholder="Why this matters to the case"></textarea></div>`
        + `<div class="field"><label for="sf-tags">Tags</label><input class="input" id="sf-tags" name="tags" placeholder="For example: money, airport" autocomplete="off"></div>`,
      actions: [{ label: 'Cancel', value: null }, { label: 'Save as finding', kind: 'primary', value: 'save', busy: 'Saving…' }],
      onAction: async (val, dlgEl) => {
        const f = formValues(dlgEl);
        const tags = String(f.tags || '').split(',').map((t) => t.trim()).filter(Boolean);
        const saved = await capi('/findings', { method: 'POST', body: { event_id: o.event_id || null, ask_id: o.ask_id || null, title: f.title, note: f.note, tags } });
        o._saved = saved;
      },
    });
    if (v !== 'save') return null;
    if (o.event_id) state.flagged.add(o.event_id);
    $$(`[data-eid="${CSS.escape(String(o.event_id || ''))}"]`).forEach((n) => n.setAttribute('data-flagged', '1'));
    status('Saved as a finding');
    emit('finding', Object.assign({ event_id: o.event_id || null }, o._saved || {}));
    return o._saved || true;
  }

  /* ------------------------------------------------------------------ the record drawer */

  let drawerOpener = null;
  const KIND_TITLE = { message: 'Message', call: 'Call', photo: 'Photo', video: 'Video', voice: 'Voice note', audio: 'Voice note',
    document: 'Document', file: 'File', location: 'Place', contact: 'Contact', note: 'Note', payment: 'Payment' };
  function recordTitle(r) {
    const k = String(r.kind || '').toLowerCase();
    const base = KIND_TITLE[k] || 'Record';
    if (k === 'call') return callWords(Object.assign({}, r, { duration_s: 0 }));
    if (r.app && !/^(phone|gallery|photos|camera|files)$/i.test(r.app)) return `${base} on ${appName(r.app)}`;
    if (k === 'photo' || k === 'video' || k === 'document') return `${base} on the phone`;
    return base;
  }
  function drawerShell(title, inner) {
    return `<div class="drawer-head"><h2 id="drawer-title" class="section-title grow">${title}</h2>`
      + `<button type="button" class="btn icon ghost" data-drawer-close aria-label="Close" data-tip="Close (Esc)">${icon('x', 18)}</button></div>`
      + `<div class="drawer-body stack">${inner}</div>`;
  }
  function showDrawer(html, label) {
    const dr = $('#drawer');
    if (!dr) return null;
    if (dr.hidden) drawerOpener = drawerOpener || D.activeElement;
    dr.innerHTML = html;
    dr.hidden = false;
    dr.setAttribute('role', 'dialog');
    if (label) dr.setAttribute('aria-label', label); else dr.removeAttribute('aria-label');
    D.body.classList.add('drawer-open');
    requestAnimationFrame(() => dr.classList.add('on'));
    dr.focus();
    return dr;
  }
  function closeDrawer(quiet) {
    const dr = $('#drawer');
    if (!dr || dr.hidden) return;
    dr.hidden = true;
    dr.classList.remove('on');
    dr.innerHTML = '';
    D.body.classList.remove('drawer-open');
    latest('drawer');
    const o = drawerOpener;
    drawerOpener = null;
    if (!quiet && o && o.focus && D.contains(o)) o.focus();
  }
  function openPanel(o) {
    o = o || {};
    drawerOpener = D.activeElement;
    return showDrawer(drawerShell(esc(o.title || ''), o.html || ''), o.label);
  }

  async function openRecord(eid, opener) {
    if (!eid) return;
    drawerOpener = opener || (D.activeElement !== D.body ? D.activeElement : null);
    const mine = latest('drawer');
    showDrawer(drawerShell('Opening the record…', skeleton('rows', 5)));
    let data;
    try {
      data = await capi('/records/' + encodeURIComponent(eid));
    } catch (e) {
      if (!mine()) return;
      const dr = showDrawer(drawerShell('This record could not be opened', '<div class="drawer-fail"></div>'));
      fail($('.drawer-fail', dr), e, () => openRecord(eid, drawerOpener));
      return;
    }
    if (!mine()) return;
    const rec = (data && data.record) || data || {};
    const src = (data && data.source) || {};
    const before = (data && data.before) || [];
    const after = (data && data.after) || [];
    const k = String(rec.kind || '').toLowerCase();
    const dir = String(rec.direction || '').toLowerCase();
    const out = dir === 'out' || dir === 'outgoing' || dir === 'sent';

    const head = `<div class="drawer-meta row">${tile(kindIcon(k), k === 'call' ? 'green' : k === 'location' ? 'teal' : rec.amount ? 'orange' : 'blue')}`
      + `<div class="stack grow"><span class="small muted num">${esc(time(rec.ts))}</span><div class="row">${phoneChip(rec.phone_label || rec.source_id)}${appChip(rec.app)}${statusChip(rec.status)}</div></div></div>`;

    let body = '';
    const from = rec.sender_name || rec.sender || '';
    const to = rec.recipient_names || rec.conv_title || '';
    if (from || to) body += `<div class="small"><b>${esc(from || 'Unknown')}</b>${to ? ` <span class="muted">to</span> ${esc(Array.isArray(to) ? to.join(', ') : to)}` : ''}</div>`;
    if (rec.body) body += `<div class="bubble ${out ? 'out' : 'in'}">${esc(rec.body)}</div>`;
    if (k === 'call') body += `<p>${esc(callWords(rec))}${rec.counterparty ? ' · ' + esc(rec.counterparty) : ''}</p>`;
    if (rec.amount) body += `<div class="kv"><span>Amount</span><b class="num">${esc(money(rec.amount))}</b>${rec.counterparty ? `<span>Other side</span><span>${esc(rec.counterparty)}</span>` : ''}${rec.ref ? `<span>Reference</span><span class="code">${esc(rec.ref)}</span>` : ''}</div>`;
    if (rec.media_name) body += `<p class="small">${icon('file', 14)} ${esc(rec.media_name)}</p>`;
    if (rec.transcript) body += `<div class="stack"><div class="caps tiny muted">What is said in it</div><p>${esc(rec.transcript)}</p></div>`;
    if (rec.ocr_text) body += `<div class="stack"><div class="caps tiny muted">Words in the photo</div><p>${esc(rec.ocr_text)}</p></div>`;
    if (rec.lat !== undefined && rec.lat !== null && rec.lon !== undefined && rec.lon !== null) {
      body += `<div class="kv"><span>Place</span><span>${esc(rec.place || 'Not named')}</span><span>Position</span><span class="num">${esc(Number(rec.lat).toFixed(5))}, ${esc(Number(rec.lon).toFixed(5))}</span></div>`;
    } else if (rec.place) body += `<p>${icon('pin', 14)} ${esc(rec.place)}</p>`;
    if (!body) body = `<p class="muted">This record has no text.</p>`;

    const fp = String(src.sha256 || rec.sha256 || '');
    const origin = `<details class="fold" open><summary class="section-title">Where this came from</summary><div class="kv small">`
      + `<span>Record</span><span class="code">${esc(rec.event_id || eid)}</span>`
      + (src.label || rec.phone_label ? `<span>Phone</span><span>${esc(src.label || rec.phone_label)}${src.phone_no ? ' · ' + esc(src.phone_no) : ''}</span>` : '')
      + (src.file_name ? `<span>Phone file</span><span class="code">${esc(src.file_name)}</span>` : '')
      + (rec.origin_file || rec.src_file ? `<span>File inside it</span><span class="code">${esc(rec.origin_file || rec.src_file)}</span>` : '')
      + (rec.origin_table || rec.src_table ? `<span>Table and row</span><span class="code">${esc(rec.origin_table || rec.src_table)}${rec.origin_row || rec.src_row ? ', row ' + esc(rec.origin_row || rec.src_row) : ''}</span>` : '')
      + (fp ? `<span>Fingerprint</span><span class="row"><span class="code" data-tip="${esc(fp)}">${esc(fp.slice(0, 12))}</span><button type="button" class="btn icon ghost small" data-copy="${esc(fp)}" aria-label="Copy the whole fingerprint" data-tip="Copy the whole fingerprint">${icon('copy', 14)}</button></span>` : '')
      + `</div></details>`;

    const around = before.length || after.length
      ? `<details class="fold" open><summary class="section-title">Around it</summary><div class="rec-list compact">`
        + before.map((r) => recordRow(r, { phone: false })).join('')
        + `<div class="rec rec-here" aria-current="true"><span class="small"><b>This record</b></span></div>`
        + after.map((r) => recordRow(r, { phone: false })).join('') + `</div></details>`
      : '';

    const conv = rec.conv_id;
    const text = rec.body || rec.transcript || rec.ocr_text || '';
    const acts = `<div class="drawer-actions row">`
      + (conv ? `<a class="btn small" href="${esc(link('chats', { conv, around: rec.event_id || eid }))}">${icon('chat', 14)}<span>Open in chat</span></a>` : '')
      + `<button type="button" class="btn small" data-save-finding>${icon(isFlagged(rec.event_id || eid) ? 'flag-on' : 'flag', 14)}<span>${isFlagged(rec.event_id || eid) ? 'Saved as finding' : 'Save as finding'}</span></button>`
      + (rec.ts ? `<a class="btn small" href="${esc(link('timeline', { day: dayKey(rec.ts), around: rec.event_id || eid }))}">${icon('clock', 14)}<span>Show on timeline</span></a>` : '')
      + (text ? `<button type="button" class="btn small" data-copy="${esc(text)}">${icon('copy', 14)}<span>Copy text</span></button>` : '')
      + `</div>`;

    const dr = showDrawer(drawerShell(esc(recordTitle(rec)), head + acts + `<div class="card stack">${body}</div>` + origin + around), recordTitle(rec));
    const sb = dr && $('[data-save-finding]', dr);
    if (sb) {
      sb.addEventListener('click', async () => {
        const title = (from ? from + ': ' : '') + String(text || recordTitle(rec)).slice(0, 80);
        const ok = await saveFinding({ event_id: rec.event_id || eid, title });
        if (ok && sb.isConnected) sb.innerHTML = `${icon('flag-on', 14)}<span>Saved as finding</span>`;
      });
    }
  }

  /* ------------------------------------------------------------------ tooltip */

  let tipTimer = null, tipFor = null;
  function showTip(target) {
    const tip = $('#tooltip');
    const text = target && target.getAttribute('data-tip');
    if (!tip || !text) return;
    tipFor = target;
    tip.innerHTML = safe(text);
    tip.hidden = false;
    const r = target.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    const vw = D.documentElement.clientWidth, vh = D.documentElement.clientHeight;
    let left = r.left + r.width / 2 - t.width / 2;
    left = Math.max(8, Math.min(left, vw - t.width - 8));
    let top = r.bottom + 8;
    if (top + t.height > vh - 8) top = r.top - t.height - 8;
    tip.style.position = 'fixed';
    tip.style.left = Math.round(left) + 'px';
    tip.style.top = Math.round(Math.max(8, top)) + 'px';
    const id = 'tooltip';
    target.setAttribute('aria-describedby', id);
  }
  function hideTip() {
    clearTimeout(tipTimer);
    const tip = $('#tooltip');
    if (tip) tip.hidden = true;
    if (tipFor) tipFor.removeAttribute('aria-describedby');
    tipFor = null;
  }
  function tipSoon(e) {
    const t = e.target.closest && e.target.closest('[data-tip]');
    if (!t || t === tipFor) return;
    hideTip();
    tipTimer = setTimeout(() => { if (t.isConnected) showTip(t); }, 300);
  }

  /* ------------------------------------------------------------------ export menu */

  function exportable(pageName, query) {
    const b = $('#export-btn');
    current.exportable = { page: pageName, query };
    if (b) b.hidden = false;
  }
  function closeMenus() {
    const m = $('#export-menu'), mm = $('#me-menu');
    if (m) m.hidden = true;
    if (mm) mm.hidden = true;
    const eb = $('#export-btn'), mb = $('#me-btn');
    if (eb) eb.setAttribute('aria-expanded', 'false');
    if (mb) mb.setAttribute('aria-expanded', 'false');
  }
  function openExportMenu() {
    const m = $('#export-menu'), b = $('#export-btn');
    if (!m || !b || !current.exportable) return;
    if (!m.hidden) { closeMenus(); return; }
    m.innerHTML = [['xlsx', 'Spreadsheet (Excel)'], ['csv', 'Plain table (opens in Excel)'], ['html', 'Page to print or keep']]
      .map(([f, l]) => `<button type="button" role="menuitem" data-format="${f}">${icon(f === 'html' ? 'file' : 'sheet', 16)}<span>${esc(l)}</span></button>`).join('');
    const r = b.getBoundingClientRect();
    m.style.position = 'fixed';
    m.style.top = Math.round(r.bottom + 6) + 'px';
    m.style.right = Math.round(D.documentElement.clientWidth - r.right) + 'px';
    m.hidden = false;
    b.setAttribute('aria-expanded', 'true');
    const f = $('[role=menuitem]', m); if (f) f.focus();
  }
  function doExport(format) {
    const ex = current.exportable;
    if (!ex || !state.cid) return;
    let q = ex.query;
    if (typeof q === 'function') { try { q = q(); } catch (e) { q = {}; } }
    const url = apiUrl(`/cases/${encodeURIComponent(state.cid)}/export`, Object.assign({}, q || {}, { page: ex.page, format }));
    const a = D.createElement('a');
    a.href = url;
    a.setAttribute('download', '');
    D.body.appendChild(a);
    a.click();
    a.remove();
    closeMenus();
    status('Export started. It will be saved to your Downloads folder.');
  }

  /* ------------------------------------------------------------------ quick find */

  let qfItems = [], qfIndex = -1, qfTimer = null;
  function closePop() {
    const pop = $('#qfpop'), inp = $('#qf-input');
    if (pop) { pop.hidden = true; pop.innerHTML = ''; }
    if (inp) { inp.setAttribute('aria-expanded', 'false'); inp.removeAttribute('aria-activedescendant'); }
    qfItems = []; qfIndex = -1;
  }
  function qfHref(kind, it) {
    if (it.href) return it.href;
    if (kind === 'people') return link('person/' + encodeURIComponent(it.person_id || it.pid || it.id));
    if (kind === 'chats') return link('chats', { conv: it.conv_id || it.id });
    if (it.page || it.tab) return link(it.page || it.tab, it.params || it.query);
    return '';
  }
  function qfLabel(it) { return it.name || it.title || it.label || it.text || it.conv_title || ''; }
  function drawPop(data, q) {
    const pop = $('#qfpop'), inp = $('#qf-input'), box = $('#qf');
    if (!pop || !inp) return;
    qfItems = []; qfIndex = -1;
    const groups = [['people', 'People', 'user'], ['chats', 'Chats', 'chat'], ['pages', 'Pages', 'grid']];
    let html = '';
    groups.forEach(([k, label, ic]) => {
      const list = asList(data && data[k], k).slice(0, 5);
      if (!list.length) return;
      html += `<div class="qf-group caps tiny muted" role="presentation">${label}</div>`;
      list.forEach((it) => {
        const i = qfItems.length;
        qfItems.push(qfHref(k, it));
        const sub = it.sub || it.ident || it.phone || it.app_name || (it.app ? appName(it.app) : '') || it.hint || '';
        html += `<div class="qf-item" role="option" id="qf-opt-${i}" data-i="${i}" aria-selected="false">${icon(it.icon || ic, 16)}`
          + `<span class="grow clamp-1">${esc(qfLabel(it))}</span>${sub ? `<span class="small muted clamp-1">${esc(sub)}</span>` : ''}</div>`;
      });
    });
    const si = qfItems.length;
    qfItems.push(link('search', { q }));
    html += `<div class="qf-item qf-search" role="option" id="qf-opt-${si}" data-i="${si}" aria-selected="false">${icon('search', 16)}<span class="grow">Search every record for “${esc(q)}”</span><kbd>Enter</kbd></div>`;
    pop.innerHTML = html;
    const r = (box || inp).getBoundingClientRect();
    pop.style.position = 'fixed';
    pop.style.top = Math.round(r.bottom + 6) + 'px';
    pop.style.left = Math.round(r.left) + 'px';
    pop.style.minWidth = Math.round(Math.max(r.width, 360)) + 'px';
    pop.hidden = false;
    inp.setAttribute('aria-expanded', 'true');
  }
  function qfMove(d) {
    if (!qfItems.length) return;
    const n = qfItems.length + 1; /* the extra slot is "nothing chosen" (-1) */
    qfIndex = ((qfIndex + 1 + d + n) % n) - 1;
    $$('#qfpop .qf-item').forEach((n) => {
      const on = Number(n.getAttribute('data-i')) === qfIndex;
      n.setAttribute('aria-selected', String(on));
      n.classList.toggle('on', on);
      if (on) n.scrollIntoView({ block: 'nearest' });
    });
    const inp = $('#qf-input');
    if (inp) { if (qfIndex >= 0) inp.setAttribute('aria-activedescendant', 'qf-opt-' + qfIndex); else inp.removeAttribute('aria-activedescendant'); }
  }
  function qfOpen(i) {
    const inp = $('#qf-input');
    const q = inp ? inp.value.trim() : '';
    const href = i >= 0 ? qfItems[i] : (q ? link('search', { q }) : '');
    closePop();
    if (inp) inp.blur();
    if (href) go(href);
  }
  async function qfLookup(q) {
    const mine = latest('qf');
    let data = null;
    try { data = await capi('/quickfind', { query: { q } }); } catch (e) { data = {}; }
    if (!mine()) return;
    const inp = $('#qf-input');
    if (!inp || inp.value.trim() !== q) return;
    drawPop(data, q);
  }
  function setupQuickFind() {
    const inp = $('#qf-input'), ic = $('#qf-icon');
    if (ic) ic.innerHTML = icon('search', 16);
    if (!inp) return;
    inp.addEventListener('input', () => {
      clearTimeout(qfTimer);
      const q = inp.value.trim();
      if (!q) { closePop(); return; }
      qfTimer = setTimeout(() => qfLookup(q), 150);
    });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); qfMove(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); qfMove(-1); }
      else if (e.key === 'Enter') { e.preventDefault(); qfOpen(qfIndex); }
      else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (!$('#qfpop').hidden) closePop(); else { inp.value = ''; inp.blur(); } }
    });
    inp.addEventListener('blur', () => setTimeout(() => { if (D.activeElement !== inp) closePop(); }, 150));
    const pop = $('#qfpop');
    if (pop) {
      pop.addEventListener('mousedown', (e) => e.preventDefault());
      pop.addEventListener('click', (e) => {
        const it = e.target.closest('.qf-item');
        if (it) qfOpen(Number(it.getAttribute('data-i')));
      });
    }
  }

  /* ------------------------------------------------------------------ global wiring */

  const typing = (t) => t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
  let gPending = 0;

  function setupShell() {
    const st = $('#side-toggle');
    function sideState() {
      const hidden = D.documentElement.getAttribute('data-side') === 'hidden';
      if (!st) return;
      st.innerHTML = icon('sidebar', 18);
      st.setAttribute('aria-expanded', String(!hidden));
      const words = hidden ? 'Show the menu' : 'Hide the menu';
      st.setAttribute('aria-label', words);
      st.setAttribute('data-tip', words);
    }
    sideState();
    if (st) st.addEventListener('click', () => {
      const hidden = D.documentElement.getAttribute('data-side') === 'hidden';
      if (hidden) D.documentElement.removeAttribute('data-side'); else D.documentElement.setAttribute('data-side', 'hidden');
      store.set('ib.side', hidden ? 'shown' : 'hidden');
      hideTip();
      sideState();
    });

    $$('[data-theme-set]').forEach((b) => {
      const t = b.getAttribute('data-theme-set');
      b.innerHTML = `${icon(t === 'dark' ? 'moon' : 'sun', 14)}<span>${t === 'dark' ? 'Dark' : 'Light'}</span>`;
      b.setAttribute('aria-pressed', String(t === state.theme));
      b.addEventListener('click', () => applyTheme(t));
    });
    $$('[data-size-set]').forEach((b) => {
      const s = b.getAttribute('data-size-set');
      b.setAttribute('aria-pressed', String(s === state.textsize));
      b.addEventListener('click', () => applySize(s));
    });
    const badge = $('#badge');
    if (badge && !badge.querySelector('svg')) badge.insertAdjacentHTML('afterbegin', icon('lock', 14));

    const back = $('#back');
    if (back) back.addEventListener('click', () => history.back());
    const nb = $('#notes-btn');
    if (nb) nb.addEventListener('click', () => run('notes'));
    const eb = $('#export-btn');
    if (eb) eb.addEventListener('click', (e) => { e.stopPropagation(); openExportMenu(); });
    const em = $('#export-menu');
    if (em) em.addEventListener('click', (e) => { const b = e.target.closest('[data-format]'); if (b) doExport(b.getAttribute('data-format')); });
    const mb = $('#me-btn'), mm = $('#me-menu');
    if (mb && mm) {
      mb.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = mm.hidden;
        closeMenus();
        mm.hidden = !open;
        mb.setAttribute('aria-expanded', String(open));
        if (open) { const f = $('[role=menuitem]', mm); if (f) f.focus(); }
      });
    }
    const lo = $('#me-logout');
    if (lo) lo.addEventListener('click', () => { closeMenus(); logout(); });
    const about = $('#me-about');
    if (about) about.addEventListener('click', () => closeMenus());

    const tt = $('#totop');
    if (tt) {
      tt.innerHTML = icon('arrow-up', 18);
      tt.addEventListener('click', () => { window.scrollTo({ top: 0 }); const v = $('#view'); if (v) { v.scrollTop = 0; v.focus({ preventScroll: true }); } });
      const onScroll = () => {
        const v = $('#view');
        const y = Math.max(window.scrollY || 0, v ? v.scrollTop : 0);
        tt.hidden = y < window.innerHeight * 2;
        hideTip();
      };
      window.addEventListener('scroll', onScroll, { passive: true });
      const v = $('#view'); if (v) v.addEventListener('scroll', onScroll, { passive: true });
    }

    setupQuickFind();

    /* clicks on shared attributes */
    D.addEventListener('click', (e) => {
      const t = e.target;
      if (!t.closest) return;
      if (!t.closest('#export-menu, #export-btn, #me-menu, #me-btn')) closeMenus();
      const skip = t.closest('[data-skip]');
      if (skip) { e.preventDefault(); const v = $('#view'); if (v) v.focus(); return; }
      const act = t.closest('[data-action]');
      if (act) { e.preventDefault(); run(act.getAttribute('data-action')); return; }
      const cp = t.closest('[data-copy]');
      if (cp) { e.preventDefault(); copy(cp.getAttribute('data-copy')); return; }
      const ask = t.closest('[data-ask]');
      if (ask && state.cid) { e.preventDefault(); go(link('ask', { q: ask.getAttribute('data-ask'), go: 1 })); return; }
      const eidEl = t.closest('[data-eid]');
      if (eidEl && !t.closest('a[href]:not([data-eid]), button:not([data-eid]), input, select, textarea, label')) {
        e.preventDefault();
        openRecord(eidEl.getAttribute('data-eid'), eidEl);
        return;
      }
      const hrefEl = t.closest('[data-href]');
      if (hrefEl && !t.closest('a[href]:not([data-href]), button:not([data-href]), input, select, textarea')) {
        e.preventDefault();
        go(hrefEl.getAttribute('data-href'));
        return;
      }
      if (t.closest('[data-drawer-close]')) { closeDrawer(); return; }
    });

    D.addEventListener('keydown', (e) => {
      const t = e.target;
      if (e.key === 'Escape') {
        hideTip();
        const anyMenu = !$('#export-menu').hidden || !$('#me-menu').hidden;
        if (anyMenu) { closeMenus(); return; }
        if (!$('#qfpop').hidden) { closePop(); return; }
        const dr = $('#drawer');
        if (dr && !dr.hidden && !($('#dialog') && $('#dialog').open)) { closeDrawer(); return; }
        return;
      }
      if ((e.key === 'Enter' || e.key === ' ') && t && t.getAttribute && !typing(t)) {
        if (t.hasAttribute('data-eid') && t.tagName !== 'BUTTON' && t.tagName !== 'A') { e.preventDefault(); openRecord(t.getAttribute('data-eid'), t); return; }
        if (t.hasAttribute('data-href') && t.tagName !== 'BUTTON' && t.tagName !== 'A') { e.preventDefault(); go(t.getAttribute('data-href')); return; }
      }
      if (typing(t) || e.altKey || ($('#dialog') && $('#dialog').open)) return;
      if ((e.key === '/' && !e.ctrlKey && !e.metaKey) || ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K'))) {
        const inp = $('#qf-input');
        if (inp && !$('#qf').hidden) { e.preventDefault(); inp.focus(); inp.select(); }
        return;
      }
      if (e.ctrlKey || e.metaKey) return;
      if (e.key === 'g') { gPending = Date.now(); return; }
      if (gPending && Date.now() - gPending < 1200 && state.cid) {
        const map = { d: '', a: 'ask', s: 'search', c: 'chats', t: 'timeline' };
        gPending = 0;
        if (e.key in map) { e.preventDefault(); go(link(map[e.key])); }
      }
    });

    /* menus: arrow keys */
    $$('#me-menu, #export-menu').forEach((m) => m.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      e.preventDefault();
      const items = $$('[role=menuitem]', m);
      let i = items.indexOf(D.activeElement);
      i = e.key === 'ArrowDown' ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
      items[i].focus();
    }));

    /* tooltips */
    D.addEventListener('mouseover', tipSoon);
    D.addEventListener('focusin', tipSoon);
    D.addEventListener('mouseout', (e) => {
      const t = e.target.closest && e.target.closest('[data-tip]');
      if (t && (!e.relatedTarget || !t.contains(e.relatedTarget))) hideTip();
    });
    D.addEventListener('focusout', () => hideTip());

    /* keep focus inside the drawer when it is open and tabbing */
    D.addEventListener('keydown', (e) => {
      if (e.key !== 'Tab') return;
      const dr = $('#drawer');
      if (!dr || dr.hidden || !dr.contains(D.activeElement)) return;
      const f = $$('a[href], button:not([disabled]), input, select, textarea, [tabindex="0"]', dr).filter((x) => x.offsetParent !== null);
      if (!f.length) return;
      if (e.shiftKey && D.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && D.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    });

    window.addEventListener('hashchange', () => route());
    window.addEventListener('online', () => {});
  }

  /* ------------------------------------------------------------------ export the IB surface */

  Object.assign(IB, {
    $, $$, esc, safe, el, css, state,
    on, off, emit, action, run,
    page, pages, dashboardTab, dashboardTabs,
    api, capi, latest,
    go, link, reload,
    fmt, plural,
    tile, logo,
    loggedIn, logout,
    refreshCase, refreshJobs, refreshLimit,
    copy, status,
    phoneChip, phoneChips, statusChip, appChip, appName, pill, cite, statTile, recordRow,
    openRecord, openPanel, closeDrawer,
    dialog, formValues, confirm: confirm_,
    saveFinding, isFlagged,
    filters, moreList, tabs,
    empty, skeleton, fail, notBuilt,
    progress, updating, busy,
    theme: applyTheme, textsize: applySize,
  });

  D.addEventListener('DOMContentLoaded', () => {
    try { history.scrollRestoration = 'manual'; } catch (e) { /* older browsers */ }
    setupShell();
    loadHealth();
    route();
  });
})();
