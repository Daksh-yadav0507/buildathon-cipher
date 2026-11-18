"""Databases: one SQLite file per case (WAL), the officers database, the case list, the case version.

* A case lives in data/cases/<case_id>/case.db (schema: CASE_SCHEMA, section 3).
* data/officers.db holds officers, sessions, the case list (registry), case access,
  prefs, unit-wide audit lines (logins) and the officers' own question lists.
* Rows come back as sqlite3.Row (row[0] and row["name"] both work). Use rows()/one()
  to get plain dicts that can go straight into JSON.
* All times are UTC milliseconds (now_ms()).
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ib import ApiError, config

SCHEMA_VERSION = 1

CASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sources(
  source_id INTEGER PRIMARY KEY, phone_no INTEGER,
  label TEXT,
  owner_name TEXT, owner_person_id INTEGER,
  platform TEXT,
  device TEXT, os TEXT, file_name TEXT, sha256 TEXT,
  added_at INTEGER, added_by TEXT, status TEXT,
  first_ts INTEGER, last_ts INTEGER, n_events INTEGER, device_info TEXT
);
CREATE TABLE IF NOT EXISTS persons(
  person_id INTEGER PRIMARY KEY, name TEXT,
  names TEXT,
  kind TEXT,
  is_owner INTEGER DEFAULT 0, owner_source_id INTEGER,
  n_messages INTEGER DEFAULT 0, n_calls INTEGER DEFAULT 0, first_ts INTEGER, last_ts INTEGER,
  group_kind TEXT
);
CREATE TABLE IF NOT EXISTS identifiers(
  ident TEXT PRIMARY KEY,
  kind TEXT, display TEXT, person_id INTEGER
);
CREATE INDEX IF NOT EXISTS ident_person ON identifiers(person_id);
CREATE TABLE IF NOT EXISTS conversations(
  conv_id INTEGER PRIMARY KEY, source_id INTEGER, app TEXT,
  title TEXT, is_group INTEGER, participants TEXT,
  n_messages INTEGER, n_deleted INTEGER, first_ts INTEGER, last_ts INTEGER,
  thread_key TEXT
);
CREATE INDEX IF NOT EXISTS conv_thread ON conversations(thread_key);
CREATE TABLE IF NOT EXISTS events(
  event_id TEXT PRIMARY KEY,
  source_id INTEGER, kind TEXT,
  app TEXT, ts INTEGER, direction TEXT,
  sender TEXT, recipients TEXT, conv_id INTEGER,
  body TEXT, status TEXT,
  duration_s INTEGER, lat REAL, lon REAL, place TEXT,
  media_name TEXT, media_size INTEGER, media_sha256 TEXT,
  transcript TEXT,
  ocr_text TEXT,
  origin TEXT,
  extra TEXT, folded TEXT
);
CREATE INDEX IF NOT EXISTS ev_ts ON events(ts);
CREATE INDEX IF NOT EXISTS ev_conv ON events(conv_id, ts);
CREATE INDEX IF NOT EXISTS ev_kind ON events(kind, ts);
CREATE INDEX IF NOT EXISTS ev_src ON events(source_id, ts);
CREATE INDEX IF NOT EXISTS ev_sender ON events(sender);
CREATE INDEX IF NOT EXISTS ev_sha ON events(media_sha256);
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(event_id UNINDEXED, words, folded, tokenize='unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE IF NOT EXISTS events_tri USING fts5(event_id UNINDEXED, folded, tokenize='trigram');
CREATE TABLE IF NOT EXISTS money(
  money_id INTEGER PRIMARY KEY, event_id TEXT, source_id INTEGER, ts INTEGER,
  amount REAL, direction TEXT,
  method TEXT,
  counterparty TEXT, counterparty_ident TEXT, ref TEXT, said_in_chat INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS money_ts ON money(ts);
CREATE INDEX IF NOT EXISTS money_event ON money(event_id);
CREATE TABLE IF NOT EXISTS findings(finding_id INTEGER PRIMARY KEY, event_id TEXT, ask_id INTEGER, title TEXT, note TEXT, tags TEXT, officer TEXT, created_at INTEGER);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts INTEGER, officer TEXT, action TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS audit_ts ON audit(ts);
CREATE TABLE IF NOT EXISTS asks(ask_id INTEGER PRIMARY KEY, ts INTEGER, officer TEXT, question TEXT, depth TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS ready(name TEXT PRIMARY KEY, made_from TEXT, value TEXT, made_at INTEGER);
CREATE TABLE IF NOT EXISTS codes(word TEXT PRIMARY KEY, meaning TEXT, status TEXT, hits INTEGER, by TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS keyq_answers(list_id TEXT, question TEXT, result TEXT, ts INTEGER, PRIMARY KEY(list_id, question));
CREATE TABLE IF NOT EXISTS keyq_choice(list_id TEXT PRIMARY KEY, used INTEGER, why TEXT, by TEXT);
CREATE TABLE IF NOT EXISTS brief(id INTEGER PRIMARY KEY, ts INTEGER, text TEXT, sections TEXT);
"""

APP_SCHEMA = """
CREATE TABLE IF NOT EXISTS officers(officer_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  initials TEXT, pw_hash TEXT, salt TEXT, created_at INTEGER);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, officer_id INTEGER, created_at INTEGER);
CREATE TABLE IF NOT EXISTS cases(case_id TEXT PRIMARY KEY, name TEXT, number TEXT, about TEXT,
  created_by INTEGER, created_at INTEGER, last_opened INTEGER);
CREATE TABLE IF NOT EXISTS case_access(case_id TEXT, officer_id INTEGER, PRIMARY KEY(case_id, officer_id));
CREATE TABLE IF NOT EXISTS prefs(officer_id INTEGER, key TEXT, value TEXT, PRIMARY KEY(officer_id, key));
CREATE TABLE IF NOT EXISTS app_audit(id INTEGER PRIMARY KEY, ts INTEGER, officer TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS question_lists(list_id TEXT PRIMARY KEY, name TEXT, when_text TEXT, questions TEXT,
  created_by TEXT, created_at INTEGER);
"""

_schema_lock = threading.Lock()
_case_ready: set[str] = set()
_app_ready: set[str] = set()


def now_ms() -> int:
    return int(time.time() * 1000)


def _connect(path: Path, timeout: float = 10.0) -> sqlite3.Connection:
    kwargs: dict[str, Any] = {}
    if hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
        kwargs["autocommit"] = sqlite3.LEGACY_TRANSACTION_CONTROL  # implicit BEGIN before writes
    con = sqlite3.connect(str(path), timeout=timeout, check_same_thread=False, **kwargs)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA temp_store=MEMORY")
    return con


# ---------------------------------------------------------------- case databases


def case_exists(case_id: str) -> bool:
    return config.valid_case_id(case_id) and config.case_db_path(case_id).exists()


def open_case(case_id: str, create: bool = False, timeout: float = 10.0) -> sqlite3.Connection:
    """A new connection to a case's database. The caller must commit and close it.

    Raises ApiError(404) if the case has no database yet (unless create=True).
    """
    if not config.valid_case_id(case_id):
        raise ApiError(404, "That case doesn't exist.")
    path = config.case_db_path(case_id)
    if not path.exists():
        if not create:
            raise ApiError(404, "That case doesn't exist.")
        path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect(path, timeout)
    key = str(path)
    if key not in _case_ready:
        with _schema_lock:
            if key not in _case_ready:
                con.executescript(CASE_SCHEMA)
                con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('case_version', '0')")
                con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
                con.commit()
                _case_ready.add(key)
    return con


@contextmanager
def case_db(case_id: str, create: bool = False) -> Iterator[sqlite3.Connection]:
    """with case_db(cid) as con: ...  Commits when the block ends, rolls back on an error, always closes."""
    con = open_case(case_id, create=create)
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------- the officers database


def open_app(timeout: float = 10.0) -> sqlite3.Connection:
    """A new connection to data/officers.db (schema made on first use). The caller commits and closes."""
    path = config.app_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect(path, timeout)
    key = str(path)
    if key not in _app_ready:
        with _schema_lock:
            if key not in _app_ready:
                con.executescript(APP_SCHEMA)
                con.commit()
                _app_ready.add(key)
    return con


@contextmanager
def app_db() -> Iterator[sqlite3.Connection]:
    con = open_app()
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def init() -> None:
    """Make the data folders and officers.db. Safe to call many times."""
    config.ensure_dirs()
    open_app().close()


# ---------------------------------------------------------------- small query helpers


def rows(con: sqlite3.Connection, sql: str, params: Any = ()) -> list[dict]:
    """All rows as plain dicts."""
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def one(con: sqlite3.Connection, sql: str, params: Any = ()) -> dict | None:
    """The first row as a dict, or None."""
    r = con.execute(sql, params).fetchone()
    return dict(r) if r is not None else None


def scalar(con: sqlite3.Connection, sql: str, params: Any = (), default: Any = None) -> Any:
    """The first column of the first row, or default."""
    r = con.execute(sql, params).fetchone()
    return r[0] if r is not None and r[0] is not None else default


def add_column(con: sqlite3.Connection, table: str, column: str, decl: str = "TEXT") -> bool:
    """Add a column if it isn't there yet (for modules that need one more field). True if added."""
    have = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if column in have:
        return False
    con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    return True


def checkpoint(con: sqlite3.Connection) -> None:
    """Fold the write log back into the database file (run after each phone is added)."""
    con.commit()
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass  # busy readers: SQLite will checkpoint later by itself


# ---------------------------------------------------------------- meta and the case version


def get_meta(con: sqlite3.Connection, key: str, default: Any = None) -> Any:
    r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r[0] if r is not None else default


def set_meta(con: sqlite3.Connection, key: str, value: Any) -> None:
    """Store a meta value; anything that isn't a string is stored as JSON. None removes the key."""
    if value is None:
        con.execute("DELETE FROM meta WHERE key=?", (key,))
        return
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    con.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))


def get_meta_json(con: sqlite3.Connection, key: str, default: Any = None) -> Any:
    raw = get_meta(con, key)
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def case_version(con: sqlite3.Connection) -> int:
    """The case version: changes whenever records change (saved answers key on it)."""
    try:
        return int(get_meta(con, "case_version", 0) or 0)
    except (TypeError, ValueError):
        return 0


def bump_case_version(con: sqlite3.Connection) -> int:
    """Records changed: add 1 to the case version and return the new one (inside the caller's transaction).

    Bump on: a phone added or re-read, a code word confirmed or rejected, the AI's reading of records.
    Never on: audit lines, findings, asks, prefs, the warrant limit.
    """
    con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('case_version', '0')")
    con.execute("UPDATE meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key='case_version'")
    return case_version(con)


# ---------------------------------------------------------------- the case list (registry, in officers.db)

_CASE_FIELDS = ("name", "number", "about", "last_opened")


def new_case_id() -> str:
    return "c" + secrets.token_hex(4)


def list_cases(officer_id: int | None = None) -> list[dict]:
    """Every case (officer_id=None) or only those the officer created or was given, newest first."""
    with app_db() as con:
        if officer_id is None:
            return rows(con, "SELECT * FROM cases ORDER BY COALESCE(last_opened, created_at) DESC")
        return rows(con, """SELECT c.* FROM cases c JOIN case_access a ON a.case_id = c.case_id
                            WHERE a.officer_id = ? ORDER BY COALESCE(c.last_opened, c.created_at) DESC""",
                    (int(officer_id),))


def get_case(case_id: str) -> dict | None:
    if not config.valid_case_id(case_id):
        return None
    with app_db() as con:
        return one(con, "SELECT * FROM cases WHERE case_id=?", (case_id,))


def create_case(name: str, about: str, number: str = "", created_by: int | None = None,
                case_id: str | None = None) -> dict:
    """Add a case to the list, give its creator access, and make its database. Returns the registry row.

    If case_id is given and already exists, the existing case is returned unchanged.
    """
    cid = case_id or new_case_id()
    if not config.valid_case_id(cid):
        raise ApiError(400, "That case id can't be used.")
    existing = get_case(cid)
    if existing:
        return existing
    ts = now_ms()
    with app_db() as con:
        con.execute("INSERT INTO cases(case_id, name, number, about, created_by, created_at, last_opened) "
                    "VALUES(?,?,?,?,?,?,NULL)", (cid, name.strip(), (number or "").strip(), about.strip(), created_by, ts))
        if created_by is not None:
            con.execute("INSERT OR IGNORE INTO case_access(case_id, officer_id) VALUES(?, ?)", (cid, int(created_by)))
    with case_db(cid, create=True) as con:
        set_meta(con, "name", name.strip())
    return get_case(cid) or {}


def update_case(case_id: str, **fields: Any) -> dict | None:
    """Change name, number, about or last_opened. Returns the updated row (None if no such case)."""
    changes = {k: v for k, v in fields.items() if k in _CASE_FIELDS and v is not None}
    if changes:
        sets = ", ".join(f"{k}=?" for k in changes)
        with app_db() as con:
            con.execute(f"UPDATE cases SET {sets} WHERE case_id=?", (*changes.values(), case_id))
        if "name" in changes and case_exists(case_id):
            with case_db(case_id) as con:
                set_meta(con, "name", str(changes["name"]))
    return get_case(case_id)


def touch_case(case_id: str) -> None:
    """Remember that the case was just opened."""
    with app_db() as con:
        con.execute("UPDATE cases SET last_opened=? WHERE case_id=?", (now_ms(), case_id))
