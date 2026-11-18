# Front-end interfaces: the shell every page plugs into

Plain scripts, no modules, no build step. `web/index.html` loads, in this order: `icons.js`, `app.js`, `charts.js`, `across.js`, then every `pages/*.js`. The router starts on `DOMContentLoaded`, after all of them have run, so a page only has to register itself. Files are served under `/static/` (for example `/static/pages/ask.js`); the shell is `/`.

**Wrap every file in `(() => { ... })();`.** Top-level `const`, `let` and `function` names in plain scripts share one global scope, so two files that both declare `esc` break each other. The only globals are `IB` and `icon`. Page styles go through `IB.css(id, text)`, not into `style.css`.

## Registering

| Call | What it does |
|---|---|
| `IB.page(tab, {title, render(view, ctx), bare})` | The page for a route tab. `title`: a string or `ctx => string`. `render` may be async: return its promise, so Back restores the scroll once drawn. `bare: true` hides the side menu and top bar (login). Unregistered tabs show "This page is still being built". |
| `IB.dashboardTab(key, {label, order, show(ctx), render(el, ctx)})` | A Dashboard tab. Orders: plain 10, activity 20, people 30, apps 40, about 50, brief 60, keyq 70, across 80. `show` is optional (Across: 2+ phones). |
| `IB.dashboardTabs(ctx)` | The visible tabs, sorted, for dashboard.js to draw with `IB.tabs`. |
| `IB.action(name, fn)`, `IB.run(name, ...args)` | Named actions. The shell runs `limit` (Warrant limit item and the banner's Change: more.js) and `notes` (Show findings: findings.js). |
| `IB.on(event, fn)`, `IB.emit(event, data)` | Events: `route` (ctx), `case` (case, stats, phones loaded), `jobs` (running jobs), `jobs:done` (a job finished: refresh in place), `theme` (`'light'`/`'dark'`), `finding` (saved `{event_id}`), `limit` (the limit changed). |
| `IB.css(id, text)` | Adds `<style id>` once. |

## Routes (hash) and the query each page should honour

`#/` All cases (`cases`) · `#/login` · `#/about` · `#/c/{cid}` Dashboard (`?tab=key`) · `#/c/{cid}/{tab}` for `ask` (`?q=` fills the box, `&go=1` asks at once), `search` (`?q=&mode=` plus filters), `chats` (`?conv=&around={eid}&both=1&find=`), `calls` (`?type=&person=`), `media` (`?kind=photo|voice|document`), `timeline` (`?day=YYYY-MM-DD` plus filters), `places` (`?day=`), `people` (`?group=`), `findings`, `faces`, `board`, `codes`, `sources`, `audit`, `phone` (`?source=`). `#/c/{cid}/person/{pid}` is tab `person` with `ctx.params.pid`. `#/c/{cid}/record/{eid}` draws `timeline` with `ctx.params.eid`, and the shell opens the drawer itself.

## ctx (second argument of render)

| Field | Meaning |
|---|---|
| `tab`, `cid`, `params`, `query` | Route parts. `query` is a plain object of the hash query (`{q:'paisa', app:'whatsapp'}`). |
| `alive()` | False once the officer has moved on. Check it before drawing late data. |
| `api(path, opts)`, `capi(path, opts)` | Like `IB.api` / `IB.capi`, but a late answer never resolves, so code after `await` simply doesn't run. |
| `setQuery(obj, {push})` | Merges into the URL query (empty values removed) without re-rendering. `push: true` adds a history entry, so Back returns to the old filters. Updates `ctx.query`. |
| `keep` | An object saved with this history entry (open folds, chosen sub-tab). Back gives the same object back. |
| `back` | True when this render came from Back or Forward. |
| `bar(html)` | Fills the sticky 54 px page bar under the top bar; `bar('')` hides it. Returns the element. |
| `title(text)` | Changes the top bar title. |
| `exportable(page, query)` | Shows Export in the top bar. `query` is an object or a function returning the current filters. |
| `restoreScroll()` | Call after async drawing if `render` didn't return a promise. |

## Helpers

- `IB.api(path, opts)`: `path` is `'/cases'` or `'/api/cases'`. `opts`: `method`, `body` (object sent as JSON, or `FormData`), `query` (object, empty values dropped), `noLogin`. Resolves with JSON. Throws an `Error` whose `message` is the server's plain sentence, with `.status`. A 401 shows the login page.
- `IB.capi(path, opts)` = `IB.api('/cases/' + cid + path, opts)`.
- `IB.esc(v)` HTML-escapes (null gives `''`). `IB.safe(html)` keeps only `mark`, `b`, `i`, `br` from server HTML such as `snippet_html`.
- `IB.$(sel, root)`, `IB.$$(sel, root)` (an array). `IB.el(html)` makes one element.
- `IB.state`: `{cid, case, stats, phones, me, theme, textsize, health, limit}`. `phones` is the sources list.
- `IB.go(hash)`, `IB.link(path, query)` (`IB.link('person/12')` gives `#/c/{cid}/person/12`; `''` is the Dashboard), `IB.reload()`.
- `IB.fmt`: `num` (1,23,456), `money` (₹50,000), `lakh` (₹4.2 lakh, ₹1.2 crore), `time` ("16 Sep, 10:05 am"; year only when not this year), `date`, `clock` ("10:05 am"), `day` ("Wednesday, 16 September 2026"), `dayKey` ("2026-09-16"), `duration` ("4 min 12 s"), `size` ("1.2 MB"). All India time; `ts` is UTC ms or an ISO string.
- `IB.plural(n, 'call', 'calls')` gives "1 call", "2,031 calls".
- `IB.icon(name, size = 18)` and `IB.ICONS` (names in icons.js). `IB.tile(name, tone)` is an icon on a tone square. `IB.logo(size)`.
- `IB.loggedIn()` after a good login (goes back to where the officer was), `IB.logout()`.
- `IB.refreshCase()`, `IB.refreshJobs()`, `IB.refreshLimit()`, `IB.latest(name)` (returns an `alive()` that only the newest call with that name keeps).
- `IB.copy(text)`, `IB.status(text, {error})` (a 3 s polite line, never a blocking alert).

## Components (return HTML strings unless noted)

- `IB.phoneChip(p)`: `p` is a source_id, a phone number, a label `"Phone 1 | Vikram's iPhone"` or `{phone_no, label}`. Tones: 1 blue, 2 green, 3 orange. `IB.phoneChips(list)`.
- `IB.statusChip(status)` ('deleted' gives "Deleted, recovered"), `IB.appChip(app)`, `IB.pill(text, tone)`, `IB.cite(n, eid, tip)` (a numbered citation chip that opens the drawer).
- `IB.statTile({n, label, sub, href})`.
- `IB.recordRow(rec, {phone: true})`. Reads `event_id, ts, kind, app, direction, sender_name|sender, recipient_names|conv_title, snippet_html|body|transcript|ocr_text|media_name, status, amount, phone_label|source_id`.
- `IB.openRecord(eid, opener)`: the record drawer. `IB.openPanel({title, html, label})` uses the same right-side drawer for other content (the Notes panel). `IB.closeDrawer()`.
- `IB.dialog({title, body, actions: [{label, kind, value, busy}], wide, onOpen(el), onAction(value, el)})` returns a Promise of the value that closed it, or `null`. `onAction` may be async; returning `false` keeps it open, throwing shows the message inside. Fields marked `required` are checked first. `IB.formValues(el)`. `IB.confirm(text, {ok, danger})` gives a Promise of true or false.
- `IB.saveFinding({event_id, ask_id, title})`: the "Save as finding" dialog (note and tags). `IB.isFlagged(eid)`.
- `IB.filters(el, {fields, values, onChange})`. Field: `{key, label, type: 'select'|'date'|'text'|'check', options: [[value, label]], words}`. Draws the Filters button with its count, the fold and the sentence with Clear. Returns `{set(values), values()}`.
- `IB.moreList(el, {load(offset), row(r), empty, noun: ['record', 'records'], head, alive})`. `load` returns `{rows, total}`. Draws "Showing 50 of 1,284 records", the rows and "Show 50 more". With `head` (a `<tr>` of `<th>`) the rows are table rows. Returns `{reload(), rows()}`.
- `IB.tabs(el, {tabs: [{key, label, count}], active, onChange(key), look: 'tabs'|'seg', label})`: a tablist with arrow keys. Returns `{set(key)}`.
- `IB.empty(text, {icon, action})`, `IB.skeleton('rows'|'cards'|'page', n)`, `IB.fail(el, err, retry)` (the sentence and Try again), `IB.notBuilt(name)`.
- `IB.progress(job, lead)`: the progress strip (time left only once measured). `IB.updating(on)`: "Updating these numbers…".
- `IB.busy(button, 'Asking…')` sets `aria-busy`, disables it and changes the label; returns `done()`.

## Attributes the shell handles for you

`data-eid="P1-000123"` (click or Enter opens the drawer), `data-href="#/…"` (navigates), `data-tip="text"` (tooltip after 300 ms, also on focus), `data-copy="text"`, `data-ask="question"` (opens Ask with it). Give rows `tabindex="0"`.

## CSS classes to reuse

- Layout: `.page` (the padded page), `.stack` (vertical gaps), `.row` (flex with gaps), `.cols` (equal columns; `.cols-2`, `.cols-3`, `.cols-4`), `.grow`.
- Text: `.page-title`, `.section-title`, `.muted`, `.small`, `.tiny`, `.num` (tabular), `.code`, `.clamp-1`, `.clamp-2`, `.caps`.
- Cards: `.card`, `.card-head` (title left, actions right), `.card-title`, `.hero` (the dark hero card).
- Buttons: `.btn`, `.btn.primary` (one per screen), `.btn.small`, `.btn.danger`, `.btn.ghost`, `.btn.icon` (icon only: add `aria-label` and `data-tip`), `.link`.
- Chips: `.chip`, `.chip.phone.p1|p2|p3`, `.chip.status.critical|serious`, `.chip.app`, `.pill` with `.tone-blue|green|violet|orange|teal`, `.cite`, `.flag-on`.
- Tables: `.table` (small caps header, hairlines), `tr.clickable`, `td.num`. Wrap wide tables in `.table-wrap`.
- Records: `.rec-list` holding `.rec` rows; `.day-head` (sticky day header).
- Forms: `.field` (label above), `.input`, `.select`, `.textarea`, `.check`, `.search-big`.
- Tabs: `.tabs`, `.tab`, `.seg`. States: `.empty`, `.skel`, `.error-box`, `.updating`, `.progress`. Other: `.tile`, `.stat`, `.bubble.in|out`, `.kv` (key and value grid), `.fold` (a `<details>`).

## What the shell reads from the API

`/api/me` (401 means log in), `/api/prefs`, `/api/health` (`ai.host` when not local, for the badge), `/api/cases` (the case's name), `/api/cases/{cid}/stats` (`calls` and `by_app[].kind` decide whether Calls and Places show), `/sources`, `/jobs` (an array of `{id, kind, step, progress, time_left_s, label}`, polled every 10 s only while some are running), `/limit` (`{}` when off, otherwise `{from, to, apps, people: [{name}]}`), `/quickfind`, `/findings`, `/export`. The drawer reads `/records/{eid}`: `{record, source, before: [...], after: [...]}`, where `record` holds the `events` columns plus `phone_label`, `sender_name`, `recipient_names`, `conv_title`, and `source` holds `{label, phone_no, file_name, sha256}`. A plain record with `before`/`after` also works.

## Who owns which file

- Shell: `web/index.html`, `web/style.css`, `web/app.js`, `web/icons.js`, `web/brand/logo.svg`, this file.
- `web/pages/home.js`: Log in, All cases, About. `web/pages/dashboard.js`: the Dashboard and its own tabs. `web/charts.js`: the charts.
- `web/pages/ask.js`: Ask a question. `web/pages/search.js`: Search.
- `web/pages/chats.js` with `web/chat-looks.css`: Chats. `web/pages/calls.js`: Calls. `web/pages/timeline.js`: Timeline.
- `web/across.js`: the Across phones tab and its marks. `web/pages/people.js`: People and a person. `web/pages/places.js`: Places. `web/pages/media.js`: Photos and files.
- `web/pages/keyq.js`: the Key questions and Case brief tabs. `web/pages/findings.js`: Findings and the Notes panel. `web/pages/more.js`: Code words, Evidence added, Audit, Phone details, the warrant limit dialog, Faces and Link board.
- Need a change in a shell file? Ask its owner; don't edit it.
