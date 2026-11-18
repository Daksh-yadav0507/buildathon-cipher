"""Smoke test: the whole server as one piece, on the three made-up sample phones, with no AI.

    .venv/bin/python -m pytest -q tests/test_smoke.py      (if pytest is installed)
    .venv/bin/python tests/test_smoke.py                   (plain Python, no extra packages)

It uses a temporary data folder, runs background jobs inline and never calls an AI.
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_TMP = tempfile.mkdtemp(prefix="ib-smoke-")
os.environ["IB_DATA_DIR"] = _TMP
os.environ["IB_SYNC_JOBS"] = "1"
os.environ["IB_NO_AI"] = "1"
os.environ["IB_NO_SAMPLE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

import ib.api as api  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
_state: dict = {}


def _ist_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, IST).strftime("%Y-%m-%d")


def client() -> TestClient:
    if "c" not in _state:
        c = TestClient(api.app, raise_server_exceptions=False)
        c.__enter__()
        _state["c"] = c
    return _state["c"]


def login(c: TestClient) -> None:
    r = c.post("/api/auth/login", json={"name": "Arjun Rao", "password": "demo"})
    assert r.status_code == 200, r.text


def case() -> str:
    """A new case with phone1, phone2 and phone3 added (jobs run inline)."""
    if "cid" in _state:
        return _state["cid"]
    c = client()
    login(c)
    r = c.post("/api/cases", json={"name": "Smoke test", "number": "T-1", "about": "A made-up practice case."})
    assert r.status_code == 200, r.text
    cid = r.json()["case_id"]
    for s in ("phone1", "phone2", "phone3"):
        r = c.post(f"/api/cases/{cid}/sources", json={"sample": s})
        assert r.status_code == 200, r.text
    _state["cid"] = cid
    return cid


def B() -> str:
    return f"/api/cases/{case()}"


# ---------------------------------------------------------------- 1. health and login

def test_1_health_and_login():
    c = client()
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["app"] == "insights-buddy"
    bad = c.post("/api/auth/login", json={"name": "Arjun Rao", "password": "wrong"})
    assert bad.status_code == 401
    msg = bad.json().get("error", "")
    assert msg and msg.endswith(".") and "Traceback" not in msg
    login(c)
    assert c.get("/api/me").json()["name"] == "Arjun Rao"


# ---------------------------------------------------------------- 2. three phones read

def test_2_phones_and_stats():
    c = client()
    src = c.get(B() + "/sources").json()
    assert len(src) == 3 and all(s["status"] == "done" for s in src), src
    st = c.get(B() + "/stats").json()
    assert 19_000 <= st["records"] <= 21_000, st["records"]
    assert len(st["phones"]) == 3
    assert st["deleted"] > 0


# ---------------------------------------------------------------- 3. search

def test_3_search():
    c = client()
    r = c.get(B() + "/search", params={"q": "paisa"}).json()
    assert r["total"] > 0
    how = r["how"].lower()
    assert "paisa" in how and "pese" in how, r["how"]
    dev = c.get(B() + "/search", params={"q": "पैसे"}).json()
    assert dev["total"] > 0 and "paisa" in dev["how"].lower(), dev["how"]
    num = c.get(B() + "/search", params={"q": "9899512640"}).json()
    assert num["total"] > 0
    assert any(h["event_id"].startswith("P2-") for h in num["hits"])


# ---------------------------------------------------------------- 4. ask, no AI

def test_4_ask_money():
    c = client()
    a = c.post(B() + "/ask", json={"question": "paisa kisne kisko bheja?"}).json()
    lines = a["lines"]
    assert lines and all(ln["records"] for ln in lines), lines
    hit = [ln for ln in lines if any(x.startswith("P1-") for x in ln["records"])
           and any(x.startswith("P2-") for x in ln["records"]) and "50,000" in ln["text"]]
    assert hit, [ln["text"] for ln in lines]


# ---------------------------------------------------------------- 5. across phones

def test_5_across():
    c = client()
    x = c.get(B() + "/across").json()
    pn = lambda p: (p or {}).get("phone_no")  # noqa: E731
    money = [m for m in x["money"] if abs((m.get("amount") or 0) - 50000) < 1
             and {pn(m.get("from_phone")), pn(m.get("to_phone"))} == {1, 2}
             and abs(m["credit"]["ts"] - m["debit"]["ts"]) < 5 * 60_000]
    assert money, "no 50,000 match between phone 1 and phone 2"
    calls = [k for k in x["calls"] if k.get("kind") == "missing" and pn(k.get("on_phone")) == 1
             and pn(k.get("missing_on")) == 2 and k.get("day") == "2026-09-16"]
    assert calls, "no call missing from phone 2's log on 16 Sep"
    tog = [t for t in x["together"] if t.get("day") == "2026-09-15" and "airport" in (t.get("place") or "").lower()]
    assert tog, "no together event at the airport on 15 Sep"
    img = [f for f in x["files"] if f.get("name") == "IMG_4471.jpg"
           and {1, 3} <= {pn(p) for p in f.get("phones", [])}]
    assert img, "IMG_4471.jpg not found on phones 1 and 3"
    saved = {s.get("saved_as") for n in x["names"] for s in n.get("saved", [])}
    assert {"Raju Flight", "Vikram Sir"} <= saved, saved


# ---------------------------------------------------------------- 6. key questions

def test_6_key_questions():
    c = client()
    k = c.get(B() + "/key-questions").json()
    used = {lst["name"]: lst["used"] for lst in k["lists"]}
    assert used.get("Every phone") is True, used
    assert used.get("Goods and gold smuggling") is True, used
    assert used.get("Drugs") is False, used


# ---------------------------------------------------------------- 7. findings and export

def test_7_findings_and_export():
    c = client()
    r = c.post(B() + "/findings", json={"event_id": "P1-000016", "note": "Smoke test note", "tags": ["money"]})
    assert r.status_code == 200, r.text
    f = r.json()
    fid = f.get("finding_id") or f.get("id") or (f.get("finding") or {}).get("finding_id")
    assert fid, f
    rows = c.get(B() + "/findings").json()["rows"]
    assert any((x.get("finding_id") or x.get("id")) == fid for x in rows)
    assert c.delete(B() + f"/findings/{fid}").status_code == 200
    rows = c.get(B() + "/findings").json()["rows"]
    assert not any((x.get("finding_id") or x.get("id")) == fid for x in rows)

    params = {"page": "timeline", "format": "csv", "kind": "call", "app": "phone"}
    ex = c.get(B() + "/export", params=params)
    assert ex.status_code == 200, ex.text
    body = ex.content.decode("utf-8-sig")
    lines = list(csv.reader(io.StringIO(body)))
    data = [ln for ln in lines[1:] if ln and not ln[0].startswith("#")]
    assert lines[0] and len(lines[0]) > 2, lines[:2]
    tl = c.get(B() + "/timeline", params={"kind": "call", "app": "phone"}).json()
    assert len(data) == tl["total"], (len(data), tl["total"])


# ---------------------------------------------------------------- 8. warrant limit

def test_8_warrant_limit():
    c = client()
    before = c.get(B() + "/search", params={"q": "paisa"}).json()["total"]
    r = c.post(B() + "/limit", json={"from": "2026-09-01", "to": "2026-09-30", "apps": ["whatsapp"], "people": []})
    assert r.status_code == 200, r.text
    try:
        lim = c.get(B() + "/search", params={"q": "paisa"}).json()
        assert 0 < lim["total"] < before, (lim["total"], before)
        for h in lim["hits"]:
            assert h["app"] == "whatsapp", h
            assert "2026-09-01" <= _ist_day(h["ts"]) <= "2026-09-30", h
    finally:
        assert c.post(B() + "/limit", json={}).status_code == 200
    assert c.get(B() + "/search", params={"q": "paisa"}).json()["total"] == before


# ---------------------------------------------------------------- 9. every route without a 500

def test_9_no_500():
    c = client()
    b = B()
    conv = (c.get(b + "/chats").json().get("rows") or [{}])[0].get("conv_id", 1)
    calls = [
        ("GET", "/api/health", None), ("GET", "/api/me", None), ("GET", "/api/prefs", None),
        ("POST", "/api/prefs", {"theme": "dark", "textsize": "normal"}),
        ("GET", "/api/cases", None), ("PATCH", b, {"about": "A made-up practice case, edited."}),
        ("GET", "/api/samples", None), ("GET", b + "/sources", None), ("GET", b + "/jobs", None),
        ("GET", b + "/stats", None), ("GET", b + "/activity", None), ("GET", b + "/story", None),
        ("GET", b + "/search?q=biscuit&mode=exact", None), ("GET", b + "/search?q=bisket&mode=fuzzy", None),
        ("GET", b + "/search?q=gold&mode=meaning", None),
        ("GET", b + "/search?q=paisa&app=whatsapp&kind=message&status=deleted&phone=1&from=2026-09-01&to=2026-09-30",
         None),
        ("GET", b + "/quickfind?q=raju", None), ("GET", b + "/chats", None), ("GET", b + f"/chats/{conv}", None),
        ("GET", b + f"/chats/{conv}?find=paisa&both=1", None),
        ("GET", b + "/calls", None), ("GET", b + "/calls?type=missed", None),
        ("GET", b + "/timeline?money=1&order=asc", None),
        ("GET", b + "/people", None), ("GET", b + "/people?group=same-groups", None),
        ("GET", b + "/people?group=lists-only", None), ("GET", b + "/people?group=apps", None),
        ("GET", b + "/people/1", None), ("GET", b + "/places", None), ("GET", b + "/places?day=2026-09-15", None),
        ("GET", b + "/media?kind=photo", None), ("GET", b + "/media?kind=voice", None),
        ("GET", b + "/media?kind=document", None), ("POST", b + "/media/read", {"kind": "voice"}),
        ("GET", b + "/records/P1-000001", None),
        ("POST", b + "/ask", {"question": "16 Sep ko kya hua?", "depth": "quick"}),
        ("POST", b + "/ask", {"question": "kaunse message delete kiye?", "depth": "auto"}),
        ("GET", b + "/ask/estimate?depth=deep", None), ("GET", b + "/asks", None),
        ("GET", b + "/brief", None), ("POST", b + "/brief", {}),
        ("GET", b + "/key-questions", None), ("POST", b + "/key-questions/run", {}),
        ("POST", b + "/key-questions/use", {"list_id": "drugs", "use": False}),
        ("GET", "/api/question-lists", None),
        ("GET", b + "/across", None), ("GET", b + "/codes", None),
        ("POST", b + "/codes", {"word": "biscuit", "meaning": "gold bar", "status": "confirmed"}),
        ("GET", b + "/findings", None), ("GET", b + "/audit", None), ("GET", b + "/limit", None),
        ("GET", b + "/phone/1", None),
        ("GET", b + "/export?page=search&format=csv&q=paisa", None),
        ("GET", b + "/export?page=chats&format=html", None), ("GET", b + "/export?page=calls&format=xlsx", None),
        ("GET", b + "/export?page=people&format=csv", None), ("GET", b + "/export?page=findings&format=csv", None),
        ("GET", b + "/export?page=media&format=csv", None),
        ("GET", b + "/records/P9-999999", None), ("GET", b + "/people/999999", None),
        ("GET", "/api/cases/no-such-case/stats", None),
    ]
    bad = []
    for m, u, body in calls:
        r = c.request(m, u, json=body) if body is not None else c.request(m, u)
        if r.status_code >= 500:
            bad.append((m, u, r.status_code, r.text[:200]))
    lst = c.post("/api/question-lists", json={"name": "Smoke list", "when": "never", "questions": ["Who?"]})
    if lst.status_code >= 500:
        bad.append(("POST", "/api/question-lists", lst.status_code, lst.text[:200]))
    elif lst.status_code == 200:
        d = c.delete(f"/api/question-lists/{lst.json()['id']}")
        if d.status_code >= 500:
            bad.append(("DELETE", "/api/question-lists", d.status_code, d.text[:200]))
    assert c.get(b + "/stats").status_code == 200
    assert not bad, bad
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get(b + "/stats").status_code == 401
    login(c)


def teardown_module(_m=None):
    c = _state.pop("c", None)
    if c is not None:
        c.__exit__(None, None, None)
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    failed = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {str(exc)[:600]}")
    teardown_module()
    print(f"{len(tests) - failed} of {len(tests)} passed")
    sys.exit(1 if failed else 0)
