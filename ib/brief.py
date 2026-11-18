"""The case brief (section 8.6): seven sections, every line citing the records it rests on.

Code gathers the facts first (phones, top people by two-way messages, money totals, planted keywords and code words,
deletions by chat, late-night share, places). With an AI set up, it rewrites each section from those facts plus the
top 60 records for the section, and every line is checked the same way Ask checks its lines. Without an AI, the
code's own lines are the brief.
"""
from __future__ import annotations

import json
import sys
import traceback

from fastapi import APIRouter, Depends

from ib import audit, db, limits, text
from ib.officers import CaseAccess, require_case

router = APIRouter()

TITLES = [
    "Whose phones these are",
    "The people who matter, and what each does",
    "What the case seems to be about",
    "Money",
    "Places and travel",
    "What was hidden or deleted",
    "Open questions to follow up",
]
PER_SECTION = 60
MAX_LINES = 8
LATE_FROM, LATE_TO = 23, 5  # 11 pm to 5 am, India time


def _line(t: str, ids) -> dict:
    ids = [i for i in dict.fromkeys(ids) if i][:6]
    return {"text": t, "records": ids, "checked": True}


def _ask_mod():
    try:
        from ib import ask
        return ask
    except Exception:
        return None


def _who_name(con, ident: str, cache: dict) -> str:
    if not ident:
        return ""
    if ident not in cache:
        r = db.one(con, "SELECT i.display, p.name FROM identifiers i LEFT JOIN persons p ON p.person_id = i.person_id "
                        "WHERE i.ident = ?", (ident,))
        cache[ident] = (r and (r.get("name") or r.get("display"))) or ident.split(":", 1)[-1]
    return cache[ident]


# ====================================================================== facts by code


def s_phones(con, w, p) -> list[dict]:
    out = []
    for s in db.rows(con, "SELECT * FROM sources ORDER BY phone_no"):
        rows = db.rows(con, f"SELECT e.event_id, e.ts FROM events e WHERE {w} AND e.source_id = ? AND e.ts IS NOT NULL "
                            f"ORDER BY e.ts", [*p, s["source_id"]])
        if not rows:
            continue
        n = len(rows)
        dev = " ".join(x for x in (s.get("device"), s.get("os")) if x)
        t = (f"{s.get('label') or 'Phone ' + str(s.get('phone_no'))}: belongs to {s.get('owner_name') or 'an unknown owner'}"
             f"{', ' + dev if dev else ''}. {text.plural(n, 'record')} from {text.fmt_date(rows[0]['ts'])} to "
             f"{text.fmt_date(rows[-1]['ts'])}.")
        out.append(_line(t, [rows[0]["event_id"], rows[-1]["event_id"]]))
    return out


def s_people(con, w, p, names: dict) -> list[dict]:
    owners = {r[0] for r in con.execute("SELECT person_id FROM persons WHERE is_owner = 1")}
    cands = db.rows(con, "SELECT person_id, name, is_owner, owner_source_id FROM persons WHERE kind = 'person' OR kind IS NULL "
                         "ORDER BY n_messages + n_calls DESC LIMIT 25")
    scored = []
    for c in cands:
        idents = [r[0] for r in con.execute("SELECT ident FROM identifiers WHERE person_id = ?", (c["person_id"],))]
        if not idents:
            continue
        ph = ",".join("?" * len(idents))
        if c.get("is_owner") and c.get("owner_source_id") is not None:  # an owner counts on the other phones only
            w2, p2 = f"{w} AND e.source_id <> ?", [*p, c["owner_source_id"]]
        else:
            w2, p2 = w, p
        likes = " OR ".join("e.recipients LIKE ?" for _ in idents)
        lp = [f'%"{i}"%' for i in idents]
        frm = db.rows(con, f"SELECT e.event_id, e.ts FROM events e WHERE {w2} AND e.kind = 'message' AND e.sender IN ({ph}) "
                           f"ORDER BY e.ts DESC", [*p2, *idents])
        to = db.rows(con, f"SELECT e.event_id, e.ts FROM events e WHERE {w2} AND e.kind = 'message' AND e.direction = 'out' "
                          f"AND ({likes}) ORDER BY e.ts DESC", [*p2, *lp])
        calls = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE {w2} AND e.kind = 'call' AND (e.sender IN ({ph}) OR "
                               f"{likes})", [*p2, *idents, *lp], default=0) or 0
        if not frm and not to:
            continue
        two_way = min(len(frm), len(to))
        scored.append((two_way, len(frm) + len(to), c, frm, to, calls))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    out = []
    for two_way, n, c, frm, to, calls in scored[:6]:
        own = " (a phone owner in this case)" if c["person_id"] in owners else ""
        last = max([r["ts"] for r in frm + to if r["ts"]] or [0])
        t = (f"{c['name']}{own}: {text.plural(n, 'message')} ({len(to)} sent to, {len(frm)} from)"
             f"{', ' + text.plural(calls, 'call') if calls else ''}; last in touch {text.fmt_date(last) if last else 'unknown'}.")
        out.append(_line(t, [r["event_id"] for r in (frm[:2] + to[:2])]))
    return out


def _keywords() -> list[str]:
    try:
        from ib import keyq
        words = [wd for ws in keyq.KEYWORDS.values() for wd in ws] + [keyq.DRUG_MAAL]
    except Exception:
        words = ["biscuit", "gold", "cargo", "airport", "invoice", "hawala", "cash", "customs", "raid", "delete"]
    return list(dict.fromkeys(words + ["raid", "delete", "police", "customs"]))


def _hits(con, w, p, word: str, n: int = 200) -> list[str]:
    q = text.fts_query(text.tokens(word) if " " in word else [word], op="AND", column="folded")
    if not q:
        return []
    try:
        return [r[0] for r in con.execute(
            f"SELECT e.event_id FROM events e WHERE {w} AND e.event_id IN (SELECT event_id FROM events_fts WHERE "
            f"events_fts MATCH ?) ORDER BY e.ts LIMIT ?", [*p, q, n])]
    except Exception:
        return []


def s_about(con, w, p) -> list[dict]:
    out = []
    try:
        codes = db.rows(con, "SELECT word, meaning, status FROM codes WHERE status IN ('confirmed','suggested') "
                             "ORDER BY status = 'confirmed' DESC, hits DESC LIMIT 5")
    except Exception:
        codes = []
    for c in codes:
        ids = _hits(con, w, p, c["word"])
        if ids:
            how = "a confirmed code word" if c["status"] == "confirmed" else "a possible code word"
            out.append(_line(f"'{c['word']}' seems to mean '{c['meaning']}' ({how}); it comes up in "
                             f"{text.plural(len(ids), 'record')}.", ids[:3]))
    found = []
    for wd in _keywords():
        ids = _hits(con, w, p, wd)
        if ids:
            found.append((len(ids), wd, ids))
    found.sort(key=lambda x: -x[0])
    done = {c["word"].lower() for c in codes}
    for n, wd, ids in found:
        if wd.lower() in done or len(out) >= MAX_LINES:
            continue
        out.append(_line(f"'{wd}' comes up in {text.plural(n, 'record')}, first on {text.fmt_date(_ts(con, ids[0]))}.",
                         ids[:3]))
    return out


def _ts(con, eid):
    return db.scalar(con, "SELECT ts FROM events WHERE event_id = ?", (eid,), default=0) or 0


def s_money(con, w, p, names: dict) -> list[dict]:
    rows = db.rows(con, f"SELECT m.* FROM money m WHERE m.event_id IN (SELECT e.event_id FROM events e WHERE {w}) "
                        f"ORDER BY m.amount DESC", p)
    if not rows:
        return []
    out = []
    deb = [r for r in rows if r.get("direction") == "debit"]
    cre = [r for r in rows if r.get("direction") == "credit"]
    if deb:
        out.append(_line(f"{text.format_inr(sum(r['amount'] or 0 for r in deb))} went out over "
                         f"{text.plural(len(deb), 'payment')}.", [r["event_id"] for r in deb[:3]]))
    if cre:
        out.append(_line(f"{text.format_inr(sum(r['amount'] or 0 for r in cre))} came in over "
                         f"{text.plural(len(cre), 'payment')}.", [r["event_id"] for r in cre[:3]]))
    for r in rows[:5]:
        cp = r.get("counterparty") or _who_name(con, r.get("counterparty_ident") or "", names) or "someone not named"
        way = "paid to" if r.get("direction") == "debit" else "received from"
        out.append(_line(f"{text.format_inr(r['amount'] or 0)} {way} {cp} by {r.get('method') or 'an unknown route'} "
                         f"on {text.fmt_when(r.get('ts'))}.", [r["event_id"]]))
    talked = [r for r in rows if r.get("said_in_chat")]
    if talked:
        out.append(_line(f"{text.plural(len(talked), 'payment')} also talked about in chats.",
                         [r["event_id"] for r in talked[:3]]))
    return out[:MAX_LINES]


def s_places(con, w, p) -> list[dict]:
    out = []
    rows = db.rows(con, f"SELECT e.place, COUNT(*) n, MIN(e.ts) a, MAX(e.ts) b, GROUP_CONCAT(e.event_id) ids "
                        f"FROM events e WHERE {w} AND e.place IS NOT NULL AND e.place <> '' GROUP BY e.place "
                        f"ORDER BY n DESC LIMIT 5", p)
    for r in rows:
        ids = (r["ids"] or "").split(",")
        out.append(_line(f"{r['place']}: {text.plural(r['n'], 'record')}, from {text.fmt_date(r['a'])} to "
                         f"{text.fmt_date(r['b'])}.", ids[:3]))
    msgs = db.rows(con, f"SELECT e.event_id, e.ts FROM events e WHERE {w} AND e.kind IN ('message','call') AND e.ts IS NOT NULL", p)
    if msgs:
        late = [m for m in msgs if (lambda h: h >= LATE_FROM or h < LATE_TO)(text.ist(m["ts"]).hour)]
        if late:
            pct = round(100 * len(late) / len(msgs))
            out.append(_line(f"{pct}% of messages and calls ({group(len(late))} of {group(len(msgs))}) are late at night, "
                             f"between 11 pm and 5 am.", [m["event_id"] for m in late[-3:]]))
    return out


def group(n):
    return text.group_indian(n)


def s_hidden(con, w, p) -> list[dict]:
    out = []
    rows = db.rows(con, f"SELECT e.conv_id, c.title, COUNT(*) n, GROUP_CONCAT(e.event_id) ids FROM events e "
                        f"LEFT JOIN conversations c ON c.conv_id = e.conv_id WHERE {w} AND e.status IN ('deleted','unsent') "
                        f"AND e.kind <> 'call' GROUP BY e.conv_id ORDER BY n DESC LIMIT 5", p)
    for r in rows:
        ids = (r["ids"] or "").split(",")
        out.append(_line(f"{text.plural(r['n'], 'message')} deleted or unsent in "
                         f"{('the chat ' + repr(r['title'])) if r['title'] else 'a chat'}.", ids[:3]))
    calls = db.rows(con, f"SELECT e.event_id FROM events e WHERE {w} AND e.kind = 'call' AND e.status = 'deleted' "
                         f"ORDER BY e.ts", p)
    if calls:
        out.append(_line(f"{text.plural(len(calls), 'call')} deleted from a call log.", [c["event_id"] for c in calls[:3]]))
    for wd in ("delete", "raid"):
        ids = _hits(con, w, p, wd, 50)
        if ids:
            out.append(_line(f"The word '{wd}' is used in {text.plural(len(ids), 'record')}.", ids[:3]))
    return out[:MAX_LINES]


def s_open(sections: list[list[dict]]) -> list[dict]:
    """Follow-ups drawn from the other sections, each citing the same records."""
    out = []
    money, places, hidden, about = sections[3], sections[4], sections[5], sections[2]
    for ln in money[2:4]:
        out.append(_line(f"What was this payment for, and who is on the other side? {ln['text']}", ln["records"]))
    for ln in hidden[:2]:
        out.append(_line(f"What was in the deleted records, and who asked for them to go? {ln['text']}", ln["records"]))
    for ln in about[:2]:
        out.append(_line(f"What does this stand for in each chat? {ln['text']}", ln["records"]))
    for ln in places[:1]:
        out.append(_line(f"Who else was at this place at the same time? {ln['text']}", ln["records"]))
    return out[:MAX_LINES]


def code_sections(con) -> list[list[dict]]:
    w, p = limits.where(con, "e")
    names: dict = {}
    secs = [s_phones(con, w, p), s_people(con, w, p, names), s_about(con, w, p), s_money(con, w, p, names),
            s_places(con, w, p), s_hidden(con, w, p)]
    secs.append(s_open(secs))
    return secs


# ====================================================================== the AI, checked like Ask


def ai_sections(con, cid: str, secs: list[list[dict]], job=None) -> tuple[list[list[dict]], bool]:
    ask = _ask_mod()
    try:
        from ib import llm
    except Exception:
        return secs, False
    if ask is None or not llm.configured():
        return secs, False
    about = (db.get_case(cid) or {}).get("about") or ""
    ctx = ask.Ctx(con)
    used_ai = False
    out = []
    for i, (title, lines) in enumerate(zip(TITLES, secs)):
        if job:
            job.progress(i / len(TITLES))
        ids = [r for ln in lines for r in ln["records"]]
        if i == 3:
            ids += [r[0] for r in con.execute("SELECT event_id FROM money ORDER BY amount DESC LIMIT 40")]
        evmap = ask.load_events(con, ids[:PER_SECTION])
        if not evmap or not lines:
            out.append(lines)
            continue
        evid = "\n".join(ask.evidence_line(ctx, e) for e in evmap.values())
        facts = "\n".join(f"- {ln['text']} [{', '.join(ln['records'])}]" for ln in lines)
        system = ("You write one section of a case brief for an investigating officer, in plain English. Use only the "
                  "facts and records given. Every line must cite the record IDs it rests on. Reply with JSON only: "
                  "{\"lines\":[{\"text\":\"...\",\"records\":[\"P1-000123\"]}]}, at most 6 lines.")
        user = f"Case: {about}\nSection: {title}\n\nFacts found by code:\n{facts}\n\nRecords:\n{evid}"
        try:
            reply, _ = llm.ask_json(system, user)
        except Exception as e:
            print(f"[brief] AI section '{title}' failed: {e}", file=sys.stderr)
            reply = None
        money_by_event: dict = {}
        for m in ask.load_money(con, list(evmap)):
            money_by_event.setdefault(m["event_id"], []).append(m)
        checked = ask.check_lines(ctx, (reply or {}).get("lines"), evmap, money_by_event, title) if reply else []
        if checked:
            used_ai = True
            out.append(checked)
        else:
            out.append(lines)
    return out, used_ai


# ====================================================================== writing and reading


def build(con, cid: str, job=None, use_ai: bool = True) -> dict:
    secs = code_sections(con)
    used_ai = False
    if use_ai:
        secs, used_ai = ai_sections(con, cid, secs, job)
    ai_where = None
    if used_ai:
        try:
            from ib import llm
            ai_where = llm.where()
        except Exception:
            ai_where = None
    sections = [{"title": t, "lines": ls} for t, ls in zip(TITLES, secs)]
    return {"sections": sections, "ai": ai_where, "by": "Written with the AI" if used_ai else
            "Written by code only: no AI is set up on this computer, so every line is taken straight from the records",
            "made_at": db.now_ms(), "made_from": str(db.case_version(con))}


def as_text(b: dict) -> str:
    parts = []
    for i, s in enumerate(b["sections"]):
        parts.append(f"{i + 1}. {s['title']}")
        parts += [f"- {ln['text']} [{', '.join(ln['records'])}]" for ln in s["lines"]]
    return "\n".join(parts)


def write_brief(con, cid: str, job=None) -> dict:
    """Write and save the brief on an open connection (the caller commits). Not saved under a warrant limit."""
    if limits.get_limit(con) is not None:
        return build(con, cid, job, use_ai=False)
    b = build(con, cid, job)
    con.execute("INSERT INTO brief(ts, text, sections) VALUES(?,?,?)",
                (b["made_at"], as_text(b), json.dumps(b, ensure_ascii=False, default=str)))
    return b


def _work(job, cid: str):
    job.step("Writing the case brief")
    con = db.open_case(cid)
    try:
        b = write_brief(con, cid, job)
        con.commit()
        job.progress(1)
        return {"lines": sum(len(s["lines"]) for s in b["sections"])}
    finally:
        con.close()


def start(cid: str) -> dict:
    from ib import jobs
    return jobs.find(cid, "brief") or jobs.start(cid, "brief", _work, cid, label="Writing the case brief", steps=1)


def run_after_ingest(cid: str) -> None:
    start(cid)


@router.get("/api/cases/{cid}/brief")
def brief_get(cid: str, acc: CaseAccess = Depends(require_case)):
    from ib import jobs
    writing = bool(jobs.find(cid, "brief"))
    with db.case_db(cid) as con:
        banner = limits.banner_text(con)
        if limits.get_limit(con) is not None:
            b = build(con, cid, use_ai=False)  # under a warrant limit: worked out fresh, nothing saved is shown
        else:
            r = db.one(con, "SELECT sections FROM brief ORDER BY id DESC LIMIT 1")
            b = None
            if r:
                try:
                    b = json.loads(r["sections"] or "{}")
                except ValueError:
                    b = None
            if b is None:
                b = {"sections": []}
            elif b.get("made_from") != str(db.case_version(con)):
                b["stale"] = True
    b.update({"updating": writing, "writing": writing, "limit": banner})
    return b


@router.post("/api/cases/{cid}/brief")
def brief_post(cid: str, acc: CaseAccess = Depends(require_case)):
    audit.log(cid, acc, "brief", "Asked for the case brief to be written again")
    try:
        job = start(cid)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise
    return {"job": job}
