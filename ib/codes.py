"""Code words (section 10.6): suggestions found in the chats, and the officer's code book.

A word is suggested when it is used more than 5 times, in at least 2 chats, and mostly at night or
near money words or arrangements, and is not an everyday word; words from a starter list of common
code words are suggested whenever they appear at all. Confirming or rejecting a word bumps the case
version (search uses confirmed words).
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Body, Depends

from ib import ApiError, audit, db, limits, text
from ib.officers import CaseAccess, require_case

router = APIRouter()

# Starter list: common code words and what they often mean (a hint only; the officer decides).
STARTER = {
    "biscuit": "gold bar", "chai pani": "a bribe", "packet": "a consignment", "maal": "the goods",
    "doctor sahab": "the person in charge", "token": "an advance payment", "saaman": "the goods",
    "parcel": "a consignment", "mithai": "money or a bribe", "patti": "₹1 lakh", "khoka": "₹1 crore",
    "peti": "₹1 lakh", "gift": "a payment", "kaccha maal": "raw goods", "setting": "an arrangement",
}

ARRANGE = {"ready", "kal", "raat", "aaj", "pahunch", "pahuncha", "bhejo", "bhej", "airport", "cargo", "deliver",
           "delivery", "pickup", "drop", "time", "jagah", "gate", "milna", "milo", "aana", "le", "lo", "pack",
           "rakh", "rakho", "intezaam", "location", "send", "tonight", "safe", "chupa", "delete"}

# Everyday chat words that are never suggested, on top of the stop words.
EVERYDAY = {"ok", "okay", "theek", "thik", "hai", "haan", "han", "nahi", "nahin", "kya", "kab", "kaise", "kaha", "kahan",
            "bhai", "ji", "sir", "good", "morning", "night", "thanks", "thank", "you", "yes", "no", "please", "call",
            "karo", "kar", "karna", "raha", "rahi", "rahe", "tha", "thi", "the", "ho", "hoga", "gaya", "gayi", "diya",
            "liya", "abhi", "baad", "phir", "bas", "accha", "acha", "achha", "hello", "hi", "bro", "yaar", "msg",
            "message", "baat", "batao", "bolo", "bol", "dekh", "dekho", "sab", "kuch", "koi", "mujhe", "tum", "tu",
            "aap", "main", "mai", "hum", "mera", "tera", "apna", "wala", "wali", "hua", "hui", "aur", "ya", "to", "toh",
            "se", "ko", "ka", "ki", "ke", "me", "mein", "pe", "par", "bhi", "na", "ne", "jo", "ye", "yeh", "wo", "woh"}
EVERYDAY_F = {text.fold(w) for w in EVERYDAY} | set(text.STOP_WORDS)
MONEY_F = {text.fold(w) for w in text.MONEY_WORDS}
ARRANGE_F = {text.fold(w) for w in ARRANGE}

MIN_USES, MIN_CHATS, MAX_SUGGEST = 6, 2, 30


def _night(ts: int | None) -> bool:
    if ts is None:
        return False
    hour = ((int(ts) // 1000 + 19800) // 3600) % 24
    return hour >= 22 or hour < 5


def _key(tok: str) -> str:
    return tok[:-1] if len(tok) > 4 and tok.endswith("s") else tok


def _moneyish(body: str, toks: list[str]) -> bool:
    if any(t in MONEY_F for t in toks):
        return True
    try:
        return any(a.get("explicit") for a in text.find_amounts(body))
    except Exception:
        return False


def _load_messages(con) -> list[dict]:
    w, p = limits.where(con, "e")
    return db.rows(con, f"""SELECT e.event_id, e.conv_id, e.ts, COALESCE(e.body, '') || ' ' || COALESCE(e.transcript, '') AS body
                             FROM events e WHERE {w} AND e.kind IN ('message', 'voice', 'note')
                             AND (COALESCE(e.body, '') != '' OR COALESCE(e.transcript, '') != '')
                             ORDER BY e.conv_id, e.ts""", p)


def compute(con) -> list[dict]:
    """All suggestions with counts and up to 3 example record ids, best first."""
    msgs = _load_messages(con)
    starter = {w: [_key(t) for t in text.fold_tokens(w)] for w in STARTER}
    stats: dict[str, dict] = {}
    toks_of = [[_key(t) for t in text.fold_tokens(m["body"])] for m in msgs]
    money_of = [_moneyish(m["body"], t) for m, t in zip(msgs, toks_of)]
    arrange_of = [any(t in ARRANGE_F for t in ts) for ts in toks_of]

    def add(key: str, shown: str, i: int, starter_word: bool = False):
        s = stats.setdefault(key, {"word": shown, "n": 0, "chats": set(), "night": 0, "money": 0, "eids": [],
                                   "starter": starter_word, "spell": {}})
        m = msgs[i]
        s["n"] += 1
        s["chats"].add(m["conv_id"])
        s["night"] += _night(m["ts"])
        same = lambda j: 0 <= j < len(msgs) and msgs[j]["conv_id"] == m["conv_id"]
        near = money_of[i] or arrange_of[i] or any(same(j) and (money_of[j] or arrange_of[j]) for j in (i - 1, i + 1))
        s["money"] += bool(near)
        if len(s["eids"]) < 3 and m["event_id"] not in s["eids"]:
            s["eids"].append(m["event_id"])
        s["spell"][shown] = s["spell"].get(shown, 0) + 1

    for i, (m, toks) in enumerate(zip(msgs, toks_of)):
        raw = [t.lower() for t in text.tokens(m["body"])]
        seen = set()
        for word, parts in starter.items():
            n = len(parts)
            if n and any(toks[k:k + n] == parts for k in range(len(toks) - n + 1)):
                add("starter:" + word, word, i, True)
                seen.update(parts)
        for k, t in enumerate(toks):
            if t in seen or t in EVERYDAY_F or t in ARRANGE_F or len(t) < 3 or t.isdigit() or t in MONEY_F:
                continue
            shown = raw[k] if k < len(raw) and len(raw) == len(toks) else t
            if shown.endswith("s") and len(shown) > 4 and _key(t) != t:
                shown = shown[:-1]
            add(t, shown, i)
            seen.add(t)

    out = []
    for key, s in stats.items():
        n, chats = s["n"], len(s["chats"])
        night_f, money_f = s["night"] / n, s["money"] / n
        if not s["starter"]:
            if n < MIN_USES or chats < MIN_CHATS or max(night_f, money_f) < 0.5:
                continue
        word = s["word"] if s["starter"] else max(s["spell"], key=s["spell"].get)
        why = []
        if night_f >= 0.5:
            why.append(f"{round(night_f * 100)}% at night")
        if money_f >= 0.5:
            why.append(f"{round(money_f * 100)}% near money or arrangements")
        if s["starter"]:
            why.append("often used as a code word")
        out.append({"word": word, "n": n, "chats": chats, "night_share": round(night_f, 2),
                    "near_money_share": round(money_f, 2), "starter": s["starter"], "why": ", ".join(why),
                    "event_ids": s["eids"], "hint": STARTER.get(word, ""),
                    "score": n * (0.5 + night_f + money_f) + (1000 if s["starter"] else 0)})
    out.sort(key=lambda r: (-r["score"], r["word"]))
    return out[:MAX_SUGGEST]


def _suggestions(con) -> list[dict]:
    """Saved answer while it matches the case version (never while a warrant limit is on)."""
    if limits.get_limit(con) is None:
        ver = str(db.case_version(con))
        row = db.one(con, "SELECT made_from, value FROM ready WHERE name = 'codes_suggestions'")
        if row and row["made_from"] == ver:
            try:
                return json.loads(row["value"])
            except Exception:
                pass
        rows = compute(con)
        con.execute("INSERT OR REPLACE INTO ready(name, made_from, value, made_at) VALUES ('codes_suggestions', ?, ?, ?)",
                    [ver, json.dumps(rows, ensure_ascii=False), db.now_ms()])
        return rows
    return compute(con)


def _ai_meanings(con, words: list[str], cid: str) -> dict[str, str]:
    """Suggested meanings from the AI when it is set up, remembered in codes_ai."""
    con.execute("CREATE TABLE IF NOT EXISTS codes_ai(word TEXT PRIMARY KEY, meaning TEXT, ts INTEGER)")
    known = {r["word"]: r["meaning"] for r in db.rows(con, "SELECT word, meaning FROM codes_ai")}
    try:
        from ib import llm
        if not llm.configured():
            return known
    except Exception:
        return known
    todo = [w for w in words if w not in known][:15]
    if not todo:
        return known
    case = db.get_case(cid) or {}
    try:
        got, _ = llm.ask_json(
            "You help an investigating officer read seized phone chats. For each word, suggest in a few plain words "
            "what it may be a code for in this case. Reply with JSON only: {\"meanings\": {\"word\": \"meaning\"}}.",
            f"The case is about: {case.get('about') or ''}\nWords: {', '.join(todo)}", max_tokens=400)
    except Exception:
        got = None
    meanings = (got or {}).get("meanings") if isinstance(got, dict) else None
    if isinstance(meanings, dict):
        for w in todo:
            m = " ".join(str(meanings.get(w) or "").split())[:80]
            if m:
                con.execute("INSERT OR REPLACE INTO codes_ai(word, meaning, ts) VALUES (?, ?, ?)", [w, m, db.now_ms()])
                known[w] = m
    return known


def _examples(con, eids: list[str], word: str) -> dict[str, dict]:
    if not eids:
        return {}
    w, p = limits.where(con, "e")
    rows = db.rows(con, f"""SELECT e.event_id, e.ts, e.app, e.body, e.transcript, s.label AS phone_label, c.title AS conv_title
                             FROM events e LEFT JOIN sources s ON s.source_id = e.source_id
                             LEFT JOIN conversations c ON c.conv_id = e.conv_id
                             WHERE {w} AND e.event_id IN ({','.join('?' * len(eids))})""", [*p, *eids])
    words = text.fold_tokens(word)
    words = words + [t + "s" for t in words]
    out = {}
    for r in rows:
        line = r.get("body") or r.get("transcript") or ""
        out[r["event_id"]] = {"event_id": r["event_id"], "ts": r["ts"], "when": text.fmt_when(r["ts"]),
                              "phone_label": r.get("phone_label"), "conv_title": r.get("conv_title"),
                              "text": line, "snippet_html": text.snippet(line, words)}
    return out


@router.get("/api/cases/{cid}/codes")
def get_codes(cid: str, acc: CaseAccess = Depends(require_case)):
    with db.case_db(cid) as con:
        book_rows = db.rows(con, "SELECT word, meaning, status, hits, by, ts FROM codes")
        status = {r["word"].lower(): r for r in book_rows}
        sugg = _suggestions(con)
        ai = _ai_meanings(con, [s["word"] for s in sugg if s["word"].lower() not in status], cid)
        suggestions, hits = [], {}
        for s in sugg:
            hits[s["word"].lower()] = s["n"]
            st = status.get(s["word"].lower())
            if st:
                continue
            ex = _examples(con, s["event_ids"], s["word"])
            item = {k: v for k, v in s.items() if k != "score"}
            item["examples"] = [ex[e] for e in s["event_ids"] if e in ex]
            item["status"] = "suggested"
            item["meaning"] = ai.get(s["word"]) or s.get("hint") or ""
            item["meaning_from"] = "the AI" if ai.get(s["word"]) else ("the starter list" if s.get("hint") else "")
            suggestions.append(item)
        book, rejected = [], []
        for r in sorted(book_rows, key=lambda r: -(r.get("ts") or 0)):
            row = {"word": r["word"], "meaning": r.get("meaning") or "", "status": r["status"], "by": r.get("by") or "",
                   "at": r.get("ts"), "when": text.fmt_when(r["ts"]) if r.get("ts") else "",
                   "n": hits.get(r["word"].lower(), r.get("hits") or 0)}
            (book if r["status"] == "confirmed" else rejected).append(row)
        return {"suggestions": suggestions, "book": book, "rejected": rejected, "limit": limits.banner_text(con)}


@router.post("/api/cases/{cid}/codes")
def set_code(cid: str, data: dict | None = Body(default=None), acc: CaseAccess = Depends(require_case)):
    data = data if isinstance(data, dict) else {}
    word = " ".join(str(data.get("word") or "").split()).lower()[:60]
    meaning = " ".join(str(data.get("meaning") or "").split())[:200]
    status = str(data.get("status") or "confirmed").strip().lower()
    if not word or not re.search(r"\w", word):
        raise ApiError(400, "Type the code word.")
    if status in ("remove", "delete", "suggested", "undo"):
        status = "suggested"
    if status not in ("confirmed", "rejected", "suggested"):
        raise ApiError(400, "A code word can be confirmed or rejected.")
    if status == "confirmed" and not meaning:
        raise ApiError(400, f"Type what '{word}' means before confirming it.")
    with db.case_db(cid) as con:
        sugg = {s["word"].lower(): s["n"] for s in _suggestions(con)}
        if status == "suggested":
            con.execute("DELETE FROM codes WHERE word = ?", [word])
        else:
            con.execute("INSERT OR REPLACE INTO codes(word, meaning, status, hits, by, ts) VALUES (?, ?, ?, ?, ?, ?)",
                        [word, meaning if status == "confirmed" else "", status, sugg.get(word, 0), acc.officer_name,
                         db.now_ms()])
        db.bump_case_version(con)
    if status == "confirmed":
        audit.log(cid, acc, "code", f"Confirmed the code word '{word}' as '{meaning}'")
    elif status == "rejected":
        audit.log(cid, acc, "code", f"Marked '{word}' as not a code word")
    else:
        audit.log(cid, acc, "code", f"Put '{word}' back among the suggestions")
    return {"ok": True, "word": word, "meaning": meaning, "status": status}
