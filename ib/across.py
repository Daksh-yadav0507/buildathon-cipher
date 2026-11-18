"""Across phones: the cross-phone checks, worked out by code only (no AI), exact, every line pointing at its records.

GET /api/cases/{cid}/across -> {phones, enabled, note, limited, updating, headers, chats, together, money, files, calls,
names, money_totals, known_by_several}

Every row carries `event_ids` (all the records behind it, on every phone) and a plain `text` sentence. These are leads
to check, not findings. While a warrant limit is on, only records inside it are compared and nothing is called
missing; the answer is then worked out fresh and never saved.
"""
from __future__ import annotations

import bisect
import json
import math
import threading
from typing import Any

from fastapi import APIRouter, Depends

from ib import db, limits, text
from ib.officers import CaseAccess, require_case

try:
    from ib import ready as _ready
except Exception:  # noqa: BLE001 - work without it
    _ready = None

router = APIRouter()

READY_NAME = "across"
NOTE = "Compared by code, with no AI. These are leads to check, not findings."

MONEY_WINDOW_MS = 30 * 60 * 1000
MONEY_TALK_MS = 2 * 60 * 60 * 1000
CALL_WINDOW_MS = 2 * 60 * 1000
CALL_LENGTH_DIFF = 0.20
PLACE_METRES = 500.0
PLACE_WINDOW_MS = 30 * 60 * 1000
PLACE_CLUSTER_MS = 60 * 60 * 1000
CHAT_WINDOW_MS = 60 * 1000
FILE_MIN_BYTES = 10 * 1024
MAX_ROWS = 60

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(cid: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(cid, threading.Lock())


# ============================================================== who is who


def _key(ident: str | None) -> str | None:
    """One comparable key for an identifier: a phone number in +91 form, else the identifier in lower case."""
    if not ident:
        return None
    s = str(ident).strip()
    if not s:
        return None
    p = text.norm_phone(s)
    if p:
        return p
    low = s.lower()
    for pre in ("email:", "upi:", "wa:", "tg:"):
        if low.startswith(pre):
            return low
    return low


def _json_list(value: Any) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        v = json.loads(value)
    except (TypeError, ValueError):
        return [value]
    return v if isinstance(v, list) else [v]


class Ctx:
    """The phones in the case, their owners, and a map from any identifier to a person."""

    def __init__(self, con):
        self.con = con
        self.limit_on = limits.get_limit(con) is not None
        self.w, self.p = limits.where(con, "e")
        self.key_person: dict[str, int] = {}
        for r in con.execute("SELECT ident, person_id FROM identifiers WHERE person_id IS NOT NULL"):
            k = _key(r["ident"])
            if k:
                self.key_person.setdefault(k, r["person_id"])
            self.key_person.setdefault(str(r["ident"]).lower(), r["person_id"])
        self.person_name = {r["person_id"]: r["name"] for r in con.execute("SELECT person_id, name FROM persons")}
        srcs = db.rows(con, "SELECT source_id, phone_no, label, owner_name, owner_person_id, first_ts, last_ts, status"
                            " FROM sources WHERE COALESCE(status, '') != 'failed' ORDER BY phone_no, source_id")
        self.phones: dict[int, dict] = {}
        for s in srcs:
            no = s["phone_no"] or s["source_id"]
            span = db.one(con, "SELECT MIN(ts) a, MAX(ts) b FROM events WHERE source_id = ?", [s["source_id"]]) or {}
            self.phones[s["source_id"]] = {
                "source_id": s["source_id"], "phone_no": no,
                "label": s["label"] or f"Phone {no}", "short": f"Phone {no}",
                "owner_name": s["owner_name"] or self.person_name.get(s["owner_person_id"]) or "",
                "owner_person_id": s["owner_person_id"],
                "first_ts": s["first_ts"] or span.get("a"), "last_ts": s["last_ts"] or span.get("b"),
            }
        self.owner_of = {sid: ph["owner_person_id"] for sid, ph in self.phones.items() if ph["owner_person_id"]}
        self.source_of_owner: dict[int, list[int]] = {}
        for sid, pid in self.owner_of.items():
            self.source_of_owner.setdefault(pid, []).append(sid)

    @property
    def enabled(self) -> bool:
        return len(set(self.owner_of.values())) >= 2

    def person(self, ident: str | None) -> int | None:
        if not ident:
            return None
        k = _key(ident)
        if k and k in self.key_person:
            return self.key_person[k]
        return self.key_person.get(str(ident).strip().lower())

    def parties(self, sender: str | None, recipients: Any) -> set[int]:
        out = set()
        for ident in [sender, *_json_list(recipients)]:
            pid = self.person(ident if isinstance(ident, str) else str(ident or ""))
            if pid is not None:
                out.add(pid)
        return out

    def name(self, pid: int | None) -> str:
        return self.person_name.get(pid) or "someone"

    def public_phones(self) -> list[dict]:
        return [{k: ph[k] for k in ("source_id", "phone_no", "label", "owner_name", "owner_person_id", "first_ts", "last_ts")}
                for ph in self.phones.values()]

    def in_span(self, sid: int, ts: int) -> bool:
        ph = self.phones.get(sid) or {}
        a, b = ph.get("first_ts"), ph.get("last_ts")
        return a is not None and b is not None and a < ts < b


def _phone_ref(ctx: Ctx, sid: int) -> dict:
    ph = ctx.phones[sid]
    return {"source_id": sid, "phone_no": ph["phone_no"], "label": ph["label"]}


# ============================================================== 3. money between the phones


def _name_words(name: str | None) -> set[str]:
    return {w for w in text.fold_tokens(name or "") if len(w) >= 3}


def _names_match(counterparty: str | None, cp_ident: str | None, ctx: Ctx, pid: int | None) -> bool:
    if pid is None:
        return False
    if cp_ident and ctx.person(cp_ident) == pid:
        return True
    want = _name_words(ctx.name(pid))
    got = _name_words(counterparty)
    return bool(want and got and (want & got) and len(want & got) >= min(2, len(want)))


def check_money(ctx: Ctx) -> tuple[list[dict], list[dict]]:
    con, w, p = ctx.con, ctx.w, ctx.p
    rows = db.rows(con, f"""
        SELECT m.money_id, m.event_id, m.source_id, COALESCE(m.ts, e.ts) AS ts, m.amount, m.direction, m.method,
               m.counterparty, m.counterparty_ident, m.ref, e.body
        FROM money m JOIN events e ON e.event_id = m.event_id
        WHERE {w} AND COALESCE(m.said_in_chat, 0) = 0 AND m.amount IS NOT NULL AND m.amount > 0
        ORDER BY ts""", p)
    rows = [r for r in rows if r["source_id"] in ctx.phones and r["ts"] is not None]
    debits = [r for r in rows if (r["direction"] or "").lower() == "debit"]
    credits = [r for r in rows if (r["direction"] or "").lower() == "credit"]
    credit_ts = [c["ts"] for c in credits]
    used: set[int] = set()
    matches: list[dict] = []
    for d in debits:
        lo = bisect.bisect_left(credit_ts, d["ts"] - MONEY_WINDOW_MS)
        hi = bisect.bisect_right(credit_ts, d["ts"] + MONEY_WINDOW_MS)
        best, best_score = None, None
        for c in credits[lo:hi]:
            if c["money_id"] in used or c["source_id"] == d["source_id"]:
                continue
            if ctx.owner_of.get(c["source_id"]) is not None and ctx.owner_of.get(c["source_id"]) == ctx.owner_of.get(d["source_id"]):
                continue
            if abs(float(c["amount"]) - float(d["amount"])) > 1.0:
                continue
            names = int(_names_match(d["counterparty"], d["counterparty_ident"], ctx, ctx.owner_of.get(c["source_id"])))
            names += int(_names_match(c["counterparty"], c["counterparty_ident"], ctx, ctx.owner_of.get(d["source_id"])))
            same_ref = int(bool(d["ref"] and c["ref"] and str(d["ref"]) == str(c["ref"])))
            score = (names + same_ref, int(c["ts"] >= d["ts"]), -abs(c["ts"] - d["ts"]))
            if best_score is None or score > best_score:
                best, best_score = c, score
        if best is None:
            continue
        used.add(best["money_id"])
        matches.append(_money_row(ctx, d, best, best_score[0]))
    totals: dict[tuple, dict] = {}
    for m in matches:
        k = (m["from_phone"]["source_id"], m["to_phone"]["source_id"])
        t = totals.setdefault(k, {"from_phone": m["from_phone"], "to_phone": m["to_phone"], "n": 0, "total": 0.0,
                                  "event_ids": []})
        t["n"] += 1
        t["total"] += m["amount"]
        t["event_ids"].extend(m["event_ids"][:2])
    tot_rows = []
    for t in totals.values():
        t["total_text"] = text.format_inr(t["total"])
        t["text"] = (f"{t['total_text']} from {t['from_phone']['label']} to {t['to_phone']['label']} in "
                     f"{text.plural(t['n'], 'matched payment')}")
        tot_rows.append(t)
    tot_rows.sort(key=lambda t: -t["total"])
    return matches[:MAX_ROWS], tot_rows


def _money_row(ctx: Ctx, d: dict, c: dict, strength: int) -> dict:
    a, b = d["source_id"], c["source_id"]
    gap = c["ts"] - d["ts"]
    amount = float(d["amount"])
    if abs(gap) < 30_000:
        when_words = "within a minute"
    elif gap >= 0:
        when_words = f"{text.gap_words(gap)} later"
    else:
        when_words = f"{text.gap_words(gap)} earlier"
    left = f"{d['method'] or 'payment'} to {d['counterparty']}" if d["counterparty"] else (d["method"] or "payment")
    came = f"from {c['counterparty']}" if c["counterparty"] else (c["method"] or "payment")
    sentence = (f"{text.format_inr(amount)} left {ctx.phones[a]['label']} ({left}) and arrived on "
                f"{ctx.phones[b]['label']} {when_words} ({came})")
    talk = _money_talk(ctx, a, b, d["ts"])
    ids = [d["event_id"], c["event_id"], *[t["event_id"] for t in talk]]
    return {
        "kind": "money", "amount": amount, "amount_text": text.format_inr(amount),
        "from_phone": _phone_ref(ctx, a), "to_phone": _phone_ref(ctx, b),
        "debit": {"event_id": d["event_id"], "ts": d["ts"], "amount": amount, "when": text.fmt_when(d["ts"]), "method": d["method"],
                  "counterparty": d["counterparty"], "ref": d["ref"], "phone": _phone_ref(ctx, a)},
        "credit": {"event_id": c["event_id"], "ts": c["ts"], "amount": float(c["amount"]), "when": text.fmt_when(c["ts"]), "method": c["method"],
                   "counterparty": c["counterparty"], "ref": c["ref"], "phone": _phone_ref(ctx, b)},
        "gap_ms": gap, "gap_s": round(gap / 1000), "gap_words": text.gap_words(gap),
        "names_match": strength > 0, "same_ref": bool(d["ref"] and c["ref"] and str(d["ref"]) == str(c["ref"])),
        "ts": d["ts"], "when": text.fmt_when(d["ts"]), "day": text.ist_day(d["ts"]),
        "talk": talk, "text": sentence, "event_ids": ids,
    }


def _money_talk(ctx: Ctx, a: int, b: int, ts: int) -> list[dict]:
    """What either owner wrote about it within 2 hours: messages between the two owners that name an amount."""
    pa, pb = ctx.owner_of.get(a), ctx.owner_of.get(b)
    if pa is None or pb is None:
        return []
    w, p = ctx.w, ctx.p
    said = {r["event_id"] for r in ctx.con.execute(
        "SELECT event_id FROM money WHERE said_in_chat = 1 AND source_id IN (?, ?) AND ts BETWEEN ? AND ?",
        [a, b, ts - MONEY_TALK_MS, ts + MONEY_TALK_MS])}
    rows = db.rows(ctx.con, f"""
        SELECT e.event_id, e.source_id, e.ts, e.sender, e.recipients, e.body, e.app FROM events e
        WHERE {w} AND e.kind = 'message' AND e.source_id IN (?, ?) AND e.ts BETWEEN ? AND ?
        ORDER BY e.ts LIMIT 400""", [*p, a, b, ts - MONEY_TALK_MS, ts + MONEY_TALK_MS])
    out = []
    for r in rows:
        if not {pa, pb} <= ctx.parties(r["sender"], r["recipients"]):
            continue
        if r["event_id"] not in said and not text.find_amounts(r["body"]):
            continue
        out.append({"event_id": r["event_id"], "ts": r["ts"], "when": text.fmt_when(r["ts"]), "body": r["body"],
                    "sender_name": ctx.name(ctx.person(r["sender"])), "phone": _phone_ref(ctx, r["source_id"])})
        if len(out) >= 6:
            break
    return out


# ============================================================== 5. calls checked against each other


def check_calls(ctx: Ctx) -> list[dict]:
    con, w, p = ctx.con, ctx.w, ctx.p
    calls = db.rows(con, f"""
        SELECT e.event_id, e.source_id, e.ts, e.direction, e.sender, e.recipients, e.duration_s, e.status, e.app
        FROM events e WHERE {w} AND e.kind = 'call' AND e.ts IS NOT NULL ORDER BY e.ts""", p)
    all_ts: dict[int, list[int]] = {}
    by_day: dict[tuple[int, str], list[dict]] = {}
    bucket: dict[tuple[int, int], list[dict]] = {}
    for c in calls:
        sid = c["source_id"]
        if sid not in ctx.phones:
            continue
        all_ts.setdefault(sid, []).append(c["ts"])
        by_day.setdefault((sid, text.ist_day(c["ts"])), []).append(c)
        mine = ctx.owner_of.get(sid)
        for pid in ctx.parties(c["sender"], c["recipients"]):
            if pid == mine:
                continue
            for other in ctx.source_of_owner.get(pid, []):
                if other != sid:
                    bucket.setdefault((sid, other), []).append(c)
    out: list[dict] = []
    sids = sorted(ctx.phones)
    for i, a in enumerate(sids):
        for b in sids[i + 1:]:
            la, lb = bucket.get((a, b), []), bucket.get((b, a), [])
            pairs = []
            for x in la:
                for y in lb:
                    dt = abs(x["ts"] - y["ts"])
                    if dt <= CALL_WINDOW_MS:
                        pairs.append((int((x["app"] or "") != (y["app"] or "")), dt, x["event_id"], y["event_id"], x, y))
            pairs.sort(key=lambda t: t[:4])
            ua, ub = set(), set()
            for _, dt, ea, eb, x, y in pairs:
                if ea in ua or eb in ub:
                    continue
                ua.add(ea)
                ub.add(eb)
                row = _length_row(ctx, x, y)
                if row:
                    out.append(row)
            if ctx.limit_on:
                continue
            for x in la:
                if x["event_id"] not in ua:
                    row = _missing_row(ctx, x, b, all_ts, by_day)
                    if row:
                        out.append(row)
            for y in lb:
                if y["event_id"] not in ub:
                    row = _missing_row(ctx, y, a, all_ts, by_day)
                    if row:
                        out.append(row)
    out.sort(key=lambda r: (r["kind"] != "missing", r["ts"]))
    return out[:MAX_ROWS]


def _call_words(ctx: Ctx, c: dict) -> str:
    app = {"whatsapp": "WhatsApp call", "telegram": "Telegram call", "signal": "Signal call"}.get((c["app"] or "").lower(), "Call")
    mine = ctx.owner_of.get(c["source_id"])
    others = [pid for pid in ctx.parties(c["sender"], c["recipients"]) if pid != mine]
    who = ctx.name(others[0]) if others else "the other phone"
    d = (c["direction"] or "").lower()
    if (c["status"] or "") in ("missed", "rejected"):
        how = f"{c['status']} call with {who}"
        return f"{app.split(' ')[0] if app != 'Call' else ''} {how}".strip().capitalize()
    if d == "out":
        return f"{app} from {ctx.name(mine)} to {who}"
    if d == "in":
        return f"{app} from {who} to {ctx.name(mine)}"
    return f"{app} between {ctx.name(mine)} and {who}"


def _missing_row(ctx: Ctx, c: dict, other: int, all_ts: dict, by_day: dict) -> dict | None:
    ts = c["ts"]
    theirs = all_ts.get(other, [])
    i = bisect.bisect_left(theirs, ts)
    in_use = 0 < i < len(theirs) and ctx.in_span(other, ts)
    if not in_use:
        return None
    day = text.ist_day(ts)
    near = [{"event_id": y["event_id"], "ts": y["ts"], "when": text.fmt_time(y["ts"])} for y in by_day.get((other, day), [])]
    on, off = ctx.phones[c["source_id"]], ctx.phones[other]
    length = f", {text.duration_words(c['duration_s'])}" if c["duration_s"] else ""
    sentence = (f"{_call_words(ctx, c)}, {text.fmt_when(ts)}{length}, is on {on['short']}'s log. "
                f"Missing on {off['short']}'s log: may have been deleted there.")
    if near:
        sentence += f" {off['short']}'s log has other calls that day (at {', '.join(n['when'] for n in near[:4])})."
    return {
        "kind": "missing", "ts": ts, "when": text.fmt_when(ts), "day": day, "app": c["app"],
        "duration_s": c["duration_s"], "duration": text.duration_words(c["duration_s"]) if c["duration_s"] else "",
        "event_id": c["event_id"], "on_phone": _phone_ref(ctx, c["source_id"]), "missing_on": _phone_ref(ctx, other),
        "mark": f"Missing on {off['short']}'s log", "same_day": near[:10], "text": sentence,
        "event_ids": [c["event_id"], *[n["event_id"] for n in near[:10]]],
    }


def _length_row(ctx: Ctx, x: dict, y: dict) -> dict | None:
    da, db_ = int(x["duration_s"] or 0), int(y["duration_s"] or 0)
    if da <= 0 or db_ <= 0 or abs(da - db_) / max(da, db_) <= CALL_LENGTH_DIFF:
        return None
    pa, pb = ctx.phones[x["source_id"]], ctx.phones[y["source_id"]]
    sentence = (f"{_call_words(ctx, x)}, {text.fmt_when(x['ts'])}: {text.duration_words(da)} on {pa['short']}'s log "
                f"but {text.duration_words(db_)} on {pb['short']}'s log.")
    return {
        "kind": "length", "ts": x["ts"], "when": text.fmt_when(x["ts"]), "day": text.ist_day(x["ts"]), "app": x["app"],
        "event_id": x["event_id"], "other_event_id": y["event_id"],
        "on_phone": _phone_ref(ctx, x["source_id"]), "other_phone": _phone_ref(ctx, y["source_id"]),
        "duration_s": da, "other_duration_s": db_,
        "mark": f"Different length on {pb['short']}: {text.duration_words(db_)}",
        "text": sentence, "event_ids": [x["event_id"], y["event_id"]],
    }


# ============================================================== 2. together at the same place and time


def _metres(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def check_together(ctx: Ctx) -> list[dict]:
    con, w, p = ctx.con, ctx.w, ctx.p
    pts = db.rows(con, f"""
        SELECT e.event_id, e.source_id, e.ts, e.lat, e.lon, e.place, e.kind, e.direction, e.sender FROM events e
        WHERE {w} AND e.lat IS NOT NULL AND e.lon IS NOT NULL AND e.ts IS NOT NULL
          AND e.kind IN ('location', 'photo', 'video') AND COALESCE(e.direction, '') != 'in'
        ORDER BY e.ts""", p)
    per: dict[int, list[dict]] = {}
    for r in pts:
        sid = r["source_id"]
        if sid not in ctx.phones:
            continue
        if r["sender"]:
            who = ctx.person(r["sender"])
            if who is not None and who != ctx.owner_of.get(sid):
                continue  # a location someone else sent is not this phone's own
        per.setdefault(sid, []).append(r)
    out: list[dict] = []
    sids = sorted(per)
    for i, a in enumerate(sids):
        for b in sids[i + 1:]:
            if ctx.owner_of.get(a) is not None and ctx.owner_of.get(a) == ctx.owner_of.get(b):
                continue
            lb = per[b]
            tb = [y["ts"] for y in lb]
            hits = []
            for x in per[a]:
                lo = bisect.bisect_left(tb, x["ts"] - PLACE_WINDOW_MS)
                hi = bisect.bisect_right(tb, x["ts"] + PLACE_WINDOW_MS)
                for y in lb[lo:hi]:
                    d = _metres(x["lat"], x["lon"], y["lat"], y["lon"])
                    if d <= PLACE_METRES:
                        hits.append((min(x["ts"], y["ts"]), d, abs(x["ts"] - y["ts"]), x, y))
            hits.sort(key=lambda h: h[0])
            cluster: list = []
            for h in hits:
                if cluster and h[0] - cluster[-1][0] > PLACE_CLUSTER_MS:
                    out.append(_together_row(ctx, a, b, cluster))
                    cluster = []
                cluster.append(h)
            if cluster:
                out.append(_together_row(ctx, a, b, cluster))
    out.sort(key=lambda r: r["ts"])
    return out[:MAX_ROWS]


def _together_row(ctx: Ctx, a: int, b: int, cluster: list) -> dict:
    _, d, dt, x, y = min(cluster, key=lambda h: (h[1], h[2]))
    place = x["place"] or y["place"] or f"{x['lat']:.4f}, {x['lon']:.4f}"
    ids: list[str] = []
    for h in cluster:
        for e in (h[3]["event_id"], h[4]["event_id"]):
            if e not in ids:
                ids.append(e)
    ids = [x["event_id"], y["event_id"]] + [e for e in ids if e not in (x["event_id"], y["event_id"])][:12]
    metres = int(round(d / 10.0) * 10) if d >= 10 else int(round(d))
    pa, pb = ctx.phones[a], ctx.phones[b]
    gap = "at the same minute" if dt < 60_000 else f"{text.gap_words(dt)} apart"
    sentence = (f"{pa['label']} and {pb['label']} were about {metres} m apart at {place}, {gap} "
                f"({text.fmt_when(x['ts'])} and {text.fmt_when(y['ts']) if text.ist_day(y['ts']) != text.ist_day(x['ts']) else text.fmt_time(y['ts'])}).")
    return {
        "kind": "together", "ts": min(x["ts"], y["ts"]), "day": text.ist_day(min(x["ts"], y["ts"])), "place": place,
        "distance_m": metres, "gap_ms": dt, "gap_words": text.gap_words(dt),
        "a": {"phone": _phone_ref(ctx, a), "event_id": x["event_id"], "ts": x["ts"], "when": text.fmt_when(x["ts"]),
              "lat": x["lat"], "lon": x["lon"], "place": x["place"], "kind": x["kind"]},
        "b": {"phone": _phone_ref(ctx, b), "event_id": y["event_id"], "ts": y["ts"], "when": text.fmt_when(y["ts"]),
              "lat": y["lat"], "lon": y["lon"], "place": y["place"], "kind": y["kind"]},
        "phones": [_phone_ref(ctx, a), _phone_ref(ctx, b)], "n_points": len(cluster),
        "text": sentence, "event_ids": ids,
    }


# ============================================================== the answer, saved per case version


def compute(con) -> dict:
    ctx = Ctx(con)
    result: dict[str, Any] = {"phones": ctx.public_phones(), "enabled": ctx.enabled, "note": NOTE,
                              "limited": ctx.limit_on, "chats": [], "together": [], "money": [], "money_totals": [],
                              "files": [], "calls": [], "names": [], "known_by_several": []}
    if ctx.enabled:
        result["money"], result["money_totals"] = check_money(ctx)
        result["calls"] = check_calls(ctx)
        result["together"] = check_together(ctx)
        for part, fn in _MORE.items():
            got = fn(ctx)
            if isinstance(got, tuple):
                result[part], result[_MORE_EXTRA[part]] = got
            else:
                result[part] = got
    else:
        result["why_off"] = "Across phones needs two or more people's phones in the case."
    result["headers"] = _headers(result)
    return result


_MORE: dict = {}
_MORE_EXTRA: dict = {}


def _headers(r: dict) -> dict:
    total = sum(m["amount"] for m in r["money"])
    missing = sum(1 for c in r["calls"] if c["kind"] == "missing")
    length = sum(1 for c in r["calls"] if c["kind"] == "length")
    h = {
        "money": f"Money between the phones | {text.plural(len(r['money']), 'match', 'matches')}"
                 + (f" | {text.format_inr(total)}" if r["money"] else ""),
        "together": f"Together at the same place and time | {text.plural(len(r['together']), 'time')}",
        "calls": f"Calls checked against each other | {missing} missing | {text.plural(length, 'different length', 'different lengths')}",
        "chats": f"Both sides of the same chat | {text.plural(len(r['chats']), 'chat')}",
        "files": f"The same file on several phones | {text.plural(len(r['files']), 'file')}",
        "names": f"How each phone saved the others | {text.plural(len(r['names']), 'person', 'people')}",
    }
    if r.get("limited"):
        h["calls"] = f"Calls checked against each other | {text.plural(length, 'different length', 'different lengths')}"
    return h


def get_across(cid: str) -> dict:
    if _ready is not None:
        value, updating = _ready.get(cid, READY_NAME, compute)
        return _ready.with_updating(value, updating)
    return _get_across_here(cid)


def _get_across_here(cid: str) -> dict:
    """The same saved-answer rule as ib/ready.py, used only if that module is missing."""
    with db.case_db(cid) as con:
        if limits.get_limit(con) is not None:
            out = compute(con)
            out["updating"] = False
            return out
        version = str(db.case_version(con))
        saved = db.one(con, "SELECT made_from, value FROM ready WHERE name = ?", [READY_NAME])
    if saved and saved["made_from"] == version:
        out = json.loads(saved["value"])
        out["updating"] = False
        return out
    lk = _lock(cid)
    if saved and not lk.acquire(blocking=False):
        out = json.loads(saved["value"])
        out["updating"] = True
        return out
    if not saved:
        lk.acquire()
    try:
        with db.case_db(cid) as con:
            version = str(db.case_version(con))
            again = db.one(con, "SELECT made_from, value FROM ready WHERE name = ?", [READY_NAME])
            if again and again["made_from"] == version:
                out = json.loads(again["value"])
            else:
                out = compute(con)
                con.execute("INSERT OR REPLACE INTO ready(name, made_from, value, made_at) VALUES (?, ?, ?, ?)",
                            [READY_NAME, version, json.dumps(out, ensure_ascii=False), db.now_ms()])
    finally:
        lk.release()
    out["updating"] = False
    return out


@router.get("/api/cases/{cid}/across")
def across(cid: str, acc: CaseAccess = Depends(require_case)):
    return get_across(acc.cid)


# ============================================================== 1. both sides of the same chat


def _fallback_thread(ctx: Ctx, conv: dict) -> str | None:
    """A one-to-one chat with no thread key: the app plus the sorted pair of people, when both own a phone here."""
    if conv["is_group"]:
        return None
    people = {ctx.person(str(x)) for x in _json_list(conv["participants"])} - {None}
    people.add(ctx.owner_of.get(conv["source_id"]))
    people.discard(None)
    if len(people) != 2 or not all(p in ctx.source_of_owner for p in people):
        return None
    return f"auto:{(conv['app'] or '').lower()}:" + ":".join(str(p) for p in sorted(people))


def _who(ctx: Ctx, m: dict) -> Any:
    if m["sender"]:
        pid = ctx.person(m["sender"])
        return ("p", pid) if pid is not None else ("k", _key(m["sender"]))
    if (m["direction"] or "") == "out":
        return ("p", ctx.owner_of.get(m["source_id"]))
    return ("?", None)


_APP_WORDS = {"whatsapp": "WhatsApp", "sms": "SMS", "telegram": "Telegram", "signal": "Signal", "imessage": "iMessage"}


def check_chats(ctx: Ctx) -> list[dict]:
    con, w, p = ctx.con, ctx.w, ctx.p
    convs = db.rows(con, "SELECT conv_id, source_id, app, title, is_group, participants, thread_key FROM conversations")
    threads: dict[str, list[dict]] = {}
    for c in convs:
        if c["source_id"] not in ctx.phones:
            continue
        k = c["thread_key"] or _fallback_thread(ctx, c)
        if k:
            threads.setdefault(k, []).append(c)
    out = []
    for key, copies in threads.items():
        owners = {ctx.owner_of.get(c["source_id"], -c["source_id"]) for c in copies}
        if len({c["source_id"] for c in copies}) < 2 or len(owners) < 2:
            continue
        row = _thread_row(ctx, key, copies, w, p)
        if row:
            out.append(row)
    out.sort(key=lambda r: (-(r["n_deleted_elsewhere"] + r["n_only_one"]), -sum(c["n_messages"] for c in r["copies"])))
    return out[:MAX_ROWS]


def _thread_row(ctx: Ctx, key: str, copies: list[dict], w: str, p: list) -> dict | None:
    ids = [c["conv_id"] for c in copies]
    ph = ",".join("?" * len(ids))
    msgs = db.rows(ctx.con, f"""
        SELECT e.event_id, e.source_id, e.conv_id, e.ts, e.sender, e.direction, e.body, e.media_name, e.status
        FROM events e WHERE {w} AND e.conv_id IN ({ph}) AND e.ts IS NOT NULL ORDER BY e.ts""", [*p, *ids])
    if not msgs:
        return None
    sources = sorted({c["source_id"] for c in copies})
    first_ts = {s: min((m["ts"] for m in msgs if m["source_id"] == s), default=None) for s in sources}
    merged: list[dict] = []
    open_by_who: dict[Any, list[dict]] = {}
    for m in msgs:
        who = _who(ctx, m)
        words = text.fold_text(m["body"] or m["media_name"] or "")
        cands = open_by_who.setdefault(who, [])
        hit = None
        for item in reversed(cands):
            if m["ts"] - item["ts"] > CHAT_WINDOW_MS:
                break
            if m["source_id"] in item["holders"]:
                continue
            if item["words"] == words or not words or not item["words"]:
                hit = item
                break
        if hit is None:
            hit = {"ts": m["ts"], "words": words, "holders": {}}
            merged.append(hit)
            cands.append(hit)
        elif not hit["words"]:
            hit["words"] = words
        hit["holders"][m["source_id"]] = m
    only_one, deleted_elsewhere = [], []
    for item in merged:
        held = item["holders"]
        gone = [s for s, m in held.items() if (m["status"] or "") in ("deleted", "unsent")]
        kept = [s for s, m in held.items() if (m["status"] or "") not in ("deleted", "unsent")]
        if gone and kept:
            for s in gone:
                m, k = held[s], held[kept[0]]
                deleted_elsewhere.append({
                    "event_id": m["event_id"], "kept_event_id": k["event_id"], "ts": m["ts"], "when": text.fmt_when(m["ts"]),
                    "deleted_on": _phone_ref(ctx, s), "kept_on": _phone_ref(ctx, kept[0]),
                    "body": (k["body"] or m["body"] or k["media_name"] or "")[:200],
                    "mark": f"Deleted on {ctx.phones[s]['short']}"})
        if ctx.limit_on:
            continue
        missing = [s for s in sources if s not in held and first_ts.get(s) is not None
                   and first_ts[s] < item["ts"] < (ctx.phones[s]["last_ts"] or 0)]
        if missing:
            s0 = next(iter(held))
            m = held[s0]
            only_one.append({"event_id": m["event_id"], "ts": m["ts"], "when": text.fmt_when(m["ts"]),
                             "on": [_phone_ref(ctx, s) for s in held], "not_on": [_phone_ref(ctx, s) for s in missing],
                             "body": (m["body"] or m["media_name"] or "")[:200],
                             "mark": "Only on " + " and ".join(ctx.phones[s]["short"] for s in held)})
    counts = []
    for c in copies:
        mine = [m for m in msgs if m["conv_id"] == c["conv_id"]]
        counts.append({"phone": _phone_ref(ctx, c["source_id"]), "conv_id": c["conv_id"], "title": c["title"],
                       "n_messages": len(mine),
                       "n_deleted": sum(1 for m in mine if (m["status"] or "") == "deleted")})
    titles = []
    for c in copies:
        if c["title"] and c["title"] not in titles:
            titles.append(c["title"])
    app = copies[0]["app"] or ""
    holds = ", ".join(f"{x['phone']['label'].split(' | ')[0]} holds {text.plural(x['n_messages'], 'message')}" for x in counts)
    worth = []
    if deleted_elsewhere:
        by = {}
        for d in deleted_elsewhere:
            by.setdefault((d["deleted_on"]["phone_no"], d["kept_on"]["phone_no"]), 0)
            by[(d["deleted_on"]["phone_no"], d["kept_on"]["phone_no"])] += 1
        worth += [f"{n} deleted on Phone {a} and still on Phone {b}" for (a, b), n in by.items()]
    if only_one:
        worth.append(f"{text.plural(len(only_one), 'message')} on one phone only")
    app_words = _APP_WORDS.get(app.lower(), app.capitalize())
    sentence = f"{' / '.join(titles) or 'A chat'} ({app_words}): {holds}."
    if worth:
        line = "; ".join(worth)
        sentence += " " + line[:1].upper() + line[1:] + "."
    ev = [d["event_id"] for d in deleted_elsewhere[:15]] + [d["kept_event_id"] for d in deleted_elsewhere[:15]]
    ev += [o["event_id"] for o in only_one[:15]]
    if not ev:
        ev = [m["event_id"] for m in msgs[:5]]
    return {
        "kind": "chat", "thread_key": key, "title": " / ".join(titles), "app": app,
        "is_group": bool(copies[0]["is_group"]), "copies": counts, "phones": counts, "conv_ids": ids,
        "conv_id": copies[0]["conv_id"], "open": {"page": "chats", "conv_id": copies[0]["conv_id"], "both": 1},
        "n_deleted_elsewhere": len(deleted_elsewhere), "n_only_one": len(only_one),
        "deleted_elsewhere": len(deleted_elsewhere), "only_one": len(only_one),
        "deleted_rows": deleted_elsewhere[:100], "only_one_rows": only_one[:50],
        "ts": msgs[0]["ts"], "last_ts": msgs[-1]["ts"], "text": sentence, "event_ids": ev,
    }


# ============================================================== 4. the same file on several phones


def _size_words(n) -> str:
    if not n:
        return ""
    n = float(n)
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{n / 1024:.0f} KB"


def check_files(ctx: Ctx) -> list[dict]:
    con, w, p = ctx.con, ctx.w, ctx.p
    rows = db.rows(con, f"""
        SELECT e.media_sha256 AS sha, e.event_id, e.source_id, e.ts, e.media_name, e.media_size, e.kind, e.direction,
               e.sender, e.conv_id, e.ocr_text
        FROM events e
        WHERE {w} AND e.media_sha256 IS NOT NULL AND e.media_sha256 != ''
          AND (e.media_size IS NULL OR e.media_size >= ?)
          AND e.media_sha256 IN (SELECT media_sha256 FROM events WHERE media_sha256 IS NOT NULL AND media_sha256 != ''
                                 GROUP BY media_sha256 HAVING COUNT(DISTINCT source_id) >= 2)
        ORDER BY e.ts""", [*p, FILE_MIN_BYTES])
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r["source_id"] in ctx.phones:
            groups.setdefault(r["sha"], []).append(r)
    out = []
    for sha, items in groups.items():
        srcs = []
        for r in items:
            if r["source_id"] not in srcs:
                srcs.append(r["source_id"])
        if len(srcs) < 2:
            continue
        first = items[0]
        name = next((r["media_name"] for r in items if r["media_name"]), "A file")
        size = next((r["media_size"] for r in items if r["media_size"]), None)
        holders = []
        for r in items:
            frm = ctx.person(r["sender"]) if r["sender"] else None
            holders.append({"phone": _phone_ref(ctx, r["source_id"]), "event_id": r["event_id"], "ts": r["ts"],
                            "when": text.fmt_when(r["ts"]), "name": r["media_name"], "direction": r["direction"],
                            "from": ctx.name(frm) if frm is not None else "", "conv_id": r["conv_id"]})
        steps = []
        seen = {first["source_id"]}
        for r in items[1:]:
            if r["source_id"] in seen:
                continue
            seen.add(r["source_id"])
            steps.append(f"then on {ctx.phones[r['source_id']]['label']} ({text.gap_words(r['ts'] - first['ts'])} later)")
        kind = first["kind"] or "file"
        bits = ", ".join(x for x in (kind, _size_words(size)) if x)
        sentence = (f"{name} ({bits}) was first on {ctx.phones[first['source_id']]['label']} ({text.fmt_when(first['ts'])}), "
                    + ", ".join(steps) + ".")
        ocr = next((r["ocr_text"] for r in items if r["ocr_text"]), "")
        out.append({
            "kind": "file", "sha256": sha, "name": name, "size": size, "size_words": _size_words(size),
            "file_kind": kind, "first_phone": _phone_ref(ctx, first["source_id"]), "ts": first["ts"],
            "when": text.fmt_when(first["ts"]), "day": text.ist_day(first["ts"]),
            "phones": [_phone_ref(ctx, s) for s in srcs], "holders": holders, "copies": holders, "words_in_it": (ocr or "")[:300],
            "text": sentence, "event_ids": [h["event_id"] for h in holders],
        })
    out.sort(key=lambda r: (-len(r["phones"]), r["ts"]))
    return out[:MAX_ROWS]


# ============================================================== 6. how each phone saved the others


def _allowed_ids(ctx: Ctx, ids: list[str]) -> set[str]:
    if not ctx.limit_on:
        return set(ids)
    if not ids:
        return set()
    ph = ",".join("?" * len(ids))
    return {r["event_id"] for r in ctx.con.execute(
        f"SELECT e.event_id FROM events e WHERE {ctx.w} AND e.event_id IN ({ph})", [*ctx.p, *ids])}


def check_names(ctx: Ctx) -> tuple[list[dict], list[dict]]:
    people = db.rows(ctx.con, "SELECT person_id, name, names, is_owner, kind FROM persons WHERE names IS NOT NULL AND names != ''")
    entries = []
    for pr in people:
        for n in _json_list(pr["names"]):
            if not isinstance(n, dict) or (n.get("how") or "") != "contact" or not n.get("name"):
                continue
            sid = n.get("source_id")
            if sid not in ctx.phones:
                continue
            entries.append((pr, sid, str(n["name"]), n.get("event_id")))
    allowed = _allowed_ids(ctx, [e[3] for e in entries if e[3]])
    entries = [e for e in entries if (e[3] in allowed) if e[3]] + ([e for e in entries if not e[3]] if not ctx.limit_on else [])
    names, seen, several = [], set(), {}
    for pr, sid, saved, eid in entries:
        pid = pr["person_id"]
        if pid in ctx.source_of_owner and ctx.owner_of.get(sid) != pid:
            k = (sid, pid, saved.lower())
            if k in seen:
                continue
            seen.add(k)
            theirs = ctx.source_of_owner[pid]
            names.append({
                "kind": "name", "saved_on": _phone_ref(ctx, sid), "person_id": pid, "owner_name": pr["name"],
                "their_phones": [_phone_ref(ctx, s) for s in theirs], "saved_as": saved, "event_id": eid,
                "text": f"{ctx.phones[sid]['label']} saved {pr['name']} ({ctx.phones[theirs[0]]['short']}) as \"{saved}\"",
                "event_ids": [eid] if eid else [],
            })
        if pid not in ctx.source_of_owner:
            several.setdefault(pid, {"pr": pr, "saved": {}})["saved"].setdefault(sid, (saved, eid))
    names.extend(_names_from_contacts(ctx, {(n["saved_on"]["source_id"], n["person_id"]) for n in names}))
    names.sort(key=lambda n: (n["saved_on"]["phone_no"], n["owner_name"] or ""))
    per_owner: dict[int, dict] = {}
    for n in names:
        pid = n["person_id"]
        row = per_owner.setdefault(pid, {
            "kind": "owner", "person_id": pid, "name": n["owner_name"], "owner_name": n["owner_name"],
            "owner_of": ctx.source_of_owner[pid][0], "their_phones": n["their_phones"], "saved": [], "event_ids": []})
        row["saved"].append({"phone": n["saved_on"], "saved_as": n["saved_as"], "name": n["saved_as"], "event_id": n["event_id"],
                             "text": n["text"]})
        if n["event_id"]:
            row["event_ids"].append(n["event_id"])
    for row in per_owner.values():
        row["n_phones"] = len({x["phone"]["source_id"] for x in row["saved"]})
        row["text"] = (f"{row['name']} ({ctx.phones[row['owner_of']]['short']}) is saved as "
                       + " and ".join(f"\"{x['saved_as']}\" on {ctx.phones[x['phone']['source_id']]['short']}" for x in row["saved"]))
    known = []
    for pid, v in several.items():
        if len(v["saved"]) < 2:
            continue
        saved = [{"phone": _phone_ref(ctx, s), "saved_as": nm, "event_id": e} for s, (nm, e) in sorted(v["saved"].items())]
        phones = " and ".join(ctx.phones[s]["short"] for s in sorted(v["saved"]))
        as_words = " and ".join(f"\"{x['saved_as']}\"" for x in saved)
        known.append({"kind": "known", "person_id": pid, "name": v["pr"]["name"], "saved": saved,
                      "phones": [x["phone"] for x in saved],
                      "text": f"{v['pr']['name']} is in the contacts of {phones} (as {as_words})",
                      "event_ids": [x["event_id"] for x in saved if x["event_id"]]})
    known.sort(key=lambda k: (-len(k["saved"]), k["name"] or ""))
    for k in known:
        k["n_phones"] = len(k["saved"])
        for x in k["saved"]:
            x["name"] = x["saved_as"]
    owners = sorted(per_owner.values(), key=lambda r: ctx.phones[r["owner_of"]]["phone_no"])
    return (owners + known)[:MAX_ROWS], known[:MAX_ROWS]


def _names_from_contacts(ctx: Ctx, done: set) -> list[dict]:
    """When the people table carries no contact names, read the phones' own contact records."""
    want = {}
    for r in ctx.con.execute("SELECT ident, person_id FROM identifiers"):
        if r["person_id"] in ctx.source_of_owner:
            d = text.digits(r["ident"])[-10:]
            if len(d) == 10:
                want[d] = r["person_id"]
    if not want:
        return []
    rows = db.rows(ctx.con, f"""
        SELECT e.event_id, e.source_id, e.body, e.sender, e.recipients, e.extra FROM events e
        WHERE {ctx.w} AND e.kind = 'contact' LIMIT 20000""", ctx.p)
    out = []
    for r in rows:
        sid = r["source_id"]
        if sid not in ctx.phones:
            continue
        blob = " ".join(str(x or "") for x in (r["sender"], r["recipients"], r["extra"], r["body"]))
        nums = {text.digits(x)[-10:] for x in __import__("re").findall(r"\+?\d[\d \-]{8,}\d", blob)}
        for d in nums:
            pid = want.get(d)
            if pid is None or ctx.owner_of.get(sid) == pid or (sid, pid) in done:
                continue
            saved = ""
            try:
                ex = json.loads(r["extra"]) if r["extra"] else {}
                saved = ex.get("name") or ex.get("display") or ""
            except (TypeError, ValueError, AttributeError):
                saved = ""
            saved = saved or (r["body"] or "").split("\n")[0].strip()
            if not saved:
                continue
            done.add((sid, pid))
            theirs = ctx.source_of_owner[pid]
            out.append({"kind": "name", "saved_on": _phone_ref(ctx, sid), "person_id": pid, "owner_name": ctx.name(pid),
                        "their_phones": [_phone_ref(ctx, s) for s in theirs], "saved_as": saved, "event_id": r["event_id"],
                        "text": f"{ctx.phones[sid]['label']} saved {ctx.name(pid)} ({ctx.phones[theirs[0]]['short']}) as \"{saved}\"",
                        "event_ids": [r["event_id"]]})
    return out


_MORE.update({"chats": check_chats, "files": check_files, "names": check_names})
_MORE_EXTRA.update({"names": "known_by_several"})

if _ready is not None:
    _ready.register(READY_NAME, compute)
