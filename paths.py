from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

import fcntl

from hermes_constants import get_hermes_home


def audit_root() -> Path:
    return get_hermes_home() / "turn.closure.audit"


def audit_log_path() -> Path:
    return audit_root() / "turns.jsonl"


def latest_dir() -> Path:
    return audit_root() / "latest"


def memory_day_path(day: Optional[str] = None, *, today: str = "") -> Path:
    if not day:
        if not today:
            raise ValueError("day or today must be provided")
        day = today
    return get_hermes_home() / "memory" / f"{day}.md"


def review_candidate_path(day: Optional[str] = None, *, today: str = "") -> Path:
    if not day:
        if not today:
            raise ValueError("day or today must be provided")
        day = today
    return get_hermes_home() / "knowledge" / "review" / f"turn-closure-candidates-{day}.jsonl"


def session_key(session_id: str) -> str:
    return session_id or "unknown-session"


def record_id(session_id: str, opened_at: str, judged_at: str) -> str:
    return f"{session_key(session_id)}:{opened_at}:{judged_at}"


def safe_session_filename(session_id: str) -> str:
    raw = session_key(session_id)
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")
    if not cleaned:
        cleaned = "session"
    cleaned = cleaned[:80]
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{cleaned}--{digest}"


def display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(get_hermes_home().resolve()).as_posix()
    except Exception:
        return str(path)


@contextmanager
def locked_file(path: Path) -> Iterator[Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            yield fh
        finally:
            fh.flush()
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
