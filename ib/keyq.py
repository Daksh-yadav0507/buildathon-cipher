"""Key questions (section 8.5): built-in lists and the unit's own lists, answered by themselves after a phone is read.

A list switches on by what the phone shows (the AI reads the case brief; without an AI, keywords decide). An officer's
own choice for the case always wins. Each question is answered through Ask with depth Quick and saved in keyq_answers.
"""
from __future__ import annotations

import json
import secrets
import sys
import traceback

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from ib import ApiError, audit, db, limits, text
from ib.officers import CaseAccess, require_case, require_officer

router = APIRouter()

EVERY = "every-phone"

BUILTIN: list[dict] = [
    {"id": EVERY, "name": "Every phone", "when": "", "questions": [
        "Who are the people closest to the owner in this work, and what does each one do?",
        "What goods, documents or consignments are talked about, with their numbers, quantities and dates?",
        "Where did the money go? Who paid whom, how much, and by what route: bank, UPI, cash or hawala?",
        "Were any officials, agents or brokers paid, or asked for favours?",
        "Was anyone told to delete chats, hide something, switch off a phone, use another number or keep quiet?",
        "Did anyone warn the owner about a raid or inquiry, and who?",
        "Which code words or coded amounts are used, and what do they seem to mean?",
        "Which messages or apps were deleted or removed, especially shortly before the phone's last activity?",
        "What trips, meetings or handovers are planned or mentioned, with places and dates?",
        "Which other phone numbers, SIMs, email IDs or accounts does the owner use?",
        "What happened in the last seven days of activity on this phone?",
        "Which companies, bank accounts, vehicles, addresses or ID numbers could be traced outside this phone?",
    ]},
    {"id": "smuggling", "name": "Goods and gold smuggling",
     "when": "The phone shows goods or gold being brought in or moved secretly: consignments, couriers, carriers, "
             "concealment, airports or ports.", "questions": [
        "Which flights, containers, air waybills, bills of lading or bills of entry are mentioned, and for which goods?",
        "How were the goods hidden, relabelled or carried, and who carried them?",
        "Who receives the goods, and where and when are they handed over?",
        "Is gold talked about? What weight, purity and form, and who buys, melts or sells it?",
        "Which airports, ports, warehouses or clearing agents are used, and is anyone there helping?",
        "Which people or suppliers abroad are involved, and in which countries?",
    ]},
    {"id": "undervaluation", "name": "Undervaluation and false documents",
     "when": "The phone shows imports or exports with invoices, declared values, customs duty, bills of entry or "
             "clearing agents.", "questions": [
        "Are two sets of invoices or values talked about: a real one and one to declare?",
        "Which importer or exporter names, IEC numbers, GST numbers or firms are used, and do any look like dummies?",
        "Is there talk of changing a description, quantity, country of origin or HS code?",
        "Who arranges the documents: which clearing agent, broker or accountant?",
        "Is money paid above the declared value, in cash or through hawala?",
    ]},
    {"id": "export-fraud", "name": "Export fraud",
     "when": "The phone shows exports with incentives or claims: over-invoicing, drawback and export-incentive "
             "claims, or fake exports.", "questions": [
        "Which exporter names, IEC numbers, GST numbers or firms are used, and do any look like dummies?",
        "Are export values raised above what the goods are worth? Which goods, and by how much?",
        "Which drawback, export-incentive or GST refund claims are talked about, with amounts and dates?",
        "Were goods really shipped? Is there talk of empty containers, junk goods, or shipping bills with no goods "
        "behind them?",
        "How does the money come back from abroad, and who arranges it?",
        "Who arranges the documents: which clearing agent, broker or accountant?",
    ]},
    {"id": "other-contraband", "name": "Other contraband",
     "when": "The phone shows these goods: cigarettes, fake currency, wildlife or wildlife parts, e-waste, or "
             "restricted electronics.", "questions": [
        "Which of these goods are talked about: cigarettes, fake currency, wildlife, e-waste or restricted "
        "electronics? With what quantities and prices?",
        "Where do the goods come from, and who supplies them?",
        "How are the goods hidden, labelled or described to get them through?",
        "Who carries them, and by what route?",
        "Who buys them, and where and when are they handed over?",
        "If fake currency is talked about, what notes and how many, and at what rate is it sold?",
        "How are the goods paid for?",
    ]},
    {"id": "hawala", "name": "Hawala and money movement",
     "when": "The phone shows cash moved outside banks, hawala or angadia, tokens, money sent abroad, or many "
             "accounts used for one person.", "questions": [
        "Who moves money outside banks: which hawala operators or angadias, and in which cities?",
        "Are tokens or codes used to release cash, such as a note's serial number?",
        "Who carried cash, how much, and between which places?",
        "Which bank accounts, UPI IDs, wallets or crypto addresses are used, and whose are they?",
        "Are amounts split or kept under a limit, or are accounts used in other people's names?",
        "Which money is sent to or received from abroad, and through whom?",
    ]},
    {"id": "drugs", "name": "Drugs",
     "when": "The phone shows drugs being bought, sold, carried or talked about, including slang for them.",
     "questions": [
        "Which substances are talked about, including slang, with quantities and prices?",
        "Who supplies, who buys, and who carries?",
        "Where and when are deliveries, parcels or drop points arranged?",
        "How are the drugs paid for?",
        "Which people or places abroad are involved?",
    ]},
]
BUILTIN_IDS = {x["id"] for x in BUILTIN}

# Without an AI, lists switch on by these words (section 8.5).
KEYWORDS: dict[str, list[str]] = {
    "smuggling": ["biscuit", "gold", "sona", "flight", "cargo", "airport", "courier", "carrier", "packet", "maal",
                  "customs"],
    "undervaluation": ["invoice", "declared", "duty", "bill of entry", "CHA", "clearing"],
    "export-fraud": ["export", "drawback", "incentive", "shipping bill"],
    "other-contraband": ["cigarette", "fake note", "wildlife", "e-waste"],
    "hawala": ["hawala", "angadia", "token", "cash", "Dubai", "transfer"],
    "drugs": ["powder", "ganja", "charas", "MD", "smack"],
}
DRUG_MAAL = "maal"  # counts for drugs only next to another drug word


# ====================================================================== lists


def own_lists() -> list[dict]:
    with db.app_db() as con:
        rows = db.rows(con, "SELECT * FROM question_lists ORDER BY created_at")
    out = []
    for r in rows:
        try:
            qs = json.loads(r.get("questions") or "[]")
        except ValueError:
            qs = []
        out.append({"id": r["list_id"], "name": r.get("name") or "Questions", "when": r.get("when_text") or "",
                    "questions": [str(q) for q in qs if str(q).strip()], "own": True,
                    "created_by": r.get("created_by") or "", "created_at": r.get("created_at")})
    return out


def all_lists() -> list[dict]:
    return [dict(x, own=False) for x in BUILTIN] + own_lists()


def _choices(con) -> dict[str, dict]:
    return {r["list_id"]: r for r in db.rows(con, "SELECT list_id, used, why, by FROM keyq_choice")}


def _hits(con, word: str) -> list[str]:
    """Record IDs (inside the warrant limit) whose words contain this word or phrase, newest first."""
    q = text.fts_query(text.tokens(word) if " " in word else [word], op="AND", column="folded")
    if not q:
        return []
    w, p = limits.where(con, "e")
    try:
        return [r[0] for r in con.execute(
            f"SELECT e.event_id FROM events e WHERE {w} AND e.event_id IN "
            f"(SELECT event_id FROM events_fts WHERE events_fts MATCH ?) ORDER BY e.ts DESC LIMIT 200", [*p, q])]
    except Exception:
        return []


def keyword_choice(con) -> dict[str, str]:
    """list_id -> why, for the built-in lists whose words show up in the records (no AI)."""
    out: dict[str, str] = {}
    cache: dict[str, int] = {}

    def n(word):
        if word not in cache:
            cache[word] = len(_hits(con, word))
        return cache[word]

    for lid, words in KEYWORDS.items():
        found = [(wd, n(wd)) for wd in words if n(wd) > 0]
        if lid == "drugs" and found and n(DRUG_MAAL) > 0:
            found.append((DRUG_MAAL, n(DRUG_MAAL)))
        total = sum(c for _, c in found)
        if len(found) >= 2 or total >= 3:
            found.sort(key=lambda x: -x[1])
            out[lid] = "The records mention " + ", ".join(
                f"'{wd}' ({text.plural(c, 'record', 'records')})" for wd, c in found[:5]) + "."
    return out


def own_list_choice(con, lists: list[dict]) -> dict[str, str]:
    """Officers' own lists with a 'when': switch on if at least two of its content words are in the records."""
    out = {}
    for lst in lists:
        if not lst.get("own") or not lst.get("when"):
            continue
        words = [w for w in dict.fromkeys(text.content_words(lst["when"])) if len(w) >= 4][:12]
        found = [(w, len(_hits(con, w))) for w in words]
        found = [x for x in found if x[1] > 0]
        if len(found) >= 2:
            out[lst["id"]] = "The records mention " + ", ".join(f"'{w}' ({c})" for w, c in found[:4]) + "."
    return out


def ai_choice(con, lists: list[dict]) -> dict[str, str] | None:
    """The AI reads the case brief (or the stats) and picks lists. None when there's no AI or it fails."""
    try:
        from ib import llm
    except Exception:
        return None
    if not llm.configured():
        return None
    brief_txt = ""
    r = db.one(con, "SELECT text FROM brief ORDER BY id DESC LIMIT 1")
    if r and r.get("text"):
        brief_txt = r["text"][:6000]
    if not brief_txt:
        kw = keyword_choice(con)
        brief_txt = "Words found in the records: " + " ".join(kw.values())
    menu = "\n".join(f"- {x['id']}: {x['name']}. When: {x['when']}" for x in lists if x.get("when"))
    system = ("You help an investigating officer. Pick which question lists fit this case from what the brief "
              "shows. Reply with JSON only: {\"lists\":[{\"id\":\"...\",\"why\":\"one plain sentence on what "
              "in the records pointed to it\"}]}. Pick only lists the brief clearly supports.")
    try:
        out, _ = llm.ask_json(system, f"Lists:\n{menu}\n\nCase brief:\n{brief_txt}", max_tokens=600)
    except Exception:
        return None
    if not out or not isinstance(out.get("lists"), list):
        return None
    ids = {x["id"] for x in lists}
    res = {}
    for item in out["lists"]:
        if isinstance(item, dict) and item.get("id") in ids and item["id"] != EVERY:
            res[item["id"]] = str(item.get("why") or "The case brief points to it.")[:300]
    return res


def auto_choose(con) -> None:
    """Set the automatic choice for every list the officers haven't chosen for themselves."""
    lists = all_lists()
    picked = keyword_choice(con)
    picked.update(own_list_choice(con, lists))
    ai = ai_choice(con, lists)
    if ai:
        picked.update(ai)  # the AI's reasons win; lists the words clearly point to stay on as well
    picked[EVERY] = "Runs on every phone."
    ch = _choices(con)
    for lst in lists:
        cur = ch.get(lst["id"])
        if cur and cur.get("by") and cur["by"] != "auto":
            continue  # an officer's choice always wins
        on = lst["id"] in picked or (not lst.get("when") and lst.get("own"))
        why = picked.get(lst["id"]) or ("Runs on every phone." if on else "")
        con.execute("INSERT OR REPLACE INTO keyq_choice(list_id, used, why, by) VALUES(?,?,?, 'auto')",
                    (lst["id"], 1 if on else 0, why))


# ====================================================================== answering


def _answer_one(con, question: str, about: str, use_ai: bool | None = None) -> dict:
    try:
        from ib import ask
    except Exception:
        ask = None
    if ask is not None and hasattr(ask, "answer"):
        res = ask.answer(con, question, depth="quick", about=about, use_ai=use_ai)
    else:
        res = _code_only(con, question)
    res["status"] = "answered" if res.get("lines") else "not found"
    res["made_from"] = str(db.case_version(con))
    return res


def _code_only(con, question: str) -> dict:
    """A plain fallback when ib.ask is not there: the newest records with the question's words."""
    words = text.content_words(question)[:6]
    q = text.fts_query(words, op="OR", column="folded")
    lines = []
    if q:
        w, p = limits.where(con, "e")
        rows = db.rows(con, f"SELECT e.event_id, e.ts, e.body FROM events e WHERE {w} AND e.event_id IN "
                            f"(SELECT event_id FROM events_fts WHERE events_fts MATCH ?) AND e.body <> '' "
                            f"ORDER BY e.ts DESC LIMIT 5", [*p, q])
        lines = [{"text": f"{text.fmt_when(r['ts'])}: {(r['body'] or '')[:200]}", "records": [r["event_id"]],
                  "checked": True} for r in rows]
    return {"question": question, "lines": lines, "answered_by": "code",
            "not_found": [] if lines else ["Nothing in the records answers this question."], "follow_ups": []}


def _used_lists(con, only: str | None = None) -> list[dict]:
    ch = _choices(con)
    out = []
    for lst in all_lists():
        if only and lst["id"] != only:
            continue
        c = ch.get(lst["id"])
        used = bool(c["used"]) if c else lst["id"] == EVERY
        if used:
            out.append(lst)
    return out


def _work(job, cid: str, only: str | None = None, choose: bool = True, with_brief: bool = False):
    about = (db.get_case(cid) or {}).get("about") or ""
    con = db.open_case(cid)
    try:
        if with_brief:
            job.step("Writing the case brief")
            try:
                from ib import brief
                brief.write_brief(con, cid, job=job)
                con.commit()
            except Exception:
                print("[keyq] the case brief could not be written:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
        if choose:
            job.step("Choosing the lists that fit this case")
            auto_choose(con)
            con.commit()
        lists = _used_lists(con, only)
        todo = [(lst["id"], q) for lst in lists for q in lst["questions"]]
        now = db.now_ms()
        for lid, q in todo:
            con.execute("INSERT OR REPLACE INTO keyq_answers(list_id, question, result, ts) VALUES(?,?,?,?)",
                        (lid, q, json.dumps({"status": "waiting"}), now))
        con.commit()
        job.step("Answering the key questions")
        n_ok = 0
        for i, (lid, q) in enumerate(todo):
            try:
                res = _answer_one(con, q, about)
                n_ok += res["status"] == "answered"
            except Exception as e:
                print(f"[keyq] could not answer '{q}': {e}", file=sys.stderr)
                res = {"status": "failed"}
            con.execute("INSERT OR REPLACE INTO keyq_answers(list_id, question, result, ts) VALUES(?,?,?,?)",
                        (lid, q, json.dumps(res, ensure_ascii=False, default=str), db.now_ms()))
            con.commit()
            job.progress((i + 1) / max(1, len(todo)))
        return {"questions": len(todo), "answered": n_ok}
    finally:
        con.close()


def start_run(cid: str, only: str | None = None, choose: bool = True, with_brief: bool = False) -> dict:
    running = jobs_find(cid)
    if running and not only:
        return running
    from ib import jobs
    steps = 1 + (1 if choose else 0) + (1 if with_brief else 0)
    return jobs.start(cid, "keyq", _work, cid, only=only, choose=choose, with_brief=with_brief,
                      label="Answering the key questions", steps=steps)


def jobs_find(cid: str):
    from ib import jobs
    return jobs.find(cid, "keyq")


def run_after_ingest(cid: str) -> None:
    """Called by ingest after a phone is read: write the brief, choose the lists, answer the questions."""
    start_run(cid, choose=True, with_brief=True)


# ====================================================================== routes


@router.get("/api/cases/{cid}/key-questions")
def key_questions(cid: str, acc: CaseAccess = Depends(require_case)):
    lists = all_lists()
    with db.case_db(cid) as con:
        ch = _choices(con)
        lim = limits.get_limit(con)
        banner = limits.banner_text(con)
        saved: dict[tuple, dict] = {}
        if lim is None:
            for r in db.rows(con, "SELECT list_id, question, result FROM keyq_answers"):
                try:
                    saved[(r["list_id"], r["question"])] = json.loads(r["result"] or "{}")
                except ValueError:
                    pass
        has_records = (db.scalar(con, "SELECT COUNT(*) FROM events", default=0) or 0) > 0
        out, waiting = [], 0
        for lst in lists:
            c = ch.get(lst["id"])
            used = bool(c["used"]) if c else lst["id"] == EVERY
            qs = []
            for q in lst["questions"]:
                res = None
                if used and lim is not None and has_records:
                    try:  # under a warrant limit nothing saved is shown: worked out fresh by code
                        res = _answer_one(con, q, acc.case.get("about") or "", use_ai=False)
                    except Exception:
                        res = {"status": "failed"}
                elif used:
                    res = saved.get((lst["id"], q))
                status = (res or {}).get("status") or ("waiting" if used else "")
                if status == "waiting":
                    waiting += 1
                body = res if res and res.get("status") not in ("waiting", "failed") else None
                qs.append({"q": q, "status": status, "result": body})
            out.append({"id": lst["id"], "name": lst["name"], "when": lst["when"], "used": used,
                        "why": (c or {}).get("why") or ("Runs on every phone." if lst["id"] == EVERY else ""),
                        "by": (c or {}).get("by") or "auto", "own": lst.get("own", False), "questions": qs})
    job = jobs_find(cid)
    return {"lists": out, "waiting": waiting if (job or has_records) else 0, "auto": True,
            "running": bool(job), "job": job, "limit": banner}


class UseIn(BaseModel):
    list_id: str
    use: bool = True


@router.post("/api/cases/{cid}/key-questions/use")
def key_questions_use(cid: str, body: UseIn, acc: CaseAccess = Depends(require_case)):
    lst = next((x for x in all_lists() if x["id"] == body.list_id), None)
    if not lst:
        raise ApiError(404, "That list of questions doesn't exist.")
    with db.case_db(cid) as con:
        why = f"Switched {'on' if body.use else 'off'} by {acc.officer_name}."
        con.execute("INSERT OR REPLACE INTO keyq_choice(list_id, used, why, by) VALUES(?,?,?,?)",
                    (lst["id"], 1 if body.use else 0, why, acc.officer_name))
    audit.log(cid, acc, "keyq", f"Switched {'on' if body.use else 'off'} the list '{lst['name']}' for this case")
    job = start_run(cid, only=lst["id"], choose=False) if body.use else None
    return {"ok": True, "job": job}


@router.post("/api/cases/{cid}/key-questions/run")
def key_questions_run(cid: str, acc: CaseAccess = Depends(require_case)):
    audit.log(cid, acc, "keyq", "Ran the key questions again")
    return {"job": start_run(cid, choose=True)}


class ListIn(BaseModel):
    name: str
    when: str = ""
    questions: list[str] = []


@router.get("/api/question-lists")
def question_lists(officer: dict = Depends(require_officer)):
    return {"lists": own_lists(), "builtin": [{"id": x["id"], "name": x["name"]} for x in BUILTIN]}


@router.post("/api/question-lists")
def question_list_add(body: ListIn, officer: dict = Depends(require_officer)):
    name = (body.name or "").strip()[:120]
    qs = [q.strip()[:500] for q in body.questions if q and q.strip()][:40]
    if not name:
        raise ApiError(400, "Give the list a name.")
    if not qs:
        raise ApiError(400, "Write at least one question.")
    lid = "own-" + secrets.token_hex(4)
    with db.app_db() as con:
        con.execute("INSERT INTO question_lists(list_id, name, when_text, questions, created_by, created_at) "
                    "VALUES(?,?,?,?,?,?)", (lid, name, (body.when or "").strip()[:500],
                                            json.dumps(qs, ensure_ascii=False), officer.get("name"), db.now_ms()))
    return {"id": lid, "name": name, "when": (body.when or "").strip(), "questions": qs, "own": True}


def _delete(list_id: str) -> dict:
    if list_id in BUILTIN_IDS:
        raise ApiError(400, "The built-in lists can't be removed. Switch it off for the case instead.")
    with db.app_db() as con:
        n = con.execute("DELETE FROM question_lists WHERE list_id = ?", (list_id,)).rowcount
    if not n:
        raise ApiError(404, "That list of questions doesn't exist.")
    return {"ok": True}


@router.delete("/api/question-lists/{list_id}")
def question_list_delete(list_id: str, officer: dict = Depends(require_officer)):
    return _delete(list_id)


@router.delete("/api/question-lists")
def question_list_delete_q(list_id: str = "", payload: dict | None = Body(None),
                           officer: dict = Depends(require_officer)):
    lid = list_id or (payload or {}).get("list_id") or (payload or {}).get("id") or ""
    return _delete(lid)
