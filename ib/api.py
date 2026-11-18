"""The FastAPI app: core routes, the session check on every route, static files, and every module's router.

Modules are picked up by themselves: for each name in MODULES, ib.<name> is imported and its `router`
included. A module that is missing, has no router, or fails to import is skipped (the console says why),
so nobody needs to edit this file to add their routes.
"""
from __future__ import annotations

import importlib
import sys
import threading
import traceback
from contextlib import asynccontextmanager

from fastapi import APIRouter, Body, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ib import ApiError, audit, config, db, jobs, limits, officers

MODULES = ["ingest", "search", "stats", "people", "browse", "ask", "across", "keyq", "brief", "codes",
           "findings", "export"]
loaded: dict[str, str] = {}  # name -> "ok" | "missing" | "no router" | "failed: ..."

GENERAL_ERROR = "Something went wrong on this computer. Try again; if it keeps happening, restart Insights Buddy."
STATUS_WORDS = {400: "That request isn't right. Check what was entered and try again.",
                401: officers.NOT_LOGGED_IN, 403: "You don't have access to that.",
                404: "That wasn't found.", 405: "That can't be done here.", 413: "That file is too big.",
                415: "That kind of file can't be read here."}


def error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


# ---------------------------------------------------------------- the check on every request


_opened: set[tuple[str, str]] = set()  # (session, case) pairs already written to the audit log
_opened_lock = threading.Lock()


def guard(request: Request) -> None:
    """Every /api route needs a session (except health and auth); every {cid} route needs access to that case.

    The first time a session reads a case, the core writes "Opened the case" and updates its last-opened time.
    """
    path = request.url.path
    if not path.startswith("/api/") or path == "/api/health" or path.startswith("/api/auth/"):
        return
    officers.require_officer(request)
    cid = request.path_params.get("cid")
    if cid is None:
        return
    acc = officers.check_case(request, str(cid))
    if request.method == "GET" and path.startswith(f"/api/cases/{acc.cid}/"):
        key = (request.cookies.get(config.SESSION_COOKIE, ""), acc.cid)
        with _opened_lock:
            first = key not in _opened
            _opened.add(key)
        if first:
            db.touch_case(acc.cid)
            audit.log(acc.cid, acc, "case", "Opened the case")


# ---------------------------------------------------------------- start-up


def _make_sample_case() -> None:
    mod = sys.modules.get("ib.ingest")
    fn = getattr(mod, "ensure_sample_case", None) if mod else None
    if not callable(fn):
        return
    try:
        fn()
    except Exception:
        print("[start-up] making the sample case failed:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    officers.seed()
    if config.auto_sample():
        threading.Thread(target=_make_sample_case, name="ib-sample-case", daemon=True).start()
    yield


app = FastAPI(title="Insights Buddy", version=config.VERSION, lifespan=lifespan, dependencies=[Depends(guard)],
              docs_url=None, redoc_url=None, openapi_url="/openapi.json")


# ---------------------------------------------------------------- errors as plain sentences


@app.exception_handler(ApiError)
async def _api_error(_request: Request, exc: ApiError):
    return error(exc.status, exc.message)


@app.exception_handler(StarletteHTTPException)
async def _http_error(_request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        message = str(detail["error"])
    elif isinstance(detail, str) and detail and detail.lower() not in ("not found", "method not allowed",
                                                                       "bad request", "unauthorized", "forbidden"):
        message = detail
    else:
        message = STATUS_WORDS.get(exc.status_code, GENERAL_ERROR)
    return JSONResponse({"error": message}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def _validation_error(_request: Request, exc: RequestValidationError):
    fields = []
    for e in exc.errors():
        loc = [str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path", "header", "cookie")]
        if loc and loc[-1] not in fields:
            fields.append(loc[-1])
    if fields:
        return error(422, "Some details are missing or not in the right form: " + ", ".join(fields) + ".")
    return error(422, "Some details are missing or not in the right form.")


class CatchAll:
    """Turns any unexpected exception into a 500 with a plain sentence; static files are always revalidated."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        started = False
        static = scope.get("path", "").startswith("/static/")

        async def send_wrapper(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                if static:
                    message.setdefault("headers", [])
                    message["headers"] = [*message["headers"], (b"cache-control", b"no-cache")]
            await send(message)

        try:
            await self.inner(scope, receive, send_wrapper)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            if started:
                raise
            await error(500, GENERAL_ERROR)(scope, receive, send)


app.add_middleware(CatchAll)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "::1", "testserver"])


# ---------------------------------------------------------------- core routes

core = APIRouter()


@core.get("/api/health")
def health():
    a = config.ai()
    return {"app": config.APP_NAME, "version": config.VERSION,
            "ai": {"configured": a.configured, "model": a.model if a.configured else "", "local": a.local,
                   "host": a.host, "where": a.where},
            "modules": dict(loaded)}


@core.post("/api/auth/login")
def login(response: Response, payload: dict | None = Body(None)):
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    password = str(payload.get("password") or "")
    if not name or not password:
        raise ApiError(400, "Enter your name and password.")
    officers.seed()
    officer = officers.authenticate(name, password)
    if officer is None:
        audit.log_app(name, "login_failed", f"A log-in as '{name}' failed")
        raise ApiError(401, officers.LOGIN_FAILED)
    token = officers.create_session(officer["officer_id"])
    response.set_cookie(config.SESSION_COOKIE, token, max_age=config.SESSION_HOURS * 3600, httponly=True,
                        samesite="lax", path="/")
    audit.log_app(officer, "login", "Logged in")
    return officer


@core.post("/api/auth/logout")
def logout(request: Request, response: Response):
    officer = officers.officer_from_request(request)
    officers.end_session(request.cookies.get(config.SESSION_COOKIE))
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    if officer:
        audit.log_app(officer, "logout", "Logged out")
    return {"ok": True}


@core.get("/api/me")
def me(officer: dict = Depends(officers.require_officer)):
    return officer


@core.get("/api/prefs")
def prefs_get(officer: dict = Depends(officers.require_officer)):
    return officers.get_prefs(officer["officer_id"])


@core.post("/api/prefs")
def prefs_set(payload: dict | None = Body(None), officer: dict = Depends(officers.require_officer)):
    return officers.set_prefs(officer["officer_id"], payload or {})


app.include_router(core)
app.include_router(audit.router)
app.include_router(limits.router)
app.include_router(jobs.router)


# ---------------------------------------------------------------- the other modules, picked up by themselves


def _load_modules() -> None:
    for name in MODULES:
        modname = f"ib.{name}"
        try:
            mod = importlib.import_module(modname)
        except ModuleNotFoundError as e:
            if e.name == modname:
                loaded[name] = "missing"
                continue
            loaded[name] = f"failed: {e}"
            print(f"[modules] {modname} could not be loaded: {e}", file=sys.stderr)
            continue
        except Exception as e:
            loaded[name] = f"failed: {type(e).__name__}: {e}"
            print(f"[modules] {modname} could not be loaded:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            continue
        router = getattr(mod, "router", None)
        if not isinstance(router, APIRouter):
            loaded[name] = "no router"
            continue
        try:
            app.include_router(router)
        except Exception as e:
            loaded[name] = f"failed: {type(e).__name__}: {e}"
            print(f"[modules] {modname}'s routes could not be added: {e}", file=sys.stderr)
            continue
        loaded[name] = "ok"


_load_modules()


# ---------------------------------------------------------------- the web pages


class _WebFiles(StaticFiles):
    async def check_config(self) -> None:  # web/ may not exist yet: missing files are simply 404
        return None


app.mount("/static", _WebFiles(directory=str(config.WEB_DIR), check_dir=False), name="static")

_PLACEHOLDER = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Insights Buddy</title></head>
<body style="font-family:system-ui,sans-serif;margin:3rem;color:#1f2937;background:#f8fafc">
<h1 style="font-size:1.4rem">Insights Buddy is running</h1>
<p>The screens are not in place yet. Reload this page in a moment.</p></body></html>"""


@app.get("/", include_in_schema=False)
def index():
    page = config.WEB_DIR / "index.html"
    if page.exists():
        return FileResponse(page, media_type="text/html", headers={"Cache-Control": "no-cache"})
    return HTMLResponse(_PLACEHOLDER)
