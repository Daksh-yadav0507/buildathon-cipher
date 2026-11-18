"""Findings: records and answers an officer saves with a note and tags (section 10.4).

Saving, editing or removing a finding never bumps the case version: one officer's notes
never make another officer wait.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends

from ib import ApiError, audit, db, limits, text
from ib.officers import CaseAccess, require_case

router = APIRouter()


def _tags(value) -> list[str]:
    """Tags from a list, a JSON list or 'a, b, c': trimmed, no repeats, in order."""
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("["):
            try:
                value = json.loads(s)
            except Exception:
                value = s.split(",")
        else:
            value = s.split(",")
    out: list[str] = []
    for t in value if isinstance(value, (list, tuple)) else [value]:
        t = " ".join(str(t or "").split())[:60]
        if t and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out[:20]


def _names(con) -> dict[str, str]:
    """ident -> the person's best name."""
    try:
        rows = db.rows(con, "SELECT i.ident, i.display, p.name FROM identifiers i "
                            "LEFT JOIN persons p ON p.person_id = i.person_id")
    except Exception:
        return {}
    return {r["ident"]: (r.get("name") or r.get("display") or r["ident"]) for r in rows}


def record_rows(con, eids: list[str], names: dict | None = None) -> dict[str, dict]:
    """The records behind findings, inside the warrant limit, shaped like a search hit."""
    eids = [e for e in dict.fromkeys(eids) if e]
    if not eids:
        return {}
    names = names if names is not None else _names(con)
    w, p = limits.where(con, "e")
    out: dict[str, dict] = {}
    for i in range(0, len(eids), 500):
        part = eids[i:i + 500]
        rows = db.rows(con, f"""
            SELECT e.event_id, e.source_id, e.kind, e.app, e.ts, e.direction, e.sender, e.recipients, e.conv_id,
                   e.body, e.status, e.duration_s, e.place, e.media_name, e.transcript, e.ocr_text,
                   s.label AS phone_label, s.phone_no, s.owner_name, c.title AS conv_title
            FROM events e LEFT JOIN sources s ON s.source_id = e.source_id
            LEFT JOIN conversations c ON c.conv_id = e.conv_id
            WHERE {w} AND e.event_id IN ({','.join('?' * len(part))})""", [*p, *part])
        for r in rows:
            if r.get("sender"):
                r["sender_name"] = names.get(r["sender"], r["sender"])
            else:
                r["sender_name"] = r.get("owner_name") or ""
            line = r.get("body") or r.get("transcript") or r.get("ocr_text") or r.get("media_name") or r.get("place") or ""
            r["snippet_html"] = text.esc(line[:300])
            out[r["event_id"]] = r
    return out


def _title_for(rec: dict | None) -> str:
    if not rec:
        return ""
    line = rec.get("body") or rec.get("transcript") or rec.get("ocr_text") or rec.get("media_name") or rec.get("place") or ""
    line = " ".join(str(line).split())
    who = rec.get("sender_name") or ""
    kind = rec.get("kind") or "record"
    lead = f"A {kind} from {who}" if who and rec.get("direction") != "out" else f"A {kind}"
    return (f"{lead}: {line}" if line else lead)[:200]


def list_findings(con, tag: str = "") -> list[dict]:
    """Every finding the officer may see (records outside the warrant limit are left out), newest first."""
    rows = db.rows(con, "SELECT finding_id, event_id, ask_id, title, note, tags, officer, created_at "
                        "FROM findings ORDER BY created_at DESC, finding_id DESC")
    names = _names(con)
    recs = record_rows(con, [r["event_id"] for r in rows if r.get("event_id")], names)
    asks = {}
    ask_ids = [r["ask_id"] for r in rows if r.get("ask_id") is not None]
    if ask_ids:
        try:
            for a in db.rows(con, f"SELECT ask_id, question FROM asks WHERE ask_id IN ({','.join('?' * len(ask_ids))})",
                             ask_ids):
                asks[a["ask_id"]] = a["question"]
        except Exception:
            pass
    out = []
    limited = limits.get_limit(con) is not None
    for r in rows:
        r["tags"] = _tags(r.get("tags"))
        if tag and tag.lower() not in [t.lower() for t in r["tags"]]:
            continue
        eid = r.get("event_id")
        if eid:
            rec = recs.get(eid)
            if rec is None and limited:
                continue  # outside the warrant limit
            r["record"] = rec
            if rec is None:
                r["missing"] = True
        if r.get("ask_id") is not None:
            r["question"] = asks.get(r["ask_id"], "")
        r["when"] = text.fmt_when(r["created_at"]) if r.get("created_at") else ""
        r["id"] = r["finding_id"]
        out.append(r)
    return out


def flagged_ids(con) -> list[str]:
    try:
        return [r[0] for r in con.execute("SELECT DISTINCT event_id FROM findings WHERE event_id IS NOT NULL AND event_id != ''")]
    except Exception:
        return []


def _all_tags(con) -> list[str]:
    counts: dict[str, int] = {}
    for (t,) in con.execute("SELECT tags FROM findings"):
        for x in _tags(t):
            counts[x] = counts.get(x, 0) + 1
    return sorted(counts, key=lambda k: (-counts[k], k.lower()))


def _body(data) -> dict:
    return data if isinstance(data, dict) else {}


def _fid(value) -> int:
    try:
        return int(value)
    except Exception:
        raise ApiError(400, "Say which finding to change.")


@router.get("/api/cases/{cid}/findings")
def get_findings(cid: str, tag: str = "", acc: CaseAccess = Depends(require_case)):
    with db.case_db(cid) as con:
        rows = list_findings(con, tag)
        return {"total": len(rows), "rows": rows, "tags": _all_tags(con), "flagged": flagged_ids(con),
                "limit": limits.banner_text(con)}


@router.post("/api/cases/{cid}/findings")
def add_finding(cid: str, data: dict | None = Body(default=None), acc: CaseAccess = Depends(require_case)):
    return _add(cid, _body(data), acc)


def _add(cid: str, data: dict, acc: CaseAccess) -> dict:
    eid = str(data.get("event_id") or "").strip() or None
    ask_id = data.get("ask_id")
    try:
        ask_id = int(ask_id) if ask_id not in (None, "") else None
    except Exception:
        ask_id = None
    title = " ".join(str(data.get("title") or "").split())[:500]
    note = str(data.get("note") or "").strip()[:5000]
    tags = _tags(data.get("tags"))
    if not eid and ask_id is None and not title:
        raise ApiError(400, "Choose a record or an answer to save as a finding.")
    with db.case_db(cid) as con:
        if eid:
            rec = record_rows(con, [eid]).get(eid)
            if not rec:
                raise ApiError(404, "That record isn't in this case, or it is outside the warrant limit.")
            title = title or _title_for(rec)
        if ask_id is not None and not title:
            q = db.scalar(con, "SELECT question FROM asks WHERE ask_id = ?", [ask_id], default="")
            title = f"Answer: {q}" if q else "A saved answer"
        cur = con.execute("INSERT INTO findings(event_id, ask_id, title, note, tags, officer, created_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?)",
                          [eid, ask_id, title, note, json.dumps(tags, ensure_ascii=False), acc.officer_name, db.now_ms()])
        fid = cur.lastrowid
    audit.log(cid, acc, "finding", f"Saved a finding: {title[:120]}" + (f" ({eid})" if eid else ""))
    with db.case_db(cid) as con:
        row = next((r for r in list_findings(con) if r["finding_id"] == fid), None)
    return row or {"finding_id": fid, "id": fid, "event_id": eid, "ask_id": ask_id, "title": title, "note": note,
                   "tags": tags, "officer": acc.officer_name}


def _patch(cid: str, fid: int, data: dict, acc: CaseAccess) -> dict:
    with db.case_db(cid) as con:
        old = db.one(con, "SELECT * FROM findings WHERE finding_id = ?", [fid])
        if not old:
            raise ApiError(404, "That finding isn't on this case any more.")
        sets, params = [], []
        if "note" in data:
            sets.append("note = ?")
            params.append(str(data.get("note") or "").strip()[:5000])
        if "tags" in data:
            sets.append("tags = ?")
            params.append(json.dumps(_tags(data.get("tags")), ensure_ascii=False))
        if "title" in data and str(data.get("title") or "").strip():
            sets.append("title = ?")
            params.append(" ".join(str(data["title"]).split())[:500])
        if sets:
            con.execute(f"UPDATE findings SET {', '.join(sets)} WHERE finding_id = ?", [*params, fid])
    audit.log(cid, acc, "finding", f"Changed a finding: {(old.get('title') or '')[:120]}")
    with db.case_db(cid) as con:
        row = next((r for r in list_findings(con) if r["finding_id"] == fid), None)
    return row or {"finding_id": fid, "id": fid, "ok": True}


def _delete(cid: str, fid: int, acc: CaseAccess) -> dict:
    with db.case_db(cid) as con:
        old = db.one(con, "SELECT * FROM findings WHERE finding_id = ?", [fid])
        if not old:
            raise ApiError(404, "That finding isn't on this case any more.")
        con.execute("DELETE FROM findings WHERE finding_id = ?", [fid])
    audit.log(cid, acc, "finding", f"Removed a finding: {(old.get('title') or '')[:120]}")
    return {"ok": True, "finding_id": fid}


@router.patch("/api/cases/{cid}/findings/{fid}")
def patch_finding(cid: str, fid: int, data: dict | None = Body(default=None), acc: CaseAccess = Depends(require_case)):
    return _patch(cid, fid, _body(data), acc)


@router.patch("/api/cases/{cid}/findings")
def patch_finding_body(cid: str, data: dict | None = Body(default=None), acc: CaseAccess = Depends(require_case)):
    data = _body(data)
    return _patch(cid, _fid(data.get("finding_id", data.get("id"))), data, acc)


@router.delete("/api/cases/{cid}/findings/{fid}")
def delete_finding(cid: str, fid: int, acc: CaseAccess = Depends(require_case)):
    return _delete(cid, fid, acc)


@router.delete("/api/cases/{cid}/findings")
def delete_finding_query(cid: str, finding_id: str = "", id: str = "", acc: CaseAccess = Depends(require_case)):
    return _delete(cid, _fid(finding_id or id), acc)
