from __future__ import annotations

import json
from typing import Any

from .paths import audit_log_path
from .redaction import preview


def format_recent(limit: int = 5) -> str:
    path = audit_log_path()
    if not path.exists():
        return f"[turn-closure-audit] no records yet. path={path}"
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    for raw in lines[-max(1, limit):]:
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    if not rows:
        return f"[turn-closure-audit] no readable records. path={path}"
    out = [f"[turn-closure-audit] path={path}"]
    for row in rows:
        out.append(
            "- {status} | judged_at={judged_at} | session={session_id} | observed_writes={writes} | auto_writes={auto_writes} | user={user}".format(
                status=row.get("status", ""),
                judged_at=row.get("judged_at", ""),
                session_id=row.get("session_id", ""),
                writes=len(row.get("writes", []) or []),
                auto_writes=len(row.get("auto_writes", []) or []),
                user=preview(row.get("user_preview", ""), 80),
            )
        )
    return "\n".join(out)


def handle_command(raw_args: str) -> str:
    parts = [p for p in raw_args.strip().split() if p]
    if not parts or parts[0] in {"last", "recent", "status"}:
        limit = 5
        if len(parts) >= 2:
            try:
                limit = max(1, min(20, int(parts[1])))
            except ValueError:
                limit = 5
        return format_recent(limit)
    if parts[0] == "path":
        return str(audit_log_path())
    return "[turn-closure-audit] usage: /turn-closure [recent|last|status] [N] | /turn-closure path"
