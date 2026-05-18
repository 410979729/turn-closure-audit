from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import Any, Literal

CandidateStatus = Literal[
    "pending",
    "promoted",
    "merged",
    "rejected_noise",
    "rejected_temporary",
    "rejected_sensitive",
    "needs_user_confirmation",
    "expired",
]

FinalSink = Literal[
    "user",
    "memory",
    "project",
    "ops",
    "skill",
    "knowledge",
    "discard",
    "ask_user",
]

RiskLevel = Literal["low", "medium", "high"]

EventType = Literal[
    "candidate.created",
    "candidate.classified",
    "candidate.promote.dry_run",
    "candidate.promoted",
    "candidate.merged",
    "candidate.rejected",
    "candidate.needs_user_confirmation",
    "candidate.expired",
]

VALID_FINAL_SINKS: set[str] = {"user", "memory", "project", "ops", "skill", "knowledge", "discard", "ask_user"}
VALID_STATUSES: set[str] = {
    "pending",
    "promoted",
    "merged",
    "rejected_noise",
    "rejected_temporary",
    "rejected_sensitive",
    "needs_user_confirmation",
    "expired",
}
TERMINAL_STATUSES: set[str] = VALID_STATUSES - {"pending"}
VALID_RISKS: set[str] = {"low", "medium", "high"}
VALID_EVENT_TYPES: set[str] = {
    "candidate.created",
    "candidate.classified",
    "candidate.promote.dry_run",
    "candidate.promoted",
    "candidate.merged",
    "candidate.rejected",
    "candidate.needs_user_confirmation",
    "candidate.expired",
}

EXPLICIT_PREFERENCE_HINTS = ("remember", "记住", "以后", "always", "from now on")
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


def normalize_candidate_content(text: str) -> str:
    """Normalize text for deterministic candidate identity.

    Candidate identity intentionally ignores provenance such as ``record_id``.
    It is based on the concise candidate payload plus the intended final sink
    and classification, so the same memory suggested from two turns dedupes.
    """

    return " ".join(str(text or "").strip().casefold().split())


def stable_candidate_id(candidate_content: str, final_sink: str, classification: str) -> str:
    if not normalize_candidate_content(candidate_content):
        raise ValueError("candidate_content is required for stable candidate_id")
    if final_sink not in VALID_FINAL_SINKS:
        raise ValueError(f"invalid final_sink: {final_sink}")
    payload = "|".join(
        [
            normalize_candidate_content(candidate_content),
            str(final_sink).strip().casefold(),
            " ".join(str(classification or "").strip().casefold().split()),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"tcand_{digest}"


@dataclass(frozen=True)
class CandidateDecision:
    final_sink: str
    risk: str
    confidence: float

    @property
    def recommended_sink(self) -> str:
        return self.final_sink


@dataclass
class CandidateRecord:
    candidate_id: str
    record_id: str
    session_id: str
    created_at: str
    updated_at: str
    status: str
    classification: str
    final_sink: str
    risk: str
    confidence: float
    candidate_content: str
    evidence_summary: str
    decision_reason: str
    source: dict[str, Any] = field(default_factory=dict)
    receipt: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid candidate status: {self.status}")
        if self.final_sink not in VALID_FINAL_SINKS:
            raise ValueError(f"invalid final_sink: {self.final_sink}")
        if self.risk not in VALID_RISKS:
            raise ValueError(f"invalid risk: {self.risk}")
        if not normalize_candidate_content(self.candidate_content):
            raise ValueError("candidate_content is required")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        expected = stable_candidate_id(self.candidate_content, self.final_sink, self.classification)
        if self.candidate_id and self.candidate_id != expected:
            raise ValueError("candidate_id does not match candidate_content/final_sink/classification")
        if not self.candidate_id:
            self.candidate_id = expected

    @property
    def recommended_sink(self) -> str:
        """Deprecated compatibility alias for older review JSONL readers."""

        return self.final_sink

    @property
    def candidate_status(self) -> str:
        return self.status

    def with_updates(self, **changes: Any) -> "CandidateRecord":
        return replace(self, **changes)

    def to_dict(self, *, compatibility: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "record_id": self.record_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "candidate_status": self.status,
            "classification": self.classification,
            "final_sink": self.final_sink,
            "risk": self.risk,
            "confidence": float(self.confidence),
            "candidate_content": self.candidate_content,
            "evidence_summary": self.evidence_summary,
            "decision_reason": self.decision_reason,
            "source": dict(self.source or {}),
            "receipt": self.receipt,
        }
        if compatibility:
            data["recommended_sink"] = self.final_sink
            data.setdefault("recommended_sinks", [self.final_sink])
            data.setdefault("content", self.candidate_content)
            data.setdefault("candidate_reason", self.decision_reason)
            data.setdefault("evidence", dict(self.source or {}))
        return data

    def to_json(self) -> dict[str, Any]:
        return self.to_dict(compatibility=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateRecord":
        final_sink = str(data.get("final_sink") or data.get("recommended_sink") or "")
        status = str(data.get("candidate_status") or data.get("status") or "pending")
        candidate_content = str(data.get("candidate_content") or data.get("content") or "")
        classification = str(data.get("classification") or "routine")
        candidate_id = str(data.get("candidate_id") or "")
        if not candidate_id and candidate_content and final_sink:
            candidate_id = stable_candidate_id(candidate_content, final_sink, classification)
        return cls(
            candidate_id=candidate_id,
            record_id=str(data.get("record_id") or ""),
            session_id=str(data.get("session_id") or ""),
            created_at=str(data.get("created_at") or data.get("judged_at") or data.get("at") or ""),
            updated_at=str(data.get("updated_at") or data.get("created_at") or data.get("judged_at") or data.get("at") or ""),
            status=status,
            classification=classification,
            final_sink=final_sink,
            risk=str(data.get("risk") or "medium"),
            confidence=float(data.get("confidence") if data.get("confidence") is not None else 0.5),
            candidate_content=candidate_content,
            evidence_summary=str(data.get("evidence_summary") or data.get("candidate_reason") or data.get("evidence") or ""),
            decision_reason=str(data.get("decision_reason") or data.get("candidate_reason") or ""),
            source=dict(data.get("source") or data.get("evidence") or {}),
            receipt=data.get("receipt"),
        )


@dataclass
class CandidateEvent:
    event_id: str
    event_type: str
    candidate_id: str
    at: str
    record_id: str = ""
    candidate: dict[str, Any] | None = None
    status: str | None = None
    reason: str = ""
    receipt: dict[str, Any] | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"invalid candidate event_type: {self.event_type}")
        if not self.candidate_id:
            raise ValueError("candidate_id is required")
        if self.status is not None and self.status not in VALID_STATUSES:
            raise ValueError(f"invalid candidate event status: {self.status}")
        if not self.event_id:
            self.event_id = stable_event_id(
                self.event_type,
                self.candidate_id,
                self.at,
                status=self.status,
                reason=self.reason,
                receipt=self.receipt,
            )

    @classmethod
    def new(
        cls,
        event_type: str,
        candidate_id: str,
        at: str,
        *,
        record_id: str = "",
        candidate: CandidateRecord | dict[str, Any] | None = None,
        status: str | None = None,
        reason: str = "",
        receipt: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> "CandidateEvent":
        candidate_payload: dict[str, Any] | None
        if isinstance(candidate, CandidateRecord):
            candidate_payload = candidate.to_dict()
        elif isinstance(candidate, dict):
            candidate_payload = dict(candidate)
        else:
            candidate_payload = None
        return cls(
            event_id="",
            event_type=event_type,
            candidate_id=candidate_id,
            at=at,
            record_id=record_id,
            candidate=candidate_payload,
            status=status,
            reason=reason,
            receipt=receipt,
            details=dict(details or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "candidate_id": self.candidate_id,
            "at": self.at,
            "record_id": self.record_id,
            "candidate": self.candidate,
            "status": self.status,
            "reason": self.reason,
            "receipt": self.receipt,
            "details": dict(self.details or {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateEvent":
        return cls(
            event_id=str(data.get("event_id") or ""),
            event_type=str(data.get("event_type") or ""),
            candidate_id=str(data.get("candidate_id") or ""),
            at=str(data.get("at") or data.get("created_at") or data.get("updated_at") or ""),
            record_id=str(data.get("record_id") or ""),
            candidate=data.get("candidate"),
            status=data.get("candidate_status") or data.get("status"),
            reason=str(data.get("reason") or ""),
            receipt=data.get("receipt"),
            details=dict(data.get("details") or {}),
        )


def stable_event_id(
    event_type: str,
    candidate_id: str,
    at: str,
    *,
    status: str | None = None,
    reason: str = "",
    receipt: dict[str, Any] | None = None,
) -> str:
    payload = repr((event_type, candidate_id, at, status, reason, receipt or {}))
    return "tcevt_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def candidate_is_terminal(candidate: CandidateRecord | dict[str, Any]) -> bool:
    status = candidate.status if isinstance(candidate, CandidateRecord) else str(candidate.get("candidate_status") or candidate.get("status") or "")
    return status in TERMINAL_STATUSES


def decide_candidate(classification: str, interrupted: bool = False, text: str = "") -> CandidateDecision:
    lowered = str(text or "").casefold()
    if interrupted or classification == "interrupted-turn":
        return CandidateDecision("ask_user", "high", 0.9)
    if classification == "user-preference-or-boundary":
        explicit = any(hint in lowered for hint in EXPLICIT_PREFERENCE_HINTS)
        sensitive = any(hint in lowered for hint in SENSITIVE_HINTS)
        return CandidateDecision("user", "low" if explicit and not sensitive else "medium", 0.86 if explicit else 0.82)
    if classification == "governance-or-knowledge":
        return CandidateDecision("knowledge", "medium", 0.78)
    if classification == "task-outcome-or-diagnostic":
        if any(hint in lowered for hint in ("workflow", "procedure", "sop", "流程", "步骤")):
            return CandidateDecision("skill", "medium", 0.76)
        return CandidateDecision("knowledge", "medium", 0.72)
    if classification == "already-written":
        return CandidateDecision("discard", "low", 0.95)
    return CandidateDecision("discard", "low", 0.55)


def _candidate_content_from_record(record: dict[str, Any]) -> str:
    explicit = str(record.get("candidate_content") or record.get("content") or "").strip()
    if explicit:
        return explicit
    user_preview = str(record.get("user_preview") or "").strip()
    assistant_preview = str(record.get("assistant_preview") or "").strip()
    classification = str(record.get("classification") or "routine")
    if classification == "user-preference-or-boundary" and user_preview:
        return f"User preference/boundary: {user_preview}"
    if classification == "interrupted-turn" and user_preview:
        return f"Interrupted turn needing follow-up: {user_preview}"
    if assistant_preview:
        return f"{classification}: {assistant_preview}"
    if user_preview:
        return f"{classification}: {user_preview}"
    return ""


def build_review_candidate(record: dict[str, Any]) -> CandidateRecord | None:
    if not record.get("candidate"):
        return None
    classification = str(record.get("classification") or "routine")
    combined = "\n".join(str(record.get(key) or "") for key in ("user_preview", "assistant_preview", "candidate_reason"))
    decision = decide_candidate(classification, bool(record.get("interrupted")), combined)
    candidate_content = _candidate_content_from_record(record)
    if not normalize_candidate_content(candidate_content):
        return None
    candidate_id = stable_candidate_id(candidate_content, decision.final_sink, classification)
    judged_at = str(record.get("judged_at") or record.get("created_at") or "")
    source = {
        "plugin": "turn-closure-audit",
        "record_id": record.get("record_id", ""),
        "assistant_preview": record.get("assistant_preview", ""),
        "judged_at": judged_at,
        "platform": record.get("platform", ""),
        "tool_events": record.get("tool_events", 0),
        "user_preview": record.get("user_preview", ""),
    }
    evidence_bits = []
    if record.get("candidate_reason"):
        evidence_bits.append(str(record.get("candidate_reason")))
    if record.get("user_preview"):
        evidence_bits.append(f"user={record.get('user_preview')}")
    if record.get("assistant_preview"):
        evidence_bits.append(f"assistant={record.get('assistant_preview')}")
    return CandidateRecord(
        candidate_id=candidate_id,
        record_id=str(record.get("record_id") or ""),
        session_id=str(record.get("session_id") or ""),
        created_at=judged_at,
        updated_at=judged_at,
        status="pending",
        classification=classification,
        final_sink=decision.final_sink,
        risk=decision.risk,
        confidence=decision.confidence,
        candidate_content=candidate_content,
        evidence_summary=" | ".join(evidence_bits)[:500],
        decision_reason="awaiting promotion decision",
        source=source,
        receipt=None,
    )


# Backward-compatible public name used by the first candidate-governance draft.
ReviewCandidate = CandidateRecord
