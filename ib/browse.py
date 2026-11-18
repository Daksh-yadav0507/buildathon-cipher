"""Browse: the chats list, one chat, calls, the timeline, places, photos and files, and one record.

Every query that reads records goes through limits.where(), so the warrant limit holds on every page.
Records come back as the events columns plus plain-word extras the pages need: phone_label, phone_no,
sender_name, recipient_names, conv_title, amount (for money records), and origin/extra/recipients as JSON.
"""
from __future__ import annotations

import json
import math
import time

from fastapi import APIRouter, Body, Depends, Query

from ib import ApiError, audit, config, db, jobs, limits, text
from ib.officers import CaseAccess, require_case

router = APIRouter()

PAGE = config.PAGE_SIZE
CHAT_PAGE = 100
DAY_MS = 86_400_000
IST_MS = 19_800_000  # UTC+5:30

APP_LABELS = {"whatsapp": "WhatsApp", "sms": "SMS", "telegram": "Telegram", "signal": "Signal",
              "imessage": "Messages", "phone": "Phone", "email": "Email"}
KIND_WORDS = {"message": "message", "call": "call", "location": "location", "photo": "photo", "video": "video",
              "voice": "voice note", "document": "document", "contact": "contact", "note": "note"}


# ---------------------------------------------------------------- small helpers


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _json(v, default=None):
    if v is None or v == "":
        return default
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def _bound(value, end: bool) -> int | None:
    """'YYYY-MM-DD' (India day; `to` is inclusive) or UTC ms -> UTC ms (end: exclusive)."""
    if value in (None, ""):
        return None
    s = str(value).strip()
    if s.lstrip("-").isdigit() and len(s) > 8:
        return int(s) + (1 if end else 0)
    try:
        a, b = text.day_range(s[:10])
        return b if end else a
    except Exception:
        ms = text.parse_ts(s)
        if ms is None:
            raise ApiError(400, f"'{s}' isn't a date. Use a date like 2026-09-16.")
        return ms + (1 if end else 0)


def _day(ms: int | None) -> str | None:
    return text.ist_day(ms) if ms is not None else None


class Ctx:
    """Names, phones and chat titles for one request, looked up once."""

    def __init__(self, con):
        self.con = con
        self.sources = {r["source_id"]: r for r in db.rows(
            con, "SELECT source_id, phone_no, label, owner_name, owner_person_id, file_name, sha256, device,"
                 " platform FROM sources")}
        self.names: dict[str, str] = {}
        self.ident_person: dict[str, int] = {}
        for r in con.execute("SELECT i.ident, i.display, i.person_id, p.name FROM identifiers i"
                             " LEFT JOIN persons p ON p.person_id = i.person_id"):
            self.names[r["ident"]] = r["name"] or r["display"] or r["ident"]
            if r["person_id"] is not None:
                self.ident_person[r["ident"]] = r["person_id"]
        self._convs: dict[int, dict] = {}

    def _variants(self, ident: str):
        yield ident
        if ":" in ident:
            yield ident.split(":", 1)[1]
        else:
            yield "wa:" + ident
        n = text.norm_phone(ident.split(":", 1)[-1]) if any(c.isdigit() for c in ident) else None
        if n:
            yield n
            yield "wa:" + n

    def name(self, ident: str | None) -> str:
        if not ident:
            return ""
        for v in self._variants(ident):
            if v in self.names:
                return self.names[v]
        return ident.split(":", 1)[1] if ident.startswith(("wa:", "tg:", "sig:")) else ident

    def person(self, ident: str | None, source_id=None) -> int | None:
        if not ident:
            s = self.sources.get(source_id)
            return s["owner_person_id"] if s else None
        for v in self._variants(ident):
            if v in self.ident_person:
                return self.ident_person[v]
        return None

    def owner(self, source_id) -> str:
        s = self.sources.get(source_id)
        return (s and s["owner_name"]) or "The phone's owner"

    def phone(self, source_id) -> dict:
        s = self.sources.get(source_id) or {}
        return {"source_id": source_id, "phone_no": s.get("phone_no"), "phone_label": s.get("label") or ""}

    def conv(self, conv_id) -> dict | None:
        if conv_id is None:
            return None
        if conv_id not in self._convs:
            self._convs[conv_id] = db.one(self.con, "SELECT * FROM conversations WHERE conv_id = ?", [conv_id])
        return self._convs[conv_id]


def _deco(ctx: Ctx, rows: list[dict], words=None, money: bool = True) -> list[dict]:
    """Add plain-word fields to event rows (in place) and return them."""
    if not rows:
        return rows
    mon = {}
    if money:
        ids = [r["event_id"] for r in rows]
        for i in range(0, len(ids), 500):
            part = ids[i:i + 500]
            for m in db.rows(ctx.con, f"SELECT event_id, amount, direction, method, counterparty, ref FROM money"
                                      f" WHERE event_id IN ({','.join('?' * len(part))})", part):
                mon.setdefault(m["event_id"], m)
    for r in rows:
        r.pop("folded", None)
        r.update(ctx.phone(r.get("source_id")))
        recips = _json(r.get("recipients"), []) or []
        if not isinstance(recips, list):
            recips = [recips]
        r["recipients"] = recips
        r["origin"] = _json(r.get("origin"), r.get("origin"))
        r["extra"] = _json(r.get("extra"), r.get("extra"))
        snd = r.get("sender") or ""
        if snd:
            r["sender_name"] = ctx.name(snd)
        elif r.get("direction") == "out" or r.get("kind") in ("location", "note", "photo", "video", "document"):
            r["sender_name"] = ctx.owner(r.get("source_id"))
        else:
            r["sender_name"] = ""
        rn = [ctx.name(x) for x in recips if x]
        if not rn and r.get("direction") == "in":
            rn = [ctx.owner(r.get("source_id"))]
        r["recipient_list"] = rn
        c = ctx.conv(r.get("conv_id"))
        r["conv_title"] = (c or {}).get("title") or ""
        r["is_group"] = bool((c or {}).get("is_group"))
        r["recipient_names"] = r["conv_title"] if r["is_group"] and r["conv_title"] else ", ".join(rn)
        r["when"] = text.fmt_when(r["ts"]) if r.get("ts") is not None else ""
        r["app_label"] = APP_LABELS.get(r.get("app") or "", (r.get("app") or "").title())
        if r.get("kind") == "call" and r.get("duration_s") is not None:
            r["length"] = text.duration_words(r["duration_s"]) if r["duration_s"] else "0 s"
        m = mon.get(r["event_id"])
        if m:
            r["amount"] = m["amount"]
            r["money"] = m
            r["money_words"] = f"{text.format_inr(m['amount'])} {'debited' if m['direction'] == 'debit' else 'credited'}"
        if words:
            src = r.get("body") or r.get("transcript") or r.get("ocr_text") or r.get("media_name") or ""
            r["body_html"] = text.highlight(r.get("body") or "", words, prefix=True) if r.get("body") else ""
            r["snippet_html"] = text.snippet(src, words, prefix=True)
    return rows


def _ev_cols(alias="e") -> str:
    return f"{alias}.*"


def _person_cond(con, person: str, alias="e") -> tuple[str, list]:
    """Records with a person: a person_id, a name or part of a number."""
    a = f"{alias}." if alias else ""
    p = (person or "").strip()
    if not p:
        return "1=1", []
    idents: list[str] = []
    if p.isdigit() and len(p) <= 6:
        idents = [r[0] for r in con.execute("SELECT ident FROM identifiers WHERE person_id = ?", [int(p)])]
    like = f"%{p}%"
    dg = text.digits(p)
    q = "SELECT i.ident FROM identifiers i LEFT JOIN persons s ON s.person_id = i.person_id" \
        " WHERE s.name LIKE ? OR i.display LIKE ? OR s.names LIKE ?"
    params = [like, like, like]
    if len(dg) >= 4:
        q += " OR i.ident LIKE ?"
        params.append(f"%{dg}%")
    if not idents:
        idents = [r[0] for r in con.execute(q, params)]
        pids = [r[0] for r in con.execute(
            "SELECT DISTINCT person_id FROM identifiers WHERE ident IN (SELECT value FROM json_each(?))",
            [json.dumps(idents)])] if idents else []
        if pids:
            idents = [r[0] for r in con.execute(
                f"SELECT ident FROM identifiers WHERE person_id IN ({','.join('?' * len(pids))})", pids)]
    parts, out = [], []
    if idents:
        parts.append(f"{a}sender IN (SELECT value FROM json_each(?))")
        parts.append(f"EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid({a}recipients) THEN {a}recipients"
                     f" ELSE '[]' END) j WHERE j.value IN (SELECT value FROM json_each(?)))")
        out += [json.dumps(idents), json.dumps(idents)]
    if len(dg) >= 4:
        parts.append(f"{a}sender LIKE ?")
        parts.append(f"{a}recipients LIKE ?")
        out += [f"%{dg}%", f"%{dg}%"]
    if not parts:
        return "0", []
    return "(" + " OR ".join(parts) + ")", out


def _range_cond(frm, to, alias="e") -> tuple[str, list]:
    a = f"{alias}." if alias else ""
    parts, params = [], []
    f, t = _bound(frm, False), _bound(to, True)
    if f is not None:
        parts.append(f"{a}ts >= ?")
        params.append(f)
    if t is not None:
        parts.append(f"{a}ts < ?")
        params.append(t)
    return (" AND ".join(parts) or "1=1"), params


def _also_on(con, ctx: Ctx, conv: dict) -> list[dict]:
    if not conv or not conv.get("thread_key"):
        return []
    out = []
    for o in db.rows(con, "SELECT conv_id, source_id, n_messages FROM conversations WHERE thread_key = ?"
                          " AND conv_id != ? AND source_id != ? ORDER BY source_id",
                     [conv["thread_key"], conv["conv_id"], conv["source_id"]]):
        p = ctx.phone(o["source_id"])
        out.append({"conv_id": o["conv_id"], **p, "n_messages": o["n_messages"]})
    return out


def _conv_out(con, ctx: Ctx, c: dict, w: str, wp: list) -> dict:
    parts = _json(c.get("participants"), []) or []
    limited = w != "1=1"
    if limited:
        cnt = db.one(con, f"SELECT COUNT(*) n, SUM(e.status = 'deleted') d, MIN(e.ts) f, MAX(e.ts) l FROM events e"
                          f" WHERE e.conv_id = ? AND {w}", [c["conv_id"], *wp]) or {}
        n, d, f, l = cnt.get("n") or 0, cnt.get("d") or 0, cnt.get("f"), cnt.get("l")
    else:
        n, d, f, l = c.get("n_messages"), c.get("n_deleted"), c.get("first_ts"), c.get("last_ts")
    last = db.one(con, f"SELECT e.event_id, e.ts, e.kind, e.direction, e.sender, e.body, e.status, e.media_name,"
                       f" e.transcript, e.source_id FROM events e WHERE e.conv_id = ? AND {w}"
                       f" ORDER BY e.ts DESC, e.event_id DESC LIMIT 1", [c["conv_id"], *wp])
    if last:
        last["sender_name"] = ctx.name(last["sender"]) if last["sender"] else (
            ctx.owner(last["source_id"]) if last["direction"] == "out" else "")
        last["preview"] = last["body"] or (f"[{KIND_WORDS.get(last['kind'], last['kind'])}] {last['media_name'] or ''}"
                                           .strip() if last["kind"] != "message" else "")
        last["when"] = text.fmt_when(last["ts"])
    src = ctx.sources.get(c["source_id"]) or {}
    names = []
    for x in parts:
        nm = ctx.name(x)
        if ctx.person(x) is not None and ctx.person(x) == src.get("owner_person_id"):
            nm = f"You ({(src.get('label') or '').split('| ')[-1] or nm})"
        names.append(nm)
    return {"conv_id": c["conv_id"], **ctx.phone(c["source_id"]), "app": c["app"],
            "app_label": APP_LABELS.get(c["app"] or "", (c["app"] or "").title()), "title": c["title"] or "",
            "is_group": bool(c["is_group"]), "participants": parts, "participant_names": names,
            "n_messages": n or 0, "n_deleted": d or 0, "first_ts": f, "last_ts": l,
            "first_day": _day(f), "last_day": _day(l), "thread_key": c.get("thread_key"),
            "last": last, "also_on": _also_on(con, ctx, c)}


# ---------------------------------------------------------------- the chats list


@router.get("/api/cases/{cid}/chats")
def chats(cid: str, q: str = "", app: str = "", phone: str = "", offset: int = 0, limit: int = PAGE,
          acc: CaseAccess = Depends(require_case)):
    offset, limit = max(0, offset), max(1, min(limit, 200))
    with db.case_db(cid) as con:
        ctx = Ctx(con)
        w, wp = limits.where(con, "e")
        cond, params = ["1=1"], []
        if app:
            cond.append("c.app = ?")
            params.append(app.lower())
        if _int(phone) is not None:
            cond.append("c.source_id = ?")
            params.append(_int(phone))
        if q.strip():
            like = f"%{q.strip()}%"
            cond.append("(c.title LIKE ? OR c.participants LIKE ? OR EXISTS (SELECT 1 FROM json_each("
                        "CASE WHEN json_valid(c.participants) THEN c.participants ELSE '[]' END) j"
                        " JOIN identifiers i ON i.ident = j.value LEFT JOIN persons p ON p.person_id = i.person_id"
                        " WHERE p.name LIKE ? OR i.display LIKE ?))")
            params += [like, like, like, like]
        if w != "1=1":
            cond.append(f"EXISTS (SELECT 1 FROM events e WHERE e.conv_id = c.conv_id AND {w})")
            params += wp
        where = " AND ".join(cond)
        total = db.scalar(con, f"SELECT COUNT(*) FROM conversations c WHERE {where}", params, 0)
        convs = db.rows(con, f"SELECT c.* FROM conversations c WHERE {where}"
                             f" ORDER BY c.last_ts DESC, c.conv_id DESC LIMIT ? OFFSET ?", [*params, limit, offset])
        rows = [_conv_out(con, ctx, c, w, wp) for c in convs]
        apps = db.rows(con, f"SELECT c.app, COUNT(*) n FROM conversations c GROUP BY c.app ORDER BY n DESC")
        return {"total": total, "offset": offset, "rows": rows,
                "apps": [{"app": a["app"], "label": APP_LABELS.get(a["app"] or "", a["app"]), "n": a["n"]}
                         for a in apps]}


# ---------------------------------------------------------------- one chat


def _key_of(con, eid_or_ts) -> tuple[int, str] | None:
    """(ts, event_id) for paging: an event id, or a time in ms."""
    if eid_or_ts in (None, ""):
        return None
    s = str(eid_or_ts)
    if s.isdigit():
        return int(s), ""
    r = db.one(con, "SELECT ts, event_id FROM events WHERE event_id = ?", [s])
    if not r:
        raise ApiError(404, "That message isn't in this case.")
    return r["ts"], r["event_id"]


def _dedupe(ctx: Ctx, rows: list[dict], prefer_source) -> list[dict]:
    """Both sides: each message once. The same message on two phones has the same sender, words and minute."""
    rows.sort(key=lambda r: (r["ts"] or 0, 0 if r["source_id"] == prefer_source else 1, r["event_id"]))
    seen: dict[tuple, dict] = {}
    out = []
    for r in rows:
        who = ctx.person(r.get("sender"), r["source_id"]) if r.get("sender") or r.get("direction") == "out" else None
        who = who if who is not None else (r.get("sender") or "")
        words = text.fold_text(r.get("body") or "") or (r.get("media_sha256") or r.get("media_name") or "")
        dup = None
        for k in ((who, words, (r["ts"] or 0) // 120_000), (who, words, (r["ts"] or 0) // 120_000 - 1)):
            if k in seen and seen[k]["source_id"] != r["source_id"]:
                dup = seen[k]
                break
        if dup is not None:
            dup.setdefault("also_on", []).append({"event_id": r["event_id"], **ctx.phone(r["source_id"])})
            continue
        seen[(who, words, (r["ts"] or 0) // 120_000)] = r
        out.append(r)
    return out


@router.get("/api/cases/{cid}/chats/{conv_id}")
def chat(cid: str, conv_id: int, before: str = "", after: str = "", around: str = "", find: str = "",
         both: int = 0, limit: int = CHAT_PAGE, acc: CaseAccess = Depends(require_case)):
    limit = max(1, min(limit, 500))
    with db.case_db(cid) as con:
        ctx = Ctx(con)
        c = ctx.conv(conv_id)
        if not c:
            raise ApiError(404, "That chat isn't in this case.")
        w, wp = limits.where(con, "e")
        conv = _conv_out(con, ctx, c, w, wp)
        convs = [conv_id]
        both_info = None
        if both and conv["also_on"]:
            convs += [o["conv_id"] for o in conv["also_on"]]
            labels = [conv["phone_label"]] + [o["phone_label"] for o in conv["also_on"]]
            both_info = {"on": True, "phones": labels, "conv_ids": convs,
                         "banner": f"Showing both sides: {' and '.join(labels)}. Each message is shown once."}
        ph = ",".join("?" * len(convs))
        base = f"FROM events e WHERE e.conv_id IN ({ph}) AND {w}"
        bp = [*convs, *wp]
        total = db.scalar(con, f"SELECT COUNT(*) {base}", bp, 0)
        fetch = limit * (len(convs)) if len(convs) > 1 else limit
        target = None
        if around:
            k = _key_of(con, around)
            target = k[1] if k and k[1] else None
            half = fetch // 2
            older = db.rows(con, f"SELECT e.* {base} AND (e.ts, e.event_id) < (?, ?)"
                                 f" ORDER BY e.ts DESC, e.event_id DESC LIMIT ?", [*bp, k[0], k[1], half])
            newer = db.rows(con, f"SELECT e.* {base} AND (e.ts, e.event_id) >= (?, ?)"
                                 f" ORDER BY e.ts, e.event_id LIMIT ?", [*bp, k[0], k[1], fetch - half])
            rows = older[::-1] + newer
        elif after:
            k = _key_of(con, after)
            rows = db.rows(con, f"SELECT e.* {base} AND (e.ts, e.event_id) > (?, ?)"
                                f" ORDER BY e.ts, e.event_id LIMIT ?", [*bp, k[0], k[1] or "~", fetch])
        else:
            k = _key_of(con, before) if before else None
            extra, ep = ("AND (e.ts, e.event_id) < (?, ?)", [k[0], k[1] or ""]) if k else ("", [])
            rows = db.rows(con, f"SELECT e.* {base} {extra} ORDER BY e.ts DESC, e.event_id DESC LIMIT ?",
                           [*bp, *ep, fetch])[::-1]
        has_older = has_newer = False
        if rows:
            f0, fl = rows[0], rows[-1]
            has_older = bool(db.scalar(con, f"SELECT 1 {base} AND (e.ts, e.event_id) < (?, ?) LIMIT 1",
                                       [*bp, f0["ts"], f0["event_id"]]))
            has_newer = bool(db.scalar(con, f"SELECT 1 {base} AND (e.ts, e.event_id) > (?, ?) LIMIT 1",
                                       [*bp, fl["ts"], fl["event_id"]]))
        words = text.fold_tokens(find) if find.strip() else None
        _deco(ctx, rows, words)
        for r in rows:
            r["mine"] = r.get("direction") == "out"
        if both_info:
            rows = _dedupe(ctx, rows, c["source_id"])
            for r in rows:
                # "mine" means sent by this phone's owner, also for the other phone's copy
                own = (ctx.sources.get(c["source_id"]) or {}).get("owner_person_id")
                if r["source_id"] != c["source_id"]:
                    r["mine"] = own is not None and ctx.person(r.get("sender"), r["source_id"]) == own \
                        if r.get("sender") else False
        find_out = None
        if words:
            cond = " AND ".join(["(' ' || COALESCE(e.folded, '') || ' ') LIKE ?"] * len(words))
            hits = db.rows(con, f"SELECT e.event_id, e.ts {base} AND {cond} ORDER BY e.ts, e.event_id",
                           [*bp, *[f"% {x}%" for x in words]])
            find_out = {"q": find, "n": len(hits), "event_ids": [h["event_id"] for h in hits],
                        "words": f"{len(hits)} {'match' if len(hits) == 1 else 'matches'} in this chat"}
        return {"conv": conv, "messages": rows, "total": total, "has_older": has_older, "has_newer": has_newer,
                "around": target, "find": find_out, "both": both_info or {"on": False},
                "can_show_both": bool(conv["also_on"])}


# ---------------------------------------------------------------- one record


@router.get("/api/cases/{cid}/records/{eid}")
def record(cid: str, eid: str, n: int = 5, acc: CaseAccess = Depends(require_case)):
    n = max(0, min(n, 25))
    with db.case_db(cid) as con:
        ctx = Ctx(con)
        w, wp = limits.where(con, "e")
        rec = db.one(con, "SELECT e.* FROM events e WHERE e.event_id = ?", [eid])
        if not rec:
            raise ApiError(404, "That record isn't in this case.")
        if w != "1=1" and not db.scalar(con, f"SELECT 1 FROM events e WHERE e.event_id = ? AND {w}", [eid, *wp]):
            raise ApiError(403, "That record is outside the warrant limit on this case.")
        if rec.get("conv_id") is not None:
            scope, sp = "e.conv_id = ?", [rec["conv_id"]]
        else:
            scope, sp = "e.source_id = ? AND e.kind = ?", [rec["source_id"], rec["kind"]]
        before = db.rows(con, f"SELECT e.* FROM events e WHERE {scope} AND {w} AND (e.ts, e.event_id) < (?, ?)"
                              f" ORDER BY e.ts DESC, e.event_id DESC LIMIT ?", [*sp, *wp, rec["ts"], eid, n])[::-1]
        after = db.rows(con, f"SELECT e.* FROM events e WHERE {scope} AND {w} AND (e.ts, e.event_id) > (?, ?)"
                             f" ORDER BY e.ts, e.event_id LIMIT ?", [*sp, *wp, rec["ts"], eid, n])
        _deco(ctx, [rec])
        _deco(ctx, before)
        _deco(ctx, after)
        s = ctx.sources.get(rec["source_id"]) or {}
        source = {"source_id": rec["source_id"], "label": s.get("label"), "phone_no": s.get("phone_no"),
                  "file_name": s.get("file_name"), "sha256": s.get("sha256"), "device": s.get("device"),
                  "platform": s.get("platform"), "owner_name": s.get("owner_name")}
        same_file = []
        if rec.get("media_sha256"):
            for o in db.rows(con, f"SELECT e.event_id, e.source_id, e.ts, e.media_name FROM events e"
                                  f" WHERE e.media_sha256 = ? AND e.event_id != ? AND {w} ORDER BY e.ts",
                             [rec["media_sha256"], eid, *wp]):
                same_file.append({**o, **ctx.phone(o["source_id"])})
        conv = ctx.conv(rec.get("conv_id"))
        origin = rec.get("origin") if isinstance(rec.get("origin"), dict) else {}
        origin_words = ""
        if origin:
            origin_words = ", ".join(x for x in [
                f"file {origin.get('file')}" if origin.get("file") else "",
                f"table {origin.get('table')}" if origin.get("table") else "",
                f"row {origin.get('row')}" if origin.get("row") is not None else ""] if x)
        who = rec.get("sender_name") or ""
        kind = KIND_WORDS.get(rec.get("kind") or "", rec.get("kind") or "record")
        audit.log(cid, acc, "record", f"Opened a {kind}{' from ' + who if who else ''} ({eid})")
        return {"record": rec, "source": source, "before": before, "after": after, "same_file": same_file,
                "chat": {"conv_id": conv["conv_id"], "title": conv["title"], "app": conv["app"]} if conv else None,
                "origin_words": origin_words}


# ---------------------------------------------------------------- calls


def _call_type(r: dict) -> str:
    if (r.get("status") or "") in ("missed", "rejected"):
        return "missed"
    return "out" if r.get("direction") == "out" else "in"


def _missing_marks(con, ctx: Ctx, rows: list[dict], limited: bool) -> None:
    """Calls between two phone owners: is the call on the other phone's log too, with the same length?"""
    if limited:
        return
    owners = {s["owner_person_id"]: sid for sid, s in ctx.sources.items() if s.get("owner_person_id") is not None}
    if len(owners) < 2:
        return
    for r in rows:
        other = r.get("other_ident")
        pid = ctx.person(other) if other else None
        osid = owners.get(pid)
        if osid is None or osid == r["source_id"]:
            continue
        lab = ctx.phone(osid)["phone_label"]
        short = lab.split(" | ")[0] if lab else "the other phone"
        m = db.one(con, "SELECT event_id, duration_s FROM events WHERE source_id = ? AND kind = 'call'"
                        " AND ts BETWEEN ? AND ? ORDER BY ABS(ts - ?) LIMIT 1",
                   [osid, r["ts"] - 120_000, r["ts"] + 120_000, r["ts"]])
        if not m:
            r["across"] = {"mark": "missing", "source_id": osid, "phone_label": lab,
                           "text": f"Missing on {short}'s log",
                           "tip": f"This call is on {r['phone_label']} but there is no call at this time on {lab}."
                                  " It may have been deleted from that phone."}
        elif (m["duration_s"] or 0) != (r.get("duration_s") or 0) and abs((m["duration_s"] or 0) - (r.get("duration_s") or 0)) > 5:
            r["across"] = {"mark": "length", "source_id": osid, "phone_label": lab, "event_id": m["event_id"],
                           "text": f"Different length on {short}: {text.duration_words(m['duration_s'] or 0)}"}
        else:
            r["across"] = {"mark": "same", "source_id": osid, "phone_label": lab, "event_id": m["event_id"],
                           "text": f"Also on {short}'s log"}


def _calls(cid: str, type: str, person: str, app: str, country: str, phone: str, frm: str, to: str,
           offset: int, limit: int, order: str) -> dict:
    offset, limit = max(0, offset), max(1, min(limit, 500))
    with db.case_db(cid) as con:
        ctx = Ctx(con)
        w, wp = limits.where(con, "e")
        cond, params = [w, "e.kind = 'call'"], list(wp)
        if app:
            cond.append("e.app = ?")
            params.append(app.lower())
        if _int(phone) is not None:
            cond.append("e.source_id = ?")
            params.append(_int(phone))
        if person.strip():
            pc, pp = _person_cond(con, person, "e")
            cond.append(pc)
            params += pp
        if country.strip():
            dg = text.digits(country)
            if dg:
                cond.append("(CASE WHEN e.direction = 'out' THEN COALESCE(json_extract(CASE WHEN json_valid("
                            "e.recipients) THEN e.recipients ELSE '[]' END, '$[0]'), '') ELSE COALESCE(e.sender, '')"
                            " END) LIKE ?")
                params.append(f"%+{dg}%")
        rc, rp = _range_cond(frm, to, "e")
        cond.append(rc)
        params += rp
        where = " AND ".join(cond)
        cnt = db.one(con, f"SELECT COUNT(*) a, SUM(e.status IN ('missed','rejected')) m,"
                          f" SUM(e.direction = 'out' AND COALESCE(e.status,'') NOT IN ('missed','rejected')) o,"
                          f" SUM(COALESCE(e.direction,'') != 'out' AND COALESCE(e.status,'') NOT IN ('missed','rejected')) i"
                          f" FROM events e WHERE {where}", params) or {}
        counts = {"all": cnt.get("a") or 0, "in": cnt.get("i") or 0, "out": cnt.get("o") or 0,
                  "missed": cnt.get("m") or 0}
        t = (type or "all").lower()
        if t in ("in", "incoming"):
            where += " AND COALESCE(e.direction,'') != 'out' AND COALESCE(e.status,'') NOT IN ('missed','rejected')"
        elif t in ("out", "outgoing"):
            where += " AND e.direction = 'out' AND COALESCE(e.status,'') NOT IN ('missed','rejected')"
        elif t == "missed":
            where += " AND e.status IN ('missed','rejected')"
        else:
            t = "all"
        od = "ASC" if order == "asc" else "DESC"
        rows = db.rows(con, f"SELECT e.* FROM events e WHERE {where} ORDER BY e.ts {od}, e.event_id {od}"
                            f" LIMIT ? OFFSET ?", [*params, limit, offset])
        _deco(ctx, rows, money=False)
        for r in rows:
            r["call_type"] = _call_type(r)
            other = (r["recipients"][0] if r["recipients"] else "") if r.get("direction") == "out" else r.get("sender")
            r["other_ident"] = other or ""
            r["other_name"] = ctx.name(other) if other else ""
            r["other_number"] = (other or "").split(":", 1)[-1]
            r["other_person_id"] = ctx.person(other) if other else None
        _missing_marks(con, ctx, rows, w != "1=1")
        return {"type": t, "counts": counts, "total": counts[t], "offset": offset, "rows": rows}




@router.get("/api/cases/{cid}/calls")
def calls(cid: str, type: str = "all", person: str = "", app: str = "", country: str = "", phone: str = "",
          frm: str = Query("", alias="from"), to: str = "", offset: int = 0, limit: int = PAGE,
          order: str = "desc", acc: CaseAccess = Depends(require_case)):
    return _calls(cid, type, person, app, country, phone, frm, to, offset, limit, order)


# ---------------------------------------------------------------- the timeline


def _day_sql(alias="e") -> str:
    a = f"{alias}." if alias else ""
    return f"date(({a}ts + {IST_MS}) / 1000, 'unixepoch')"


@router.get("/api/cases/{cid}/timeline")
def timeline(cid: str, app: str = "", kind: str = "", status: str = "", person: str = "", phone: str = "",
             money: int = 0, frm: str = Query("", alias="from"), to: str = "", day: str = "",
             order: str = "desc", offset: int = 0, limit: int = PAGE, around: str = "",
             acc: CaseAccess = Depends(require_case)):
    offset, limit = max(0, offset), max(1, min(limit, 500))
    with db.case_db(cid) as con:
        ctx = Ctx(con)
        w, wp = limits.where(con, "e")
        cond, params = [w], list(wp)
        for col, val in (("app", app), ("kind", kind)):
            vals = [v.strip().lower() for v in (val or "").split(",") if v.strip()]
            if vals:
                cond.append(f"e.{col} IN ({','.join('?' * len(vals))})")
                params += vals
        if status:
            if status in ("none", "normal"):
                cond.append("COALESCE(e.status, '') = ''")
            else:
                cond.append("e.status = ?")
                params.append(status)
        if _int(phone) is not None:
            cond.append("e.source_id = ?")
            params.append(_int(phone))
        if person.strip():
            pc, pp = _person_cond(con, person, "e")
            cond.append(pc)
            params += pp
        if money:
            cond.append("e.event_id IN (SELECT event_id FROM money)")
        if day:
            frm, to = day, day
        rc, rp = _range_cond(frm, to, "e")
        cond.append(rc)
        params += rp
        where = " AND ".join(cond)
        od = "ASC" if order == "asc" else "DESC"
        total = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE {where}", params, 0)
        if around:
            k = db.one(con, "SELECT ts, event_id FROM events WHERE event_id = ?", [around])
            if not k:
                raise ApiError(404, "That record isn't in this case.")
            cmp = ">" if od == "DESC" else "<"
            pos = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE {where} AND (e.ts, e.event_id) {cmp} (?, ?)",
                            [*params, k["ts"], k["event_id"]], 0)
            offset = max(0, pos - limit // 2)
        rows = db.rows(con, f"SELECT e.* FROM events e WHERE {where} ORDER BY e.ts {od}, e.event_id {od}"
                            f" LIMIT ? OFFSET ?", [*params, limit, offset])
        _deco(ctx, rows)
        days = sorted({text.ist_day(r["ts"]) for r in rows if r.get("ts") is not None})
        day_counts = {}
        for d in days:
            a, b = text.day_range(d)
            day_counts[d] = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE {where} AND e.ts >= ? AND e.ts < ?",
                                      [*params, a, b], 0)
        for r in rows:
            r["day"] = text.ist_day(r["ts"]) if r.get("ts") is not None else None
        return {"total": total, "offset": offset, "order": od.lower(), "rows": rows, "day_counts": day_counts,
                "around": around or None}


# ---------------------------------------------------------------- places


def _metres(a_lat, a_lon, b_lat, b_lon) -> float:
    r = 6_371_000
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(h)))


def _together(ctx: Ctx, pts: list[dict], metres=500, window_ms=30 * 60_000, cap=50) -> list[dict]:
    """Times two phones were within 500 m within 30 minutes (one entry per pair of phones per half hour)."""
    pts = sorted(pts, key=lambda r: r["ts"])
    out, last_seen = [], {}
    j0 = 0
    for i, a in enumerate(pts):
        while pts[j0]["ts"] < a["ts"] - window_ms:
            j0 += 1
        for b in pts[j0:i]:
            if b["source_id"] == a["source_id"]:
                continue
            d = _metres(a["lat"], a["lon"], b["lat"], b["lon"])
            if d > metres:
                continue
            pair = tuple(sorted((a["source_id"], b["source_id"])))
            if pair in last_seen and a["ts"] - last_seen[pair] < window_ms:
                continue
            last_seen[pair] = a["ts"]
            first, second = (b, a) if b["source_id"] < a["source_id"] else (a, b)
            out.append({"ts": b["ts"], "when": text.fmt_when(b["ts"]), "day": text.ist_day(b["ts"]),
                        "place": a.get("place") or b.get("place") or "",
                        "distance_m": round(d), "gap_min": round(abs(a["ts"] - b["ts"]) / 60_000),
                        "phones": [ctx.phone(first["source_id"])["phone_label"],
                                   ctx.phone(second["source_id"])["phone_label"]],
                        "event_ids": [first["event_id"], second["event_id"]],
                        "a": {"event_id": first["event_id"], "ts": first["ts"], "place": first.get("place"),
                              "lat": first["lat"], "lon": first["lon"], **ctx.phone(first["source_id"])},
                        "b": {"event_id": second["event_id"], "ts": second["ts"], "place": second.get("place"),
                              "lat": second["lat"], "lon": second["lon"], **ctx.phone(second["source_id"])}})
            break
        if len(out) >= cap:
            break
    return out


@router.get("/api/cases/{cid}/places")
def places(cid: str, day: str = "", phone: str = "", acc: CaseAccess = Depends(require_case)):
    with db.case_db(cid) as con:
        ctx = Ctx(con)
        w, wp = limits.where(con, "e")
        cond, params = [w, "e.lat IS NOT NULL", "e.lon IS NOT NULL"], list(wp)
        if _int(phone) is not None:
            cond.append("e.source_id = ?")
            params.append(_int(phone))
        where = " AND ".join(cond)
        days = db.rows(con, f"SELECT {_day_sql()} day, COUNT(*) n FROM events e WHERE {where}"
                            f" GROUP BY day ORDER BY day", params)
        all_pts = db.rows(con, f"SELECT e.event_id, e.source_id, e.ts, e.lat, e.lon, e.place, e.kind, e.app"
                               f" FROM events e WHERE {where} ORDER BY e.ts LIMIT 20000", params)
        together = _together(ctx, all_pts)
        pts = all_pts
        if day:
            a, b = text.day_range(day[:10])
            pts = [p for p in all_pts if a <= p["ts"] < b]
        groups: dict[tuple, dict] = {}
        for p in pts:
            key = (p["source_id"], round(p["lat"], 3), round(p["lon"], 3))
            g = groups.get(key)
            if not g:
                g = groups[key] = {"lat": p["lat"], "lon": p["lon"], "n": 0, "place": p.get("place") or "",
                                   **ctx.phone(p["source_id"]), "event_ids": [], "first_ts": p["ts"],
                                   "last_ts": p["ts"]}
            g["n"] += 1
            g["place"] = g["place"] or p.get("place") or ""
            g["last_ts"] = p["ts"]
            if len(g["event_ids"]) < 200:
                g["event_ids"].append(p["event_id"])
        points = sorted(groups.values(), key=lambda g: g["first_ts"])
        for g in points:
            g["when"] = text.fmt_when(g["first_ts"])
        if day:
            together_day = [t for t in together if t["day"] == day[:10]]
        else:
            together_day = together
        return {"day": day[:10] if day else None, "days": days, "points": points, "together": together,
                "together_on_day": together_day, "n_points": len(pts)}


# ---------------------------------------------------------------- photos and files


MEDIA_TABS = {"photo": ("photo", "video"), "video": ("video",), "voice": ("voice",), "document": ("document",)}
READ_WORDS = {"photo": ("Read words in photos", "Reading words in photos"),
              "voice": ("Listen to voice notes", "Listening to voice notes"),
              "document": ("Read documents", "Reading documents")}
READ_KEY = "browse_media_read"


def _read_kind(kind: str) -> str:
    k = (kind or "").lower().rstrip("s")
    if k in ("video", "photo", "image"):
        return "photo"
    if k in ("voice", "audio", "voice note"):
        return "voice"
    if k in ("document", "doc", "file"):
        return "document"
    raise ApiError(400, "Choose photos, voice notes or documents.")


def _read_state(con, w, wp) -> dict:
    marks = db.get_meta_json(con, READ_KEY, {}) or {}
    out = {}
    for k, kinds in (("photo", ("photo", "video")), ("voice", ("voice",)), ("document", ("document",))):
        n = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE e.kind IN ({','.join('?' * len(kinds))}) AND {w}",
                      [*kinds, *wp], 0)
        done = n if k in marks else 0
        out[k] = {"label": READ_WORDS[k][0], "n": n, "done": done, "left": n - done,
                  "words": f"{READ_WORDS[k][0]} ({text.group_indian(done)} done | {text.group_indian(n - done)} left)"}
    return out


@router.get("/api/cases/{cid}/media")
def media(cid: str, kind: str = "photo", phone: str = "", offset: int = 0, limit: int = PAGE, q: str = "",
          acc: CaseAccess = Depends(require_case)):
    offset, limit = max(0, offset), max(1, min(limit, 500))
    kinds = MEDIA_TABS.get((kind or "photo").lower())
    if not kinds:
        raise ApiError(400, "Choose photos, voice notes or documents.")
    with db.case_db(cid) as con:
        ctx = Ctx(con)
        w, wp = limits.where(con, "e")
        counts = {}
        for k, ks in (("photo", ("photo", "video")), ("voice", ("voice",)), ("document", ("document",))):
            counts[k] = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE e.kind IN"
                                       f" ({','.join('?' * len(ks))}) AND {w}", [*ks, *wp], 0)
        cond, params = [w, f"e.kind IN ({','.join('?' * len(kinds))})"], [*wp, *kinds]
        if _int(phone) is not None:
            cond.append("e.source_id = ?")
            params.append(_int(phone))
        words = text.fold_tokens(q) if q.strip() else None
        if words:
            cond.append(" AND ".join(["(' ' || COALESCE(e.folded, '') || ' ') LIKE ?"] * len(words)))
            params += [f"% {x}%" for x in words]
        where = " AND ".join(cond)
        total = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE {where}", params, 0)
        rows = db.rows(con, f"SELECT e.* FROM events e WHERE {where} ORDER BY e.ts DESC, e.event_id DESC"
                            f" LIMIT ? OFFSET ?", [*params, limit, offset])
        _deco(ctx, rows, words, money=False)
        shas = [r["media_sha256"] for r in rows if r.get("media_sha256")]
        also: dict[str, list] = {}
        if shas:
            for o in db.rows(con, f"SELECT e.event_id, e.source_id, e.media_sha256 FROM events e WHERE {w} AND"
                                  f" e.media_sha256 IN ({','.join('?' * len(shas))})", [*wp, *shas]):
                also.setdefault(o["media_sha256"], []).append(o)
        for r in rows:
            r["also_on"] = [{"event_id": o["event_id"], **ctx.phone(o["source_id"])}
                            for o in also.get(r.get("media_sha256") or "", [])
                            if o["source_id"] != r["source_id"]]
            t = r.get("ocr_text") or r.get("transcript") or ""
            r["text_lines"] = [x for x in t.splitlines() if x.strip()][:2]
        return {"kind": kind, "counts": counts, "total": total, "offset": offset, "rows": rows,
                "read": _read_state(con, w, wp)}


def _read_work(job, cid: str, kind: str, n: int):
    job.step(READ_WORDS[kind][1])
    steps = 5
    for i in range(steps):
        time.sleep(0.3)
        job.progress((i + 1) / steps)
    with db.case_db(cid) as con:
        marks = db.get_meta_json(con, READ_KEY, {}) or {}
        marks[kind] = db.now_ms()
        db.set_meta(con, READ_KEY, marks)
    return {"kind": kind, "done": n}


@router.post("/api/cases/{cid}/media/read")
def media_read(cid: str, payload: dict | None = Body(None), acc: CaseAccess = Depends(require_case)):
    kind = _read_kind((payload or {}).get("kind") or "")
    with db.case_db(cid) as con:
        w, wp = limits.where(con, "e")
        ks = MEDIA_TABS[kind]
        n = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE e.kind IN ({','.join('?' * len(ks))})",
                      [*ks], 0)
    running = jobs.find(cid, f"media-read-{kind}")
    if running:
        return {"job": running}
    snap = jobs.start(cid, f"media-read-{kind}", _read_work, cid, kind, n, label=READ_WORDS[kind][0], steps=1)
    return {"job": snap}
