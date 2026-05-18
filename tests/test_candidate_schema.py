from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_package():
    module_name = f"turn_closure_audit_schema_test_{id(object())}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module_name


@pytest.fixture
def schema():
    from importlib import import_module

    return import_module(f"{_load_package()}.candidate_schema")


def test_candidate_record_roundtrip(schema):
    candidate_id = schema.stable_candidate_id("Remember tea preference", "user", "user-preference-or-boundary")
    candidate = schema.CandidateRecord(
        candidate_id=candidate_id,
        record_id="record-a",
        session_id="session-a",
        created_at="2026-05-17T00:00:00+00:00",
        updated_at="2026-05-17T00:00:00+00:00",
        status="pending",
        classification="user-preference-or-boundary",
        final_sink="user",
        risk="low",
        confidence=0.9,
        candidate_content="Remember tea preference",
        evidence_summary="redacted summary",
        decision_reason="awaiting review",
        source={"plugin": "turn-closure-audit"},
    )

    roundtrip = schema.CandidateRecord.from_dict(candidate.to_dict())

    assert roundtrip == candidate
    assert roundtrip.to_dict()["recommended_sink"] == "user"
    assert roundtrip.to_dict()["candidate_status"] == "pending"


def test_invalid_final_sink_status_and_empty_content_rejected(schema):
    base = {
        "candidate_id": "",
        "record_id": "record-a",
        "session_id": "session-a",
        "created_at": "2026-05-17T00:00:00+00:00",
        "updated_at": "2026-05-17T00:00:00+00:00",
        "status": "pending",
        "classification": "user-preference-or-boundary",
        "final_sink": "user",
        "risk": "low",
        "confidence": 0.9,
        "candidate_content": "Remember tea preference",
        "evidence_summary": "redacted summary",
        "decision_reason": "awaiting review",
    }
    with pytest.raises(ValueError):
        schema.CandidateRecord(**{**base, "final_sink": "memory/day"})
    with pytest.raises(ValueError):
        schema.CandidateRecord(**{**base, "status": "done"})
    with pytest.raises(ValueError):
        schema.CandidateRecord(**{**base, "candidate_content": "   "})


def test_deterministic_id_ignores_record_id_whitespace_and_case(schema):
    one = schema.stable_candidate_id(" Remember   Tea Preference ", "user", "User-Preference-Or-Boundary")
    two = schema.stable_candidate_id("remember tea preference", "user", "user-preference-or-boundary")

    assert one == two

    candidate = schema.CandidateRecord.from_dict(
        {
            "record_id": "record-one",
            "session_id": "session-a",
            "created_at": "2026-05-17T00:00:00+00:00",
            "updated_at": "2026-05-17T00:00:00+00:00",
            "status": "pending",
            "classification": "user-preference-or-boundary",
            "final_sink": "user",
            "risk": "low",
            "confidence": 0.9,
            "candidate_content": " Remember   Tea Preference ",
            "evidence_summary": "redacted summary",
            "decision_reason": "awaiting review",
        }
    )
    same_content_different_record = schema.CandidateRecord.from_dict(
        {**candidate.to_dict(), "record_id": "record-two", "candidate_id": ""}
    )
    assert candidate.candidate_id == same_content_different_record.candidate_id


def test_sink_change_changes_candidate_id(schema):
    one = schema.stable_candidate_id("Remember tea preference", "user", "user-preference-or-boundary")
    two = schema.stable_candidate_id("Remember tea preference", "project", "user-preference-or-boundary")

    assert one != two
