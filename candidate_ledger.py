from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .candidate_schema import (
    TERMINAL_STATUSES,
    CandidateEvent,
    CandidateRecord,
    candidate_is_terminal as schema_candidate_is_terminal,
)
from .clock import now_iso, today_str
from .paths import display_path, locked_file


TRANSITION_EVENT_TO_STATUS: dict[str, str] = {
    "candidate.promoted": "promoted",
    "candidate.merged": "merged",
    "candidate.needs_user_confirmation": "needs_user_confirmation",
    "candidate.expired": "expired",
}
REJECTION_STATUSES = {"rejected_noise", "rejected_temporary", "rejected_sensitive"}


def candidate_events_dir(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root) / "turn.closure.audit" / "candidates" / "events"
    from .paths import audit_root

    return audit_root() / "candidates" / "events"


def candidate_event_path(day: str | None = None, root: Path | None = None) -> Path:
    return candidate_events_dir(root) / f"{day or today_str()}.jsonl"


def _event_day(event: CandidateEvent) -> str:
    return (event.at or today_str())[:10] or today_str()


def _iter_event_paths(root: Path | None = None, *, since: str | None = None) -> list[Path]:
    base = candidate_events_dir(root)
    if not base.exists():
        return []
    paths = sorted(base.glob("*.jsonl"))
    if since:
        paths = [path for path in paths if path.stem >= since[:10]]
    return paths


def serialize_candidate(candidate: CandidateRecord) -> dict[str, Any]:
    return candidate.to_json()


def append_candidate_jsonl(fh: Any, candidate: CandidateRecord) -> None:
    fh.seek(0, 2)
    fh.write(json.dumps(serialize_candidate(candidate), ensure_ascii=False, sort_keys=True) + "\n")


def candidate_is_terminal(candidate: CandidateRecord | dict[str, Any]) -> bool:
    return schema_candidate_is_terminal(candidate)


def attach_receipt(candidate: dict[str, Any], *, status: str, receipt: dict[str, Any], reason: str = "") -> dict[str, Any]:
    updated = dict(candidate)
    updated["status"] = status
    updated["candidate_status"] = status
    updated["receipt"] = dict(receipt)
    if reason:
        updated["decision_reason"] = reason
    return updated


def append_event(event: CandidateEvent, *, root: Path | None = None) -> dict[str, Any]:
    path = candidate_event_path(_event_day(event), root)
    with locked_file(path) as fh:
        fh.seek(0, 2)
        fh.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return {"ok": True, "event_id": event.event_id, "path": display_path(path)}


def load_events(*, since: str | None = None, limit: int | None = None, root: Path | None = None) -> list[CandidateEvent]:
    events: list[CandidateEvent] = []
    for path in _iter_event_paths(root, since=since):
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not raw.strip():
                continue
            try:
                event = CandidateEvent.from_dict(json.loads(raw))
            except Exception:
                continue
            event.details.setdefault("_ledger_path", str(path))
            event.details.setdefault("_ledger_line", line_no)
            events.append(event)
    events.sort(key=lambda event: (event.at, event.details.get("_ledger_path", ""), int(event.details.get("_ledger_line", 0))))
    if limit is not None:
        return events[-max(0, limit) :]
    return events


def _candidate_from_event(event: CandidateEvent) -> CandidateRecord | None:
    if not event.candidate:
        return None
    return CandidateRecord.from_dict(event.candidate)


def materialize_candidates(events: Iterable[CandidateEvent]) -> dict[str, CandidateRecord]:
    current: dict[str, CandidateRecord] = {}
    for event in events:
        if event.event_type == "candidate.created":
            candidate = _candidate_from_event(event)
            if candidate is not None and event.candidate_id not in current:
                current[event.candidate_id] = candidate
            continue

        existing = current.get(event.candidate_id)
        if existing is None:
            continue
        if existing.status in TERMINAL_STATUSES:
            continue

        new_status = event.status
        if event.event_type in TRANSITION_EVENT_TO_STATUS:
            new_status = TRANSITION_EVENT_TO_STATUS[event.event_type]
        elif event.event_type == "candidate.rejected" and event.status in REJECTION_STATUSES:
            new_status = event.status
        elif event.event_type == "candidate.classified" and event.status:
            new_status = event.status

        if new_status:
            current[event.candidate_id] = existing.with_updates(
                status=new_status,
                updated_at=event.at or existing.updated_at,
                receipt=event.receipt if event.receipt is not None else existing.receipt,
                decision_reason=event.reason or existing.decision_reason,
            )
    return current


def list_candidates(
    *,
    status: str | None = None,
    since: str | None = None,
    limit: int = 50,
    root: Path | None = None,
) -> list[CandidateRecord]:
    candidates = list(materialize_candidates(load_events(since=since, root=root)).values())
    if status:
        candidates = [candidate for candidate in candidates if candidate.status == status]
    candidates.sort(key=lambda candidate: (candidate.updated_at or candidate.created_at, candidate.candidate_id), reverse=True)
    return candidates[: max(0, limit)]


def append_candidate_created(candidate: CandidateRecord, *, root: Path | None = None) -> dict[str, Any]:
    existing = materialize_candidates(load_events(root=root))
    if candidate.candidate_id in existing:
        return {
            "ok": True,
            "deduped": True,
            "candidate_id": candidate.candidate_id,
            "status": existing[candidate.candidate_id].status,
        }
    event = CandidateEvent.new(
        "candidate.created",
        candidate.candidate_id,
        candidate.created_at or now_iso(),
        record_id=candidate.record_id,
        candidate=candidate,
        status=candidate.status,
        reason=candidate.decision_reason,
    )
    result = append_event(event, root=root)
    result.update({"deduped": False, "candidate_id": candidate.candidate_id, "status": candidate.status})
    return result


def transition_candidate(
    candidate_id: str,
    event_type: str,
    *,
    receipt: dict[str, Any] | None = None,
    reason: str = "",
    status: str | None = None,
    at: str | None = None,
    root: Path | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = materialize_candidates(load_events(root=root))
    candidate = candidates.get(candidate_id)
    if candidate is None:
        return {"ok": False, "error": "candidate_not_found", "candidate_id": candidate_id}
    if candidate.status in TERMINAL_STATUSES:
        return {
            "ok": True,
            "deduped": True,
            "terminal": True,
            "candidate_id": candidate_id,
            "status": candidate.status,
            "receipt": candidate.receipt,
        }

    final_status = status
    if final_status is None:
        final_status = TRANSITION_EVENT_TO_STATUS.get(event_type)
    if event_type == "candidate.rejected" and final_status not in REJECTION_STATUSES:
        return {"ok": False, "error": "invalid_rejection_status", "candidate_id": candidate_id, "status": final_status}
    if event_type not in TRANSITION_EVENT_TO_STATUS and event_type != "candidate.rejected" and event_type != "candidate.classified":
        return {"ok": False, "error": "invalid_transition_event", "candidate_id": candidate_id, "event_type": event_type}

    event = CandidateEvent.new(
        event_type,
        candidate_id,
        at or now_iso(),
        record_id=candidate.record_id,
        status=final_status,
        reason=reason,
        receipt=receipt,
        details=details,
    )
    result = append_event(event, root=root)
    result.update({"candidate_id": candidate_id, "status": final_status, "receipt": receipt, "deduped": False})
    return result


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def pending_report(
    *,
    now: str | None = None,
    overdue_hours: int = 24,
    root: Path | None = None,
) -> dict[str, Any]:
    events = load_events(root=root)
    candidates = list(materialize_candidates(events).values())
    current_time = _parse_dt(now or now_iso())
    today = (now or now_iso())[:10]
    pending = [candidate for candidate in candidates if candidate.status == "pending"]
    needs_confirmation = [candidate for candidate in candidates if candidate.status == "needs_user_confirmation"]
    overdue = []
    for candidate in pending:
        created = _parse_dt(candidate.created_at) or _parse_dt(candidate.updated_at)
        if current_time is not None and created is not None and current_time - created > timedelta(hours=overdue_hours):
            overdue.append(candidate)
    oldest = min(pending, key=lambda candidate: candidate.created_at or candidate.updated_at, default=None)
    return {
        "pending_total": len(pending),
        "pending_over_24h": len(overdue),
        "needs_user_confirmation_total": len(needs_confirmation),
        "promoted_today": sum(1 for event in events if event.event_type == "candidate.promoted" and event.at[:10] == today),
        "merged_today": sum(1 for event in events if event.event_type == "candidate.merged" and event.at[:10] == today),
        "rejected_today": sum(1 for event in events if event.event_type == "candidate.rejected" and event.at[:10] == today),
        "oldest_pending": oldest.to_dict() if oldest else None,
    }
