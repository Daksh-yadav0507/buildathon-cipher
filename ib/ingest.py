"""Adding a phone to a case (section 5.1): cases, samples, sources and phone details.

A phone export (JSON, section 4) is read into the case as a background job in seven steps:
opening the phone, chats, other records, who is who, money, the search index, and the Dashboard.
ensure_sample_case() makes "Operation Biscuit (sample data)" with the three made-up phones on first run.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
import threading
import traceback
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Request

from ib import ApiError, audit, config, db, jobs, text
from ib.officers import CaseAccess, demo_officer_id, require_case, require_officer

router = APIRouter()

STEPS = ["Opening the phone", "Reading chats", "Reading calls, contacts, places, photos, voice notes and documents",
         "Working out who is who", "Finding money", "Making the records searchable", "Getting the Dashboard ready"]
SAMPLE_CID = "sample"
SAMPLE_NAME = "Operation Biscuit (sample data)"
SAMPLE_NUMBER = "SAMPLE-2026-001"
SAMPLE_ABOUT = ("A made-up gold-smuggling network in which gold bars are called 'biscuits'. Three seized phones: "
                "Vikram Mehra (the organiser), Raju Verma (a cargo handler at the airport) and Meena Iyer "
                "(who moves the money). Every person, number and record here is made up for practice.")
SAMPLES = ["phone1", "phone2", "phone3"]
MAX_UPLOAD = 300 * 1024 * 1024
BATCH = 2000

EVENT_COLS = ["event_id", "source_id", "kind", "app", "ts", "direction", "sender", "recipients", "conv_id", "body",
              "status", "duration_s", "lat", "lon", "place", "media_name", "media_size", "media_sha256",
              "transcript", "ocr_text", "origin", "extra", "folded"]
_KNOWN = {"kind", "app", "ts", "direction", "sender", "recipients", "conv", "conv_id", "body", "status", "duration_s",
          "duration", "lat", "lon", "place", "media_name", "media_size", "media_sha256", "transcript", "ocr_text",
          "origin", "extra", "id"}
CHAT_KINDS = {"message"}
KIND_WORDS = {"message": "messages", "call": "calls", "location": "places", "photo": "photos", "video": "videos",
              "voice": "voice notes", "document": "documents", "contact": "contacts", "note": "notes"}

_case_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_sample_lock = threading.Lock()


def _case_lock(cid: str) -> threading.Lock:
    with _locks_guard:
        return _case_locks.setdefault(cid, threading.Lock())


# ================================================================ small helpers


def _jl(value, default):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _ident(raw) -> str | None:
    """A number, a sender ID or an email, normalised to the identifiers form ('+91…', 'AD-BUBANK', 'email:…')."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    low = s.lower()
    if low.startswith(("email:", "upi:")):
        return low
    if low.startswith("wa:"):
        s = s[3:]
    if "@" in s and " " not in s:
        return "email:" + s.lower()
    if text.is_sender_id(s):
        return s.upper()
    p = text.norm_phone(s)
    return p or s


def _display_phone(p: str) -> str:
    d = text.digits(p)
    if p.startswith("+91") and len(d) == 12:
        return f"+91 {d[2:7]} {d[7:]}"
    return p


def _phone_kind(device: dict) -> str:
    blob = f"{device.get('model', '')} {device.get('os', '')} {device.get('platform', '')}".lower()
    return "iPhone" if ("iphone" in blob or "ios" in blob) else "Android"


def _default_origin(platform: str, kind: str, app: str, n: int, file_name: str) -> dict:
    if platform == "ufdr-report":
        model = {"message": "Chat", "call": "Call", "contact": "Contact", "location": "Location"}.get(kind, "File")
        return {"file": "report.xml", "table": f'<model type="{model}">', "row": n}
    if kind == "contact":
        return ({"file": "AddressBook.sqlitedb", "table": "ABPerson", "row": n} if platform == "iphone-backup"
                else {"file": "contacts2.db", "table": "raw_contacts", "row": n})
    return {"file": file_name or "export", "table": kind, "row": n}


# ================================================================ reading an export


def load_export(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise ApiError(400, "That file isn't a phone export this app can read. Choose the export file (.json) "
                            "made by the phone reader.")
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise ApiError(400, "That file has no records in it. Choose the export file made by the phone reader.")
    if not isinstance(data.get("device"), dict):
        data["device"] = {}
    if not isinstance(data.get("owner"), dict):
        data["owner"] = {}
    return data


def _sample_path(name: str) -> Path:
    return config.samples_dir() / f"{name}.json"


def _ensure_sample_files() -> bool:
    if all(_sample_path(s).exists() for s in SAMPLES):
        return True
    try:
        gen = importlib.import_module("ib.generate")
    except Exception:
        return False
    fn = getattr(gen, "ensure_samples", None)
    if callable(fn):
        fn()
    return all(_sample_path(s).exists() for s in SAMPLES)


_sample_info_cache: dict[str, tuple[float, dict]] = {}


def sample_info(name: str) -> dict | None:
    p = _sample_path(name)
    if not p.exists():
        return None
    mt = p.stat().st_mtime
    hit = _sample_info_cache.get(name)
    if hit and hit[0] == mt:
        return hit[1]
    data = load_export(p.read_bytes())
    dev, owner = data["device"], data["owner"]
    nums = owner.get("numbers") or []
    info = {"sample": name, "owner": owner.get("name") or dev.get("label_owner") or "",
            "short_label": f"{dev.get('label_owner') or owner.get('name') or 'Unknown'}'s {_phone_kind(dev)}",
            "device": dev.get("model") or "", "os": dev.get("os") or "", "platform": dev.get("platform") or "",
            "file_name": dev.get("file_name") or p.name, "number": _display_phone(_ident(nums[0]) or "") if nums else "",
            "records": len(data["events"]) + len(data.get("contacts") or [])}
    _sample_info_cache[name] = (mt, info)
    return info


# ================================================================ the job


def ingest_job(job, cid: str, raw_path: str, added_by: str, sample: str | None = None, delete_after: bool = False):
    lock = _case_lock(cid)
    if not lock.acquire(blocking=False):
        job.step("Waiting for the other phone to finish")
        lock.acquire()
        job.step_no = 0
    try:
        return _ingest(job, cid, Path(raw_path), added_by, sample)
    finally:
        lock.release()
        if delete_after:
            try:
                Path(raw_path).unlink()
            except OSError:
                pass


def _ingest(job, cid: str, path: Path, added_by: str, sample: str | None) -> dict:
    # ---- 1. Opening the phone
    job.step(STEPS[0])
    raw = path.read_bytes()
    job.progress(0.3)
    sha = hashlib.sha256(raw).hexdigest()
    data = load_export(raw)
    del raw
    job.progress(0.7)
    dev, owner = data["device"], data["owner"]
    platform = dev.get("platform") or "ufdr-report"
    file_name = dev.get("file_name") or path.name
    con = db.open_case(cid)
    try:
        same = db.one(con, "SELECT label, status FROM sources WHERE sha256=?", (sha,))
        if same and same["status"] != "failed":
            raise ApiError(409, f"This phone is already in the case, as {same['label']}.")
        if sample:
            for r in db.rows(con, "SELECT label, status, device_info FROM sources"):
                if (_jl(r["device_info"], {}) or {}).get("sample") == sample and r["status"] != "failed":
                    raise ApiError(409, f"This sample phone is already in the case, as {r['label']}.")
        con.execute("DELETE FROM sources WHERE sha256=? AND status='failed'", (sha,))
        phone_no = db.scalar(con, "SELECT MAX(phone_no) FROM sources", default=0) + 1
        owner_name = owner.get("name") or dev.get("label_owner") or "Unknown owner"
        label = f"Phone {phone_no} | {dev.get('label') or (dev.get('label_owner') or owner_name.split()[0]) + chr(39) + 's ' + _phone_kind(dev)}"
        owner_ids = [i for i in (_ident(n) for n in (owner.get("numbers") or [])) if i]
        owner_ids += [i for i in (_ident("email:" + e) for e in (owner.get("emails") or [])) if i]
        info = {k: v for k, v in dev.items()}
        info.update({"owner_name": owner_name, "owner_numbers": [_display_phone(i) for i in owner_ids if i.startswith("+")],
                     "owner_emails": owner.get("emails") or [], "sample": sample})
        cur = con.execute(
            "INSERT INTO sources(phone_no, label, owner_name, platform, device, os, file_name, sha256, added_at, "
            "added_by, status, n_events, device_info) VALUES(?,?,?,?,?,?,?,?,?,?,'reading',0,?)",
            (phone_no, label, owner_name, platform, dev.get("model") or "", dev.get("os") or "", file_name, sha,
             db.now_ms(), added_by, json.dumps(info, ensure_ascii=False)))
        sid = cur.lastrowid
        con.commit()
        job.progress(1)
        try:
            result = _read_records(job, con, cid, sid, phone_no, label, data, owner_ids, owner_name, platform, file_name)
        except BaseException:
            con.rollback()
            _undo(con, sid)
            raise
    finally:
        con.close()
    audit.log(cid, added_by, "phone", f"Added {label}")
    _after_ingest(job, cid)
    return result


def _undo(con, sid: int) -> None:
    try:
        ids = "SELECT event_id FROM events WHERE source_id=?"
        con.execute(f"DELETE FROM events_fts WHERE event_id IN ({ids})", (sid,))
        con.execute(f"DELETE FROM events_tri WHERE event_id IN ({ids})", (sid,))
        con.execute("DELETE FROM money WHERE source_id=?", (sid,))
        con.execute("DELETE FROM events WHERE source_id=?", (sid,))
        con.execute("DELETE FROM conversations WHERE source_id=?", (sid,))
        con.execute("UPDATE sources SET status='failed' WHERE source_id=?", (sid,))
        con.commit()
    except Exception:
        traceback.print_exc(file=sys.stderr)


def _num(v, cast=float):
    if v in (None, ""):
        return None
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


def _read_records(job, con, cid, sid, phone_no, label, data, owner_ids, owner_name, platform, file_name) -> dict:
    owner_main = next((i for i in owner_ids if i.startswith("+")), owner_ids[0] if owner_ids else None)
    # ---- 2. Reading chats: conversations first
    job.step(STEPS[1])
    conv_map: dict[str, int] = {}
    conv_meta: dict[int, dict] = {}

    def add_conv(key: str, app: str, title: str, is_group: bool, parts: list) -> int:
        members = sorted({p for p in (_ident(x) for x in parts) if p})
        if is_group:
            tk = f"{app}:g:{text.fold_text(title)}:" + "|".join(sorted(set(members) | ({owner_main} if owner_main else set())))
        else:
            others = [m for m in members if m not in owner_ids]
            pair = sorted({*(others[:1] or [title]), *([owner_main] if owner_main else [])})
            tk = f"{app}:" + "|".join(pair)
        c = con.execute("INSERT INTO conversations(source_id, app, title, is_group, participants, n_messages, "
                        "n_deleted, thread_key) VALUES(?,?,?,?,?,0,0,?)",
                        (sid, app, title, 1 if is_group else 0, json.dumps(members, ensure_ascii=False), tk))
        conv_map[key] = c.lastrowid
        conv_meta[c.lastrowid] = {"is_group": is_group, "members": members}
        return c.lastrowid

    for c in data.get("conversations") or []:
        if not isinstance(c, dict):
            continue
        key = str(c.get("key") or c.get("id") or c.get("title") or len(conv_map))
        add_conv(key, c.get("app") or "whatsapp", c.get("title") or key, bool(c.get("is_group")),
                 c.get("participants") or [])

    raw_events = [e for e in data["events"] if isinstance(e, dict)]
    order = sorted(range(len(raw_events)), key=lambda i: (text.parse_ts(raw_events[i].get("ts")) or 0, i))
    has_contact_events = any(e.get("kind") == "contact" for e in raw_events)
    rows_chat, rows_other = [], []
    n = 0
    for idx in order:
        e = raw_events[idx]
        n += 1
        kind = (e.get("kind") or "note").lower()
        app = (e.get("app") or ("phone" if kind == "call" else "")).lower()
        ts = text.parse_ts(e.get("ts"))
        sender = _ident(e.get("sender"))
        recips = [r for r in (_ident(x) for x in (e.get("recipients") or [])) if r]
        conv_id = None
        ck = e.get("conv") or e.get("conv_id")
        if ck not in (None, ""):
            ck = str(ck)
            conv_id = conv_map.get(ck) or add_conv(ck, app or "whatsapp", ck, len(recips) > 1, [sender, *recips])
        extra = {k: v for k, v in e.items() if k not in _KNOWN}
        if isinstance(e.get("extra"), dict):
            extra.update(e["extra"])
        origin = e.get("origin") if isinstance(e.get("origin"), dict) else _default_origin(platform, kind, app, n, file_name)
        row = {"event_id": f"P{phone_no}-{n:06d}", "source_id": sid, "kind": kind, "app": app, "ts": ts,
               "direction": e.get("direction") or "", "sender": sender, "recipients": json.dumps(recips, ensure_ascii=False),
               "conv_id": conv_id, "body": e.get("body") or "", "status": e.get("status") or "",
               "duration_s": _num(e.get("duration_s", e.get("duration")), int), "lat": _num(e.get("lat")),
               "lon": _num(e.get("lon")), "place": e.get("place") or None, "media_name": e.get("media_name") or None,
               "media_size": _num(e.get("media_size"), int), "media_sha256": e.get("media_sha256") or None,
               "transcript": e.get("transcript") or None, "ocr_text": e.get("ocr_text") or None,
               "origin": json.dumps(origin, ensure_ascii=False), "extra": json.dumps(extra, ensure_ascii=False) if extra else None,
               "folded": None}
        (rows_chat if kind in CHAT_KINDS else rows_other).append(row)

    contacts = [c for c in (data.get("contacts") or []) if isinstance(c, dict)]
    contact_rows = []
    if not has_contact_events:
        for i, c in enumerate(contacts, 1):
            n += 1
            nums = [x for x in (_ident(v) for v in (c.get("numbers") or [])) if x]
            body = (c.get("name") or "") + ("\n" + "\n".join(_display_phone(x) for x in nums) if nums else "")
            contact_rows.append({**dict.fromkeys(EVENT_COLS), "event_id": f"P{phone_no}-{n:06d}", "source_id": sid,
                                 "kind": "contact", "app": "contacts", "direction": "", "status": "",
                                 "recipients": json.dumps(nums), "body": body,
                                 "origin": json.dumps(c.get("origin") or _default_origin(platform, "contact", "", i, file_name)),
                                 "extra": json.dumps({"name": c.get("name"), "numbers": c.get("numbers"),
                                                      "emails": c.get("emails")}, ensure_ascii=False)})
            c["_event_id"] = contact_rows[-1]["event_id"]
    rows_other += contact_rows

    sql = f"INSERT INTO events({', '.join(EVENT_COLS)}) VALUES({', '.join('?' * len(EVENT_COLS))})"

    def insert(rows: list[dict]):
        for i in range(0, len(rows), BATCH):
            con.executemany(sql, [[r[c] for c in EVENT_COLS] for r in rows[i:i + BATCH]])
            con.commit()
            job.progress((i + BATCH) / max(1, len(rows)))

    insert(rows_chat)
    con.execute("""UPDATE conversations SET
        n_messages = (SELECT COUNT(*) FROM events e WHERE e.conv_id = conversations.conv_id),
        n_deleted = (SELECT COUNT(*) FROM events e WHERE e.conv_id = conversations.conv_id AND e.status='deleted'),
        first_ts = (SELECT MIN(ts) FROM events e WHERE e.conv_id = conversations.conv_id),
        last_ts = (SELECT MAX(ts) FROM events e WHERE e.conv_id = conversations.conv_id)
        WHERE source_id = ?""", (sid,))
    con.commit()
    job.progress(1)

    # ---- 3. Other records
    job.step(STEPS[2])
    insert(rows_other)
    con.execute("""UPDATE conversations SET
        n_messages = (SELECT COUNT(*) FROM events e WHERE e.conv_id = conversations.conv_id AND e.kind='message'),
        first_ts = (SELECT MIN(ts) FROM events e WHERE e.conv_id = conversations.conv_id),
        last_ts = (SELECT MAX(ts) FROM events e WHERE e.conv_id = conversations.conv_id)
        WHERE source_id = ?""", (sid,))
    con.execute("UPDATE sources SET n_events=(SELECT COUNT(*) FROM events WHERE source_id=?), "
                "first_ts=(SELECT MIN(ts) FROM events WHERE source_id=?), "
                "last_ts=(SELECT MAX(ts) FROM events WHERE source_id=?) WHERE source_id=?", (sid, sid, sid, sid))
    db.bump_case_version(con)
    con.commit()
    job.progress(1)
    all_rows = rows_chat + rows_other

    # ---- 4. Who is who
    job.step(STEPS[3])
    owner_pid = _people(con, sid, phone_no, label, owner_ids, owner_name, contacts, all_rows, job)
    con.execute("UPDATE sources SET owner_person_id=? WHERE source_id=?", (owner_pid, sid))
    con.commit()
    job.progress(1)

    # ---- 5. Money
    job.step(STEPS[4])
    n_money = _money(con, sid, all_rows, conv_meta, owner_ids, job)
    con.commit()
    job.progress(1)

    # ---- 6. Search index
    job.step(STEPS[5])
    _index(con, all_rows, job)
    con.commit()
    job.progress(1)

    # ---- 7. The Dashboard (status done first so saved answers are worked out on the finished records)
    job.step(STEPS[6])
    con.execute("UPDATE sources SET status='done' WHERE source_id=?", (sid,))
    db.bump_case_version(con)
    con.commit()
    db.checkpoint(con)
    return {"source_id": sid, "phone_no": phone_no, "label": label, "records": len(all_rows), "money": n_money}


def _after_ingest(job, cid: str) -> None:
    """Saved Dashboard answers (ib.ready) and the key questions (ib.keyq), when those modules are there."""
    hooks = [("ib.ready", ("refresh_case", "warm", "prepare", "refresh_all")),
             ("ib.keyq", ("run_after_ingest", "run_auto", "auto_run"))]
    for i, (modname, names) in enumerate(hooks):
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        fn = next((getattr(mod, nm) for nm in names if callable(getattr(mod, nm, None))), None)
        if fn is None:
            continue
        try:
            fn(cid)
        except Exception:
            print(f"[ingest] {modname}.{fn.__name__} failed after adding a phone:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        job.progress((i + 1) / len(hooks))
    job.progress(1)


# ================================================================ who is who


def _people(con, sid, phone_no, label, owner_ids, owner_name, contacts, all_rows, job) -> int | None:
    known: dict[str, int] = {r["ident"]: r["person_id"] for r in con.execute("SELECT ident, person_id FROM identifiers")}
    persons: dict[int, dict] = {}
    for r in db.rows(con, "SELECT * FROM persons"):
        r["names"] = _jl(r["names"], [])
        persons[r["person_id"]] = r

    def new_person(name: str, kind: str) -> int:
        c = con.execute("INSERT INTO persons(name, names, kind, is_owner, n_messages, n_calls) VALUES(?, '[]', ?, 0, 0, 0)",
                        (name, kind))
        persons[c.lastrowid] = {"person_id": c.lastrowid, "name": name, "names": [], "kind": kind, "is_owner": 0,
                                "owner_source_id": None, "_dirty": True}
        return c.lastrowid

    def add_ident(ident: str, pid: int, app: str | None = None):
        kind = ("email" if ident.startswith("email:") else "upi" if ident.startswith("upi:")
                else "sender" if text.is_sender_id(ident) else "phone" if ident.startswith("+") else "other")
        disp = ident.split(":", 1)[1] if ident.startswith(("email:", "upi:")) else _display_phone(ident)
        if ident not in known:
            con.execute("INSERT OR IGNORE INTO identifiers(ident, kind, display, person_id) VALUES(?,?,?,?)",
                        (ident, kind, disp, pid))
            known[ident] = pid
        if app == "whatsapp" and ident.startswith("+") and "wa:" + ident not in known:
            con.execute("INSERT OR IGNORE INTO identifiers(ident, kind, display, person_id) VALUES(?,?,?,?)",
                        ("wa:" + ident, "whatsapp", "WhatsApp " + disp, known[ident]))
            known["wa:" + ident] = known[ident]

    def person_for(ident: str, name_hint: str | None = None, app: str | None = None) -> int:
        pid = known.get(ident)
        if pid is None:
            service = text.is_sender_id(ident)
            pid = new_person(name_hint or (ident if service else _display_phone(ident)), "service" if service else "person")
        add_ident(ident, pid, app)
        return pid

    def add_name(pid: int, name: str, how: str, event_id: str | None = None):
        p = persons[pid]
        if not name or any(x.get("name") == name and x.get("source_id") == sid and x.get("how") == how for x in p["names"]):
            return
        p["names"].append({"name": name, "how": how, "source_id": sid, "phone": label, "event_id": event_id})
        p["_dirty"] = True

    # the owner
    owner_pid = None
    for ident in owner_ids:
        if ident in known:
            owner_pid = known[ident]
            break
    if owner_pid is None and owner_ids:
        owner_pid = new_person(owner_name, "person")
    if owner_pid is not None:
        for ident in owner_ids:
            add_ident(ident, owner_pid, "whatsapp")
        p = persons[owner_pid]
        p.update({"is_owner": 1, "owner_source_id": sid, "name": owner_name, "kind": "person", "_dirty": True})
        add_name(owner_pid, owner_name, "profile")

    # contacts on this phone
    for c in contacts:
        nums = [x for x in (_ident(v) for v in (c.get("numbers") or [])) if x]
        nums += [x for x in (_ident("email:" + v) for v in (c.get("emails") or [])) if x]
        if not nums:
            continue
        pid = next((known[x] for x in nums if x in known), None) or new_person(c.get("name") or _display_phone(nums[0]), "person")
        for x in nums:
            add_ident(x, pid)
        add_name(pid, c.get("name") or "", "contact", c.get("_event_id"))
    job.progress(0.3)

    # everyone in the records
    for i, r in enumerate(all_rows):
        ids = ([r["sender"]] if r["sender"] else []) + _jl(r["recipients"], [])
        for ident in ids:
            person_for(ident, None, r["app"])
        if i % 5000 == 0:
            job.progress(0.3 + 0.3 * i / max(1, len(all_rows)))

    # best names: the owner's own name, else the first saved name, else the number
    for pid, p in persons.items():
        if not p.get("_dirty"):
            continue
        if not p.get("is_owner"):
            saved = [x["name"] for x in p["names"] if x.get("how") == "contact" and x.get("name")]
            if saved and (p["name"] == "" or p["name"].startswith("+") or p["name"].isdigit()):
                p["name"] = saved[0]
        con.execute("UPDATE persons SET name=?, names=?, kind=?, is_owner=?, owner_source_id=? WHERE person_id=?",
                    (p["name"], json.dumps(p["names"], ensure_ascii=False), p["kind"], p.get("is_owner") or 0,
                     p.get("owner_source_id"), pid))
    con.commit()
    job.progress(0.7)
    _person_counts(con, known)
    return owner_pid


def _person_counts(con, known: dict[str, int]) -> None:
    """Messages, calls, first and last contact, and the People group, over every phone in the case."""
    convs = {r["conv_id"]: r["is_group"] for r in con.execute("SELECT conv_id, is_group FROM conversations")}
    owners = {r["person_id"] for r in con.execute("SELECT person_id FROM persons WHERE is_owner=1")}
    stats: dict[int, dict] = {}
    for r in con.execute("SELECT kind, ts, sender, recipients, conv_id, status, duration_s FROM events "
                         "WHERE kind IN ('message','call')"):
        pids = {known.get(x) for x in ([r["sender"]] if r["sender"] else []) + _jl(r["recipients"], [])}
        pids.discard(None)
        group = bool(convs.get(r["conv_id"])) if r["conv_id"] else False
        for pid in pids:
            s = stats.setdefault(pid, {"m": 0, "c": 0, "f": None, "l": None, "direct": False, "group": False})
            if r["kind"] == "message":
                s["m"] += 1
            else:
                s["c"] += 1
            ts = r["ts"]
            if ts is not None:
                s["f"] = ts if s["f"] is None else min(s["f"], ts)
                s["l"] = ts if s["l"] is None else max(s["l"], ts)
            if group:
                s["group"] = True
            elif r["kind"] == "message" or (r["status"] not in ("missed", "rejected") and (r["duration_s"] or 0) > 0):
                s["direct"] = True
    updates = []
    for p in con.execute("SELECT person_id, kind FROM persons").fetchall():
        s = stats.get(p["person_id"], {"m": 0, "c": 0, "f": None, "l": None, "direct": False, "group": False})
        g = ("apps" if p["kind"] == "service" else "in-touch" if (s["direct"] or p["person_id"] in owners)
             else "same-groups" if s["group"] else "lists-only")
        updates.append((s["m"], s["c"], s["f"], s["l"], g, p["person_id"]))
    con.executemany("UPDATE persons SET n_messages=?, n_calls=?, first_ts=?, last_ts=?, group_kind=? WHERE person_id=?",
                    updates)


# ================================================================ money

_DEBIT_RE = re.compile(r"\b(debited|debit|spent|paid|sent|withdrawn|transferred)\b", re.I)
_CREDIT_RE = re.compile(r"\b(credited|credit|received|deposited)\b", re.I)
_REF_RE = re.compile(r"\b(?:upi\s*)?ref(?:erence)?(?:\s*no)?\.?\s*:?\s*([A-Z0-9]{6,})", re.I)
_PARTY_RE = re.compile(r"\b(?:to|from)\s+(?!a/?c\b|your\b|ac\b|account\b)([A-Za-z][A-Za-z .&'-]{1,40}?)"
                       r"(?=\s*(?:\.\s|\.$|,|\s+on\b|\s+upi\b|\s+ref\b|\s+via\b|\s+avl\b|$))", re.I)
_VPA_RE = re.compile(r"\b([\w.-]{2,}@[a-z]{2,})\b", re.I)
_METHOD_RE = re.compile(r"\b(UPI|IMPS|NEFT|RTGS|hawala|cash|angadia)\b", re.I)


def _method(body: str) -> str:
    m = _METHOD_RE.search(body or "")
    if not m:
        return ""
    w = m.group(1).lower()
    return {"upi": "UPI", "imps": "IMPS", "neft": "NEFT", "rtgs": "RTGS", "angadia": "hawala"}.get(w, w)


def bank_sms(body: str) -> dict | None:
    """'Rs 50,000.00 debited from A/c XX4471 … by UPI to RAJU VERMA. UPI Ref 624118930551.' -> the transfer."""
    if not body:
        return None
    deb, cre = _DEBIT_RE.search(body), _CREDIT_RE.search(body)
    if not deb and not cre:
        return None
    direction = "debit" if deb and (not cre or deb.start() < cre.start()) else "credit"
    amounts = [a for a in text.find_amounts(body) if a["explicit"]]
    if not amounts:
        return None
    party = None
    for m in _PARTY_RE.finditer(body):
        cand = m.group(1).strip(" .")
        if cand and not re.match(r"(?i)^(a/?c|ac|xx)", cand):
            party = cand
            break
    vpa = _VPA_RE.search(body)
    ref = _REF_RE.search(body)
    return {"amount": amounts[0]["value"], "direction": direction, "method": _method(body) or "UPI",
            "counterparty": party or (vpa.group(1) if vpa else ""),
            "counterparty_ident": ("upi:" + vpa.group(1).lower()) if vpa else "", "ref": ref.group(1) if ref else ""}


def chat_amounts(body: str) -> list[float]:
    """Money said in a chat: '50k', '1.2 lakh', and 'pachaas' or '25' only next to a money word."""
    out = []
    toks = [text.fold(t) for t in text.tokens(body)]
    raw_toks = [t.lower() for t in text.tokens(body)]
    money = {text.fold(w) for w in text.MONEY_WORDS} | set(text.MONEY_WORDS)
    for a in text.find_amounts(body):
        v = a["value"]
        if a["explicit"]:
            if v >= 10:
                out.append(v)
            continue
        if v < 10 or v > 1e9:
            continue
        word = text.fold(a["text"].split()[0]) if a["text"] else ""
        idx = next((i for i, t in enumerate(toks) if t == word or raw_toks[i] == a["text"].lower()), None)
        if idx is None:
            continue
        near = set(raw_toks[max(0, idx - 3): idx + 4]) | set(toks[max(0, idx - 3): idx + 4])
        if near & money:
            out.append(v)
    return out


def _money(con, sid, all_rows, conv_meta, owner_ids, job) -> int:
    titles = {r["conv_id"]: r["title"] for r in con.execute("SELECT conv_id, title FROM conversations WHERE source_id=?", (sid,))}
    names = {r["ident"]: r["name"] for r in con.execute(
        "SELECT i.ident, p.name FROM identifiers i JOIN persons p ON p.person_id=i.person_id")}
    out = []
    for i, r in enumerate(all_rows):
        if r["kind"] != "message" or not r["body"]:
            continue
        body = r["body"]
        if r["sender"] and text.is_sender_id(r["sender"]):
            b = bank_sms(body)
            if b:
                out.append((r["event_id"], sid, r["ts"], b["amount"], b["direction"], b["method"], b["counterparty"],
                            b["counterparty_ident"], b["ref"], 0))
            continue
        vals = chat_amounts(body)
        if not vals:
            continue
        other = r["sender"] if r["direction"] == "in" else next(iter(_jl(r["recipients"], [])), None)
        meta = conv_meta.get(r["conv_id"]) or {}
        party = titles.get(r["conv_id"]) if meta.get("is_group") else (names.get(other) or titles.get(r["conv_id"]) or other or "")
        for v in vals:
            out.append((r["event_id"], sid, r["ts"], v, "debit" if r["direction"] == "out" else "credit",
                        _method(body) or ("hawala" if "token" in body.lower() else ""), party or "", other or "", "", 1))
        if i % 5000 == 0:
            job.progress(i / max(1, len(all_rows)))
    con.executemany("INSERT INTO money(event_id, source_id, ts, amount, direction, method, counterparty, "
                    "counterparty_ident, ref, said_in_chat) VALUES(?,?,?,?,?,?,?,?,?,?)", out)
    return len(out)


# ================================================================ search index


def _index(con, all_rows, job) -> None:
    total = max(1, len(all_rows))
    for i in range(0, len(all_rows), BATCH):
        chunk = all_rows[i:i + BATCH]
        upd, fts, tri = [], [], []
        for r in chunk:
            words = " ".join(x for x in (r["body"], r["transcript"], r["ocr_text"], r["place"], r["media_name"]) if x)
            folded = text.fold_text(words)
            r["folded"] = folded
            upd.append((folded, r["event_id"]))
            fts.append((r["event_id"], words, folded))
            tri.append((r["event_id"], folded))
        con.executemany("UPDATE events SET folded=? WHERE event_id=?", upd)
        con.executemany("INSERT INTO events_fts(event_id, words, folded) VALUES(?,?,?)", fts)
        con.executemany("INSERT INTO events_tri(event_id, folded) VALUES(?,?)", tri)
        con.commit()
        job.progress((i + len(chunk)) / total)


# ================================================================ starting a job


def start_ingest(cid: str, path: Path, added_by: str, sample: str | None = None, delete_after: bool = False,
                 label: str | None = None) -> dict:
    return jobs.start(cid, "ingest", ingest_job, cid, str(path), added_by, sample, delete_after,
                      label=label or "Adding a phone", steps=STEPS)


def ensure_sample_case() -> str | None:
    """On first run: the sample case with the three made-up phones (adds any that are missing)."""
    with _sample_lock:
        if not _ensure_sample_files():
            print("[sample] the sample phones aren't there yet, so the sample case waits.", file=sys.stderr)
        try:
            creator = demo_officer_id()
        except Exception:
            creator = None
        db.create_case(SAMPLE_NAME, SAMPLE_ABOUT, SAMPLE_NUMBER, created_by=creator, case_id=SAMPLE_CID)
        with db.case_db(SAMPLE_CID) as con:
            have = {(_jl(r["device_info"], {}) or {}).get("sample") for r in
                    db.rows(con, "SELECT device_info FROM sources WHERE status != 'failed'")}
        for s in SAMPLES:
            if s in have or not _sample_path(s).exists():
                continue
            info = sample_info(s) or {}
            snap = start_ingest(SAMPLE_CID, _sample_path(s), "Arjun Rao", sample=s,
                                label=f"Adding {info.get('short_label') or s}")
            done = jobs.wait(snap["id"], timeout=1800)
            if done and done.get("status") == "failed":
                print(f"[sample] adding {s} failed: {done.get('error')}", file=sys.stderr)
        return SAMPLE_CID


# ================================================================ routes: cases


def _case_out(case: dict) -> dict:
    out = {k: case.get(k) for k in ("case_id", "name", "number", "about", "created_by", "created_at", "last_opened")}
    out.update({"phones": [], "records": 0, "reading": False, "is_sample": case.get("case_id") == SAMPLE_CID})
    if db.case_exists(case["case_id"]):
        try:
            with db.case_db(case["case_id"]) as con:
                srcs = db.rows(con, "SELECT label, status, n_events FROM sources ORDER BY phone_no")
        except Exception:
            srcs = []
        out["phones"] = [s["label"] for s in srcs if s["status"] != "failed"]
        out["records"] = sum(s["n_events"] or 0 for s in srcs if s["status"] == "done")
        out["reading"] = any(s["status"] == "reading" for s in srcs) or bool(jobs.find(case["case_id"], "ingest"))
    return out


@router.get("/api/cases")
def list_cases(officer: dict = Depends(require_officer)):
    return [_case_out(c) for c in db.list_cases(officer["officer_id"])]


def _clean(body: dict, key: str, limit: int) -> str | None:
    v = body.get(key)
    if v is None:
        return None
    return str(v).strip()[:limit]


@router.post("/api/cases")
def create_case(body: dict = Body(...), officer: dict = Depends(require_officer)):
    name = _clean(body, "name", 200) or ""
    about = _clean(body, "about", 4000) or ""
    number = _clean(body, "number", 100) or ""
    if not name:
        raise ApiError(400, "Give the case a name.")
    if not about:
        raise ApiError(400, "Say in a sentence or two what the case is about. The AI reads it to understand the case.")
    case = db.create_case(name, about, number, created_by=officer["officer_id"])
    audit.log(case["case_id"], officer, "case", f"Made the case '{name}'")
    return _case_out(case)


@router.patch("/api/cases/{cid}")
def edit_case(cid: str, body: dict = Body(...), acc: CaseAccess = Depends(require_case)):
    name, number, about = _clean(body, "name", 200), _clean(body, "number", 100), _clean(body, "about", 4000)
    if name is not None and not name:
        raise ApiError(400, "The case needs a name.")
    if about is not None and not about:
        raise ApiError(400, "Say in a sentence or two what the case is about.")
    case = db.update_case(cid, name=name, number=number, about=about)
    if not case:
        raise ApiError(404, "That case doesn't exist.")
    changed = [w for w, v in (("name", name), ("number", number), ("what it is about", about)) if v is not None]
    if changed:
        audit.log(cid, acc, "case", "Changed the case's " + ", ".join(changed))
    return _case_out(case)


# ================================================================ routes: samples and sources


@router.get("/api/samples")
def list_samples(cid: str = "", officer: dict = Depends(require_officer)):
    _ensure_sample_files()
    added = set()
    if cid and db.case_exists(cid):
        from ib.officers import can_access
        if can_access(officer["officer_id"], cid):
            with db.case_db(cid) as con:
                added = {(_jl(r["device_info"], {}) or {}).get("sample") for r in
                         db.rows(con, "SELECT device_info FROM sources WHERE status != 'failed'")}
    out = []
    for s in SAMPLES:
        info = sample_info(s)
        if info:
            out.append({**info, "added": s in added})
    return out


def _upload_from_request(raw: bytes, ctype: str) -> tuple[bytes, str]:
    if "multipart/form-data" in ctype:
        msg = BytesParser(policy=email_policy).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + raw)
        for part in msg.iter_parts():
            fname = part.get_filename()
            if fname or part.get_param("name", header="content-disposition") == "file":
                return part.get_payload(decode=True) or b"", fname or "upload.json"
        raise ApiError(400, "No file came with the request. Choose the phone's export file and try again.")
    return raw, "upload.json"


@router.post("/api/cases/{cid}/sources")
async def add_source(cid: str, request: Request, acc: CaseAccess = Depends(require_case)):
    raw = await request.body()
    if len(raw) > MAX_UPLOAD:
        raise ApiError(413, "That file is too big to add here (the limit is 300 MB).")
    ctype = request.headers.get("content-type", "")
    sample = None
    if "json" in ctype or not ctype:
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("sample"):
            sample = str(body["sample"])
            if sample not in SAMPLES:
                raise ApiError(404, "There is no sample phone by that name.")
            if not _ensure_sample_files() and not _sample_path(sample).exists():
                raise ApiError(503, "The sample phones are still being made. Try again in a minute.")
            info = sample_info(sample) or {}
            return {"job": start_ingest(cid, _sample_path(sample), acc.officer_name, sample=sample,
                                        label=f"Adding {info.get('short_label') or sample}")}
    data, fname = _upload_from_request(raw, ctype)
    if not data:
        raise ApiError(400, "That file is empty. Choose the phone's export file and try again.")
    load_export(data)  # say at once if it can't be read
    up = config.case_dir(cid) / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    path = up / (hashlib.sha256(data).hexdigest()[:16] + ".json")
    path.write_bytes(data)
    return {"job": start_ingest(cid, path, acc.officer_name, delete_after=True, label=f"Adding {fname}")}


def _source_out(con, s: dict) -> dict:
    info = _jl(s.pop("device_info", None), {}) or {}
    sid = s["source_id"]
    counts = {r["kind"]: r["n"] for r in con.execute(
        "SELECT kind, COUNT(*) n FROM events WHERE source_id=? GROUP BY kind", (sid,))}
    s.update({"fingerprint": s.get("sha256"), "counts": counts,
              "counts_words": [f"{text.group_indian(n)} {KIND_WORDS.get(k, k)}" for k, n in
                               sorted(counts.items(), key=lambda kv: -kv[1])],
              "first": text.fmt_date(s["first_ts"]) if s.get("first_ts") else "",
              "last": text.fmt_date(s["last_ts"]) if s.get("last_ts") else "",
              "added": text.fmt_when(s["added_at"]) if s.get("added_at") else "",
              "number": (info.get("owner_numbers") or [""])[0], "sample": info.get("sample"),
              "short_label": s["label"].split("|", 1)[-1].strip() if s.get("label") else ""})
    return s


@router.get("/api/cases/{cid}/sources")
def list_sources(cid: str, acc: CaseAccess = Depends(require_case)):
    with db.case_db(cid) as con:
        srcs = db.rows(con, "SELECT * FROM sources WHERE status != 'failed' ORDER BY phone_no")
        out = [_source_out(con, s) for s in srcs]
    running = [j for j in jobs.for_case(cid) if j["kind"] == "ingest" and j["status"] in ("waiting", "running")]
    for s in out:
        s["job"] = running[0] if (s["status"] == "reading" and running) else None
    return out


@router.get("/api/cases/{cid}/phone/{source_id}")
def phone_details(cid: str, source_id: int, acc: CaseAccess = Depends(require_case)):
    with db.case_db(cid) as con:
        s = db.one(con, "SELECT * FROM sources WHERE source_id=?", (source_id,))
        if not s:
            raise ApiError(404, "That phone isn't in this case.")
        info = _jl(s.get("device_info"), {}) or {}
        out = _source_out(con, s)
        by_app = db.rows(con, "SELECT app, kind, COUNT(*) n FROM events WHERE source_id=? GROUP BY app, kind "
                              "ORDER BY n DESC", (source_id,))
        deleted = db.scalar(con, "SELECT COUNT(*) FROM events WHERE source_id=? AND status='deleted'", (source_id,), 0)
        n_chats = db.scalar(con, "SELECT COUNT(*) FROM conversations WHERE source_id=?", (source_id,), 0)
        owner = None
        if s.get("owner_person_id"):
            owner = db.one(con, "SELECT person_id, name FROM persons WHERE person_id=?", (s["owner_person_id"],))
    details = [("Owner", info.get("owner_name")), ("Phone", info.get("model")), ("Software", info.get("os")),
               ("Kind of export", {"iphone-backup": "iPhone backup", "android-backup": "Android backup",
                                   "ufdr-report": "Phone reader report"}.get(info.get("platform"), info.get("platform"))),
               ("IMEI", info.get("imei")), ("File added", out.get("file_name")), ("Fingerprint", out.get("sha256")),
               ("Added", out.get("added") + (f" by {out.get('added_by')}" if out.get("added_by") else ""))]
    out.update({"device_info": info, "owner": owner, "by_app": by_app, "deleted": deleted, "chats": n_chats,
                "sims": info.get("sims") or [], "accounts": info.get("accounts") or [], "wifi": info.get("wifi") or [],
                "apps": info.get("apps") or [],
                "details": [{"label": k, "value": v} for k, v in details if v]})
    return out
