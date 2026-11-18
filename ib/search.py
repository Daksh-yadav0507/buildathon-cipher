"""Search (section 7): every spelling of a word, an exact phrase, typing mistakes, filters, and the find box.

GET /api/cases/{cid}/search?q=&mode=auto|exact|fuzzy|meaning&app=&kind=&person=&from=&to=&status=&phone=&money=&offset=
GET /api/cases/{cid}/quickfind?q=
"""
from __future__ import annotations

import difflib
import re

from fastapi import APIRouter, Depends, Query

from ib import audit, config, db, limits, text
from ib.officers import CaseAccess, require_case

router = APIRouter()

MAX_SPELLINGS = 6
FUZZY_MIN = 0.4
FUZZY_CANDIDATES = 4000
EXACT_RE = re.compile(r'^\s*"(.*)"\s*$')

APP_LABELS = {"whatsapp": "WhatsApp", "sms": "SMS", "telegram": "Telegram", "signal": "Signal",
              "imessage": "iMessage", "phone": "Phone", "email": "Email"}


# ============================================================== filters

def _day_ms(value: str, end: bool) -> int | None:
    v = (value or "").strip()
    if not v:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        start, stop = text.day_range(v)
        return stop if end else start
    try:
        ms = text.parse_ts(v)
    except Exception:
        ms = None
    if ms is None:
        return None
    return ms + 1 if end else ms


def _filters(con, app="", kind="", person="", phone="", start="", stop="", status="", money="") -> tuple[str, list]:
    """The officer's filters as SQL on events e, with the warrant limit always applied."""
    w, p = limits.where(con, "e")
    parts, params = [w], list(p)
    apps = [a.strip() for a in (app or "").split(",") if a.strip()]
    if apps:
        names = [a for a in apps if a != "calls"]
        either = []
        if names:
            either.append(f"e.app IN ({','.join('?' * len(names))})")
            params.extend(names)
        if "calls" in apps:
            either.append("e.kind = 'call'")
        parts.append("(" + " OR ".join(either) + ")")
    kinds = [k.strip() for k in (kind or "").split(",") if k.strip()]
    if kinds:
        parts.append(f"e.kind IN ({','.join('?' * len(kinds))})")
        params.extend(kinds)
    if str(person or "").strip().isdigit():
        pid = int(str(person).strip())
        idents = "(SELECT ident FROM identifiers WHERE person_id = ?)"
        parts.append(
            f"(e.sender IN {idents}"
            f" OR EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid(e.recipients) THEN e.recipients ELSE '[]' END) j"
            f" WHERE j.value IN {idents})"
            " OR (COALESCE(e.sender, '') = '' AND e.source_id IN (SELECT source_id FROM sources WHERE owner_person_id = ?)))")
        params.extend([pid, pid, pid])
    if str(phone or "").strip().isdigit():
        n = int(str(phone).strip())
        parts.append("e.source_id IN (SELECT source_id FROM sources WHERE phone_no = ? OR "
                     "(source_id = ? AND NOT EXISTS (SELECT 1 FROM sources WHERE phone_no = ?)))")
        params.extend([n, n, n])
    a = _day_ms(start, False)
    if a is not None:
        parts.append("e.ts >= ?")
        params.append(a)
    b = _day_ms(stop, True)
    if b is not None:
        parts.append("e.ts < ?")
        params.append(b)
    st = (status or "").strip().lower()
    if st in ("deleted", "unsent", "edited", "missed", "rejected"):
        parts.append("e.status = ?")
        params.append(st)
    elif st in ("deleted-unsent", "deleted_or_unsent", "gone", "any", "1", "deleted,unsent"):
        parts.append("e.status IN ('deleted', 'unsent')")
    if str(money or "").strip().lower() in ("1", "true", "yes", "on"):
        parts.append("EXISTS (SELECT 1 FROM money m WHERE m.event_id = e.event_id)")
    return " AND ".join(parts), params


# ============================================================== code words

def _code_words(con, folded_words: list[str]) -> list[tuple[str, str]]:
    """Confirmed code words among the searched words: [(word, meaning)]."""
    try:
        rows = db.rows(con, "SELECT word, meaning FROM codes WHERE status = 'confirmed'")
    except Exception:
        return []
    out = []
    wanted = set(folded_words)
    for r in rows:
        word, meaning = r.get("word") or "", r.get("meaning") or ""
        if not meaning:
            continue
        fw = text.fold_tokens(word)
        if fw and all(f in wanted for f in fw):
            out.append((word, meaning))
    return out


def _q(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def _fts_expr(words: list[str], op: str, codes: list[tuple[str, str]]) -> str:
    """folded-column MATCH: each word quoted; a code word also matches its meaning."""
    extra: dict[str, list[str]] = {}
    for word, meaning in codes:
        mw = text.fold_tokens(meaning)
        if not mw:
            continue
        for f in text.fold_tokens(word):
            extra.setdefault(f, []).append("(" + " AND ".join(_q(x) for x in mw) + ")")
    parts = []
    for w in words:
        if w in extra:
            parts.append("(" + " OR ".join([_q(w), *extra[w]]) + ")")
        else:
            parts.append(_q(w))
    return "folded : (" + f" {op} ".join(parts) + ")"


# ============================================================== record text and people

def _texts(r: dict) -> list[str]:
    return [t for t in (r.get("body"), r.get("transcript"), r.get("ocr_text"), r.get("media_name"), r.get("place")) if t]


def _best_text(r: dict, words, exact: bool = False) -> str:
    ts = _texts(r)
    for t in ts:
        if exact:
            if any(w.lower() in t.lower() for w in words):
                return t
        elif set(text.fold_tokens(t)) & set(words):
            return t
    return ts[0] if ts else ""


def _fallback_line(r: dict) -> str:
    if r.get("kind") == "call":
        d = r.get("duration_s")
        how = (r.get("status") or "").strip() or ("outgoing" if r.get("direction") == "out" else "incoming")
        return f"Call ({how})" + (f", {text.duration_words(d)}" if d else "")
    return (r.get("kind") or "record").capitalize()


class _Names:
    """Looks up person names, phone labels and chat titles once per request."""

    def __init__(self, con):
        self.con = con
        self.idents: dict[str, str | None] = {}
        self.sources = {r["source_id"]: r for r in db.rows(
            con, "SELECT source_id, phone_no, label, owner_name FROM sources")}
        self.convs: dict = {}

    def ident(self, ident: str | None) -> str | None:
        if not ident:
            return None
        if ident not in self.idents:
            row = db.one(self.con, "SELECT p.name, i.display FROM identifiers i LEFT JOIN persons p"
                         " ON p.person_id = i.person_id WHERE i.ident = ?", [ident])
            if row is None:
                n = text.norm_phone(ident)
                if n and n != ident:
                    row = db.one(self.con, "SELECT p.name, i.display FROM identifiers i LEFT JOIN persons p"
                                 " ON p.person_id = i.person_id WHERE i.ident IN (?, ?)", [n, "wa:" + n])
            self.idents[ident] = (row and (row.get("name") or row.get("display"))) or None
        return self.idents[ident] or ident

    def conv(self, conv_id) -> str | None:
        if conv_id is None:
            return None
        if conv_id not in self.convs:
            self.convs[conv_id] = db.scalar(self.con, "SELECT title FROM conversations WHERE conv_id = ?", [conv_id])
        return self.convs[conv_id]

    def hit(self, r: dict, snippet_html: str) -> dict:
        src = self.sources.get(r.get("source_id")) or {}
        if r.get("sender"):
            sender = self.ident(r["sender"])
        elif r.get("direction") == "out" or r.get("kind") not in ("message", "call"):
            sender = src.get("owner_name")
        else:
            sender = None
        return {
            "event_id": r["event_id"], "ts": r.get("ts"), "when": text.fmt_when(r.get("ts")) if r.get("ts") else "",
            "app": r.get("app") or "", "app_label": APP_LABELS.get(r.get("app") or "", (r.get("app") or "").title()),
            "kind": r.get("kind") or "", "direction": r.get("direction") or "",
            "source_id": r.get("source_id"), "phone_no": src.get("phone_no"), "phone_label": src.get("label") or "",
            "conv_id": r.get("conv_id"), "conv_title": self.conv(r.get("conv_id")) or "",
            "sender": r.get("sender") or "", "sender_name": sender or "",
            "snippet_html": snippet_html or text.esc(_fallback_line(r)),
            "status": r.get("status") or "", "media_name": r.get("media_name") or "",
        }


COLS = ("e.event_id, e.source_id, e.kind, e.app, e.ts, e.direction, e.sender, e.recipients, e.conv_id, e.body,"
        " e.status, e.duration_s, e.place, e.media_name, e.transcript, e.ocr_text")


# ============================================================== the searches

def _recency(con, w: str, p: list) -> tuple[int, int]:
    row = db.one(con, f"SELECT MIN(e.ts) a, MAX(e.ts) b FROM events e WHERE {w}", p) or {}
    a, b = row.get("a") or 0, row.get("b") or 0
    return a, max(1, b - a)


def _fts_search(con, expr: str, w: str, p: list, offset: int, limit: int) -> tuple[int, list[dict], list[dict]]:
    """(total, page rows, a sample of up to 400 rows for the spellings line)."""
    base = f"FROM events_fts f JOIN events e ON e.event_id = f.event_id WHERE events_fts MATCH ? AND {w}"
    total = db.scalar(con, f"SELECT COUNT(*) {base}", [expr, *p], 0) or 0
    if not total:
        return 0, [], []
    lo, span = _recency(con, w, p)
    page = db.rows(con, f"SELECT {COLS} {base} ORDER BY bm25(events_fts) - 2.0 * (e.ts - ?) / ? LIMIT ? OFFSET ?",
                   [expr, *p, lo, span, limit, offset])
    sample = page if offset == 0 and total <= limit else db.rows(
        con, f"SELECT e.body, e.transcript, e.ocr_text, e.media_name, e.place {base} ORDER BY e.ts DESC LIMIT 400",
        [expr, *p])
    return total, page, sample


def _trigrams(s: str) -> set[str]:
    s = "  " + s + " "
    return {s[i:i + 3] for i in range(len(s) - 2)}


def _similar(a: str, b: str) -> float:
    if a == b:
        return 1.0
    ta, tb = _trigrams(a), _trigrams(b)
    tri = len(ta & tb) / max(1, len(ta | tb))
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    # the sequence ratio is generous on short words, so it only counts when it is high
    return max(tri, seq if seq >= 0.75 and min(len(a), len(b)) >= 4 else 0.0)


def _fuzzy_search(con, words: list[str], w: str, p: list, offset: int, limit: int):
    """Typing mistakes: candidates from the trigram table, kept when every word has a close match (>= 0.4)."""
    words = [x for x in words if x]
    if not words:
        return 0, [], set()
    grams = set()
    for x in words:
        if len(x) >= 3:
            grams.update(x[i:i + 3] for i in range(len(x) - 2))
    if grams:
        expr = " OR ".join(_q(g) for g in sorted(grams))
        cand = db.rows(con, f"SELECT e.event_id, e.folded, e.ts FROM events_tri t JOIN events e ON e.event_id = t.event_id"
                            f" WHERE events_tri MATCH ? AND {w} ORDER BY rank LIMIT {FUZZY_CANDIDATES}", [expr, *p])
    else:
        cand = db.rows(con, f"SELECT e.event_id, e.folded, e.ts FROM events_fts f JOIN events e ON e.event_id = f.event_id"
                            f" WHERE events_fts MATCH ? AND {w} LIMIT {FUZZY_CANDIDATES}",
                            [_fts_expr(words, "OR", []), *p])
    scored, matched = [], set()
    memo: dict[tuple[str, str], float] = {}

    def sim(x: str, t: str) -> float:
        k = (x, t)
        if k not in memo:
            memo[k] = _similar(x, t) if abs(len(t) - len(x)) <= max(2, len(x) // 2) else 0.0
        return memo[k]

    for c in cand:
        toks = set((c.get("folded") or "").split())
        if not toks:
            continue
        total, hits = 0.0, set()
        ok = True
        for x in words:
            best, best_tok = 0.0, None
            for t in toks:
                s = sim(x, t)
                if s > best:
                    best, best_tok = s, t
            if best < FUZZY_MIN:
                ok = False
                break
            total += best
            hits.add(best_tok)
        if ok:
            scored.append((total / len(words), c.get("ts") or 0, c["event_id"], hits))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    for s in scored:
        matched |= s[3]
    page_ids = [s[2] for s in scored[offset:offset + limit]]
    rows = []
    if page_ids:
        got = {r["event_id"]: r for r in db.rows(
            con, f"SELECT {COLS} FROM events e WHERE e.event_id IN ({','.join('?' * len(page_ids))})", page_ids)}
        rows = [got[i] for i in page_ids if i in got]
    return len(scored), rows, matched


def _number_search(con, q: str, w: str, p: list, offset: int, limit: int):
    """A phone number (or part of one): records to, from or mentioning it, matched by digits."""
    d = text.digits(q)
    if len(d) > 10 and d.startswith("91"):
        d = d[-10:]
    if len(d) > 10 and d.startswith("0"):
        d = d.lstrip("0")
    idents = [r["ident"] for r in db.rows(con, "SELECT ident FROM identifiers") if d in text.digits(r["ident"])]
    parts, params = [], []
    if idents:
        ph = ",".join("?" * len(idents))
        parts.append(f"e.sender IN ({ph})")
        params.extend(idents)
        parts.append(f"EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid(e.recipients) THEN e.recipients ELSE '[]' END) j"
                     f" WHERE j.value IN ({ph}))")
        params.extend(idents)
        conv = (f"e.conv_id IN (SELECT c.conv_id FROM conversations c, json_each(CASE WHEN json_valid(c.participants)"
                f" THEN c.participants ELSE '[]' END) j WHERE j.value IN ({ph}) AND COALESCE(c.is_group, 0) = 0)")
        parts.append(conv)
        params.extend(idents)
    if len(d) >= 3:
        parts.append("e.event_id IN (SELECT event_id FROM events_tri WHERE events_tri MATCH ?)")
        params.append(_q(d))
    if not parts:
        return 0, [], idents, d
    cond = f"({' OR '.join(parts)}) AND {w}"
    total = db.scalar(con, f"SELECT COUNT(*) FROM events e WHERE {cond}", [*params, *p], 0) or 0
    rows = db.rows(con, f"SELECT {COLS} FROM events e WHERE {cond} ORDER BY e.ts DESC LIMIT ? OFFSET ?",
                   [*params, *p, limit, offset]) if total else []
    return total, rows, idents, d


def _number_like(q: str) -> bool:
    s = q.strip()
    return bool(s) and len(text.digits(s)) >= 5 and re.fullmatch(r"[+\d\s().-]+", s) is not None


def _spellings(sample: list[dict], words) -> list[str]:
    out: list[str] = []
    for r in sample:
        for t in _texts(r):
            for s in text.spellings(t, words):
                if s not in out:
                    out.append(s)
    # Roman spellings first, then Devanagari, as the officer reads them
    out.sort(key=lambda s: bool(re.search(r"[\u0900-\u097F]", s)))
    return out[:MAX_SPELLINGS]


def _quote_list(items: list[str]) -> str:
    items = [f"'{i}'" for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def run_search(con, q: str, mode: str = "auto", offset: int = 0, limit: int = config.PAGE_SIZE, **filters) -> dict:
    """The whole search, usable by other modules (export, ask): returns the /search answer."""
    q = (q or "").strip()
    mode = (mode or "auto").strip().lower()
    if mode not in ("auto", "exact", "fuzzy", "meaning"):
        mode = "auto"
    m = EXACT_RE.match(q)
    if m and mode == "auto":
        q, mode = m.group(1).strip(), "exact"
    out = {"q": q, "total": 0, "how": "", "mode_used": mode, "hits": [], "offset": offset, "limit": limit,
           "spellings": [], "also": []}
    w, p = _filters(con, **filters)
    names = _Names(con)

    if mode == "meaning":
        out["how"] = "Find by meaning is not set up on this computer. Use the other search choices instead."
        return out

    if not q:
        out["how"] = "Type a word, a name or a phone number to search."
        return out

    if _number_like(q):
        total, rows, idents, d = _number_search(con, q, w, p, offset, limit)
        out["total"], out["mode_used"] = total, "number"
        shown: list[str] = []
        for i in idents:
            nm = names.ident(i)
            if nm and nm != i and nm not in shown:
                shown.append(nm)
        if total:
            who = f" (saved as {', '.join(shown[:3])})" if shown else ""
            out["how"] = f"Found records to, from or mentioning the number {d}{who}."
        else:
            out["how"] = f"No record has the number {d}."
        out["hits"] = [names.hit(r, text.snippet(_best_text(r, [d], exact=True), [d], exact=True)
                                 if any(d in t for t in _texts(r)) else text.snippet(_best_text(r, []), []))
                       for r in rows]
        return out

    if mode == "exact":
        phrase = " ".join(text.tokens(q))
        if not phrase:
            out["how"] = "Type the exact words to look for."
            return out
        expr = "words : " + _q(phrase)
        total, rows, _ = _fts_search(con, expr, w, p, offset, limit)
        out["total"] = total
        toks = text.tokens(phrase)
        out["how"] = (f"Found only the exact words \"{phrase}\"." if total
                      else f"No record has the exact words \"{phrase}\". Try the search that finds every spelling.")
        out["hits"] = [names.hit(r, text.snippet(_best_text(r, toks, exact=True), toks, exact=True)) for r in rows]
        return out

    words = text.fold_tokens(q)
    seen = set()
    words = [x for x in words if not (x in seen or seen.add(x))]
    if not words:
        out["how"] = "Type a word, a name or a phone number to search."
        return out
    codes = _code_words(con, words)
    mark_words = list(words)
    for _, meaning in codes:
        mark_words.extend(text.fold_tokens(meaning))
    also = [f"Also searched '{meaning}', because '{word}' is in the code book." for word, meaning in codes]
    out["also"] = also

    if mode == "auto":
        total, rows, sample = _fts_search(con, _fts_expr(words, "AND", codes), w, p, offset, limit)
        how_prefix = ""
        if not total and len(words) > 1:
            total, rows, sample = _fts_search(con, _fts_expr(words, "OR", codes), w, p, offset, limit)
            how_prefix = "No record has all of these words, so these have any of them. "
        if total:
            sp = _spellings(sample, mark_words)
            out["spellings"] = sp
            out["total"] = total
            out["how"] = (how_prefix + (f"Found every spelling: {', '.join(sp)}" if sp else "Found these words.")
                          + ("" if not also else " " + " ".join(also))).strip()
            out["hits"] = [names.hit(r, text.snippet(_best_text(r, mark_words), mark_words)) for r in rows]
            return out
        # nothing at all: allow typing mistakes
        mode = "fuzzy"
        fell_back = True
    else:
        fell_back = False

    total, rows, matched = _fuzzy_search(con, words, w, p, offset, limit)
    out["mode_used"] = "fuzzy"
    out["total"] = total
    if total:
        spell: list[str] = []
        for r in rows:
            for t in _texts(r):
                for tok in text.tokens(t):
                    if text.fold(tok) in matched and tok.lower() not in spell:
                        spell.append(tok.lower())
        out["spellings"] = spell[:MAX_SPELLINGS]
        lead = f"Nothing matched '{q}' exactly, so this allows typing mistakes. " if fell_back else "Allowing typing mistakes. "
        out["how"] = (lead + (f"Found close spellings: {', '.join(spell[:MAX_SPELLINGS])}" if spell else "")).strip()
        out["hits"] = [names.hit(r, text.snippet(_best_text(r, list(matched)), spell, exact=True)) for r in rows]
    else:
        out["how"] = f"Nothing found for '{q}', even allowing typing mistakes."
    if also:
        out["how"] += " " + " ".join(also)
    return out


@router.get("/api/cases/{cid}/search")
def search_route(cid: str, q: str = "", mode: str = "auto", app: str = "", kind: str = "", person: str = "",
                 phone: str = "", status: str = "", money: str = "", offset: int = Query(0, ge=0),
                 date_from: str = Query("", alias="from"), date_to: str = Query("", alias="to"),
                 acc: CaseAccess = Depends(require_case)):
    with db.case_db(acc.cid) as con:
        res = run_search(con, q, mode, offset=offset, app=app, kind=kind, person=person, phone=phone,
                         start=date_from, stop=date_to, status=status, money=money)
    if q.strip() and offset == 0:
        audit.log(acc.cid, acc, "search", f"Searched for '{q.strip()[:200]}'")
    return res


# ============================================================== quick find

PAGES = [
    ("Dashboard", "dashboard", "overview summary home case"),
    ("Ask a question", "ask", "ask question answer ai"),
    ("Search", "search", "search find words"),
    ("Chats", "chats", "chats messages whatsapp sms telegram signal conversation"),
    ("Calls", "calls", "calls call log phone missed"),
    ("Timeline", "timeline", "timeline events day order"),
    ("Places", "places", "places map location together gps"),
    ("People", "people", "people contacts persons names"),
    ("Photos and files", "media", "photos files media images documents voice notes video"),
    ("Findings", "findings", "findings notes saved bookmarks"),
    ("Key questions", "dashboard?tab=key", "key questions"),
    ("Across phones", "dashboard?tab=across", "across phones compare money match"),
    ("Code words", "codes", "code words codebook biscuit"),
    ("Evidence added", "sources", "evidence added phones sources fingerprint"),
    ("Audit log", "audit", "audit log who opened"),
]


@router.get("/api/cases/{cid}/quickfind")
def quickfind(cid: str, q: str = "", acc: CaseAccess = Depends(require_case)):
    q = (q or "").strip()
    out = {"q": q, "people": [], "chats": [], "pages": []}
    if not q:
        return out
    base = f"#/c/{acc.cid}"
    like = f"%{q.lower()}%"
    d = text.digits(q)
    folded = text.fold_tokens(q)
    with db.case_db(acc.cid) as con:
        w, p = limits.where(con, "e")
        lim = limits.get_limit(con)
        # people: by name, any saved name, or the digits of a number
        cand = db.rows(con, "SELECT person_id, name, names, kind, is_owner, n_messages, n_calls FROM persons"
                            " WHERE lower(name) LIKE ? OR lower(names) LIKE ? ORDER BY is_owner DESC,"
                            " COALESCE(n_messages,0) + COALESCE(n_calls,0) DESC LIMIT 40", [like, like])
        if folded and len(cand) < 5:
            for r in db.rows(con, "SELECT person_id, name, names, kind, is_owner, n_messages, n_calls FROM persons"
                                  " ORDER BY COALESCE(n_messages,0) + COALESCE(n_calls,0) DESC LIMIT 2000"):
                if any(f in text.fold_tokens(r.get("name")) for f in folded) and r["person_id"] not in \
                        {c["person_id"] for c in cand}:
                    cand.append(r)
        if len(d) >= 4:
            ids = {r["person_id"] for r in db.rows(con, "SELECT ident, person_id FROM identifiers")
                   if r["person_id"] is not None and d in text.digits(r["ident"])}
            have = {c["person_id"] for c in cand}
            extra = [x for x in ids if x not in have]
            if extra:
                cand += db.rows(con, f"SELECT person_id, name, names, kind, is_owner, n_messages, n_calls FROM persons"
                                     f" WHERE person_id IN ({','.join('?' * len(extra))})", extra)
        for r in cand:
            if len(out["people"]) >= 5:
                break
            pid = r["person_id"]
            if lim:
                inside = db.scalar(con, f"SELECT 1 FROM events e WHERE {w} AND (e.sender IN (SELECT ident FROM"
                                        f" identifiers WHERE person_id = ?) OR e.source_id IN (SELECT source_id FROM"
                                        f" sources WHERE owner_person_id = ?)) LIMIT 1", [*p, pid, pid])
                if not inside and pid not in (lim.get("people") or []):
                    continue
            ident = db.one(con, "SELECT display, ident FROM identifiers WHERE person_id = ? ORDER BY"
                                " CASE WHEN ident LIKE '+%' THEN 0 ELSE 1 END LIMIT 1", [pid])
            nm, nc = r.get("n_messages") or 0, r.get("n_calls") or 0
            sub = []
            if r.get("is_owner"):
                sub.append("phone owner")
            if ident:
                sub.append(ident.get("display") or ident.get("ident"))
            if nm or nc:
                sub.append(f"{text.plural(nm, 'message')}, {text.plural(nc, 'call')}")
            out["people"].append({"person_id": pid, "name": r.get("name") or (ident or {}).get("display") or "Unknown",
                                  "sub": " · ".join(x for x in sub if x), "kind": r.get("kind") or "person",
                                  "href": f"{base}/person/{pid}",
                                  "link": {"page": "person", "params": {"pid": pid}}})
        # chats: by title
        conds = "lower(c.title) LIKE ?"
        cparams: list = [like]
        if lim:
            conds += f" AND EXISTS (SELECT 1 FROM events e WHERE e.conv_id = c.conv_id AND {w})"
            cparams += p
        for r in db.rows(con, f"SELECT c.conv_id, c.title, c.app, c.is_group, c.n_messages, c.last_ts, s.label"
                              f" FROM conversations c LEFT JOIN sources s ON s.source_id = c.source_id"
                              f" WHERE {conds} ORDER BY c.last_ts DESC LIMIT 5", cparams):
            app = APP_LABELS.get(r.get("app") or "", (r.get("app") or "").title())
            sub = [app, r.get("label") or "", text.plural(r.get("n_messages") or 0, "message")]
            out["chats"].append({"conv_id": r["conv_id"], "title": r.get("title") or "Chat", "app": r.get("app") or "",
                                 "is_group": bool(r.get("is_group")), "phone_label": r.get("label") or "",
                                 "sub": " · ".join(x for x in sub if x),
                                 "href": f"{base}/chats?conv={r['conv_id']}",
                                 "link": {"page": "chats", "params": {"conv": r["conv_id"]}}})
    ql = q.lower()
    for label, tab, keys in PAGES:
        if ql in label.lower() or any(k.startswith(ql) for k in keys.split()) or ql in keys:
            if "?" in tab:
                page, qs = tab.split("?", 1)
                href = f"{base}?{qs}" if page == "dashboard" else f"{base}/{page}?{qs}"
                params = dict(x.split("=", 1) for x in qs.split("&"))
            else:
                page, href, params = tab, (base if tab == "dashboard" else f"{base}/{tab}"), {}
            out["pages"].append({"label": label, "tab": page, "href": href, "link": {"page": page, "params": params}})
            if len(out["pages"]) >= 5:
                break
    return out
