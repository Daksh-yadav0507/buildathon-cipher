"""The warrant limit (section 10.3): people, a date range and apps, applied to every query that reads records.

Stored as JSON in the case's meta table under 'limit'. Every module that reads records calls where():

    w, p = limits.where(con, "e")
    con.execute(f"SELECT ... FROM events e WHERE {w} AND ...", [*p, ...])
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends

from ib import ApiError, audit, db, text
from ib.officers import CaseAccess, require_case

router = APIRouter()

APP_NAMES = {"whatsapp": "WhatsApp", "sms": "SMS", "telegram": "Telegram", "signal": "Signal",
             "imessage": "iMessage", "calls": "calls", "phone": "phone calls", "email": "email"}
_APP_ORDER = ["whatsapp", "sms", "telegram", "signal", "imessage", "email", "phone", "calls"]


def _app_key(app: str) -> tuple:
    return (_APP_ORDER.index(app) if app in _APP_ORDER else len(_APP_ORDER) - 1, app)


def get_limit(con) -> dict | None:
    """The limit in force, or None: {people: [person_id], from, to (exclusive), apps, from_day, to_day}."""
    lim = db.get_meta_json(con, "limit")
    if not isinstance(lim, dict):
        return None
    if not (lim.get("people") or lim.get("apps") or lim.get("from") is not None or lim.get("to") is not None):
        return None
    return lim


def where(con, alias: str = "e") -> tuple[str, list]:
    """The SQL condition (and its parameters) that keeps only records inside the limit.

    alias is what the query calls the events table ("" if it isn't aliased). Gives ("1=1", []) with no limit.
    """
    lim = get_limit(con)
    if not lim:
        return "1=1", []
    a = f"{alias}." if alias else ""
    parts: list[str] = []
    params: list = []
    if lim.get("from") is not None:
        parts.append(f"{a}ts >= ?")
        params.append(int(lim["from"]))
    if lim.get("to") is not None:
        parts.append(f"{a}ts < ?")
        params.append(int(lim["to"]))
    apps = [str(x) for x in lim.get("apps") or []]
    if apps:
        names = [x for x in apps if x != "calls"]
        either = []
        if names:
            either.append(f"{a}app IN ({','.join('?' * len(names))})")
            params.extend(names)
        if "calls" in apps:
            either.append(f"{a}kind = 'call'")
        parts.append("(" + " OR ".join(either) + ")")
    people = [int(x) for x in lim.get("people") or []]
    if people:
        ph = ",".join("?" * len(people))
        idents = f"(SELECT ident FROM identifiers WHERE person_id IN ({ph}))"
        parts.append(
            f"({a}sender IN {idents}"
            f" OR EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid({a}recipients) THEN {a}recipients ELSE '[]' END) j"
            f" WHERE j.value IN {idents})"
            f" OR (COALESCE({a}sender, '') = '' AND {a}source_id IN"
            f" (SELECT source_id FROM sources WHERE owner_person_id IN ({ph}))))")
        params.extend(people * 3)
    return " AND ".join(parts) or "1=1", params


def _people_names(con, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    ph = ",".join("?" * len(ids))
    found = {r["person_id"]: r["name"] for r in db.rows(con, f"SELECT person_id, name FROM persons WHERE person_id IN ({ph})", ids)}
    return [{"person_id": i, "name": found.get(i) or f"Person {i}"} for i in ids]


def _and_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def banner_text(con, lim: dict | None = None) -> str | None:
    """'Warrant limit on: 1 Sep 2026 – 30 Sep 2026; WhatsApp and calls. Records outside it aren't shown or read by the AI.'"""
    lim = lim if lim is not None else get_limit(con)
    if not lim:
        return None
    bits = []
    names = [p["name"] for p in _people_names(con, [int(x) for x in lim.get("people") or []])]
    if names:
        bits.append(_and_list(names))
    f, t = lim.get("from"), lim.get("to")
    if f is not None and t is not None:
        bits.append(f"{text.fmt_date(f)} – {text.fmt_date(t - 1)}")
    elif f is not None:
        bits.append(f"from {text.fmt_date(f)}")
    elif t is not None:
        bits.append(f"up to {text.fmt_date(t - 1)}")
    apps = [APP_NAMES.get(a, a) for a in lim.get("apps") or []]
    if apps:
        bits.append(_and_list(apps))
    return "Warrant limit on: " + "; ".join(bits) + ". Records outside it aren't shown or read by the AI."


def _day_bound(value, end: bool) -> tuple[int | None, str | None]:
    """'YYYY-MM-DD' (India time; an end day counts whole) or UTC ms -> (ms, day)."""
    if value in (None, ""):
        return None, None
    s = str(value).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            start, stop = text.day_range(s[:10])
        except ValueError:
            raise ApiError(400, "Dates for the warrant limit must be real days, like 2026-09-01.")
        return (stop if end else start), s[:10]
    ms = text.parse_ts(s)
    if ms is None:
        raise ApiError(400, "Dates for the warrant limit must be real days, like 2026-09-01.")
    return ms, text.ist_day(ms - 1 if end else ms)


def set_limit(con, data: dict | None) -> dict | None:
    """Store a limit from {people, from, to, apps}; an empty dict (or nothing chosen) removes it."""
    data = data or {}
    people = []
    for p in data.get("people") or []:
        pid = p.get("person_id") if isinstance(p, dict) else p
        try:
            people.append(int(pid))
        except (TypeError, ValueError):
            raise ApiError(400, "The people in a warrant limit must be chosen from the case's people list.")
    apps = sorted({str(a).strip().lower() for a in data.get("apps") or [] if str(a).strip()}, key=_app_key)
    start, from_day = _day_bound(data.get("from"), end=False)
    stop, to_day = _day_bound(data.get("to"), end=True)
    if start is not None and stop is not None and start >= stop:
        raise ApiError(400, "The warrant limit's start date must come before its end date.")
    if not people and not apps and start is None and stop is None:
        db.set_meta(con, "limit", None)
        return None
    lim = {"people": sorted(set(people)), "from": start, "to": stop, "apps": apps,
           "from_day": from_day, "to_day": to_day}
    db.set_meta(con, "limit", json.dumps(lim))
    return lim


def remove_limit(con) -> None:
    db.set_meta(con, "limit", None)


def describe(con) -> dict:
    """What GET /limit returns: {} when off."""
    lim = get_limit(con)
    if not lim:
        return {}
    return {"from": lim.get("from"), "to": (lim["to"] - 1) if lim.get("to") is not None else None,
            "from_day": lim.get("from_day"), "to_day": lim.get("to_day"), "apps": lim.get("apps") or [],
            "people": _people_names(con, [int(x) for x in lim.get("people") or []]),
            "banner": banner_text(con, lim)}


@router.get("/api/cases/{cid}/limit")
def limit_get(cid: str, acc: CaseAccess = Depends(require_case)):
    with db.case_db(cid) as con:
        return describe(con)


@router.post("/api/cases/{cid}/limit")
def limit_set(cid: str, payload: dict | None = Body(None), acc: CaseAccess = Depends(require_case)):
    with db.case_db(cid) as con:
        lim = set_limit(con, payload or {})
        out = describe(con)
    if lim:
        audit.log(cid, acc, "limit", "Set the warrant limit: " + out["banner"].split(": ", 1)[1].split(". Records")[0])
    else:
        audit.log(cid, acc, "limit", "Removed the warrant limit")
    return out
