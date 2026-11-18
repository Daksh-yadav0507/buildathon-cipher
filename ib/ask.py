"""Ask (sections 8.2, 8.3, 8.7): code finds the evidence, the AI reads only that, code checks every line.

With no AI set up, code writes the answer from templates (money, deletions, closest records); every line
still cites the records it comes from. Other modules (brief, keyq) can call answer(con, question, ...)
directly to get the same result without saving it.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ib import ApiError, audit, db, limits, llm, text
from ib.officers import CaseAccess, require_case

router = APIRouter()

QUICK_N = 40
FURTHER_MAX = 400
PART_LINES = 250
MAX_LINES = 8

SYSTEM = (
    "You are an evidence assistant for investigating officers. You read only the records given below. "
    "Each record starts with its ID in square brackets. Answer the officer's question in plain English "
    "(keep names and Hinglish quotes as written). Every sentence must end with the IDs of the records it rests on, "
    "like [P1-000482]. Never state anything the records don't show. If the records don't answer part of the "
    "question, say so in \"not_found\". Name people as \"Name (Phone N)\" when they own one of the phones. "
    "Reply with JSON only: {\"lines\":[{\"text\":\"...\",\"records\":[\"ID\", ...]}],\"not_found\":[\"...\"],"
    "\"follow_ups\":[\"...\",\"...\"]}. Use at most 8 lines and 2 follow-ups."
)
NEED_HINT = (" If these records are not enough to answer, you may instead reply {\"need\":[\"words or people\"]} "
             "and more records will be found for you (at most twice).")
MAP_SYSTEM = (
    "You are an evidence assistant for investigating officers. You read only the records given below, one part of "
    "a longer set. Each record starts with its ID in square brackets. Write short notes of everything in this part "
    "that helps answer the officer's question, keeping names and Hinglish quotes as written. Every note must cite "
    "the IDs it rests on. Never state anything the records don't show. Reply with JSON only: "
    "{\"notes\":[{\"text\":\"...\",\"records\":[\"ID\", ...]}]}. At most 10 notes; an empty list if nothing helps."
)

_ID_RE = re.compile(r"\bP\d+-\d{3,}\b")
_QUOTE_RE = re.compile(r"[\"“”]([^\"“”]{2,200})[\"“”]")
_CAP_RE = re.compile(r"(?<![\w'])([A-Z][a-z]{2,})\b")

_MONEY_EXTRA = {"money", "send", "sent", "sends", "receive", "received", "got", "pay", "payment", "paid", "pays",
                "transfer", "transferred", "rupay", "rupee", "bhejo", "bheje", "bhejna", "lena", "liya", "di", "diye",
                "mile", "gaye", "whom", "upi", "amount", "cash", "hawala", "debit", "credit"}
_MONEY_FOLDED = {text.fold(w) for w in set(text.MONEY_WORDS) | _MONEY_EXTRA} - {""}
_DELETE_FOLDED = {text.fold(w) for w in ("delete", "deleted", "deleting", "deletion", "mita", "mitaya", "mitao",
                                         "mitana", "hata", "hataya", "hatao", "erase", "erased", "removed", "wipe",
                                         "wiped", "unsent", "clear", "cleared", "saaf")}
# capitalised words a line may use without them being in the records
_COMMON_CAPS = {w.lower() for w in """The This That These Those There Then They Their Them He She His Her Him It Its
On In At By For From To Of And Or But Not No Yes Both Also After Before Between During Later Earlier Next Same
Phone Phones Records Record Message Messages Chat Chats Call Calls Photo Photos Video Voice Note Notes Document
Invoice SMS WhatsApp Telegram Signal Imessage UPI IMPS NEFT Rs INR Mr Mrs Ms Sir Bhai Ji Night Morning Evening
Afternoon Midnight Today Yesterday Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March
April May June July August September October November December Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec
Someone Nobody Everyone Nothing Something One Two Three Four Five Six Seven Eight Nine Ten Who What When Where
Why How Which Deleted Missed Outgoing Incoming Received Sent Paid There Here Officer Case Group""".split()}


# ====================================================================== people and records in plain words

class Ctx:
    """What the case's records need to be shown in words: phones, and names for idents (looked up lazily)."""

    def __init__(self, con):
        self.con = con
        self.sources = {r["source_id"]: r for r in db.rows(
            con, "SELECT source_id, phone_no, label, owner_name, owner_person_id FROM sources")}
        self.owner_phone = {}  # person_id -> phone_no
        for s in self.sources.values():
            if s.get("owner_person_id") is not None:
                self.owner_phone.setdefault(s["owner_person_id"], s["phone_no"])
        for r in db.rows(con, "SELECT person_id, owner_source_id FROM persons WHERE is_owner = 1"):
            src = self.sources.get(r["owner_source_id"])
            if src:
                self.owner_phone.setdefault(r["person_id"], src["phone_no"])
        self._names: dict[str, tuple] = {}
        self._convs: dict[int, dict] = {}

    def phone_label(self, source_id) -> str:
        s = self.sources.get(source_id)
        return (s.get("label") or f"Phone {s.get('phone_no')}") if s else ""

    def phone_short(self, source_id) -> str:
        s = self.sources.get(source_id)
        return f"Phone {s['phone_no']}" if s and s.get("phone_no") is not None else ""

    def owner_words(self, source_id) -> str:
        s = self.sources.get(source_id)
        if not s:
            return "the phone's owner"
        name = s.get("owner_name") or "the owner"
        return f"{name} ({self.phone_short(source_id)})"

    def ident(self, ident: str | None) -> tuple[str, int | None]:
        """(name in words, person_id) for an ident."""
        ident = (ident or "").strip()
        if not ident:
            return "", None
        if ident in self._names:
            return self._names[ident]
        r = db.one(self.con, "SELECT i.display, p.person_id, p.name FROM identifiers i LEFT JOIN persons p "
                             "ON p.person_id = i.person_id WHERE i.ident = ?", (ident,))
        if r and r.get("name"):
            name, pid = r["name"], r["person_id"]
            if pid in self.owner_phone:
                name = f"{name} (Phone {self.owner_phone[pid]})"
        elif r and r.get("display"):
            name, pid = r["display"], r.get("person_id")
        else:
            name, pid = re.sub(r"^(wa|tg|sig|email|upi):", "", ident), None
        self._names[ident] = (name, pid)
        return name, pid

    def conv(self, conv_id) -> dict:
        if conv_id is None:
            return {}
        if conv_id not in self._convs:
            self._convs[conv_id] = db.one(self.con, "SELECT conv_id, title, is_group, app FROM conversations "
                                                    "WHERE conv_id = ?", (conv_id,)) or {}
        return self._convs[conv_id]

    def who(self, e: dict) -> tuple[str, str]:
        """(from, to) in words for a record."""
        owner = self.owner_words(e.get("source_id"))
        sender = self.ident(e.get("sender"))[0] if e.get("sender") else ""
        try:
            recips = json.loads(e.get("recipients") or "[]")
            if not isinstance(recips, list):
                recips = [recips]
        except ValueError:
            recips = [e.get("recipients")] if e.get("recipients") else []
        conv = self.conv(e.get("conv_id"))
        if e.get("direction") == "out":
            frm = sender or owner
            if conv.get("is_group") and conv.get("title"):
                to = conv["title"]
            else:
                names = [self.ident(x)[0] for x in recips[:3] if x]
                to = ", ".join(n for n in names if n) or conv.get("title") or ""
        else:
            frm = sender or conv.get("title") or ""
            to = conv["title"] if conv.get("is_group") and conv.get("title") else owner
        return frm, to


def record_text(e: dict) -> str:
    """The words of a record: body, plus what was said or written in a voice note, video or photo."""
    parts = [e.get("body") or ""]
    if e.get("transcript"):
        parts.append(f"(said: {e['transcript']})")
    if e.get("ocr_text"):
        parts.append(f"(words in it: {e['ocr_text']})")
    if e.get("media_name") and not e.get("body"):
        parts.append(e["media_name"])
    if e.get("place"):
        parts.append(f"at {e['place']}")
    return " ".join(p for p in parts if p).strip()


def _app_words(e: dict) -> str:
    app = limits.APP_NAMES.get(e.get("app") or "", e.get("app") or "")
    kind = e.get("kind") or ""
    if kind == "call":
        return f"{app} call".strip() if app and app not in ("phone calls", "calls") else "Call"
    if kind and kind != "message":
        return f"{app} {kind}".strip()
    return app or kind


def evidence_line(ctx: Ctx, e: dict) -> str:
    """'[P1-000482] 16 Sep 2026, 10:05 am | SMS | AD-BUBANK -> Vikram Mehra (Phone 1) | Rs 50,000.00 debited ...'"""
    frm, to = ctx.who(e)
    bits = [f"[{e['event_id']}] {text.fmt_when(e.get('ts'))}", _app_words(e), f"{frm} -> {to}"]
    if e.get("kind") == "call":
        d = e.get("duration_s")
        bits.append(("missed" if e.get("status") == "missed" else text.duration_words(d) if d else "no answer")
                    + (" (deleted from the call log)" if e.get("status") == "deleted" else ""))
    body = record_text(e)
    if e.get("status") in ("deleted", "unsent", "edited") and e.get("kind") != "call":
        body = f"[{e['status']}] {body}"
    if body:
        bits.append(body[:600].replace("\n", " "))
    return " | ".join(bits)


def record_card(ctx: Ctx, e: dict) -> dict:
    """Everything the page needs to show a record and open it."""
    frm, to = ctx.who(e)
    conv = ctx.conv(e.get("conv_id"))
    return {"event_id": e["event_id"], "ts": e.get("ts"), "when": text.fmt_when(e.get("ts")),
            "kind": e.get("kind"), "app": e.get("app"), "direction": e.get("direction"),
            "status": e.get("status") or "", "phone_label": ctx.phone_label(e.get("source_id")),
            "source_id": e.get("source_id"), "conv_id": e.get("conv_id"), "conv_title": conv.get("title") or "",
            "sender_name": frm, "to_name": to, "text": record_text(e)[:500],
            "duration_s": e.get("duration_s"), "place": e.get("place") or ""}


def load_events(con, ids: list[str]) -> dict[str, dict]:
    """Records by ID, inside the warrant limit only."""
    out: dict[str, dict] = {}
    w, p = limits.where(con, "e")
    ids = list(dict.fromkeys(i for i in ids if i))
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in db.rows(con, f"SELECT e.* FROM events e WHERE {w} AND e.event_id IN ({','.join('?' * len(chunk))})",
                         [*p, *chunk]):
            out[r["event_id"]] = r
    return out


# ====================================================================== understanding the question by code

def _raw_words(question: str) -> list[str]:
    """Words of the question as written, without stop words, each once (helpers fold them themselves)."""
    out, seen = [], set()
    for t in text.tokens(question):
        f = text.fold(t)
        if not f or f in text.STOP_WORDS or f in seen:
            continue
        seen.add(f)
        out.append(t)
    return out


def _parse_scope(con, scope: dict | None) -> dict:
    """{source_ids, from, to} from {phone?, from?, to?}: phone is a phone number (1, 2, 3) or a source id."""
    scope = scope or {}
    out: dict[str, Any] = {"source_ids": None, "from": None, "to": None}
    ph = scope.get("phone")
    if ph not in (None, "", "all"):
        try:
            n = int(str(ph).replace("Phone", "").strip())
        except ValueError:
            raise ApiError(400, "That phone isn't in this case.")
        ids = [r[0] for r in con.execute("SELECT source_id FROM sources WHERE phone_no = ?", (n,))]
        if not ids:
            ids = [r[0] for r in con.execute("SELECT source_id FROM sources WHERE source_id = ?", (n,))]
        if not ids:
            raise ApiError(400, "That phone isn't in this case.")
        out["source_ids"] = ids
    for key, end in (("from", False), ("to", True)):
        v = scope.get(key)
        if v in (None, ""):
            continue
        try:
            if isinstance(v, (int, float)) or str(v).isdigit():
                out[key] = int(v)
            else:
                a, b = text.day_range(str(v)[:10])
                out[key] = b if end else a
        except ValueError:
            raise ApiError(400, "Please give dates as day, month and year.")
    return out


def _scope_sql(scope: dict, alias: str = "e") -> tuple[str, list]:
    a = f"{alias}." if alias else ""
    parts, params = [], []
    if scope.get("source_ids"):
        parts.append(f"{a}source_id IN ({','.join('?' * len(scope['source_ids']))})")
        params += scope["source_ids"]
    if scope.get("from") is not None:
        parts.append(f"{a}ts >= ?")
        params.append(scope["from"])
    if scope.get("to") is not None:
        parts.append(f"{a}ts < ?")
        params.append(scope["to"])
    return " AND ".join(parts) or "1=1", params


def understand(con, question: str) -> dict:
    """Pick out people, dates, amounts, topic words and code words from the question, by code."""
    words = _raw_words(question)
    folded = {text.fold(w): w for w in words}
    ref = db.scalar(con, "SELECT MAX(ts) FROM events", default=None)
    dates = text.find_date_range(question, ref)
    date_words = set(text.fold_tokens(dates["words"])) if dates else set()
    if dates:
        date_words |= {text.fold(x) for x in ("night", "raat", "rat", "kal", "aaj", "today", "yesterday", "parso",
                                              "last", "week", "month", "pichle", "hafte", "mahine", "days", "din")}
    amounts = [a["value"] for a in text.find_amounts(question)
               if a["explicit"] or (a["value"] >= 100 and not 1900 <= a["value"] <= 2100)]
    # people: a question word that is a word of someone's name, or a phone number
    people: dict[int, str] = {}
    name_words = {f for f in folded if len(f) >= 3 and not f.isdigit()}
    if name_words:
        for r in db.rows(con, "SELECT person_id, name, names FROM persons WHERE name IS NOT NULL AND name != ''"):
            alln = [r["name"]]
            try:
                alln += [n.get("name", "") for n in json.loads(r["names"] or "[]") if isinstance(n, dict)]
            except (ValueError, AttributeError):
                pass
            toks = set()
            for n in alln:
                toks.update(t for t in text.fold_tokens(n) if len(t) >= 3)
            hit = toks & name_words
            if hit:
                people[r["person_id"]] = r["name"]
                date_words |= hit  # not topic words any more
    for d in re.findall(r"\+?\d[\d ]{8,13}\d", question):
        ph = text.norm_phone(d)
        if ph:
            for r in db.rows(con, "SELECT i.person_id, p.name FROM identifiers i JOIN persons p ON p.person_id = "
                                  "i.person_id WHERE i.ident IN (?, ?)", (ph, "wa:" + ph)):
                people[r["person_id"]] = r["name"]
    money_q = bool(amounts) or any(f in _MONEY_FOLDED for f in folded)
    delete_q = any(f in _DELETE_FOLDED for f in folded)
    topic = [w for w in words if text.fold(w) not in date_words and not (text.fold(w).isdigit() and dates)]
    # code words from the book: a meaning in the question brings in its code word, and the other way round
    codes = []
    try:
        for r in db.rows(con, "SELECT word, meaning FROM codes WHERE status = 'confirmed'"):
            mw = set(text.fold_tokens(r["meaning"]))
            cw = text.fold(r["word"])
            if cw in folded or (mw and mw & set(folded)):
                codes.append({"word": r["word"], "meaning": r["meaning"]})
                if cw not in {text.fold(t) for t in topic}:
                    topic.append(r["word"])
    except Exception:
        pass
    return {"words": words, "topic": topic, "people": people, "dates": dates, "amounts": amounts,
            "money": money_q, "delete": delete_q, "codes": codes}


# ====================================================================== gathering the evidence

def _fts_hits(con, words: list[str], scope_w: str, scope_p: list, limit: int = 400) -> dict[str, float]:
    """FTS hits on any of the words, scored 0..1 by bm25 (best = 1)."""
    if not words:
        return {}
    q = text.fts_query(words, op="OR", column="folded")
    if not q:
        return {}
    w, p = limits.where(con, "e")
    try:
        rows = con.execute(
            f"SELECT f.event_id, bm25(events_fts) AS s FROM events_fts f JOIN events e ON e.event_id = f.event_id "
            f"WHERE events_fts MATCH ? AND {w} AND {scope_w} ORDER BY s LIMIT ?", [q, *p, *scope_p, limit]).fetchall()
    except Exception:
        rows = []
    if not rows:
        return {}
    best = min(r[1] for r in rows)  # bm25: more negative = better
    return {r[0]: (r[1] / best if best else 1.0) for r in rows}


def _person_idents(con, pids) -> list[str]:
    pids = list(pids)
    if not pids:
        return []
    return [r[0] for r in con.execute(f"SELECT ident FROM identifiers WHERE person_id IN ({','.join('?' * len(pids))})",
                                      pids)]


def _people_events(con, pids, scope_w, scope_p, rng, limit=400) -> list[str]:
    idents = _person_idents(con, pids)
    owner_src = [r[0] for r in con.execute(
        f"SELECT source_id FROM sources WHERE owner_person_id IN ({','.join('?' * len(pids))})", list(pids))] if pids else []
    if not idents and not owner_src:
        return []
    w, p = limits.where(con, "e")
    conds, cp = [], []
    if idents:
        ph = ",".join("?" * len(idents))
        conds.append(f"e.sender IN ({ph})")
        conds.append(f"EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid(e.recipients) THEN e.recipients ELSE '[]' "
                     f"END) j WHERE j.value IN ({ph}))")
        cp += idents + idents
        conds.append(f"e.conv_id IN (SELECT c.conv_id FROM conversations c, json_each(CASE WHEN json_valid("
                     f"c.participants) THEN c.participants ELSE '[]' END) j WHERE j.value IN ({ph}) AND c.is_group = 0)")
        cp += idents
    if owner_src:
        conds.append(f"(e.direction = 'out' AND e.source_id IN ({','.join('?' * len(owner_src))}))")
        cp += owner_src
    rw, rp = "1=1", []
    if rng:
        rw, rp = "e.ts >= ? AND e.ts < ?", [rng["from"], rng["to"]]
    sql = (f"SELECT e.event_id FROM events e WHERE {w} AND {scope_w} AND {rw} AND e.kind IN ('message','call','voice',"
           f"'photo','document','video','location') AND ({' OR '.join(conds) if conds else '0'}) "
           f"ORDER BY e.ts DESC LIMIT ?")
    return [r[0] for r in con.execute(sql, [*p, *scope_p, *rp, *cp, limit])]


def _money_rows(con, scope_w, scope_p, rng, amounts=None, limit=200) -> list[dict]:
    w, p = limits.where(con, "e")
    rw, rp = "1=1", []
    if rng:
        rw, rp = "m.ts >= ? AND m.ts < ?", [rng["from"], rng["to"]]
    rows = db.rows(con, f"SELECT m.* FROM money m WHERE m.event_id IN (SELECT e.event_id FROM events e WHERE {w} AND "
                        f"{scope_w}) AND {rw} ORDER BY m.ts LIMIT ?", [*p, *scope_p, *rp, limit * 3])
    if amounts:
        near = [r for r in rows if any(abs((r["amount"] or 0) - a) <= max(1.0, a * 0.01) for a in amounts)]
        if near:
            rows = near
    return rows[:limit]


def gather(con, qi: dict, scope: dict, cap: int) -> tuple[list[str], dict]:
    """Ranked record IDs for the question (best first) and the money rows found. Never more than `cap`."""
    sw, sp = _scope_sql(scope, "e")
    rng = qi["dates"]
    score: dict[str, float] = {}

    def add(eid, s):
        score[eid] = score.get(eid, 0.0) + s

    fts = _fts_hits(con, qi["topic"], sw, sp)
    for eid, s in fts.items():
        add(eid, 1.0 + s)
    if qi["people"]:
        for eid in _people_events(con, qi["people"].keys(), sw, sp, rng):
            add(eid, 1.5)
    money = []
    if qi["money"]:
        money = _money_rows(con, sw, sp, rng, qi["amounts"])
        for m in money:
            add(m["event_id"], 2.0 + (1.0 if qi["amounts"] else 0.0))
    if qi["delete"]:
        w, p = limits.where(con, "e")
        rw, rp = ("e.ts >= ? AND e.ts < ?", [rng["from"], rng["to"]]) if rng else ("1=1", [])
        for r in con.execute(f"SELECT e.event_id FROM events e WHERE {w} AND {sw} AND {rw} AND e.status IN "
                             f"('deleted','unsent') ORDER BY e.ts LIMIT 400", [*p, *sp, *rp]):
            add(r[0], 2.0)
    if rng:
        # inside the date window counts; with no other clue, the records of that window are the evidence
        ids = list(score)
        if ids:
            evs = load_events(con, ids)
            for eid, e in evs.items():
                if e.get("ts") is not None and rng["from"] <= e["ts"] < rng["to"]:
                    add(eid, 1.0)
        if not score:
            w, p = limits.where(con, "e")
            for r in con.execute(f"SELECT e.event_id FROM events e WHERE {w} AND {sw} AND e.ts >= ? AND e.ts < ? AND "
                                 f"e.kind IN ('message','call','voice','photo','document','location') ORDER BY e.ts "
                                 f"LIMIT ?", [*p, *sp, rng["from"], rng["to"], cap]):
                add(r[0], 1.0)
    # trigram fallback for typing mistakes
    if not score and qi["topic"]:
        w, p = limits.where(con, "e")
        for word in qi["topic"][:5]:
            f = text.fold(word)
            if len(f) < 3:
                continue
            try:
                for r in con.execute(f"SELECT t.event_id FROM events_tri t JOIN events e ON e.event_id = t.event_id "
                                     f"WHERE events_tri MATCH ? AND {w} AND {sw} LIMIT 60",
                                     ['"' + f.replace('"', '""') + '"', *p, *sp]):
                    add(r[0], 0.5)
            except Exception:
                pass
    ranked = sorted(score, key=lambda k: -score[k])
    return ranked[:cap], {"money": money, "total": len(ranked)}


def _clean_for_ai(evs: list[dict]) -> list[dict]:
    return [e for e in evs if not llm.is_secret(" ".join(filter(None, [e.get("body"), e.get("transcript"),
                                                                        e.get("ocr_text")])))]


# ====================================================================== checking every line by code

def _context_tokens(ctx: Ctx, evs: list[dict], money_by_event: dict) -> tuple[set, list[float]]:
    toks: set[str] = set()
    amounts: list[float] = []
    for e in evs:
        line = evidence_line(ctx, e)
        toks.update(text.fold_tokens(line))
        toks.update(text.fold_tokens(ctx.phone_label(e.get("source_id"))))
        amounts += [a["value"] for a in text.find_amounts(record_text(e))]
        for m in money_by_event.get(e["event_id"], []):
            if m.get("amount") is not None:
                amounts.append(float(m["amount"]))
            toks.update(text.fold_tokens(m.get("counterparty") or ""))
        if e.get("duration_s"):
            toks.update(text.fold_tokens(text.duration_words(e["duration_s"])))
    return toks, amounts


def check_line(ctx: Ctx, line_text: str, cited: list[dict], money_by_event: dict, question: str) -> bool:
    """Every number, amount, date, name and quoted phrase must be found, after folding, in the cited records."""
    toks, amounts = _context_tokens(ctx, cited, money_by_event)
    # amounts
    taken = []
    for a in text.find_amounts(line_text):
        if not a["explicit"] and a["value"] < 100:
            continue
        taken.append((a["start"], a["end"]))
        if not any(abs(a["value"] - b) <= max(1.0, b * 0.005) for b in amounts):
            # the same figure may be written another way ("50,000" vs "50k"); fall back to its digits
            if text.fold(a["text"].replace("₹", "").replace("Rs", "").strip().split(" ")[0]) not in toks:
                return False
    # other numbers (dates, times, counts)
    rest = "".join(ch if not any(s <= i < e for s, e in taken) else " " for i, ch in enumerate(line_text))
    for t in re.findall(r"\d+", rest):
        n = t.lstrip("0") or "0"
        if t not in toks and n not in toks and t.zfill(2) not in toks:
            if len(t) <= 2 and int(t) <= 12 and int(t) <= len(cited) + 2:
                continue  # small counts ("two messages") are worked out, not quoted
            return False
    # quoted phrases
    for q in _QUOTE_RE.findall(line_text):
        qt = [t for t in text.fold_tokens(q)]
        if qt and not all(t in toks for t in qt):
            return False
    # names: capitalised words that aren't common words or the start of the line
    qtoks = set(text.fold_tokens(question))
    for m in _CAP_RE.finditer(line_text):
        w = m.group(1)
        if m.start() == 0 or w.lower() in _COMMON_CAPS:
            continue
        f = text.fold(w)
        if f in toks or f in qtoks or f in text.STOP_WORDS:
            continue
        return False
    return True


def check_lines(ctx: Ctx, raw_lines, given: dict[str, dict], money_by_event: dict, question: str) -> list[dict]:
    out = []
    for item in raw_lines or []:
        if isinstance(item, str):
            item = {"text": item, "records": []}
        if not isinstance(item, dict):
            continue
        t = str(item.get("text") or "").strip()
        ids = [str(x).strip().strip("[]") for x in (item.get("records") or []) if x]
        ids += _ID_RE.findall(t)
        ids = list(dict.fromkeys(ids))
        clean = re.sub(r"\s*\[(?:\s*,?\s*P\d+-\d{3,})+\s*\]", "", t)
        clean = re.sub(r"\s*\(\s*P\d+-\d{3,}(?:\s*,\s*P\d+-\d{3,})*\s*\)", "", clean).strip()
        if not clean or not ids:
            continue  # cites nothing: dropped
        if any(i not in given for i in ids):
            continue  # cites a record it was never given: removed
        ok = check_line(ctx, clean, [given[i] for i in ids], money_by_event, question)
        line = {"text": clean, "records": ids, "checked": ok}
        if not ok:
            line["note"] = "Couldn't confirm this from the records it cites"
        out.append(line)
        if len(out) >= MAX_LINES:
            break
    return out


def reliability(lines: list[dict], code_only: bool) -> str:
    if not lines:
        return "Nothing to check: no statement could be made from the records"
    if code_only:
        return "Every statement is taken straight from the records it cites"
    n, ok = len(lines), sum(1 for x in lines if x["checked"])
    if ok == n:
        return "Every statement checked against its messages"
    bad = n - ok
    return f"{ok} of {n} statements checked; {bad} couldn't be confirmed"


# ====================================================================== code-only answers (section 8.7)

def _money_lines(ctx: Ctx, con, money: list[dict], question_amounts) -> tuple[list[dict], set]:
    lines, used = [], set()
    debits = [m for m in money if m.get("direction") == "debit"]
    credits = [m for m in money if m.get("direction") == "credit"]
    # credits on other phones that may match a debit, also outside the question's own evidence
    for d in debits:
        if len(lines) >= MAX_LINES:
            break
        if d["money_id"] in used:
            continue
        used.add(d["money_id"])
        phone = ctx.phone_short(d["source_id"])
        sender = ctx.sources.get(d["source_id"], {}).get("owner_name") or "the owner"
        cp = d.get("counterparty") or d.get("counterparty_ident") or "someone not named"
        method = f" by {d['method']}" if d.get("method") else ""
        t = (f"{text.format_inr(d['amount'])} left {sender} ({phone}){method} on {text.fmt_date(d['ts'])} at "
             f"{text.fmt_time(d['ts'])} to {cp}.")
        recs = [d["event_id"]]
        w, p = limits.where(con, "e")
        match = db.one(con, f"SELECT m.* FROM money m WHERE m.direction = 'credit' AND m.source_id != ? AND "
                            f"ABS(m.amount - ?) < 1 AND m.ts >= ? AND m.ts <= ? AND m.event_id IN (SELECT e.event_id "
                            f"FROM events e WHERE {w}) ORDER BY m.ts LIMIT 1",
                       [d["source_id"], d["amount"], d["ts"] - 60_000, d["ts"] + 2 * 86_400_000, *p])
        if match:
            used.add(match["money_id"])
            gap = match["ts"] - d["ts"]
            when = f"{text.gap_words(gap)} later" if gap > 0 else "at the same time"
            t += f" It arrived on {ctx.phone_label(match['source_id'])} {when}."
            recs.append(match["event_id"])
        lines.append({"text": t, "records": recs, "checked": True})
    for c in credits:
        if len(lines) >= MAX_LINES:
            break
        if c["money_id"] in used:
            continue
        used.add(c["money_id"])
        owner = ctx.sources.get(c["source_id"], {}).get("owner_name") or "the owner"
        cp = c.get("counterparty") or c.get("counterparty_ident") or "someone not named"
        method = f" by {c['method']}" if c.get("method") else ""
        lines.append({"text": f"{text.format_inr(c['amount'])} arrived on {owner}'s phone ({ctx.phone_short(c['source_id'])})"
                              f"{method} on {text.fmt_date(c['ts'])} at {text.fmt_time(c['ts'])} from {cp}.",
                      "records": [c["event_id"]], "checked": True})
    return lines, used


def _delete_lines(ctx: Ctx, evs: list[dict]) -> list[dict]:
    by_conv: dict[Any, list[dict]] = {}
    for e in evs:
        if e.get("status") in ("deleted", "unsent"):
            by_conv.setdefault((e.get("source_id"), e.get("conv_id"), e.get("kind")), []).append(e)
    lines = []
    for (src, conv_id, kind), items in sorted(by_conv.items(), key=lambda kv: -len(kv[1])):
        if len(lines) >= MAX_LINES:
            break
        items.sort(key=lambda e: e.get("ts") or 0)
        title = ctx.conv(conv_id).get("title") or ""
        what = text.plural(len(items), "deleted call" if kind == "call" else "deleted message")
        where = f" in the chat \"{title}\"" if title else ""
        first, last = items[0].get("ts"), items[-1].get("ts")
        span = text.fmt_when(first) if first == last else f"{text.fmt_when(first)} and {text.fmt_when(last)}"
        lines.append({"text": f"{what}{where} on {ctx.phone_label(src)}, {'on' if first == last else 'between'} {span}.",
                      "records": [e["event_id"] for e in items[:12]], "checked": True})
    return lines


def _closest_lines(ctx: Ctx, evs: list[dict]) -> list[dict]:
    top = evs[:5]
    if not top:
        return []
    lines = [{"text": "The closest messages to your question are below.", "records": [e["event_id"] for e in top],
              "checked": True}]
    for e in top:
        frm, to = ctx.who(e)
        body = record_text(e)
        body = (body[:160] + "…") if len(body) > 160 else body
        kind = "call" if e.get("kind") == "call" else e.get("kind") or "message"
        t = f"{frm} to {to}, {text.fmt_when(e.get('ts'))} ({_app_words(e)})"
        if kind == "call":
            t += f": {text.duration_words(e['duration_s']) if e.get('duration_s') else e.get('status') or 'call'}"
        elif body:
            t += f": \"{body}\""
        lines.append({"text": t, "records": [e["event_id"]], "checked": True})
    return lines


def code_answer(ctx: Ctx, con, qi: dict, evs: list[dict], money: list[dict]) -> dict:
    lines: list[dict] = []
    not_found: list[str] = []
    if qi["money"] and money:
        lines, _ = _money_lines(ctx, con, money, qi["amounts"])
    if qi["delete"]:
        dl = _delete_lines(ctx, evs)
        lines += dl[:max(0, MAX_LINES - len(lines))]
        if not dl:
            not_found.append("No deleted messages were found for this question.")
    if not lines:
        lines = _closest_lines(ctx, evs)
    if qi["money"] and not money:
        not_found.append("No payment matching this question is in the records.")
    if not evs:
        not_found = ["Nothing in the records matches this question. Try other words or a wider date range."]
    follow = []
    if qi["money"] and money:
        follow = ["What was the money for?", "Did anyone else receive money that week?"]
    elif qi["people"]:
        n = next(iter(qi["people"].values()))
        follow = [f"Who did {n} talk to most?", f"Where was {n} on these days?"]
    return {"lines": lines, "not_found": not_found, "follow_ups": follow}


# ====================================================================== asking the AI

def _ai_once(ctx: Ctx, system: str, question: str, about: str, evs: list[dict], extra: str = "") -> tuple[dict, int]:
    """Ask with these records; halve and ask twice when the reply is cut off. Returns (merged reply, calls)."""
    body = (f"Case: {about}\n\n" if about else "") + f"The officer's question: {question}\n\nRecords:\n" + \
        "\n".join(evidence_line(ctx, e) for e in evs) + (f"\n\n{extra}" if extra else "")
    out, finish = llm.ask_json(system, body)
    if finish == "length" and len(evs) > 4:
        half = len(evs) // 2
        a, n1 = _ai_once(ctx, system, question, about, evs[:half], extra)
        b, n2 = _ai_once(ctx, system, question, about, evs[half:], extra)
        merged = {"lines": (a.get("lines") or []) + (b.get("lines") or []),
                  "notes": (a.get("notes") or []) + (b.get("notes") or []),
                  "not_found": (a.get("not_found") or []) + (b.get("not_found") or []),
                  "follow_ups": (a.get("follow_ups") or []) + (b.get("follow_ups") or [])}
        return merged, n1 + n2 + 1
    return out or {}, 1


def ai_answer(ctx: Ctx, con, qi: dict, question: str, about: str, evs: list[dict], depth: str,
              scope: dict) -> tuple[dict, list[dict], int]:
    """Returns (reply, every record the AI was given, rounds)."""
    given = list(evs)
    rounds = 1
    if depth == "deep":
        notes = []
        for i in range(0, len(given), PART_LINES):
            part, _ = _ai_once(ctx, MAP_SYSTEM, question, about, given[i:i + PART_LINES])
            notes += [n for n in part.get("notes") or [] if isinstance(n, dict)]
        rounds = max(1, (len(given) + PART_LINES - 1) // PART_LINES)
        by_id = {e["event_id"]: e for e in given}
        cited = []
        for n in notes:
            for i in (n.get("records") or []):
                if i in by_id and by_id[i] not in cited:
                    cited.append(by_id[i])
        cited = cited[:150] or given[:QUICK_N]
        note_text = "Notes made while reading every chat:\n" + "\n".join(
            f"- {n.get('text', '')} {' '.join('[' + str(i) + ']' for i in n.get('records') or [])}" for n in notes[:60])
        reply, _ = _ai_once(ctx, SYSTEM, question, about, cited, note_text)
        return reply, given, rounds + 1
    reply, _ = _ai_once(ctx, SYSTEM + (NEED_HINT if depth == "further" else ""), question, about, given)
    while depth == "further" and rounds < 3 and isinstance(reply.get("need"), list) and reply["need"] \
            and not reply.get("lines"):
        need = [str(x) for x in reply["need"][:6]]
        sub = understand(con, " ".join(need))
        sub["dates"] = sub["dates"] or qi["dates"]
        ids, _ = gather(con, sub, scope, QUICK_N * 2)
        have = {e["event_id"] for e in given}
        new_ids = [i for i in ids if i not in have][:QUICK_N]
        if not new_ids:
            break
        evmap = load_events(con, new_ids)
        given += _clean_for_ai([evmap[i] for i in new_ids if i in evmap])
        rounds += 1
        reply, _ = _ai_once(ctx, SYSTEM + (NEED_HINT if rounds < 3 else ""), question, about, given)
    return reply, given, rounds


# ====================================================================== the whole ask

def _scope_count(con, scope: dict) -> int:
    w, p = limits.where(con, "e")
    sw, sp = _scope_sql(scope, "e")
    return db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE {w} AND {sw} AND e.kind IN ('message','voice',"
                          f"'call','photo','document','video')", [*p, *sp], default=0) or 0


def answer(con, question: str, depth: str = "auto", scope: dict | None = None, about: str = "",
           use_ai: bool | None = None) -> dict:
    """The section 8.3 result (without ask_id). Brief and key questions can call this too."""
    started = time.monotonic()
    question = (question or "").strip()
    if not question:
        raise ApiError(400, "Please type a question.")
    depth = depth if depth in ("auto", "quick", "further", "deep") else "auto"
    sc = _parse_scope(con, scope)
    ctx = Ctx(con)
    qi = understand(con, question)
    ai_on = llm.configured() if use_ai is None else (use_ai and llm.configured())

    offer_deep = False
    if depth == "deep":
        w, p = limits.where(con, "e")
        sw, sp = _scope_sql(sc, "e")
        extra_w, extra_p = "1=1", []
        if qi["dates"] and sc.get("from") is None and sc.get("to") is None:
            extra_w, extra_p = "e.ts >= ? AND e.ts < ?", [qi["dates"]["from"], qi["dates"]["to"]]
        ids = [r[0] for r in con.execute(
            f"SELECT e.event_id FROM events e WHERE {w} AND {sw} AND {extra_w} AND e.kind IN ('message','voice',"
            f"'call','photo','document','video') ORDER BY e.conv_id, e.ts LIMIT 20000", [*p, *sp, *extra_p])]
        found_ids, extra = gather(con, qi, sc, QUICK_N)
        depth_used = "deep"
        if not ai_on:
            ids = found_ids  # code reads the best matches; reading every chat needs the AI
    else:
        found_ids, extra = gather(con, qi, sc, FURTHER_MAX)
        total = extra["total"]
        if depth == "auto":
            depth_used = "quick" if total <= QUICK_N else "further"
            offer_deep = total > FURTHER_MAX
        else:
            depth_used = depth
        ids = found_ids[:QUICK_N]
    money = extra["money"]
    evmap = load_events(con, ids)
    evs = [evmap[i] for i in ids if i in evmap]
    if not evs and money:
        evmap = load_events(con, [m["event_id"] for m in money])
        evs = list(evmap.values())
    money_by_event: dict[str, list] = {}
    for m in money:
        money_by_event.setdefault(m["event_id"], []).append(m)

    rounds = 1
    status_line = llm.status_line()
    ai_note = None
    reply = None
    given_list = evs
    if ai_on and evs:
        try:
            reply, given_list, rounds = ai_answer(ctx, con, qi, question, about, _clean_for_ai(evs), depth_used, sc)
        except llm.LLMError as e:
            ai_note = f"{e} Answered by code only this time."
            reply = None
    if reply is not None:
        given = {e["event_id"]: e for e in given_list}
        extra_m = load_money(con, list(given))
        for m in extra_m:
            if m not in money_by_event.get(m["event_id"], []):
                money_by_event.setdefault(m["event_id"], []).append(m)
        lines = check_lines(ctx, reply.get("lines"), given, money_by_event, question)
        res = {"lines": lines,
               "not_found": [str(x) for x in (reply.get("not_found") or []) if x][:4],
               "follow_ups": [str(x) for x in (reply.get("follow_ups") or []) if x][:2]}
        code_only = False
        if not lines:
            # the AI wrote nothing that cites the records: fall back to code, so the officer still sees evidence
            res = code_answer(ctx, con, qi, evs, money)
            code_only = True
            ai_note = "The AI's answer didn't point to any records, so code answered instead."
    else:
        res = code_answer(ctx, con, qi, evs, money)
        code_only = True
        given_list = evs
    if code_only and depth_used == "deep" and not ai_on:
        depth_used = "further"

    # records the page needs: cited first, then the rest of the evidence
    cited = []
    for line in res["lines"]:
        for i in line["records"]:
            if i not in cited:
                cited.append(i)
    allmap = {e["event_id"]: e for e in given_list}
    missing = [i for i in cited if i not in allmap]
    if missing:
        allmap.update(load_events(con, missing))
    order = cited + [e["event_id"] for e in given_list if e["event_id"] not in cited]
    records = [record_card(ctx, allmap[i]) for i in order[:max(QUICK_N, len(cited))] if i in allmap]

    spell_src = " ".join(record_text(e) for e in given_list[:200])
    topic = qi["topic"]
    dates = qi["dates"]
    return {
        "question": question, "depth_used": depth_used,
        "lines": res["lines"], "not_found": res["not_found"], "follow_ups": res["follow_ups"],
        "reliability": reliability(res["lines"], code_only),
        "status": (ai_note or llm.CODE_ONLY_LINE) if code_only else status_line,
        "answered_by": "code" if code_only else "ai",
        "offer_deep": offer_deep,
        "limit": limits.banner_text(con),
        "how": {"words": topic, "spellings": text.spellings(spell_src, topic) if topic else [],
                "people": [{"person_id": k, "name": v} for k, v in qi["people"].items()],
                "dates": {"from": dates["from"], "to": dates["to"], "words": dates["words"]} if dates else None,
                "amounts": qi["amounts"], "codes": qi["codes"],
                "records_read": len(given_list), "rounds": rounds,
                "seconds": round(time.monotonic() - started, 1),
                "ai": "code only" if code_only else llm.where()},
        "records": records,
    }


def load_money(con, event_ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(event_ids), 500):
        chunk = event_ids[i:i + 500]
        if chunk:
            out += db.rows(con, f"SELECT * FROM money WHERE event_id IN ({','.join('?' * len(chunk))})", chunk)
    return out


# ====================================================================== routes

class AskIn(BaseModel):
    question: str = ""
    depth: str = "auto"
    scope: dict | None = None


@router.post("/api/cases/{cid}/ask")
def ask(cid: str, body: AskIn, acc: CaseAccess = Depends(require_case)):
    q = (body.question or "").strip()
    if not q:
        raise ApiError(400, "Please type a question.")
    if len(q) > 1000:
        raise ApiError(400, "That question is too long. Please ask it in fewer words.")
    about = (acc.case or {}).get("about") or ""
    with db.case_db(cid) as con:
        result = answer(con, q, body.depth, body.scope, about)
        cur = con.execute("INSERT INTO asks(ts, officer, question, depth, result) VALUES (?, ?, ?, ?, ?)",
                          (db.now_ms(), acc.officer_name, q, result["depth_used"], ""))
        ask_id = cur.lastrowid
        result = {"ask_id": ask_id, **result}
        con.execute("UPDATE asks SET result = ? WHERE ask_id = ?", (json.dumps(result, ensure_ascii=False), ask_id))
    audit.log(cid, acc, "ask", f"Asked: '{q}'")
    return result


@router.get("/api/cases/{cid}/ask/estimate")
def estimate(cid: str, depth: str = "deep", scope: str = "", phone: str = "", from_: str = Query("", alias="from"),
             to: str = "", acc: CaseAccess = Depends(require_case)):
    sc_in: dict = {}
    if scope:
        try:
            sc_in = json.loads(scope)
            if not isinstance(sc_in, dict):
                sc_in = {}
        except ValueError:
            sc_in = {}
    for k, v in (("phone", phone), ("from", from_), ("to", to)):
        if v and k not in sc_in:
            sc_in[k] = v
    s = llm.settings()
    with db.case_db(cid) as con:
        sc = _parse_scope(con, sc_in)
        n = _scope_count(con, sc)
    if depth == "quick":
        n = min(n, QUICK_N)
    elif depth == "further":
        n = min(n, QUICK_N * 3)
    parts = max(1, (n + PART_LINES - 1) // PART_LINES) if n else 0
    calls = parts + 1 if depth == "deep" else (1 if depth == "quick" else 3)
    minutes = max(1, round(calls * (0.75 if s.local else 0.3))) if n and s.configured else 0
    if not s.configured:
        cost = "no AI is set up: code will answer, with no cost"
    elif s.local:
        cost = "no cost on your own computer"
    else:
        cost = f"the AI at {s.host} may charge for reading about {text.group_indian(n * 40)} words"
    return {"records": n, "parts": parts, "minutes": minutes, "cost_words": cost,
            "minutes_words": "under a minute" if minutes <= 1 else f"about {minutes} minutes",
            "ai": {"configured": s.configured, "local": s.local, "where": s.where}}


@router.get("/api/cases/{cid}/asks")
def asks(cid: str, offset: int = 0, acc: CaseAccess = Depends(require_case)):
    offset = max(0, int(offset or 0))
    with db.case_db(cid) as con:
        total = db.scalar(con, "SELECT COUNT(*) FROM asks", default=0) or 0
        rows = db.rows(con, "SELECT ask_id, ts, officer, question, depth, result FROM asks ORDER BY ask_id DESC "
                            "LIMIT 50 OFFSET ?", (offset,))
    out = []
    for r in rows:
        try:
            res = json.loads(r["result"] or "{}")
        except ValueError:
            res = {}
        out.append({"ask_id": r["ask_id"], "ts": r["ts"], "when": text.fmt_when(r["ts"]), "officer": r["officer"],
                    "question": r["question"], "depth": r["depth"], "result": res})
    return {"total": total, "offset": offset, "rows": out}
