from __future__ import annotations

from datetime import datetime, timezone


def now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def today_str() -> str:
    return now_local().strftime("%Y-%m-%d")
