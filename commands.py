from __future__ import annotations

import json
from typing import Any

from .candidate_ledger import list_candidates, pending_report
from .paths import audit_log_path
from .promotion import dry_run_promotion, promote_candidate
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


def format_pending(limit: int = 10) -> str:
    candidates = list_candidates(status="pending", limit=limit)
    if not candidates:
        return "[turn-closure-audit] no pending candidates."
    out = [f"[turn-closure-audit] pending candidates: {len(candidates)} shown"]
    for candidate in candidates:
        out.append(
            f"- {candidate.candidate_id} | sink={candidate.final_sink} | risk={candidate.risk} | created={candidate.created_at} | content={preview(candidate.candidate_content, 100)}"
        )
    return "\n".join(out)


def format_report() -> str:
    report = pending_report()
    lines = ["[turn-closure-audit] candidate report"]
    for key in [
        "pending_total",
        "pending_over_24h",
        "needs_user_confirmation_total",
        "promoted_today",
        "merged_today",
        "rejected_today",
    ]:
        lines.append(f"- {key}: {report.get(key)}")
    oldest = report.get("oldest_pending") or {}
    if oldest:
        lines.append(f"- oldest_pending: {oldest.get('candidate_id')} created={oldest.get('created_at')}")
    return "\n".join(lines)


def format_promote(parts: list[str]) -> str:
    dry_run = "--dry-run" in parts or "dry-run" in parts or len(parts) == 1
    candidate_id = ""
    if "--candidate" in parts:
        idx = parts.index("--candidate")
        if idx + 1 < len(parts):
            candidate_id = parts[idx + 1]
    elif len(parts) >= 2 and not parts[1].startswith("--") and parts[1] != "dry-run":
        candidate_id = parts[1]

    if candidate_id:
        result = promote_candidate(candidate_id, dry_run=dry_run, allow_write=not dry_run)
        return "[turn-closure-audit] promote result\n" + json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)

    report = dry_run_promotion()
    counts = {key: len(value) for key, value in report.items()}
    return "[turn-closure-audit] promote dry-run\n" + json.dumps(counts, ensure_ascii=False, indent=2, sort_keys=True)


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
    if parts[0] == "pending":
        limit = 10
        if len(parts) >= 2:
            try:
                limit = max(1, min(50, int(parts[1])))
            except ValueError:
                limit = 10
        return format_pending(limit)
    if parts[0] == "report":
        return format_report()
    if parts[0] == "promote":
        return format_promote(parts)
    return "[turn-closure-audit] usage: /turn-closure [recent|last|status] [N] | path | pending [N] | report | promote [--dry-run] [--candidate ID]"
