from __future__ import annotations

import json
from typing import Any

from .candidate_schema import CandidateRecord, build_review_candidate


def _coerce_candidate(item: Any, *, turn: dict[str, Any], index: int = 0) -> CandidateRecord | None:
    if isinstance(item, CandidateRecord):
        return item
    if not isinstance(item, dict):
        return None
    payload = dict(item)
    payload.setdefault("candidate", True)
    payload.setdefault("record_id", turn.get("record_id") or f"semantic-{index}")
    payload.setdefault("session_id", turn.get("session_id") or "")
    payload.setdefault("judged_at", turn.get("judged_at") or turn.get("created_at") or "")
    payload.setdefault("platform", turn.get("platform") or "")
    payload.setdefault("tool_events", turn.get("tool_events") or 0)
    if "candidate_content" in payload and "content" not in payload:
        payload["content"] = payload["candidate_content"]
    if "final_sink" in payload and "recommended_sink" not in payload:
        payload["recommended_sink"] = payload["final_sink"]
    try:
        if payload.get("candidate_id") and payload.get("final_sink") and payload.get("candidate_content"):
            return CandidateRecord.from_dict(payload)
        return build_review_candidate(payload)
    except ValueError:
        return None


def _extract_model_payload(result: Any) -> Any:
    if isinstance(result, str):
        stripped = result.strip()
        if not stripped:
            return []
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return []
    if isinstance(result, dict) and "candidates" in result:
        return result["candidates"]
    return result


def extract_semantic_candidates(turn: dict[str, Any], *, model_client=None) -> list[CandidateRecord]:
    """Return redacted structured semantic candidates. No writes occur here.

    ``model_client`` is injected by callers/tests. This module deliberately does
    not select, configure, or switch providers/models. A fake model can return a
    list/dict/JSON string with candidate records for deterministic tests.
    """

    if model_client is None:
        fallback = build_review_candidate({**turn, "candidate": bool(turn.get("candidate", True))})
        return [fallback] if fallback is not None else []

    if hasattr(model_client, "extract_candidates"):
        raw = model_client.extract_candidates(turn)
    elif callable(model_client):
        raw = model_client(turn)
    else:
        raise TypeError("model_client must be callable or expose extract_candidates(turn)")

    payload = _extract_model_payload(raw)
    if isinstance(payload, dict):
        payload = payload.get("candidates", [])
    if not isinstance(payload, list):
        return []
    candidates: list[CandidateRecord] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        candidate = _coerce_candidate(item, turn=turn, index=index)
        if candidate is None or candidate.candidate_id in seen:
            continue
        seen.add(candidate.candidate_id)
        candidates.append(candidate)
    return candidates
