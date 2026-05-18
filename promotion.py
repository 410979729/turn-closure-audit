from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .candidate_ledger import list_candidates, transition_candidate
from .candidate_schema import CandidateRecord, TERMINAL_STATUSES
from .receipts import merge_receipt, promotion_receipt, rejection_receipt, receipt

PROMOTION_BUCKETS = (
    "would_promote",
    "needs_confirmation",
    "suggest_skill",
    "suggest_knowledge",
    "would_reject",
    "conflicts",
    "already_satisfied",
)

SENSITIVE_HINTS = (
    "api_key",
    "api key",
    "secret",
    "token",
    "password",
    "passwd",
    "authorization",
    "bearer ",
    "cookie",
    "暗号",
)
TEMPORARY_HINTS = (
    "currently",
    "right now",
    "running",
    "status",
    "port",
    "health",
    "temporary",
    "现在",
    "当前",
    "临时",
    "运行态",
)
CONFLICT_HINTS = ("conflict", "contradict", "instead of", "不再", "改成", "冲突")
WORKFLOW_HINTS = ("workflow", "procedure", "sop", "steps", "runbook", "流程", "步骤")


class MemoryWriter(Protocol):
    def write(self, candidate: CandidateRecord) -> dict[str, Any]:
        ...


@dataclass
class InMemoryPromotionWriter:
    """Fakeable writer used by tests and explicit opt-in callers.

    The promotion engine never talks to live memory providers by default. Tests
    can inject this writer, and runtime integrations can inject a scope-recall
    adapter later.
    """

    writes: list[CandidateRecord] = field(default_factory=list)

    def write(self, candidate: CandidateRecord) -> dict[str, Any]:
        self.writes.append(candidate)
        return promotion_receipt(provider="fake-memory-writer", target=candidate.final_sink, id=candidate.candidate_id)


def empty_report() -> dict[str, list[dict[str, Any]]]:
    return {name: [] for name in PROMOTION_BUCKETS}


def _as_payload(candidate: CandidateRecord, *, reason: str = "") -> dict[str, Any]:
    data = candidate.to_dict()
    if reason:
        data["promotion_reason"] = reason
    return data


def _equivalent_match(candidate: CandidateRecord, existing_memories: list[dict[str, Any]]) -> dict[str, Any] | None:
    needle = " ".join(candidate.candidate_content.casefold().split())
    for memory in existing_memories:
        text = str(memory.get("candidate_content") or memory.get("content") or memory.get("text") or memory.get("value") or "")
        if " ".join(text.casefold().split()) == needle:
            return memory
    return None


def _has_conflict(candidate: CandidateRecord, conflicts: list[dict[str, Any]]) -> bool:
    if conflicts:
        return True
    text = f"{candidate.candidate_content}\n{candidate.evidence_summary}".casefold()
    return any(hint in text for hint in CONFLICT_HINTS)


def classify_promotion(
    candidate: CandidateRecord,
    *,
    existing_memories: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    text = f"{candidate.candidate_content}\n{candidate.evidence_summary}".casefold()
    existing = _equivalent_match(candidate, existing_memories or [])
    if existing is not None:
        return "already_satisfied", "equivalent durable memory already exists"
    if any(hint in text for hint in SENSITIVE_HINTS) or candidate.risk == "high" and candidate.final_sink != "ask_user":
        return "would_reject", "candidate looks sensitive or too risky for automatic promotion"
    if any(hint in text for hint in TEMPORARY_HINTS):
        return "would_reject", "runtime or temporary service state should be checked live"
    if _has_conflict(candidate, conflicts or []):
        return "conflicts", "candidate may conflict with existing memory"
    if candidate.final_sink == "ask_user" or candidate.status == "needs_user_confirmation":
        return "needs_confirmation", "candidate needs user confirmation"
    if candidate.final_sink == "skill" or any(hint in text for hint in WORKFLOW_HINTS):
        return "suggest_skill", "workflow/procedure candidates should become skills through explicit review"
    if candidate.final_sink == "knowledge":
        return "suggest_knowledge", "knowledge candidates should be curated into knowledge storage"
    if candidate.final_sink in {"discard"}:
        return "would_reject", "candidate final sink is discard"
    if candidate.final_sink in {"user", "memory", "project", "ops"} and candidate.risk == "low":
        return "would_promote", "low-risk explicit stable preference can be promoted with opt-in write"
    return "needs_confirmation", "promotion is not low-risk enough for default write"


def dry_run_promotion(
    candidates: list[CandidateRecord] | None = None,
    *,
    existing_memories: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    root=None,
) -> dict[str, list[dict[str, Any]]]:
    if candidates is None:
        candidates = list_candidates(status="pending", root=root, limit=500)
    report = empty_report()
    for candidate in candidates:
        if candidate.status in TERMINAL_STATUSES:
            report["already_satisfied"].append(_as_payload(candidate, reason="candidate already terminal"))
            continue
        bucket, reason = classify_promotion(candidate, existing_memories=existing_memories, conflicts=conflicts)
        report[bucket].append(_as_payload(candidate, reason=reason))
    return report


def promote_candidate(
    candidate_id: str,
    *,
    root=None,
    dry_run: bool = True,
    allow_write: bool = False,
    writer: MemoryWriter | Callable[[CandidateRecord], dict[str, Any]] | None = None,
    existing_memories: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    matches = list_candidates(root=root, limit=1000)
    candidate = next((item for item in matches if item.candidate_id == candidate_id), None)
    if candidate is None:
        return {"ok": False, "error": "candidate_not_found", "candidate_id": candidate_id}
    if candidate.status in TERMINAL_STATUSES:
        return {"ok": True, "candidate_id": candidate_id, "status": candidate.status, "receipt": candidate.receipt, "deduped": True}

    bucket, reason = classify_promotion(candidate, existing_memories=existing_memories, conflicts=conflicts)
    if dry_run or not allow_write:
        return {"ok": True, "dry_run": True, "candidate_id": candidate_id, "bucket": bucket, "reason": reason, "status": candidate.status}

    if bucket == "already_satisfied":
        match = _equivalent_match(candidate, existing_memories or []) or {}
        rec = merge_receipt(target=candidate.final_sink, target_id=str(match.get("id") or match.get("target_id") or candidate_id), source_candidate_id=candidate_id)
        return transition_candidate(candidate_id, "candidate.merged", receipt=rec, reason=reason, root=root)

    if bucket == "conflicts" or bucket == "needs_confirmation":
        rec = rejection_receipt("needs_user_confirmation", reason=reason)
        return transition_candidate(candidate_id, "candidate.needs_user_confirmation", receipt=rec, reason=reason, root=root)

    if bucket == "would_reject":
        action = "rejected_sensitive" if "sensitive" in reason else "rejected_temporary" if "temporary" in reason or "runtime" in reason else "rejected_noise"
        rec = rejection_receipt(action, reason=reason)
        return transition_candidate(candidate_id, "candidate.rejected", status=action, receipt=rec, reason=reason, root=root)

    if bucket in {"suggest_skill", "suggest_knowledge"}:
        rec = rejection_receipt("needs_user_confirmation", reason=reason)
        return transition_candidate(candidate_id, "candidate.needs_user_confirmation", receipt=rec, reason=reason, root=root)

    if bucket != "would_promote":
        rec = receipt("needs_user_confirmation", reason=reason)
        return transition_candidate(candidate_id, "candidate.needs_user_confirmation", receipt=rec, reason=reason, root=root)

    if writer is None:
        return {"ok": False, "error": "writer_required", "candidate_id": candidate_id, "reason": "actual promotion requires injected writer"}
    if hasattr(writer, "write"):
        rec = writer.write(candidate)  # type: ignore[union-attr]
    else:
        rec = writer(candidate)  # type: ignore[misc]
    if not isinstance(rec, dict):
        return {"ok": False, "error": "invalid_writer_receipt", "candidate_id": candidate_id}
    rec.setdefault("action", "promoted")
    rec.setdefault("target", candidate.final_sink)
    return transition_candidate(candidate_id, "candidate.promoted", receipt=rec, reason=reason, root=root)
