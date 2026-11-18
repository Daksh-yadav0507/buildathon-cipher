# Back-end interfaces: the server core every module builds on

Run: `.venv/bin/python run.py [--port N] [--no-browser] [--data FOLDER]` (127.0.0.1 only; the next free port if N is busy).
Tests and spare servers: set `IB_DATA_DIR` (a temporary folder), `IB_SYNC_JOBS=1` (jobs run inline), `IB_NO_AI=1`,
`IB_NO_SAMPLE=1` (no sample case at start-up) before importing `ib.api`. `GET /api/health` lists which modules loaded.

## Your module and its router

- `ib/<name>.py` exposes `router = fastapi.APIRouter()` with full paths (`/api/cases/{cid}/search`). `ib/api.py` includes
  it by itself for: ingest, search, stats, people, browse, ask, across, keyq, brief, codes, findings, export. Never edit
  api.py. A module that fails to import is skipped and the console says why: check yours with
  `.venv/bin/python -c "import ib.<name>"`, then `curl 127.0.0.1:<port>/api/health`.
- Write plain `def` routes (they run in a thread pool; SQLite blocks). Heavy work goes in a job (below).
- Every `/api/*` route except `/api/health` and `/api/auth/*` already needs a session, and every path with `{cid}`
  already checks the officer's access (app-wide). Take the dependency anyway, to know who is asking:

```python
from fastapi import APIRouter, Depends
from ib.officers import CaseAccess, require_case, require_officer
router = APIRouter()

@router.get("/api/cases/{cid}/search")
def search(cid: str, q: str = "", acc: CaseAccess = Depends(require_case)):
    ...  # acc.cid, acc.officer_id, acc.officer_name, acc.case (the case-list row: name, number, about, ...)
```
`require_officer` (routes without `{cid}`) returns `{"officer_id", "name", "initials"}`.

## Errors

`from ib import ApiError, fail`, then `raise ApiError(404, "That record isn't in this case.")` or `fail(400, "...")`.
The page gets `{"error": "<sentence>"}` with that status. `HTTPException(status, "sentence")` works too. Anything
unexpected becomes 500 with a general sentence (traceback in the console); bad request fields become 422 with a sentence.

## Databases (`ib/db.py`)

- `with db.case_db(cid) as con:` opens `data/cases/<cid>/case.db` (WAL, foreign keys on), commits at the end, rolls
  back on an error, closes. 404 `ApiError` if the case has no database. `db.open_case(cid)` gives a raw connection
  for long jobs: you commit and close it. Rows are `sqlite3.Row` (`r[0]`, `r["name"]`); for JSON use
  `db.rows(con, sql, params) -> list[dict]`, `db.one(...) -> dict | None`, `db.scalar(..., default=None)`.
- Long writes (ingest): commit every few thousand rows so audit lines and readers never wait; `db.checkpoint(con)`
  after each phone. `db.now_ms()` is the time in UTC ms; all stored times are UTC ms.
- Need one more column? `db.add_column(con, "events", "my_col", "TEXT")` (idempotent). One more table?
  `CREATE TABLE IF NOT EXISTS <yourmodule>_<name>` in your module. Do not change the section 3 tables.
- Meta: `db.get_meta(con, key, default)`, `db.set_meta(con, key, value)` (non-strings stored as JSON; None removes),
  `db.get_meta_json(con, key, default)`. Keys in use: `case_version`, `schema_version`, `name`, `limit`
  (limits.py only). Yours: prefix them (`ingest_…`, `stats_…`).
- Case list (in `data/officers.db`): `db.list_cases(officer_id=None) -> [row]` (only that officer's cases when given),
  `db.get_case(cid) -> row | None`, `db.create_case(name, about, number="", created_by=None, case_id=None) -> row`
  (gives the creator access and makes the case database; an existing `case_id` is returned unchanged),
  `db.update_case(cid, name=, number=, about=, last_opened=) -> row`, `db.touch_case(cid)` (last opened = now),
  `db.case_exists(cid)`, `db.new_case_id()`. Row fields: `case_id, name, number, about, created_by, created_at,
  last_opened`. Case ids match `[A-Za-z0-9][A-Za-z0-9_-]{0,63}` (the sample case may use a fixed id such as `sample`).
- Unit-wide (officers.db) tables: `officers`, `sessions`, `cases`, `case_access`, `prefs`, `app_audit`, and
  `question_lists(list_id TEXT PK, name, when_text, questions JSON, created_by, created_at)` for keyq's own lists
  (`with db.app_db() as con:`).

### The tables you will query most (section 3, exact names)

- `events(event_id 'P1-000123', source_id, kind, app, ts, direction 'in'|'out'|'', sender, recipients JSON, conv_id,
  body, status ''|'deleted'|'unsent'|'edited'|'missed'|'rejected', duration_s, lat, lon, place, media_name,
  media_size, media_sha256, transcript, ocr_text, origin JSON, extra JSON, folded)`
- `events_fts(event_id UNINDEXED, words, folded)` (unicode61) and `events_tri(event_id UNINDEXED, folded)` (trigram):
  join back with `events.event_id`.
- `sources(source_id, phone_no, label 'Phone 1 | Vikram's iPhone', owner_name, owner_person_id, platform, device, os,
  file_name, sha256, added_at, added_by, status 'reading'|'done'|'failed', first_ts, last_ts, n_events, device_info)`
- `persons(person_id, name, names JSON, kind 'person'|'business'|'service', is_owner, owner_source_id, n_messages,
  n_calls, first_ts, last_ts, group_kind)`; `identifiers(ident PK '+91…'|'wa:+91…'|'email:…'|'upi:…', kind, display,
  person_id)`
- `conversations(conv_id, source_id, app, title, is_group, participants JSON, n_messages, n_deleted, first_ts,
  last_ts, thread_key)`; `money(money_id, event_id, source_id, ts, amount, direction 'debit'|'credit', method,
  counterparty, counterparty_ident, ref, said_in_chat)`
- Also: `findings`, `audit`, `asks`, `ready`, `codes`, `keyq_answers`, `keyq_choice`, `brief`, `meta`.

## The case version and saved answers

`db.case_version(con) -> int`; `db.bump_case_version(con) -> int` (inside your transaction). Bump when records
change: a phone added or re-read, a code word confirmed or rejected, the AI's reading of records. Never for audit
lines, findings, asks, prefs or the warrant limit. Saved answers go in `ready(name, made_from, value, made_at)` with
`made_from = str(db.case_version(con))`; a saved value is good only while `made_from` matches. Under a warrant limit
(`limits.get_limit(con)` is not None) never read or write saved answers: work them out fresh.

## The warrant limit (`ib/limits.py`): every query that reads records

```python
w, p = limits.where(con, "e")      # ("1=1", []) when no limit is on
con.execute(f"SELECT ... FROM events e WHERE {w} AND e.kind = ? ...", [*p, "message"])
# other tables: f"... FROM money m WHERE m.event_id IN (SELECT e.event_id FROM events e WHERE {w})", p
```
Pass the alias you gave `events` (`""` for none). `limits.get_limit(con) -> dict | None`
(`{people: [person_id], from, to, apps, from_day, to_day}`; `to` is exclusive), `limits.banner_text(con) -> str | None`.
Apps match `events.app`; the value `calls` also lets in every `kind = 'call'`. People match sender, recipients, or
the phone owner's own records. While a limit is on, across-phone checks must not call anything "missing".

## The audit log (`ib/audit.py`)

`audit.log(cid, who, action, text)`: `who` is a name, an officer dict or a `CaseAccess`; `action` a short key;
`text` the plain sentence the Audit page shows. It never raises. Keys and sentences:
`search` "Searched for 'paisa'", `ask` "Asked: 'paisa kisne kisko bheja?'", `record` "Opened a message from Raju Verma
(P2-002931)", `export` "Exported Timeline as a spreadsheet", `finding` "Saved a finding: …", `case` "Opened the case",
`phone` "Added Phone 2 | Raju's Android", `code` "Confirmed the code word 'biscuit' as 'gold bar'", `limit`, `brief`.
Logins and logouts are written by the core (`audit.log_app(who, action, text)`).

## Background jobs (`ib/jobs.py`): two run at a time

```python
def work(job, path):                 # your function: the job handle comes first
    job.step("Reading chats")        # starts the next step (plain words)
    job.progress(0.4)                # 0..1 within the current step
    return {"source_id": 3}          # becomes job["result"] (keep it small)
snap = jobs.start(cid, "ingest", work, path, label="Adding Phone 2", steps=7)
```
Raise `ApiError(…, "sentence")` to fail with that sentence; other exceptions fail with a general sentence.
`jobs.get(job_id) -> dict | None`, `jobs.for_case(cid) -> [dict]`, `jobs.find(cid, kind) -> dict | None` (one that
is waiting or running), `jobs.wait(job_id, timeout=None) -> dict`. A job dict: `{id, case_id, kind, label, status
'waiting'|'running'|'done'|'failed', step, step_no, steps, progress (whole job, 0..1), step_progress, time_left_s
(None until the step has run 5 s), time_left ("Working out how long this takes…" or "About 3 minutes left"),
started_at, finished_at, error, result}`. With `IB_SYNC_JOBS=1`, `start()` returns the finished job.

## Words (`ib/text.py`)

- `fold(word)`, `fold_text(text)` (what goes in `events.folded` and both index tables' `folded`),
  `fold_tokens(text) -> [str]`, `tokens(text)`, `content_words(text)` (folded, stop words dropped), `STOP_WORDS`.
- `fts_query(words, op="AND", prefix=False, column=None)` gives a safe MATCH string (`'"pes" AND "beja"'`).
- `highlight(text, words, exact=False, prefix=False)`: escapes first, then `<mark>`s every word that folds to one of
  `words`. `snippet(text, words, width=140)` does the same on about 140 characters around the first hit, with "…".
  `spellings(text, words)`: the distinct spellings that matched (for "Found every spelling: …"). `esc`.
- Phones: `norm_phone(s) -> '+919899512640' | None`, `digits(s)`, `is_sender_id('AD-BUBANK')`.
- Money: `find_amounts(text) -> [{value, text, start, end, explicit}]`, `parse_amount(s)`, `MONEY_WORDS`,
  `format_inr(50000) -> '₹50,000'`, `inr_short(620000) -> '₹6.2 lakh'`, `group_indian(n)`, `plural(n, one, many)`.
- Time (India time for people, UTC ms stored): `parse_ts(iso | epoch)`, `ist(ms)`, `fmt_when` ('16 Sep 2026, 10:05 am'),
  `fmt_date`, `fmt_time`, `ist_day(ms) -> '2026-09-16'`, `day_range(day) -> (start, end_exclusive)`,
  `duration_words(252) -> '4 min 12 s'`, `gap_words(ms) -> '2 minutes'`, `find_date_range(question, ref_ms)`
  -> `{from, to, words}` ('16 Sep', 'night of 15 Sep', '14-17 Sep', 'kal', 'last week'); pass the last record time.

## Settings (`ib/config.py`)

`config.ai()` -> `.configured`, `.base_url`, `.chat_url`, `.api_key`, `.model`, `.max_tokens`, `.timeout_s`, `.local`,
`.host`, `.where` ('on this computer' | 'at <host>'). Paths: `config.data_dir()`, `config.samples_dir()`,
`config.case_dir(cid)`, `config.WEB_DIR`, `config.ROOT`. `config.PAGE_SIZE = 50`. Note: python-multipart is not
installed, so read uploads from the raw body (`await request.body()`) or parse multipart with the stdlib `email` module.

## Route ownership (paths under `/api/cases/{cid}` unless they start with `/api`)

- ingest: `/api/cases` (GET, POST), PATCH `/api/cases/{cid}`, `/api/samples`, `/sources` (GET, POST), `/phone/{source_id}`
- search: `/search`, `/quickfind` · stats (with ready.py): `/stats`, `/activity`, `/story`
- people: `/people`, `/people/{pid}`
- browse: `/chats`, `/chats/{conv_id}`, `/calls`, `/timeline`, `/places`, `/media`, `/media/read`, `/records/{eid}`
- ask (with llm.py): `/ask`, `/ask/estimate`, `/asks` · across: `/across`
- keyq: `/key-questions`, `/key-questions/run`, `/key-questions/use`, `/api/question-lists` · brief: `/brief`
- codes: `/codes` · findings: `/findings` · export: `/export`
- core (api.py, audit.py, limits.py, jobs.py): `/api/health`, `/api/auth/login`, `/api/auth/logout`, `/api/me`,
  `/api/prefs`, `/audit`, `/limit`, `/jobs`, `/api/jobs/{id}`

### Core route shapes

- `GET /api/health` -> `{app: "insights-buddy", version, ai: {configured, model, local, host, where}, modules}`
- `POST /api/auth/login {name, password}` -> `{officer_id, name, initials}` and an HttpOnly cookie (12 hours);
  401 "That name and password don't match. Check the spelling and try again." First run seeds Arjun Rao / demo.
- `POST /api/auth/logout` -> `{ok: true}` · `GET /api/me` -> `{officer_id, name, initials}`
- `GET /api/prefs`, `POST /api/prefs {theme: 'light'|'dark', textsize: 'normal'|'large'}` -> the prefs
- `GET /audit?offset=&officer=&action=&from=&to=` -> `{total, offset, rows: [{ts, when, officer, action, text}],
  officers, actions}` (logins included)
- `GET /limit` -> `{}` when off, else `{from, to (inclusive, ms), from_day, to_day, apps, people: [{person_id, name}],
  banner}`; `POST /limit {people: [id], from: 'YYYY-MM-DD', to: 'YYYY-MM-DD', apps: []}` or `{}` to remove
- `GET /jobs` -> a list of job dicts (waiting, running, or finished in the last 30 s) · `GET /api/jobs/{id}` -> a job
