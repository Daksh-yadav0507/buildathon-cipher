"""Settings: where the data folder is, the port, and the AI settings from .env.

The data folder is data/ next to run.py, unless IB_DATA_DIR is set (tests and
spare servers use a temporary folder that way) or set_data_dir() is called.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is in requirements.txt, but never fail on it
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
ENV_FILE = ROOT / ".env"

if load_dotenv is not None and ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)  # real environment variables win over .env


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


APP_NAME = "insights-buddy"
VERSION = "1.0"
HOST = "127.0.0.1"  # never listen on other addresses
DEFAULT_PORT = _int_env("IB_PORT", 8000)
SESSION_COOKIE = "ib_session"
SESSION_HOURS = 12
PAGE_SIZE = 50  # lists come 50 at a time

# ---------------------------------------------------------------- data folder

_data_dir = Path(os.environ.get("IB_DATA_DIR") or (ROOT / "data")).expanduser().resolve()


def data_dir() -> Path:
    return _data_dir


def set_data_dir(path) -> Path:
    """Point the whole app at another data folder (tests). Call before the first request."""
    global _data_dir
    _data_dir = Path(path).expanduser().resolve()
    os.environ["IB_DATA_DIR"] = str(_data_dir)
    return _data_dir


def app_db_path() -> Path:
    """data/officers.db: officers, sessions, the case list, access, prefs, unit-wide lists."""
    return _data_dir / "officers.db"


def cases_dir() -> Path:
    return _data_dir / "cases"


def samples_dir() -> Path:
    return _data_dir / "samples"


CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def valid_case_id(case_id) -> bool:
    return isinstance(case_id, str) and bool(CASE_ID_RE.match(case_id))


def case_dir(case_id: str) -> Path:
    """data/cases/<case_id>/ (the case id is checked, so it can never point outside)."""
    if not valid_case_id(case_id):
        raise ValueError("not a case id")
    return cases_dir() / case_id


def case_db_path(case_id: str) -> Path:
    return case_dir(case_id) / "case.db"


def ensure_dirs() -> None:
    for d in (_data_dir, cases_dir(), samples_dir()):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- run modes


def sync_jobs() -> bool:
    """IB_SYNC_JOBS=1 runs background jobs inline (tests)."""
    return _flag("IB_SYNC_JOBS")


def auto_sample() -> bool:
    """On start-up the sample case is made unless IB_NO_SAMPLE=1."""
    return not _flag("IB_NO_SAMPLE")


# ---------------------------------------------------------------- the AI (section 8.1)


@dataclass(frozen=True)
class AISettings:
    base_url: str
    api_key: str
    model: str
    max_tokens: int
    timeout_s: float

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    @property
    def host(self) -> str:
        if not self.base_url:
            return ""
        return urlparse(self.base_url).hostname or ""

    @property
    def local(self) -> bool:
        """True when nothing leaves this computer: no AI, or the AI is on 127.0.0.1 / localhost."""
        if not self.configured:
            return True
        return self.host in ("127.0.0.1", "localhost", "::1")

    @property
    def where(self) -> str:
        """Plain words for the status line: 'on this computer' or 'at <host>'."""
        return "on this computer" if self.local else f"at {self.host}"

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions" if self.base_url else ""


def ai() -> AISettings:
    """The AI settings, read fresh from the environment (.env was loaded at import).

    IB_NO_AI=1 switches the AI off whatever .env says (tests, code-only demos).
    """
    base = "" if _flag("IB_NO_AI") else os.environ.get("AI_BASE_URL", "").strip()
    return AISettings(
        base_url=base,
        api_key=os.environ.get("AI_API_KEY", "").strip(),
        model=os.environ.get("AI_MODEL", "").strip(),
        max_tokens=_int_env("AI_MAX_TOKENS", 1200),
        timeout_s=_float_env("AI_TIMEOUT_S", 90.0),
    )
