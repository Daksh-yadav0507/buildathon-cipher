"""Saved dashboard answers (section 5.4): worked out once per case version and kept in the `ready` table.

    value, updating = ready.get(cid, "stats", compute)      # compute(con) -> a JSON-able value

* The saved value is used while its `made_from` matches the case version.
* When it is out of date, only one thread per (case, piece) works it out again. Every other request
  gets the last saved value straight away with updating=True ("Updating these numbers...").
* A request never waits more than WAIT_S seconds when an older saved answer exists.
* While a warrant limit is on, saved answers are never read or written: the value is worked out fresh.
* ready.warm(cid) starts every registered piece in the background (call it after a phone is added).
"""
from __future__ import annotations

import json
import logging
import threading
import time

from ib import ApiError, db, limits

log = logging.getLogger("ib.ready")

WAIT_S = 2.0          # most a request waits when an older answer can be shown
FIRST_WAIT_S = 120.0  # most a request waits when there is no answer at all yet

_guard = threading.Lock()
_running: dict[tuple[str, str], "_Run"] = {}
_pieces: dict[str, object] = {}


class _Run:
    def __init__(self):
        self.done = threading.Event()
        self.value = None
        self.error: BaseException | None = None


def register(name: str, compute) -> None:
    """Name a piece so warm() can work it out in the background."""
    _pieces[name] = compute


def _saved(con, name: str):
    r = db.one(con, "SELECT made_from, value FROM ready WHERE name=?", [name])
    if not r:
        return None, None
    try:
        return r["made_from"], json.loads(r["value"])
    except (TypeError, ValueError):
        return None, None


def _work(cid: str, name: str, compute, run: _Run) -> None:
    try:
        con = db.open_case(cid)
        try:
            ver = db.case_version(con)
            value = compute(con)
            value = json.loads(json.dumps(value, ensure_ascii=False))
            if limits.get_limit(con) is None and db.case_version(con) == ver:
                con.execute("INSERT INTO ready(name, made_from, value, made_at) VALUES(?,?,?,?) "
                            "ON CONFLICT(name) DO UPDATE SET made_from=excluded.made_from, "
                            "value=excluded.value, made_at=excluded.made_at",
                            [name, str(ver), json.dumps(value, ensure_ascii=False), db.now_ms()])
                con.commit()
        finally:
            con.close()
        run.value = value
    except BaseException as e:  # noqa: BLE001 - handed to the waiting requests
        log.exception("Working out %s for case %s failed", name, cid)
        run.error = e
    finally:
        with _guard:
            if _running.get((cid, name)) is run:
                _running.pop((cid, name), None)
        run.done.set()


def _start(cid: str, name: str, compute) -> _Run:
    key = (cid, name)
    with _guard:
        run = _running.get(key)
        if run is None:
            run = _Run()
            _running[key] = run
            threading.Thread(target=_work, args=(cid, name, compute, run), daemon=True,
                             name=f"ready-{cid}-{name}").start()
    return run


def get(cid: str, name: str, compute, wait_s: float = WAIT_S):
    """(value, updating). compute(con) gets an open case connection and returns a JSON-able value."""
    with db.case_db(cid) as con:
        if limits.get_limit(con) is not None:
            return compute(con), False
        ver = str(db.case_version(con))
        made_from, old = _saved(con, name)
    if made_from == ver and old is not None:
        return old, False
    run = _start(cid, name, compute)
    run.done.wait(wait_s if old is not None else FIRST_WAIT_S)
    if run.done.is_set():
        if run.error is None:
            return run.value, False
        if old is not None:
            return old, True
        if isinstance(run.error, ApiError):
            raise run.error
        raise ApiError(500, "These numbers could not be worked out. Try again in a moment.")
    if old is not None:
        return old, True
    raise ApiError(503, "These numbers are still being worked out. Try again in a moment.")


def with_updating(value, updating: bool):
    """A dict value with "updating" set (a copy: saved values are shared between requests)."""
    out = dict(value) if isinstance(value, dict) else {"value": value}
    out["updating"] = bool(updating)
    return out


def warm(cid: str, names=None) -> None:
    """Start working out the registered pieces (all of them, or `names`) in the background."""
    for name in names or list(_pieces):
        compute = _pieces.get(name)
        if compute is not None:
            _start(cid, name, compute)


def clear(cid: str, name: str | None = None) -> None:
    """Forget saved answers (one piece, or all of them) so they are worked out again."""
    with db.case_db(cid) as con:
        if name:
            con.execute("DELETE FROM ready WHERE name=?", [name])
        else:
            con.execute("DELETE FROM ready")


def busy(cid: str) -> list[str]:
    """The pieces being worked out for a case right now."""
    with _guard:
        return [n for (c, n) in _running if c == cid]


def wait_idle(cid: str, timeout: float = 30.0) -> bool:
    """For tests: wait until no piece of this case is being worked out."""
    end = time.time() + timeout
    while time.time() < end:
        if not busy(cid):
            return True
        time.sleep(0.05)
    return False
