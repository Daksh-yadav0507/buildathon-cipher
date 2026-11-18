"""The Dashboard's numbers: /stats, /activity and /story (worked out once per case version, see ib/ready.py).

Every link is {page, params}, for the page to turn into a hash with IB.link(page, params):
page '' is the Dashboard, 'timeline', 'calls', 'people', 'person/12', 'chats', 'places', 'sources'.
All times are UTC ms; days, months and hours are India time. The warrant limit applies to every count.
"""
from __future__ import annotations

import json
import math

from fastapi import APIRouter, Depends

from ib import db, limits, ready, text
from ib.officers import CaseAccess, require_case

router = APIRouter()

IST_SHIFT = "'+330 minutes'"   # SQLite modifier: UTC to India time
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
APP_NAMES = {"whatsapp": "WhatsApp", "sms": "SMS", "telegram": "Telegram", "signal": "Signal",
             "imessage": "iMessage", "phone": "Calls", "calls": "Calls", "email": "Email",
             "photos": "Photos", "camera": "Photos", "files": "Files", "maps": "Maps"}


def link(page: str, **params) -> dict:
    return {"page": page, "params": {k: str(v) for k, v in params.items() if v not in (None, "")}}


def hour_words(h: int) -> str:
    h %= 24
    if h == 0:
        return "midnight"
    if h == 12:
        return "noon"
    return f"{h % 12} {'am' if h < 12 else 'pm'}"


def first_name(name: str | None) -> str:
    return (name or "").split()[0] if (name or "").strip() else "the owner"


def short_device(src: dict) -> str:
    probe = f"{src.get('device') or ''} {src.get('platform') or ''} {src.get('os') or ''}".lower()
    if "iphone" in probe or "ios" in probe:
        return "iPhone"
    if "android" in probe:
        return "Android"
    label = src.get("label") or ""
    return label.split("|", 1)[1].strip() if "|" in label else (src.get("device") or "phone")


def phone_words(src: dict) -> str:
    if src.get("owner_name"):
        return f"{src['owner_name']}'s {short_device(src)}"
    label = src.get("label") or f"Phone {src.get('phone_no') or ''}".strip()
    return label.split("|", 1)[1].strip() if "|" in label else label


def and_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def day_words(ms: int) -> str:
    d = text.ist(ms)
    return f"{d.day} {d.strftime('%b')}"


def span_words(lo: int, hi: int) -> str:
    a, b = text.ist(lo), text.ist(hi)
    if a.date() == b.date():
        return f"on {day_words(lo)}"
    if (a.year, a.month) == (b.year, b.month):
        return f"between {a.day} and {b.day} {b.strftime('%b')}"
    return f"between {day_words(lo)} and {day_words(hi)}"


def _sources(con) -> list[dict]:
    return db.rows(con, "SELECT source_id, phone_no, label, owner_name, owner_person_id, platform, device, os, "
                        "status, first_ts, last_ts, n_events FROM sources ORDER BY phone_no, source_id")


def _contacts(con, w: str, p: list, source_id: int | None = None) -> list[dict]:
    """One row per (other person, record) for messages and calls: who the record was with."""
    src = " AND e.source_id = ?" if source_id is not None else ""
    sp = [source_id] if source_id is not None else []
    sql = (
        "SELECT i.person_id AS pid, e.kind, e.ts, e.direction, e.source_id FROM events e "
        "JOIN identifiers i ON i.ident = e.sender "
        f"WHERE {w} AND e.kind IN ('message','call') AND e.direction = 'in'{src} "
        "UNION ALL "
        "SELECT i.person_id AS pid, e.kind, e.ts, e.direction, e.source_id FROM events e, "
        "json_each(CASE WHEN json_valid(e.recipients) THEN e.recipients ELSE '[]' END) j "
        "JOIN identifiers i ON i.ident = j.value "
        f"WHERE {w} AND e.kind IN ('message','call') AND e.direction = 'out'{src}")
    return db.rows(con, sql, [*p, *sp, *p, *sp])


def _people_info(con) -> dict[int, dict]:
    out = {}
    for r in db.rows(con, "SELECT person_id, name, names, kind, is_owner, owner_source_id FROM persons"):
        out[r["person_id"]] = r
    return out


def _aliases(person: dict) -> list[str]:
    try:
        names = json.loads(person.get("names") or "[]")
    except (TypeError, ValueError):
        names = []
    seen, out = {(person.get("name") or "").lower()}, []
    for n in names:
        nm = (n.get("name") if isinstance(n, dict) else str(n)) or ""
        if nm and nm.lower() not in seen:
            seen.add(nm.lower())
            out.append(nm)
    return out[:4]


def _owners(con) -> set[int]:
    ids = {r[0] for r in con.execute("SELECT person_id FROM persons WHERE is_owner = 1")}
    ids |= {r[0] for r in con.execute("SELECT owner_person_id FROM sources WHERE owner_person_id IS NOT NULL")}
    return ids


# ================================================================ /stats


def compute_stats(con) -> dict:
    w, p = limits.where(con, "e")
    one = lambda sql, extra=(): db.scalar(con, f"SELECT {sql} FROM events e WHERE {w}{extra[0] if extra else ''}",
                                         [*p, *(extra[1] if extra else [])], 0) or 0
    records = one("COUNT(*)")
    messages = one("COUNT(*)", (" AND e.kind = 'message'", []))
    calls = one("COUNT(*)", (" AND e.kind = 'call'", []))
    deleted = one("COUNT(*)", (" AND e.kind = 'message' AND e.status = 'deleted'", []))
    deleted_all = one("COUNT(*)", (" AND e.status = 'deleted'", []))
    missed = one("COUNT(*)", (" AND e.kind = 'call' AND e.status = 'missed'", []))
    span = db.one(con, f"SELECT MIN(e.ts) AS lo, MAX(e.ts) AS hi FROM events e WHERE {w} AND e.ts IS NOT NULL", p) or {}

    by_app = db.rows(con, f"SELECT COALESCE(e.app,'') AS app, e.kind, COUNT(*) AS n, MIN(e.ts) AS first_ts, "
                          f"MAX(e.ts) AS last_ts FROM events e WHERE {w} GROUP BY 1, 2 ORDER BY n DESC", p)
    for r in by_app:
        r["name"] = APP_NAMES.get(r["app"], r["app"].title() if r["app"] else r["kind"].title())
        r["link"] = link("calls") if r["kind"] == "call" else link("timeline", app=r["app"], kind=r["kind"])
    kinds: dict[str, int] = {}
    for r in by_app:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + r["n"]

    per_src = {r["source_id"]: r["n"] for r in db.rows(
        con, f"SELECT e.source_id, COUNT(*) AS n FROM events e WHERE {w} GROUP BY 1", p)}
    phones = []
    for s in _sources(con):
        phones.append({**s, "records": per_src.get(s["source_id"], 0), "words": phone_words(s),
                       "link": link("phone", source=s["source_id"])})

    # people: one pass over who each message and call was with
    owner_of = {s["source_id"]: s["owner_person_id"] for s in phones}
    info = _people_info(con)
    agg: dict[int, dict] = {}
    for r in _contacts(con, w, p):
        pid = r["pid"]
        if pid == owner_of.get(r["source_id"]):
            continue
        a = agg.setdefault(pid, {"messages": 0, "calls": 0, "in": 0, "out": 0, "last_ts": None, "phones": set()})
        a["messages" if r["kind"] == "message" else "calls"] += 1
        a["in" if r["direction"] == "in" else "out"] += 1
        if r["ts"] is not None and (a["last_ts"] is None or r["ts"] > a["last_ts"]):
            a["last_ts"] = r["ts"]
        a["phones"].add(r["source_id"])
    in_touch = sum(1 for a in agg.values() if a["in"] and a["out"])
    if not limits.get_limit(con):
        grouped = db.scalar(con, "SELECT COUNT(*) FROM persons WHERE group_kind = 'in-touch' AND "
                                 "COALESCE(is_owner,0) = 0", [], 0) or 0
        in_touch = grouped or in_touch
    labels = {s["source_id"]: s["label"] for s in phones}
    ranked = sorted(agg.items(), key=lambda kv: (bool(kv[1]["in"] and kv[1]["out"]),
                                                 kv[1]["messages"] + kv[1]["calls"]), reverse=True)
    top = []
    for pid, a in ranked[:10]:
        per = info.get(pid) or {}
        top.append({"person_id": pid, "name": per.get("name") or "Unknown", "aliases": _aliases(per),
                    "messages": a["messages"], "calls": a["calls"], "two_way": bool(a["in"] and a["out"]),
                    "last_ts": a["last_ts"], "phones": [labels.get(s) for s in sorted(a["phones"]) if labels.get(s)],
                    "link": link(f"person/{pid}")})

    return {
        "records": records, "messages": messages, "calls": calls, "people_in_touch": in_touch,
        "deleted": deleted, "deleted_all": deleted_all, "missed": missed,
        "phones": phones, "by_app": by_app, "kinds": kinds, "top_people": top,
        "first_ts": span.get("lo"), "last_ts": span.get("hi"),
        "links": {"records": link("timeline"), "messages": link("timeline", kind="message"),
                  "calls": link("calls"), "people_in_touch": link("people", group="in-touch"),
                  "deleted": link("timeline", kind="message", status="deleted"),
                  "missed": link("calls", type="missed")},
    }


# ================================================================ /activity


def compute_activity(con) -> dict:
    w, p = limits.where(con, "e")
    base = f"FROM events e WHERE {w} AND e.ts IS NOT NULL AND e.kind != 'contact'"
    months = {r["m"]: r["n"] for r in db.rows(
        con, f"SELECT strftime('%Y-%m', e.ts/1000, 'unixepoch', {IST_SHIFT}) AS m, COUNT(*) AS n {base} GROUP BY 1", p)}
    monthly = []
    if months:
        y, m = map(int, min(months).split("-"))
        ye, me = map(int, max(months).split("-"))
        while (y, m) <= (ye, me) and len(monthly) < 240:
            key = f"{y:04d}-{m:02d}"
            monthly.append({"month": key, "n": months.get(key, 0),
                            "link": link("timeline", **{"from": f"{key}-01", "to": _month_end(y, m)})})
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    heat = [[0] * 24 for _ in range(7)]
    for r in db.rows(con, f"SELECT CAST(strftime('%w', e.ts/1000, 'unixepoch', {IST_SHIFT}) AS INTEGER) AS d, "
                          f"CAST(strftime('%H', e.ts/1000, 'unixepoch', {IST_SHIFT}) AS INTEGER) AS h, COUNT(*) AS n "
                          f"{base} GROUP BY 1, 2", p):
        heat[(r["d"] + 6) % 7][r["h"]] = r["n"]
    hours = [sum(heat[d][h] for d in range(7)) for h in range(24)]
    total = sum(hours)
    busiest_hour = None
    if total:
        h = max(range(24), key=lambda i: hours[i])
        busiest_hour = {"hour": h, "n": hours[h], "text": f"{hour_words(h)} to {hour_words(h + 1)}"}
    days = db.rows(con, f"SELECT strftime('%Y-%m-%d', e.ts/1000, 'unixepoch', {IST_SHIFT}) AS day, COUNT(*) AS n "
                        f"{base} GROUP BY 1 ORDER BY n DESC, day DESC LIMIT 5", p)
    for d in days:
        d["link"] = link("timeline", day=d["day"])
    return {"monthly": monthly, "heat": heat, "heat_days": DAYS, "hours": hours, "busiest_hour": busiest_hour,
            "window": _window(hours), "busiest_days": days, "total": total}


def _month_end(y: int, m: int) -> str:
    import calendar
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def _window(hours: list[int], width: int = 3) -> dict | None:
    """The busiest `width`-hour stretch of the day (wrapping past midnight), and its share of all records."""
    total = sum(hours)
    if not total:
        return None
    start = max(range(24), key=lambda s: sum(hours[(s + i) % 24] for i in range(width)))
    n = sum(hours[(start + i) % 24] for i in range(width))
    return {"from": start, "to": (start + width) % 24, "n": n, "share": round(n / total, 3),
            "text": f"between {hour_words(start)} and {hour_words(start + width)}"}


# ================================================================ /story


def _km(a_lat, a_lon, b_lat, b_lon) -> float:
    dy = (a_lat - b_lat) * 111.0
    dx = (a_lon - b_lon) * 111.0 * math.cos(math.radians((a_lat + b_lat) / 2))
    return math.hypot(dx, dy)


def together(con, w: str, p: list, window_ms: int = 15 * 60_000, km: float = 0.3) -> list[dict]:
    """Times two different phones were at the same place within 15 minutes: one entry per occasion."""
    pts = db.rows(con, f"SELECT e.event_id, e.source_id, e.ts, e.lat, e.lon, e.place FROM events e WHERE {w} "
                       f"AND e.lat IS NOT NULL AND e.lon IS NOT NULL AND e.ts IS NOT NULL ORDER BY e.ts LIMIT 60000", p)
    hits = []
    for i, a in enumerate(pts):
        j = i + 1
        while j < len(pts) and pts[j]["ts"] - a["ts"] <= window_ms:
            b = pts[j]
            if b["source_id"] != a["source_id"] and _km(a["lat"], a["lon"], b["lat"], b["lon"]) <= km:
                hits.append((a, b))
            j += 1
    occasions: list[dict] = []
    for a, b in hits:
        if occasions and a["ts"] - occasions[-1]["last"] <= 2 * 3600_000:
            o = occasions[-1]
            o["last"] = max(o["last"], b["ts"])
            o["event_ids"].extend(x for x in (a["event_id"], b["event_id"]) if x not in o["event_ids"])
            o["sources"] |= {a["source_id"], b["source_id"]}
        else:
            occasions.append({"ts": a["ts"], "last": b["ts"], "place": a["place"] or b["place"] or "",
                              "lat": a["lat"], "lon": a["lon"], "sources": {a["source_id"], b["source_id"]},
                              "event_ids": [a["event_id"], b["event_id"]]})
    for o in occasions:
        o["sources"] = sorted(o["sources"])
        o["event_ids"] = o["event_ids"][:20]
    return occasions


def compute_story(con) -> dict:
    w, p = limits.where(con, "e")
    sentences: list[dict] = []
    srcs = _sources(con)
    info = _people_info(con)

    # 1. the phones
    if not srcs:
        sentences.append({"key": "phones", "text": "No phones have been added to this case yet.",
                          "link": link("sources")})
        return {"sentences": sentences, "questions": []}
    words = [phone_words(s) for s in srcs]
    sentences.append({"key": "phones", "link": link("sources"),
                      "text": f"This case holds {text.plural(len(srcs), 'phone')}: {and_list(words)}."})

    # 2. who each phone's owner talks to most
    best_pair = None
    for s in srcs[:4]:
        agg: dict[int, dict] = {}
        for r in _contacts(con, w, p, s["source_id"]):
            pid = r["pid"]
            if pid == s.get("owner_person_id"):
                continue
            per = info.get(pid) or {}
            if per.get("kind") not in (None, "", "person"):
                continue
            a = agg.setdefault(pid, {"messages": 0, "calls": 0, "hours": [0] * 24})
            a["messages" if r["kind"] == "message" else "calls"] += 1
            if r["ts"] is not None:
                a["hours"][text.ist(r["ts"]).hour] += 1
        if not agg:
            continue
        pid, a = max(agg.items(), key=lambda kv: kv[1]["messages"] + kv[1]["calls"])
        if a["messages"] + a["calls"] < 2:
            continue
        name = (info.get(pid) or {}).get("name") or "an unknown number"
        bits = []
        if a["messages"]:
            bits.append(text.plural(a["messages"], "message"))
        if a["calls"]:
            bits.append(text.plural(a["calls"], "call"))
        line = f"{first_name(s.get('owner_name'))} talks most with {name}: {and_list(bits)}"
        win = _window(a["hours"])
        if win and win["share"] >= 0.4 and a["messages"] + a["calls"] >= 6:
            line += f", mostly {win['text']}"
        sentences.append({"key": f"top-{s['source_id']}", "text": line + ".", "link": link(f"person/{pid}"),
                          "person_id": pid, "n": a["messages"] + a["calls"]})
        if best_pair is None or a["messages"] + a["calls"] > best_pair[2]:
            best_pair = (s, name, a["messages"] + a["calls"])

    # 3. money
    mrows = db.rows(con, f"SELECT m.money_id, m.event_id, m.ts, m.amount, m.ref, m.method FROM money m "
                         f"WHERE m.amount IS NOT NULL AND COALESCE(m.said_in_chat, 0) = 0 "
                         f"AND m.event_id IN (SELECT e.event_id FROM events e WHERE {w})", p)
    seen, total, biggest, n_pay = set(), 0.0, None, 0
    for m in mrows:
        key = ("ref", m["ref"]) if m["ref"] else ("id", m["money_id"])
        if key in seen:
            continue
        seen.add(key)
        n_pay += 1
        total += float(m["amount"] or 0)
        if biggest is None or float(m["amount"] or 0) > float(biggest["amount"] or 0):
            biggest = m
    if n_pay:
        line = f"{text.inr_short(total)} moved through {text.plural(n_pay, 'payment')} in bank and UPI messages"
        if biggest and n_pay > 1:
            line += f"; the biggest was {text.inr_short(biggest['amount'])}"
            if biggest["ts"]:
                line += f" on {day_words(biggest['ts'])}"
        more = [{"text": "The biggest payment", **link(f"record/{biggest['event_id']}")}] if biggest else []
        sentences.append({"key": "money", "text": line + ".", "link": link("timeline", money=1), "more": more,
                          "n": n_pay, "total": total})

    # 4. deleted messages
    deleted = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE {w} AND e.kind='message' AND e.status='deleted'",
                        p, 0) or 0
    if deleted:
        line = f"{text.plural(deleted, 'message was', 'messages were')} deleted and recovered"
        top = db.one(con, f"SELECT e.conv_id, COUNT(*) AS n, MIN(e.ts) AS lo, MAX(e.ts) AS hi FROM events e "
                          f"WHERE {w} AND e.kind='message' AND e.status='deleted' AND e.conv_id IS NOT NULL "
                          f"GROUP BY e.conv_id ORDER BY n DESC LIMIT 1", p)
        more = []
        if top and top["n"] >= 2 and deleted > 1:
            conv = db.one(con, "SELECT c.title, c.is_group, s.owner_name FROM conversations c "
                               "LEFT JOIN sources s ON s.source_id = c.source_id WHERE c.conv_id=?", [top["conv_id"]])
            if conv:
                where = (f"the group '{conv['title']}'" if conv["is_group"]
                         else f"{first_name(conv['owner_name'])}'s chat with {conv['title'] or 'one person'}")
                share = "all" if top["n"] == deleted else group(top["n"])
                line += f", {share} of them in {where}"
                if top["lo"] is not None:
                    line += f" {span_words(top['lo'], top['hi'])}"
                more.append({"text": "Open that chat", **link("chats", conv=top["conv_id"])})
        sentences.append({"key": "deleted", "text": line + ".", "more": more, "n": deleted,
                          "link": link("timeline", kind="message", status="deleted")})

    # 5. the phones together
    if len(srcs) >= 2:
        occ = together(con, w, p)
        if occ:
            last = occ[-1]
            line = f"The phones were together {_times(len(occ))}"
            line += ", last" if len(occ) > 1 else ","
            if last["place"]:
                place = last["place"]
                line += f" {place[0].lower()}{place[1:]}" if place.lower().startswith("near ") else f" at {place}"
            line += f" on {day_words(last['ts'])} at {text.fmt_time(last['ts'])}"
            sentences.append({"key": "together", "text": line + ".", "n": len(occ),
                              "link": link("places", day=text.ist_day(last["ts"])), "event_ids": last["event_ids"]})

    # 6. missed calls and the busiest day
    missed = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE {w} AND e.kind='call' AND e.status='missed'",
                       p, 0) or 0
    if missed:
        sentences.append({"key": "missed", "text": f"{text.plural(missed, 'call was', 'calls were')} missed.",
                          "link": link("calls", type="missed"), "n": missed})
    day = db.one(con, f"SELECT strftime('%Y-%m-%d', e.ts/1000, 'unixepoch', {IST_SHIFT}) AS day, COUNT(*) AS n "
                      f"FROM events e WHERE {w} AND e.ts IS NOT NULL AND e.kind != 'contact' "
                      f"GROUP BY 1 ORDER BY n DESC LIMIT 1", p)
    if day and day["n"] > 1:
        d0, _ = text.day_range(day["day"])
        sentences.append({"key": "busiest", "link": link("timeline", day=day["day"]), "n": day["n"],
                          "text": f"The busiest day was {day_words(d0)} {text.ist(d0).year}, "
                                  f"with {text.plural(day['n'], 'record')}."})

    questions = ["Paisa kisne kisko bheja?"]
    if best_pair:
        questions.append(f"What did {first_name(best_pair[0].get('owner_name'))} and {best_pair[1]} talk about?")
    if deleted:
        questions.append("What do the deleted messages say?")
    if day:
        d0, _ = text.day_range(day["day"])
        questions.append(f"What happened on {day_words(d0)}?")
    questions.append("Who was at the same place at the same time?")
    return {"sentences": sentences, "questions": questions[:4]}


def group(n: int) -> str:
    return text.group_indian(n)


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{text.group_indian(n)} times")


ready.register("stats", compute_stats)
ready.register("activity", compute_activity)
ready.register("story", compute_story)


# ================================================================ routes


@router.get("/api/cases/{cid}/stats")
def stats(cid: str, acc: CaseAccess = Depends(require_case)):
    value, updating = ready.get(acc.cid, "stats", compute_stats)
    return ready.with_updating(value, updating)


@router.get("/api/cases/{cid}/activity")
def activity(cid: str, acc: CaseAccess = Depends(require_case)):
    value, updating = ready.get(acc.cid, "activity", compute_activity)
    return ready.with_updating(value, updating)


@router.get("/api/cases/{cid}/story")
def story(cid: str, acc: CaseAccess = Depends(require_case)):
    value, updating = ready.get(acc.cid, "story", compute_story)
    return ready.with_updating(value, updating)
