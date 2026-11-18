"""People (section 12.10): the people list with its four groups, and one person's page.

Routes:
    GET /api/cases/{cid}/people?group=&q=&sort=&offset=   {groups, rows, total, offset, group, limit}
    GET /api/cases/{cid}/people/{pid}                     one person: names with evidence, identifiers, counts,
                                                          chats, calls, money, documents and photos, across phones

Every count is worked out from the records inside the warrant limit (limits.where), never from stored totals.
"""
from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Depends

from ib import ApiError, config, db, limits, text
from ib.officers import CaseAccess, require_case

router = APIRouter()

GROUPS = [
    ("in-touch", "In touch"),
    ("same-groups", "Only in the same groups"),
    ("lists-only", "Only names on lists"),
    ("apps", "Apps and automatic senders"),
]
GROUP_LABELS = dict(GROUPS)
MEDIA_KINDS = ("photo", "video", "voice", "document")
WEEK_MS = 7 * 24 * 3600 * 1000
APP_NAMES = {"whatsapp": "WhatsApp", "sms": "SMS", "telegram": "Telegram", "signal": "Signal",
             "imessage": "iMessage", "phone": "Phone", "email": "Email", "upi": "UPI"}


def _json(value, default):
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        out = json.loads(value)
    except (TypeError, ValueError):
        return default
    return out if out is not None else default


class _Who:
    """Maps the sender and recipient strings in events to person ids."""

    def __init__(self, con):
        self.exact: dict[str, int] = {}
        self.by_phone: dict[str, int] = {}
        self.idents: dict[int, list[dict]] = defaultdict(list)
        for r in db.rows(con, "SELECT ident, kind, display, person_id FROM identifiers WHERE person_id IS NOT NULL"):
            pid = int(r["person_id"])
            self.exact[r["ident"]] = pid
            self.idents[pid].append(r)
            ph = text.norm_phone(self._bare(r["ident"]))
            if ph:
                self.by_phone.setdefault(ph, pid)
        self.cache: dict[str, int | None] = {}

    @staticmethod
    def _bare(s: str) -> str:
        s = (s or "").strip()
        if ":" in s and not s.startswith("+"):
            s = s.split(":", 1)[1]
        return s

    def pid(self, s) -> int | None:
        if not s:
            return None
        s = str(s)
        if s in self.cache:
            return self.cache[s]
        found = self.exact.get(s)
        if found is None:
            bare = self._bare(s)
            found = self.exact.get(bare)
            if found is None and not text.is_sender_id(bare):
                ph = text.norm_phone(bare)
                if ph:
                    found = self.exact.get(ph) or self.exact.get("wa:" + ph) or self.by_phone.get(ph)
        self.cache[s] = found
        return found


def _sources(con) -> dict[int, dict]:
    out = {}
    for r in db.rows(con, "SELECT source_id, phone_no, label, owner_name, owner_person_id FROM sources"):
        out[int(r["source_id"])] = r
    return out


def _chip(src: dict | None) -> dict | None:
    if not src:
        return None
    return {"source_id": src["source_id"], "phone_no": src["phone_no"], "label": src["label"]}


def _scan(con, who: _Who, owners: dict[int, int]) -> dict[int, dict]:
    """One pass over the records in the limit: per person counts, times, phones and how they were in touch."""
    w, p = limits.where(con, "e")
    groups = {int(r["conv_id"]): bool(r["is_group"]) for r in db.rows(con, "SELECT conv_id, is_group FROM conversations")}
    stats: dict[int, dict] = {}

    def st(pid):
        s = stats.get(pid)
        if s is None:
            s = stats[pid] = {"messages": 0, "calls": 0, "first": None, "last": None, "sources": set(),
                              "one2one": False, "group": False, "connected": False, "wrote": 0}
        return s

    cur = con.execute(
        f"SELECT e.source_id, e.kind, e.ts, e.sender, e.recipients, e.conv_id, e.duration_s, e.status, e.direction"
        f" FROM events e WHERE {w} AND e.kind IN ('message','call','photo','video','voice','document')", p)
    for src, kind, ts, sender, recips, conv, dur, status, direction in cur:
        involved = set()
        sp = who.pid(sender)
        if sp is not None:
            involved.add(sp)
        for r in _json(recips, []):
            rp = who.pid(r.get("ident") if isinstance(r, dict) else r)
            if rp is not None:
                involved.add(rp)
        if not sender and src in owners:
            involved.add(owners[src])
        is_group = groups.get(conv, False) if conv is not None else False
        for pid in involved:
            s = st(pid)
            if kind == "call":
                s["calls"] += 1
                if (dur or 0) > 0 and status not in ("missed", "rejected"):
                    s["connected"] = True
            else:
                s["messages"] += 1
                if conv is not None:
                    if is_group:
                        s["group"] = True
                    else:
                        s["one2one"] = True
                if pid == sp:
                    s["wrote"] += 1
            if ts is not None:
                s["first"] = ts if s["first"] is None else min(s["first"], ts)
                s["last"] = ts if s["last"] is None else max(s["last"], ts)
            if src is not None:
                s["sources"].add(int(src))
    return stats


def _group_of(person: dict, s: dict | None, who: _Who) -> str:
    stored = person.get("group_kind")
    if stored in GROUP_LABELS:
        return stored
    if person.get("kind") in ("business", "service"):
        return "apps"
    ids = who.idents.get(int(person["person_id"]), [])
    if ids and all(text.is_sender_id(who._bare(i["ident"])) or i["kind"] in ("sender", "service") for i in ids):
        return "apps"
    if person.get("is_owner"):
        return "in-touch"
    if not s or (s["messages"] + s["calls"]) == 0:
        return "lists-only"
    if s["one2one"] or s["connected"]:
        return "in-touch"
    if s["group"]:
        return "same-groups"
    return "in-touch" if s["calls"] else "lists-only"


def _names(person: dict) -> list[dict]:
    return [n for n in _json(person.get("names"), []) if isinstance(n, dict) and n.get("name")]


def _also(person: dict) -> list[str]:
    seen, out = {(person.get("name") or "").strip().lower()}, []
    for n in _names(person):
        k = n["name"].strip().lower()
        if k not in seen:
            seen.add(k)
            out.append(n["name"])
    return out


def _numbers(who: _Who, pid: int) -> list[str]:
    seen, out = set(), []
    for i in who.idents.get(pid, []):
        disp = i.get("display") or i["ident"]
        key = text.digits(disp) or disp
        if key in seen:
            continue
        seen.add(key)
        out.append(disp)
    return out


def _all_people(con):
    who = _Who(con)
    srcs = _sources(con)
    owners = {sid: int(s["owner_person_id"]) for sid, s in srcs.items() if s.get("owner_person_id") is not None}
    persons = db.rows(con, "SELECT * FROM persons")
    stats = _scan(con, who, owners)
    lim = limits.get_limit(con)
    lim_people = {int(x) for x in (lim or {}).get("people") or []}
    owner_src = defaultdict(list)
    for sid, pid in owners.items():
        owner_src[pid].append(sid)
    rows = []
    for per in persons:
        pid = int(per["person_id"])
        s = stats.get(pid)
        if lim and not s and pid not in lim_people:
            continue  # nothing of theirs inside the warrant limit
        g = _group_of(per, s, who)
        src_ids = sorted((s["sources"] if s else set()) | set(owner_src.get(pid, [])))
        owner_of = [_chip(srcs[x]) for x in owner_src.get(pid, []) if x in srcs]
        rows.append({
            "person_id": pid,
            "name": per.get("name") or (_numbers(who, pid) or [f"Person {pid}"])[0],
            "also": _also(per),
            "numbers": _numbers(who, pid),
            "kind": per.get("kind") or "person",
            "is_owner": bool(per.get("is_owner")) or bool(owner_of),
            "owner_of": owner_of,
            "group": g,
            "group_label": GROUP_LABELS[g],
            "messages": s["messages"] if s else 0,
            "calls": s["calls"] if s else 0,
            "wrote": s["wrote"] if s else 0,
            "first_ts": s["first"] if s else None,
            "last_ts": s["last"] if s else None,
            "first": text.fmt_when(s["first"]) if s and s["first"] else "",
            "last": text.fmt_when(s["last"]) if s and s["last"] else "",
            "phones": [_chip(srcs[x]) for x in src_ids if x in srcs],
        })
    return rows, who, srcs


SORTS = {
    "messages": lambda r: (-(r["messages"]), -(r["calls"]), r["name"].lower()),
    "calls": lambda r: (-(r["calls"]), -(r["messages"]), r["name"].lower()),
    "name": lambda r: r["name"].lower(),
    "last": lambda r: (-(r["last_ts"] or 0), r["name"].lower()),
    "first": lambda r: ((r["first_ts"] or 2**62), r["name"].lower()),
}


def _matches(r: dict, q: str) -> bool:
    if not q:
        return True
    ql = q.lower().strip()
    if any(ql in (n or "").lower() for n in [r["name"], *r["also"]]):
        return True
    d = text.digits(q)
    return len(d) >= 3 and any(d in text.digits(n) for n in r["numbers"])


@router.get("/api/cases/{cid}/people")
def people(cid: str, group: str = "", q: str = "", sort: str = "messages", offset: int = 0,
           acc: CaseAccess = Depends(require_case)):
    if group and group not in GROUP_LABELS:
        raise ApiError(400, "Choose one of the groups: in touch, same groups, names on lists, or apps.")
    with db.case_db(cid) as con:
        rows, _, _ = _all_people(con)
        banner = limits.banner_text(con)
    rows.sort(key=SORTS.get(sort, SORTS["messages"]))
    cards = []
    for key, label in GROUPS:
        members = [r for r in rows if r["group"] == key]
        top = sorted(members, key=lambda r: -(r["messages"] + r["calls"]))[:24]
        cards.append({"key": key, "label": label, "n": len(members),
                      "bars": [{"person_id": r["person_id"], "name": r["name"], "n": r["wrote"] or r["messages"]}
                               for r in top]})
    shown = [r for r in rows if (not group or r["group"] == group) and _matches(r, q)]
    offset = max(0, int(offset or 0))
    return {"groups": cards, "group": group, "q": q, "sort": sort if sort in SORTS else "messages",
            "total": len(shown), "offset": offset, "page_size": config.PAGE_SIZE,
            "rows": shown[offset:offset + config.PAGE_SIZE], "limit": banner}


def _how_text(n: dict, srcs: dict[int, dict]) -> str:
    src = srcs.get(int(n["source_id"])) if n.get("source_id") not in (None, "") else None
    where = src["label"] if src else "these phones"
    how = n.get("how") or "contact"
    name = n["name"]
    if how == "contact":
        return f"Saved as '{name}' on {where}"
    if how == "profile":
        return f"Their own profile name '{name}' on {where}"
    if how == "signature":
        return f"Signed a message '{name}' on {where}"
    if how == "ai":
        return f"The AI read the name '{name}' in a record on {where}"
    return f"'{name}' on {where}"


def _in_scope(con, w: str, p: list, eids: list[str]) -> set[str]:
    eids = [e for e in eids if e]
    if not eids:
        return set()
    ph = ",".join("?" * len(eids))
    return {r[0] for r in con.execute(f"SELECT e.event_id FROM events e WHERE {w} AND e.event_id IN ({ph})", [*p, *eids])}


@router.get("/api/cases/{cid}/people/{pid}")
def person(cid: str, pid: int, acc: CaseAccess = Depends(require_case)):
    with db.case_db(cid) as con:
        per = db.one(con, "SELECT * FROM persons WHERE person_id = ?", [pid])
        if not per:
            raise ApiError(404, "That person isn't in this case.")
        rows, who, srcs = _all_people(con)
        row = next((r for r in rows if r["person_id"] == pid), None)
        if row is None:
            raise ApiError(404, "That person has no records inside the warrant limit.")
        lim = limits.get_limit(con)
        w, p = limits.where(con, "e")
        my_idents = [i["ident"] for i in who.idents.get(pid, [])]
        own_srcs = [sid for sid, s in srcs.items() if s.get("owner_person_id") is not None and int(s["owner_person_id"]) == pid]

        # Names with how each was found; a name tied to a record outside the limit is left out.
        names = _names(per)
        ok = _in_scope(con, w, p, [n.get("event_id") for n in names]) if lim else None
        name_rows = []
        for n in names:
            if lim and n.get("event_id") and n["event_id"] not in ok:
                continue
            src = srcs.get(int(n["source_id"])) if n.get("source_id") not in (None, "") else None
            name_rows.append({"name": n["name"], "how": n.get("how") or "contact", "how_text": _how_text(n, srcs),
                              "source_id": n.get("source_id"), "phone_label": src["label"] if src else "",
                              "event_id": n.get("event_id")})

        # Records that involve them (sender, recipient, or their own phone's records with no sender).
        events = []
        cur = con.execute(
            f"SELECT e.event_id, e.source_id, e.kind, e.app, e.ts, e.direction, e.sender, e.recipients, e.conv_id,"
            f" e.body, e.status, e.duration_s, e.media_name, e.media_size, e.place FROM events e"
            f" WHERE {w} AND e.kind IN ('message','call','photo','video','voice','document') ORDER BY e.ts", p)
        for r in cur:
            r = dict(zip([c[0] for c in cur.description], r))
            mine = who.pid(r["sender"]) == pid
            if not mine:
                for x in _json(r["recipients"], []):
                    if isinstance(x, str) and who.pid(x) == pid:
                        mine = True
                        break
            if not mine and not r["sender"] and r["source_id"] in own_srcs:
                mine = True
            if mine:
                r["from_them"] = who.pid(r["sender"]) == pid
                events.append(r)

        # Contact per week, for the sparkline.
        weekly = []
        if events and row["first_ts"]:
            start = row["first_ts"] - (row["first_ts"] % WEEK_MS)
            nweeks = int((row["last_ts"] - start) // WEEK_MS) + 1
            counts = [0] * min(nweeks, 520)
            for e in events:
                if e["ts"] is not None:
                    i = int((e["ts"] - start) // WEEK_MS)
                    if 0 <= i < len(counts):
                        counts[i] += 1
            weekly = [{"week": text.ist_day(start + i * WEEK_MS), "n": n} for i, n in enumerate(counts)]

        # Chats with them.
        by_conv: dict[int, dict] = {}
        for e in events:
            if e["conv_id"] is None or e["kind"] == "call":
                continue
            c = by_conv.setdefault(int(e["conv_id"]), {"n": 0, "deleted": 0, "last_ts": None, "last_body": ""})
            c["n"] += 1
            if e["status"] in ("deleted", "unsent"):
                c["deleted"] += 1
            c["last_ts"], c["last_body"] = e["ts"], (e["body"] or e["media_name"] or "")[:120]
        chats = []
        if by_conv:
            ph = ",".join("?" * len(by_conv))
            for c in db.rows(con, f"SELECT conv_id, source_id, app, title, is_group, thread_key FROM conversations"
                                  f" WHERE conv_id IN ({ph})", list(by_conv)):
                b = by_conv[int(c["conv_id"])]
                src = srcs.get(int(c["source_id"])) if c["source_id"] is not None else None
                chats.append({"conv_id": c["conv_id"], "app": c["app"], "app_name": APP_NAMES.get(c["app"], c["app"]),
                              "title": c["title"], "is_group": bool(c["is_group"]), "thread_key": c["thread_key"],
                              "phone": _chip(src), "n_messages": b["n"], "n_deleted": b["deleted"],
                              "last_ts": b["last_ts"], "last": text.fmt_when(b["last_ts"]), "last_body": b["last_body"]})
            chats.sort(key=lambda c: -(c["last_ts"] or 0))

        # The last 10 calls.
        calls = []
        for e in reversed([e for e in events if e["kind"] == "call"][-10:]):
            src = srcs.get(int(e["source_id"])) if e["source_id"] is not None else None
            calls.append({"event_id": e["event_id"], "ts": e["ts"], "when": text.fmt_when(e["ts"]),
                          "direction": e["direction"], "status": e["status"], "app": e["app"],
                          "app_name": APP_NAMES.get(e["app"], e["app"]), "duration_s": e["duration_s"],
                          "duration": text.duration_words(e["duration_s"]) if e["duration_s"] else "",
                          "phone": _chip(src)})

        # Their documents and photos (ones they sent, or found on their own phone).
        media = []
        for e in reversed([e for e in events if e["kind"] in MEDIA_KINDS and (e["from_them"] or e["source_id"] in own_srcs)][-30:]):
            src = srcs.get(int(e["source_id"])) if e["source_id"] is not None else None
            media.append({"event_id": e["event_id"], "kind": e["kind"], "name": e["media_name"] or "",
                          "size": e["media_size"], "ts": e["ts"], "when": text.fmt_when(e["ts"]), "phone": _chip(src)})

        # Money with them: payments whose other side is one of their identifiers.
        money_rows = []
        if my_idents:
            ph = ",".join("?" * len(my_idents))
            money_rows = db.rows(
                con, f"SELECT m.* FROM money m WHERE m.counterparty_ident IN ({ph})"
                     f" AND m.event_id IN (SELECT e.event_id FROM events e WHERE {w}) ORDER BY m.ts", [*my_idents, *p])
        paid_to, got_from = 0.0, 0.0
        money = []
        owners_money: dict[int, dict] = {}
        for m in money_rows:
            src = srcs.get(int(m["source_id"])) if m["source_id"] is not None else None
            amt = float(m["amount"] or 0)
            if m["direction"] == "debit":
                paid_to += amt
            else:
                got_from += amt
            money.append({"money_id": m["money_id"], "event_id": m["event_id"], "ts": m["ts"],
                          "when": text.fmt_when(m["ts"]), "amount": m["amount"], "amount_text": text.format_inr(m["amount"]),
                          "direction": m["direction"],
                          "words": ("Paid to them" if m["direction"] == "debit" else "Received from them"),
                          "method": m["method"], "ref": m["ref"], "phone": _chip(src),
                          "said_in_chat": bool(m["said_in_chat"])})
            if src and src.get("owner_person_id") is not None and int(src["owner_person_id"]) != pid:
                o = owners_money.setdefault(int(src["source_id"]), {"owner": src["owner_name"], "phone": _chip(src),
                                                                    "paid": 0.0, "received": 0.0, "n": 0})
                o["n"] += 1
                o["paid" if m["direction"] == "debit" else "received"] += amt
        money.reverse()

        # Across phones: the name each phone saved them under.
        by_phone: dict[int, list[str]] = defaultdict(list)
        for n in name_rows:
            if n["source_id"] not in (None, "") and n["name"] not in by_phone[int(n["source_id"])]:
                by_phone[int(n["source_id"])].append(n["name"])
        across_names = []
        for sid in sorted(srcs, key=lambda s: srcs[s]["phone_no"] or 0):
            src = srcs[sid]
            seen_here = sid in {x["source_id"] for x in row["phones"]}
            across_names.append({"phone": _chip(src), "names": by_phone.get(sid, []), "has_records": seen_here,
                                 "is_their_phone": sid in own_srcs})
        across_money = [{**o, "paid_text": text.format_inr(o["paid"]), "received_text": text.format_inr(o["received"])}
                        for o in owners_money.values()]
        banner = limits.banner_text(con)

    first_msg = next((e for e in events if e["kind"] != "call"), None)
    return {
        "person": row,
        "names": name_rows,
        "identifiers": [{"ident": i["ident"], "kind": i["kind"], "display": i.get("display") or i["ident"]}
                        for i in who.idents.get(pid, [])],
        "counts": {"messages": row["messages"], "calls": row["calls"], "first_ts": row["first_ts"],
                   "last_ts": row["last_ts"], "first": row["first"], "last": row["last"],
                   "first_event_id": events[0]["event_id"] if events else None,
                   "last_event_id": events[-1]["event_id"] if events else None,
                   "first_message_id": first_msg["event_id"] if first_msg else None},
        "weekly": weekly,
        "chats": chats,
        "calls": calls,
        "money": {"rows": money, "paid_to_them": paid_to, "received_from_them": got_from,
                  "paid_text": text.format_inr(paid_to), "received_text": text.format_inr(got_from), "n": len(money)},
        "media": media,
        "places_together": [],
        "across": {"names": across_names, "money_with_owners": across_money},
        "ask": f"What do the records say about {row['name']}?",
        "limit": banner,
    }
