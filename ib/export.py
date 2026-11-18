"""Export (section 10.5): what a page lists, with its filters and the warrant limit, as CSV, a spreadsheet
(only if openpyxl is installed) or a printable page with a fingerprint of its content.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ib import ApiError, audit, db, limits, text
from ib.officers import CaseAccess, require_case

router = APIRouter()

MAX_ROWS = 20000
PAGES = {"search": "Search", "timeline": "Timeline", "chats": "Chats", "calls": "Calls", "people": "People",
         "findings": "Findings", "media": "Media"}
FORMAT_WORDS = {"csv": "a CSV file", "xlsx": "a spreadsheet", "html": "a printable page"}
RECORD_COLS = ["Record ID", "India time", "Phone", "App", "Kind", "From", "To", "Text", "Status", "Origin"]


# ------------------------------------------------------------------ filters

def _filters(con, f: dict) -> tuple[str, list]:
    """The page's filters on events e, always inside the warrant limit."""
    try:
        from ib import search
        return search._filters(con, app=f.get("app", ""), kind=f.get("kind", ""), person=f.get("person", ""),
                               phone=f.get("phone", ""), start=f.get("from", ""), stop=f.get("to", ""),
                               status=f.get("status", ""), money=f.get("money", ""))
    except Exception:
        w, p = limits.where(con, "e")
        parts, params = [w], list(p)
        if f.get("app"):
            parts.append("e.app = ?")
            params.append(f["app"])
        if f.get("kind"):
            parts.append("e.kind = ?")
            params.append(f["kind"])
        if f.get("status"):
            parts.append("e.status = ?")
            params.append(f["status"])
        try:
            if f.get("from"):
                parts.append("e.ts >= ?")
                params.append(text.day_range(f["from"])[0])
            if f.get("to"):
                parts.append("e.ts < ?")
                params.append(text.day_range(f["to"])[1])
        except Exception:
            pass
        return " AND ".join(parts), params


def _filter_words(con, page: str, f: dict) -> str:
    bits = []
    if f.get("q"):
        bits.append(f"words '{f['q']}'")
    if f.get("app"):
        bits.append(f"app {f['app']}")
    if f.get("kind"):
        bits.append(f"kind {f['kind']}")
    if f.get("type") and f["type"] != "all":
        bits.append({"in": "incoming calls", "out": "outgoing calls", "missed": "missed calls"}.get(f["type"], f["type"]))
    if f.get("status"):
        bits.append(f"status {f['status']}")
    if str(f.get("person") or "").isdigit():
        name = db.scalar(con, "SELECT name FROM persons WHERE person_id = ?", [int(f["person"])], default=None)
        bits.append(f"person {name or f['person']}")
    if f.get("phone"):
        bits.append(f"Phone {f['phone']}")
    if f.get("from") or f.get("to"):
        bits.append(f"from {f.get('from') or 'the start'} to {f.get('to') or 'the end'}")
    if f.get("conv"):
        title = db.scalar(con, "SELECT title FROM conversations WHERE conv_id = ?", [f["conv"]], default=None)
        bits.append(f"the chat {title or f['conv']}")
    if f.get("tag"):
        bits.append(f"tag {f['tag']}")
    if str(f.get("money") or "") in ("1", "true", "yes"):
        bits.append("money only")
    return "; ".join(bits) if bits else "No filters: everything the page lists."


# ------------------------------------------------------------------ rows

class _Names:
    def __init__(self, con):
        rows = db.rows(con, "SELECT i.ident, i.display, p.name FROM identifiers i LEFT JOIN persons p ON p.person_id = i.person_id")
        self.by = {r["ident"]: r.get("name") or r.get("display") or r["ident"] for r in rows}
        self.owner = {r["source_id"]: r.get("owner_name") or "" for r in db.rows(con, "SELECT source_id, owner_name FROM sources")}

    def of(self, ident) -> str:
        return self.by.get(ident, ident) if ident else ""


def _origin(v) -> str:
    try:
        o = json.loads(v) if isinstance(v, str) else (v or {})
        if isinstance(o, dict):
            return ", ".join(f"{k} {o[k]}" for k in ("file", "table", "row") if o.get(k) not in (None, ""))
    except Exception:
        pass
    return str(v or "")


def _record_line(r: dict, names: _Names) -> list:
    owner = names.owner.get(r.get("source_id"), "")
    try:
        rec = json.loads(r.get("recipients") or "[]")
    except Exception:
        rec = []
    to = ", ".join(names.of(x) for x in rec if x) if isinstance(rec, list) else ""
    frm = names.of(r.get("sender"))
    if r.get("direction") == "out":
        frm = frm or owner
    elif r.get("direction") == "in":
        to = to or owner
    body = r.get("body") or ""
    extra = [x for x in (r.get("transcript"), r.get("ocr_text")) if x]
    if r.get("kind") == "call":
        body = body or (f"Call, {text.duration_words(r['duration_s'])}" if r.get("duration_s") else "Call")
    if r.get("media_name"):
        body = (body + " " if body else "") + f"[{r['media_name']}]"
    if r.get("place") and not body:
        body = r["place"]
    if extra:
        body = (body + " " if body else "") + " ".join(extra)
    return [r["event_id"], text.fmt_when(r["ts"]) if r.get("ts") is not None else "", r.get("phone_label") or "",
            r.get("app") or "", r.get("kind") or "", frm, to, body, r.get("status") or "", _origin(r.get("origin"))]


SELECT = """SELECT e.*, s.label AS phone_label FROM events e LEFT JOIN sources s ON s.source_id = e.source_id"""


def _events_by_ids(con, eids: list[str]) -> list[dict]:
    w, p = limits.where(con, "e")
    out: dict[str, dict] = {}
    for i in range(0, len(eids), 500):
        part = eids[i:i + 500]
        for r in db.rows(con, f"{SELECT} WHERE {w} AND e.event_id IN ({','.join('?' * len(part))})", [*p, *part]):
            out[r["event_id"]] = r
    return [out[e] for e in eids if e in out]


def _rows(con, page: str, f: dict) -> tuple[list[str], list[list]]:
    names = _Names(con)
    if page == "findings":
        from ib import findings
        rows = findings.list_findings(con, f.get("tag", ""))
        recs = {r["event_id"]: r for r in _events_by_ids(con, [x["event_id"] for x in rows if x.get("event_id")])}
        out = []
        for x in rows:
            rec = recs.get(x.get("event_id"))
            line = _record_line(rec, names) if rec else [x.get("event_id") or "", "", "", "", "answer" if x.get("ask_id") else "", "", "", x.get("title") or "", "", ""]
            out.append(line + [x.get("note") or "", ", ".join(x.get("tags") or []), x.get("officer") or "",
                               text.fmt_when(x["created_at"]) if x.get("created_at") else ""])
        return RECORD_COLS + ["Note", "Tags", "Saved by", "Saved at"], out
    if page == "people":
        w, p = limits.where(con, "e")
        people = db.rows(con, "SELECT person_id, name, kind, group_kind, n_messages, n_calls, first_ts, last_ts FROM persons "
                              "ORDER BY n_messages + n_calls DESC, name")
        ids = {}
        for r in db.rows(con, "SELECT person_id, display, ident FROM identifiers WHERE person_id IS NOT NULL"):
            ids.setdefault(r["person_id"], []).append(r.get("display") or r["ident"])
        limited = limits.get_limit(con) is not None
        if limited:  # only people who appear in records inside the warrant limit
            seen = set()
            for snd, rec in con.execute(f"SELECT e.sender, e.recipients FROM events e WHERE {w}", p):
                if snd:
                    seen.add(snd)
                try:
                    seen.update(x for x in json.loads(rec or "[]") if isinstance(x, str))
                except Exception:
                    pass
            pids = {r["person_id"] for r in db.rows(con, "SELECT ident, person_id FROM identifiers") if r["ident"] in seen}
            people = [x for x in people if x["person_id"] in pids]
        if f.get("group"):
            people = [x for x in people if x.get("group_kind") == f["group"]]
        q = text.fold_text(f.get("q") or "")
        if q:
            people = [x for x in people if q in text.fold_text(x.get("name") or "") or
                      any(q in text.fold_text(i) for i in ids.get(x["person_id"], []))]
        out = [[x["person_id"], x.get("name") or "", x.get("kind") or "", "; ".join(ids.get(x["person_id"], [])),
                x.get("n_messages") or 0, x.get("n_calls") or 0,
                text.fmt_when(x["first_ts"]) if x.get("first_ts") else "", text.fmt_when(x["last_ts"]) if x.get("last_ts") else ""]
               for x in people[:MAX_ROWS]]
        return ["Person ID", "Name", "Kind", "Numbers and IDs", "Messages", "Calls", "First seen", "Last seen"], out
    if page == "search":
        eids: list[str] = []
        try:
            from ib import search
            res = search.run_search(con, f.get("q", ""), f.get("mode", "auto"), 0, MAX_ROWS,
                                    app=f.get("app", ""), kind=f.get("kind", ""), person=f.get("person", ""),
                                    phone=f.get("phone", ""), start=f.get("from", ""), stop=f.get("to", ""),
                                    status=f.get("status", ""), money=f.get("money", ""))
            eids = [h["event_id"] for h in res.get("hits", []) if h.get("event_id")]
        except ApiError:
            raise
        except Exception:
            w, p = _filters(con, f)
            words = text.content_words(f.get("q", ""))
            if words:
                eids = [r[0] for r in con.execute(
                    f"SELECT e.event_id FROM events e WHERE {w} AND e.event_id IN (SELECT event_id FROM events_fts "
                    f"WHERE events_fts MATCH ?) ORDER BY e.ts DESC LIMIT {MAX_ROWS}", [*p, text.fts_query(words, column='folded')])]
        return RECORD_COLS, [_record_line(r, names) for r in _events_by_ids(con, eids)]
    w, p = _filters(con, f)
    extra, params = [], []
    if page == "calls":
        extra.append("e.kind = 'call'")
        t = (f.get("type") or "all").lower()
        if t in ("in", "out"):
            extra.append("e.direction = ? AND COALESCE(e.status, '') NOT IN ('missed', 'rejected')")
            params.append(t)
        elif t == "missed":
            extra.append("e.status IN ('missed', 'rejected')")
    elif page == "chats":
        if str(f.get("conv") or "").isdigit():
            extra.append("e.conv_id = ?")
            params.append(int(f["conv"]))
        else:
            extra.append("e.conv_id IS NOT NULL")
    elif page == "media":
        kinds = {"photo", "video", "voice", "document"}
        k = f.get("kind") if f.get("kind") in kinds else None
        extra.append("e.kind = ?" if k else "e.kind IN ('photo', 'video', 'voice', 'document')")
        if k:
            params.append(k)
    sql = " AND ".join([w] + extra)
    order = "ASC" if (page == "chats" and f.get("conv")) or f.get("order") == "asc" else "DESC"
    rows = db.rows(con, f"{SELECT} WHERE {sql} ORDER BY e.ts {order} LIMIT {MAX_ROWS}", [*p, *params])
    return RECORD_COLS, [_record_line(r, names) for r in rows]


# ------------------------------------------------------------------ formats

def _csv(cols, rows) -> bytes:
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(cols)
    for r in rows:
        wr.writerow(["" if v is None else v for v in r])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _xlsx(cols, rows, title: str) -> bytes | None:
    try:
        import openpyxl
    except Exception:
        return None
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:30] or "Export"
    ws.append(cols)
    for r in rows:
        ws.append(["" if v is None else v for v in r])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def fingerprint(cols, rows) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(cols, ensure_ascii=False).encode("utf-8"))
    for r in rows:
        h.update(b"\n" + json.dumps(["" if v is None else str(v) for v in r], ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


def _html(cols, rows, case: dict, page_name: str, officer: str, filters: str, banner: str | None) -> bytes:
    e = text.esc
    now = text.fmt_when(db.now_ms())
    head = "".join(f"<th>{e(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{e('' if v is None else str(v))}</td>" for v in r) + "</tr>" for r in rows)
    title = f"{case.get('name') or 'Case'}: {page_name}"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(title)}</title>
<style>
body{{font:13px/1.45 system-ui,-apple-system,"Segoe UI",Arial,sans-serif;color:#111;background:#fff;margin:24px}}
h1{{font-size:20px;margin:0 0 4px}} .meta{{color:#444;margin:2px 0}} .limit{{border:1px solid #b45309;color:#7c2d12;
padding:6px 10px;margin:10px 0;border-radius:4px}} table{{border-collapse:collapse;width:100%;margin-top:14px}}
th,td{{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top}} th{{background:#f2f2f2}}
td{{word-break:break-word}} .fp{{margin-top:18px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}}
@media print{{body{{margin:10mm}} th{{background:#eee}} tr{{page-break-inside:avoid}}}}
</style></head><body>
<h1>{e(title)}</h1>
<p class="meta">Case number: {e(case.get('number') or 'not given')}</p>
<p class="meta">Exported by {e(officer)} on {e(now)} (India time) from Insights Buddy, on this computer only.</p>
<p class="meta">Filters: {e(filters)}</p>
{f'<p class="limit">Warrant limit: {e(banner)}</p>' if banner else '<p class="meta">Warrant limit: none.</p>'}
<p class="meta">{e(text.plural(len(rows), 'row', 'rows'))}{' (the first ' + str(MAX_ROWS) + ' only)' if len(rows) >= MAX_ROWS else ''}.</p>
<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
<p class="fp">Fingerprint of this export's content: {fingerprint(cols, rows)}</p>
</body></html>"""
    return page.encode("utf-8")


@router.get("/api/cases/{cid}/export")
def export(cid: str, page: str = "timeline", format: str = "csv", q: str = "", mode: str = "auto", app: str = "",
           kind: str = "", person: str = "", phone: str = "", status: str = "", money: str = "", type: str = "",
           conv: str = "", tag: str = "", group: str = "", order: str = "",
           date_from: str = Query("", alias="from"), date_to: str = Query("", alias="to"),
           acc: CaseAccess = Depends(require_case)):
    page = (page or "timeline").strip().lower()
    fmt = (format or "csv").strip().lower()
    if page not in PAGES:
        raise ApiError(400, "This page can't be exported.")
    if fmt not in FORMAT_WORDS:
        raise ApiError(400, "Choose CSV, a spreadsheet or a printable page.")
    f = {"q": q, "mode": mode, "app": app, "kind": kind, "person": person, "phone": phone, "status": status,
         "money": money, "type": type, "conv": conv, "tag": tag, "group": group, "order": order,
         "from": date_from, "to": date_to}
    f = {k: str(v).strip() for k, v in f.items() if str(v or "").strip()}
    if page == "search" and not f.get("q"):
        raise ApiError(400, "Search for something first, then export the results.")
    with db.case_db(cid) as con:
        cols, rows = _rows(con, page, f)
        words = _filter_words(con, page, f)
        banner = limits.banner_text(con)
    case = acc.case or db.get_case(cid) or {}
    name = PAGES[page]
    stamp = text.ist_day(db.now_ms())
    base = f"{(case.get('name') or cid)} {name} {stamp}"
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in base).strip().replace(" ", "-")[:80] or "export"
    if fmt == "xlsx":
        data = _xlsx(cols, rows, name)
        if data is None:
            fmt, data = "csv", _csv(cols, rows)
            media = "text/csv; charset=utf-8"
        else:
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif fmt == "html":
        data, media = _html(cols, rows, case, name, acc.officer_name, words, banner), "text/html; charset=utf-8"
    else:
        data, media = _csv(cols, rows), "text/csv; charset=utf-8"
    audit.log(cid, acc, "export", f"Exported {name} as {FORMAT_WORDS[fmt]} ({text.plural(len(rows), 'row', 'rows')})")
    disp = "inline" if fmt == "html" else "attachment"
    fname = f"{safe}.{fmt}"
    return Response(content=data, media_type=media, headers={
        "Content-Disposition": f"{disp}; filename=\"{fname}\"; filename*=UTF-8''{quote(fname)}",
        "X-Export-Rows": str(len(rows)), "X-Export-Fingerprint": fingerprint(cols, rows)})
