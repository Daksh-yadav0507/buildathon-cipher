"""Officers (section 10.1): the demo officer, password hashing, sessions, case access, prefs, and the auth dependencies.

Passwords: PBKDF2-HMAC-SHA256, 200,000 rounds, a random salt per officer.
Sessions: a random token in an HttpOnly cookie for 12 hours; only its SHA-256 is stored.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from fastapi import Request

from ib import ApiError, config, db

DEMO_NAME = "Arjun Rao"
DEMO_PASSWORD = "demo"
ITERATIONS = 200_000

PREF_DEFAULTS = {"theme": "light", "textsize": "normal"}
PREF_CHOICES = {"theme": ("light", "dark"), "textsize": ("normal", "large")}

LOGIN_FAILED = "That name and password don't match. Check the spelling and try again."
NOT_LOGGED_IN = "Please log in to go on."
NO_SUCH_CASE = "That case doesn't exist."
NO_ACCESS = "You don't have access to this case. Ask the officer who made it to add you."


# ---------------------------------------------------------------- passwords


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """(hash_hex, salt_hex) for a password."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS)
    return digest.hex(), salt


def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    try:
        candidate, _ = hash_password(password, salt)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, pw_hash or "")


def initials(name: str) -> str:
    parts = [p for p in (name or "").replace(".", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# ---------------------------------------------------------------- officers


def _public(row: dict | None) -> dict | None:
    if not row:
        return None
    return {"officer_id": row["officer_id"], "name": row["name"], "initials": row["initials"] or initials(row["name"])}


def create_officer(name: str, password: str) -> dict:
    name = " ".join((name or "").split())
    if not name or not password:
        raise ApiError(400, "An officer needs a name and a password.")
    pw_hash, salt = hash_password(password)
    with db.app_db() as con:
        if db.one(con, "SELECT officer_id FROM officers WHERE name=?", (name,)):
            raise ApiError(409, "An officer with that name already exists.")
        cur = con.execute("INSERT INTO officers(name, initials, pw_hash, salt, created_at) VALUES(?,?,?,?,?)",
                          (name, initials(name), pw_hash, salt, db.now_ms()))
        oid = cur.lastrowid
    return get_officer(oid)


def get_officer(officer_id: int) -> dict | None:
    with db.app_db() as con:
        return _public(db.one(con, "SELECT * FROM officers WHERE officer_id=?", (officer_id,)))


def find_officer(name: str) -> dict | None:
    """The officer with this name (any case, extra spaces ignored), without the password fields."""
    with db.app_db() as con:
        return _public(db.one(con, "SELECT * FROM officers WHERE name=?", (" ".join((name or "").split()),)))


def list_officers() -> list[dict]:
    with db.app_db() as con:
        return [_public(r) for r in db.rows(con, "SELECT * FROM officers ORDER BY name")]


def seed() -> dict:
    """Make sure the sample officer Arjun Rao (password 'demo') exists. Returns him."""
    found = find_officer(DEMO_NAME)
    if found:
        return found
    try:
        return create_officer(DEMO_NAME, DEMO_PASSWORD)
    except ApiError:  # made by another thread a moment ago
        return find_officer(DEMO_NAME)


def demo_officer_id() -> int:
    """Arjun Rao's officer_id (seeded if needed): the sample case is made in his name."""
    return seed()["officer_id"]


def authenticate(name: str, password: str) -> dict | None:
    """The officer if the name and password match, else None."""
    clean = " ".join((name or "").split())
    with db.app_db() as con:
        row = db.one(con, "SELECT * FROM officers WHERE name=?", (clean,))
    if not row:
        hash_password(password or "x")  # same work either way, so timing doesn't tell names apart
        return None
    if not verify_password(password or "", row["pw_hash"], row["salt"]):
        return None
    return _public(row)


# ---------------------------------------------------------------- sessions


def _key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(officer_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with db.app_db() as con:
        con.execute("INSERT INTO sessions(token, officer_id, created_at) VALUES(?,?,?)",
                    (_key(token), int(officer_id), db.now_ms()))
        # tidy up sessions older than 12 hours
        con.execute("DELETE FROM sessions WHERE created_at < ?", (db.now_ms() - config.SESSION_HOURS * 3_600_000,))
    return token


def session_officer(token: str | None) -> dict | None:
    """The officer behind a session token, or None if it's unknown or older than 12 hours."""
    if not token:
        return None
    with db.app_db() as con:
        row = db.one(con, """SELECT o.*, s.created_at AS session_at FROM sessions s
                             JOIN officers o ON o.officer_id = s.officer_id WHERE s.token=?""", (_key(token),))
        if not row:
            return None
        if row["session_at"] < db.now_ms() - config.SESSION_HOURS * 3_600_000:
            con.execute("DELETE FROM sessions WHERE token=?", (_key(token),))
            return None
    return _public(row)


def end_session(token: str | None) -> None:
    if token:
        with db.app_db() as con:
            con.execute("DELETE FROM sessions WHERE token=?", (_key(token),))


# ---------------------------------------------------------------- case access


def can_access(officer_id: int, case_id: str) -> bool:
    with db.app_db() as con:
        return db.one(con, "SELECT 1 AS ok FROM case_access WHERE case_id=? AND officer_id=?",
                      (case_id, int(officer_id))) is not None


def grant_access(case_id: str, officer_id: int) -> None:
    with db.app_db() as con:
        con.execute("INSERT OR IGNORE INTO case_access(case_id, officer_id) VALUES(?, ?)", (case_id, int(officer_id)))


def case_ids_for(officer_id: int) -> list[str]:
    with db.app_db() as con:
        return [r[0] for r in con.execute("SELECT case_id FROM case_access WHERE officer_id=?", (int(officer_id),))]


# ---------------------------------------------------------------- prefs


def get_prefs(officer_id: int) -> dict:
    prefs = dict(PREF_DEFAULTS)
    with db.app_db() as con:
        for r in con.execute("SELECT key, value FROM prefs WHERE officer_id=?", (int(officer_id),)):
            if r[0] in PREF_CHOICES and r[1] in PREF_CHOICES[r[0]]:
                prefs[r[0]] = r[1]
    return prefs


def set_prefs(officer_id: int, changes: dict) -> dict:
    """Save theme and/or textsize. Unknown keys are ignored; a wrong value is a 400."""
    clean = {}
    for k, v in (changes or {}).items():
        if k not in PREF_CHOICES:
            continue
        if v not in PREF_CHOICES[k]:
            raise ApiError(400, f"The {k} can only be {' or '.join(PREF_CHOICES[k])}.")
        clean[k] = v
    if clean:
        with db.app_db() as con:
            for k, v in clean.items():
                con.execute("INSERT INTO prefs(officer_id, key, value) VALUES(?,?,?) "
                            "ON CONFLICT(officer_id, key) DO UPDATE SET value=excluded.value", (int(officer_id), k, v))
    return get_prefs(officer_id)


# ---------------------------------------------------------------- FastAPI dependencies


@dataclass
class CaseAccess:
    """What a case route gets from Depends(require_case)."""
    cid: str
    officer_id: int
    officer_name: str
    case: dict = field(default_factory=dict)

    @property
    def officer(self) -> dict:
        return {"officer_id": self.officer_id, "name": self.officer_name, "initials": initials(self.officer_name)}


def officer_from_request(request: Request) -> dict | None:
    """The logged-in officer for this request, or None (looked up once per request)."""
    if hasattr(request.state, "officer"):
        return request.state.officer
    officer = session_officer(request.cookies.get(config.SESSION_COOKIE))
    request.state.officer = officer
    return officer


def require_officer(request: Request) -> dict:
    """Depends(require_officer): {officer_id, name, initials}, or 401 with a plain sentence."""
    officer = officer_from_request(request)
    if officer is None:
        raise ApiError(401, NOT_LOGGED_IN)
    return officer


def check_case(request: Request, cid: str) -> CaseAccess:
    cached = getattr(request.state, "case_access", None)
    if isinstance(cached, CaseAccess) and cached.cid == cid:
        return cached
    officer = require_officer(request)
    case = db.get_case(cid)
    if not case:
        raise ApiError(404, NO_SUCH_CASE)
    if not can_access(officer["officer_id"], cid):
        raise ApiError(403, NO_ACCESS)
    acc = CaseAccess(cid=cid, officer_id=officer["officer_id"], officer_name=officer["name"], case=case)
    request.state.case_access = acc
    return acc


def require_case(cid: str, request: Request) -> CaseAccess:
    """Depends(require_case) on any /api/cases/{cid}/... route: the officer must be logged in and have access."""
    return check_case(request, cid)
