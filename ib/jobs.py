"""Background jobs (section 5.2): steps, progress and an honest time left. Two run at a time.

    def work(job, sample):
        job.step("Reading chats"); job.progress(0.5)
        return {"source_id": 2}
    snap = jobs.start(cid, "ingest", work, "phone2", label="Adding Phone 2", steps=7)

Time left is given only after the current step has run for 5 seconds, from that step's own rate.
"""
from __future__ import annotations

import queue
import sys
import threading
import time
import traceback
import uuid

from fastapi import APIRouter, Depends, Request

from ib import ApiError, config, db
from ib.officers import CaseAccess, can_access, require_case, require_officer

router = APIRouter()

WORKERS = 2
KEEP_FINISHED_MS = 60 * 60 * 1000  # finished jobs stay readable for an hour
RECENT_MS = 30 * 1000  # /jobs also lists jobs that finished in the last 30 s
MEASURE_S = 5.0
WORKING_OUT = "Working out how long this takes…"

_jobs: dict[str, "Job"] = {}
_lock = threading.Lock()
_queue: "queue.Queue" = queue.Queue()
_workers: list[threading.Thread] = []


def _left_words(seconds: float, more_steps: bool) -> str:
    tail = " on this step" if more_steps else ""
    if seconds < 60:
        return f"Less than a minute left{tail}"
    minutes = int(round(seconds / 60))
    return f"About {minutes} minute{'s' if minutes != 1 else ''} left{tail}"


class Job:
    """The handle a job function gets as its first argument."""

    def __init__(self, case_id: str, kind: str, label: str, steps):
        self.id = uuid.uuid4().hex[:12]
        self.case_id = case_id
        self.kind = kind
        self.label = label
        self.step_names = list(steps) if isinstance(steps, (list, tuple)) else None
        self.n_steps = len(self.step_names) if self.step_names else (int(steps) if steps else 0)
        self.status = "waiting"
        self.step_name = "Waiting to start"
        self.step_no = 0
        self.step_progress = 0.0
        self.created_at = db.now_ms()
        self.started_at: int | None = None
        self.finished_at: int | None = None
        self.error: str | None = None
        self.result = None
        self._step_t0 = time.monotonic()
        self._lock = threading.Lock()
        self._done = threading.Event()

    # -- called by the job function
    def step(self, name: str | None = None) -> None:
        """Start the next step (its name in plain words, e.g. 'Reading chats')."""
        with self._lock:
            self.step_no += 1
            if not name and self.step_names and self.step_no <= len(self.step_names):
                name = self.step_names[self.step_no - 1]
            self.step_name = name or f"Step {self.step_no}"
            self.step_progress = 0.0
            self._step_t0 = time.monotonic()

    def progress(self, fraction: float) -> None:
        """How far the current step is, from 0 to 1."""
        try:
            f = float(fraction)
        except (TypeError, ValueError):
            return
        with self._lock:
            self.step_progress = min(1.0, max(0.0, f))

    # -- read by everyone else
    def snapshot(self) -> dict:
        with self._lock:
            p = self.step_progress
            running = self.status == "running"
            if self.status == "done":
                overall = 1.0
            elif self.n_steps:
                overall = (max(0, self.step_no - 1) + p) / self.n_steps
            else:
                overall = p
            left_s, left = None, ""
            if running:
                elapsed = time.monotonic() - self._step_t0
                if elapsed >= MEASURE_S and 0 < p < 1:
                    left_s = int(round((1 - p) * elapsed / p))
                    left = _left_words(left_s, bool(self.n_steps and self.step_no < self.n_steps))
                else:
                    left = WORKING_OUT
            return {"id": self.id, "case_id": self.case_id, "kind": self.kind, "label": self.label,
                    "status": self.status, "step": self.step_name, "step_no": self.step_no, "steps": self.n_steps,
                    "progress": round(min(1.0, overall), 4), "step_progress": round(p, 4),
                    "time_left_s": left_s, "time_left": left, "created_at": self.created_at,
                    "started_at": self.started_at, "finished_at": self.finished_at,
                    "error": self.error, "result": self.result}


def _run(job: Job, fn, args, kwargs) -> None:
    with job._lock:
        job.status = "running"
        job.started_at = db.now_ms()
        job._step_t0 = time.monotonic()
    try:
        result = fn(job, *args, **kwargs)
        with job._lock:
            job.result = result
            job.status = "done"
            job.step_progress = 1.0
    except ApiError as e:
        with job._lock:
            job.status, job.error = "failed", e.message
    except Exception:
        traceback.print_exc(file=sys.stderr)
        with job._lock:
            job.status = "failed"
            job.error = f"{job.label or 'This job'} didn't finish because of a problem on this computer. " \
                        f"Try again; the details are in the server window."
    finally:
        with job._lock:
            job.finished_at = db.now_ms()
        job._done.set()


def _worker() -> None:
    while True:
        job, fn, args, kwargs = _queue.get()
        try:
            _run(job, fn, args, kwargs)
        finally:
            _queue.task_done()


def _ensure_workers() -> None:
    with _lock:
        alive = [t for t in _workers if t.is_alive()]
        _workers[:] = alive
        while len(_workers) < WORKERS:
            t = threading.Thread(target=_worker, name=f"ib-job-{len(_workers) + 1}", daemon=True)
            t.start()
            _workers.append(t)


def _prune() -> None:
    cutoff = db.now_ms() - KEEP_FINISHED_MS
    for jid in [j.id for j in _jobs.values() if j.finished_at and j.finished_at < cutoff]:
        _jobs.pop(jid, None)


def start(case_id: str, kind: str, fn, *args, label: str | None = None, steps=None, sync: bool | None = None,
          **kwargs) -> dict:
    """Queue fn(job, *args, **kwargs) and return the job dict at once (finished, if sync or IB_SYNC_JOBS=1)."""
    job = Job(case_id, kind, label or kind.replace("_", " ").capitalize(), steps)
    with _lock:
        _prune()
        _jobs[job.id] = job
    if sync or (sync is None and config.sync_jobs()):
        _run(job, fn, args, kwargs)
    else:
        _ensure_workers()
        _queue.put((job, fn, args, kwargs))
    return job.snapshot()


def get(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    return job.snapshot() if job else None


def for_case(case_id: str, recent_ms: int = RECENT_MS) -> list[dict]:
    """The case's waiting and running jobs, plus those that finished in the last recent_ms."""
    cutoff = db.now_ms() - recent_ms
    with _lock:
        mine = [j for j in _jobs.values() if j.case_id == case_id]
    out = [j.snapshot() for j in mine]
    return [s for s in out if s["status"] in ("waiting", "running") or (s["finished_at"] or 0) >= cutoff]


def find(case_id: str, kind: str) -> dict | None:
    """A job of this kind that is waiting or running for the case (to avoid starting it twice)."""
    with _lock:
        mine = [j for j in _jobs.values() if j.case_id == case_id and j.kind == kind]
    for j in mine:
        s = j.snapshot()
        if s["status"] in ("waiting", "running"):
            return s
    return None


def wait(job_id: str, timeout: float | None = None) -> dict | None:
    """Block until the job finishes (or timeout seconds pass) and return its dict."""
    job = _jobs.get(job_id)
    if not job:
        return None
    job._done.wait(timeout)
    return job.snapshot()


@router.get("/api/cases/{cid}/jobs")
def case_jobs(cid: str, acc: CaseAccess = Depends(require_case)):
    return for_case(cid)


@router.get("/api/jobs/{job_id}")
def one_job(job_id: str, request: Request):
    officer = require_officer(request)
    snap = get(job_id)
    if not snap or not can_access(officer["officer_id"], snap["case_id"]):
        raise ApiError(404, "That job isn't known any more. It may have finished a while ago.")
    return snap
