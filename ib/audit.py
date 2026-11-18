"""The audit log (section 10.2): who did what, when, in plain words.

Case events go in the case's own `audit` table; logins and logouts go in `app_audit` in officers.db.
The Audit page shows both, newest first. Writing an audit line never makes a request fail.
"""
from __future__ import annotations

import sys

from fastapi import APIRouter, Depends, Query

from ib import config, db, text
from ib.officers import CaseAccess, require_case

router = APIRouter()


def _who(officer) -> str:
    if officer is None:
        return ""
    if isinstance(officer, str):
        return officer
    if isinstance(officer, dict):
        return str(officer.get("name") or officer.get("officer_name") or "")
    return str(getattr(officer, "officer_name", None) or getattr(officer, "name", None) or officer)


def log(cid: str, officer, action: str, detail: str = "") -> None:
    """Write one audit line for a case: log(cid, acc, "search", "Searched for 'paisa'")."""
    try:
        con = db.open_case(cid, timeout=5.0)
        try:
            con.execute("INSERT INTO audit(ts, officer, action, detail) VALUES(?,?,?,?)",
                        (db.now_ms(), _who(officer), action, detail))
            con.commit()
        finally:
            con.close()
    except Exception as e:  # never break the officer's request over an audit line
        print(f"[audit] could not write '{action}' for case {cid}: {e}", file=sys.stderr)


def log_app(officer, action: str, detail: str = "") -> None:
    """Write one unit-wide audit line (logins, logouts)."""
    try:
        with db.app_db() as con:
            con.execute("INSERT INTO app_audit(ts, officer, action, detail) VALUES(?,?,?,?)",
                        (db.now_ms(), _who(officer), action, detail))
    except Exception as e:
        print(f"[audit] could not write '{action}': {e}", file=sys.stderr)


def _bound(value, end: bool) -> int | None:
    if value in (None, ""):
        return None
    s = str(value).strip()
    if len(s) == 10 and s[4] == "-":
        try:
            start, stop = text.day_range(s)
        except ValueError:
            return None
        return stop if end else start
    return text.parse_ts(s)


def _filters(officer: str | None, action: str | None, start: int | None, stop: int | None):
    where, params = [], []
    if officer:
        where.append("officer = ? COLLATE NOCASE")
        params.append(officer)
    if action:
        where.append("action = ?")
        params.append(action)
    if start is not None:
        where.append("ts >= ?")
        params.append(start)
    if stop is not None:
        where.append("ts < ?")
        params.append(stop)
    return (" WHERE " + " AND ".join(where)) if where else "", params


def entries(cid: str, offset: int = 0, limit: int = config.PAGE_SIZE, officer: str | None = None,
            action: str | None = None, start: int | None = None, stop: int | None = None) -> dict:
    """The case's audit lines plus logins, newest first, `limit` at a time."""
    w, p = _filters(officer, action, start, stop)
    need = max(0, offset) + max(1, limit)
    with db.case_db(cid) as con:
        total = db.scalar(con, f"SELECT COUNT(*) FROM audit{w}", p, 0)
        case_rows = db.rows(con, f"SELECT id, ts, officer, action, detail FROM audit{w} ORDER BY ts DESC, id DESC LIMIT ?",
                            [*p, need])
        officers = [r[0] for r in con.execute("SELECT DISTINCT officer FROM audit WHERE officer <> '' ORDER BY officer")]
        actions = [r[0] for r in con.execute("SELECT DISTINCT action FROM audit ORDER BY action")]
    with db.app_db() as con:
        total += db.scalar(con, f"SELECT COUNT(*) FROM app_audit{w}", p, 0)
        app_rows = db.rows(con, f"SELECT id, ts, officer, action, detail FROM app_audit{w} ORDER BY ts DESC, id DESC LIMIT ?",
                           [*p, need])
        officers += [r[0] for r in con.execute("SELECT DISTINCT officer FROM app_audit WHERE officer <> ''")]
        actions += [r[0] for r in con.execute("SELECT DISTINCT action FROM app_audit")]
    merged = sorted(case_rows + app_rows, key=lambda r: r["ts"], reverse=True)[offset:offset + limit]
    rows = [{"ts": r["ts"], "when": text.fmt_when(r["ts"]), "officer": r["officer"], "action": r["action"],
             "text": r["detail"]} for r in merged]
    return {"total": total, "offset": offset, "rows": rows,
            "officers": sorted(set(officers)), "actions": sorted(set(actions))}


@router.get("/api/cases/{cid}/audit")
def audit_page(cid: str, offset: int = Query(0, ge=0), limit: int = Query(config.PAGE_SIZE, ge=1, le=500),
               officer: str | None = None, action: str | None = None,
               date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
               acc: CaseAccess = Depends(require_case)):
    return entries(cid, offset, limit, officer, action, _bound(date_from, False), _bound(date_to, True))
