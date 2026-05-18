from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_package():
    module_name = f"turn_closure_audit_ledger_test_{id(object())}"
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
def modules():
    from importlib import import_module

    package_name = _load_package()
    return import_module(f"{package_name}.candidate_schema"), import_module(f"{package_name}.candidate_ledger")


def _candidate(schema, content="Remember stable tea preference", created_at="2026-05-16T00:00:00+00:00"):
    return schema.CandidateRecord.from_dict(
        {
            "record_id": "record-1",
            "session_id": "session-1",
            "created_at": created_at,
            "updated_at": created_at,
            "status": "pending",
            "classification": "user-preference-or-boundary",
            "final_sink": "user",
            "risk": "low",
            "confidence": 0.9,
            "candidate_content": content,
            "evidence_summary": "redacted summary",
            "decision_reason": "awaiting review",
        }
    )


def test_build_review_candidate_adds_status_sink_risk_confidence_and_receipt_slot(modules):
    schema, _ledger = modules
    record = {
        "candidate": True,
        "record_id": "record-1",
        "session_id": "session-1",
        "classification": "user-preference-or-boundary",
        "candidate_reason": "user message says remember preference",
        "recommended_sinks": ["memory/day", "knowledge/review candidate"],
        "user_preview": "记住：Joy prefers durable review receipts.",
        "assistant_preview": "Understood.",
        "platform": "telegram",
        "tool_events": 0,
        "judged_at": "2026-05-17T00:00:00+00:00",
    }

    candidate = schema.build_review_candidate(record)

    assert candidate is not None
    assert candidate.candidate_id == schema.stable_candidate_id(candidate.candidate_content, "user", "user-preference-or-boundary")
    assert candidate.status == "pending"
    assert candidate.final_sink == "user"
    assert candidate.recommended_sink == "user"
    assert candidate.risk == "low"
    assert candidate.confidence >= 0.8
    assert candidate.receipt is None
    assert candidate.source["user_preview"] == "记住：Joy prefers durable review receipts."
    assert candidate.to_dict()["candidate_content"]



def test_append_and_materialize_one_pending_candidate(modules, tmp_path):
    schema, ledger = modules
    candidate = _candidate(schema)

    result = ledger.append_candidate_created(candidate, root=tmp_path)
    loaded = ledger.load_events(root=tmp_path)
    materialized = ledger.materialize_candidates(loaded)

    assert result["deduped"] is False
    assert len(loaded) == 1
    assert materialized[candidate.candidate_id].status == "pending"


def test_transition_pending_to_promoted(modules, tmp_path):
    schema, ledger = modules
    candidate = _candidate(schema)
    ledger.append_candidate_created(candidate, root=tmp_path)

    result = ledger.transition_candidate(
        candidate.candidate_id,
        "candidate.promoted",
        receipt={"action": "promoted", "provider": "fake", "target": "user", "id": "mem-1"},
        reason="opt-in promotion",
        root=tmp_path,
    )
    materialized = ledger.materialize_candidates(ledger.load_events(root=tmp_path))

    assert result["status"] == "promoted"
    assert materialized[candidate.candidate_id].status == "promoted"
    assert materialized[candidate.candidate_id].receipt["id"] == "mem-1"


def test_transition_with_same_timestamp_materializes_after_creation(modules, tmp_path):
    schema, ledger = modules
    created_at = "2026-05-18T10:29:48+08:00"
    candidate = _candidate(schema, created_at=created_at)
    ledger.append_candidate_created(candidate, root=tmp_path)

    result = ledger.transition_candidate(
        candidate.candidate_id,
        "candidate.promoted",
        at=created_at,
        receipt={"action": "promoted", "provider": "fake", "target": "user", "id": "mem-1"},
        reason="opt-in promotion",
        root=tmp_path,
    )
    materialized = ledger.materialize_candidates(ledger.load_events(root=tmp_path))

    assert result["status"] == "promoted"
    assert materialized[candidate.candidate_id].status == "promoted"
    assert materialized[candidate.candidate_id].receipt["id"] == "mem-1"


def test_duplicate_creation_is_idempotent(modules, tmp_path):
    schema, ledger = modules
    candidate = _candidate(schema)

    first = ledger.append_candidate_created(candidate, root=tmp_path)
    second = ledger.append_candidate_created(candidate, root=tmp_path)

    assert first["deduped"] is False
    assert second["deduped"] is True
    assert len(ledger.load_events(root=tmp_path)) == 1


def test_terminal_transition_is_explicit_noop(modules, tmp_path):
    schema, ledger = modules
    candidate = _candidate(schema)
    ledger.append_candidate_created(candidate, root=tmp_path)
    ledger.transition_candidate(candidate.candidate_id, "candidate.rejected", status="rejected_noise", receipt={"action": "rejected_noise"}, root=tmp_path)

    result = ledger.transition_candidate(candidate.candidate_id, "candidate.promoted", receipt={"action": "promoted"}, root=tmp_path)

    assert result["deduped"] is True
    assert result["terminal"] is True
    assert result["status"] == "rejected_noise"
    assert len(ledger.load_events(root=tmp_path)) == 2


def test_pending_report_counts_overdue_and_today_terminals(modules, tmp_path):
    schema, ledger = modules
    old_candidate = _candidate(schema, content="Remember old tea preference", created_at="2026-05-16T00:00:00+00:00")
    new_candidate = _candidate(schema, content="Remember new tea preference", created_at="2026-05-17T23:00:00+00:00")
    promoted = _candidate(schema, content="Remember promoted preference", created_at="2026-05-17T00:00:00+00:00")
    for candidate in [old_candidate, new_candidate, promoted]:
        ledger.append_candidate_created(candidate, root=tmp_path)
    ledger.transition_candidate(promoted.candidate_id, "candidate.promoted", receipt={"action": "promoted"}, at="2026-05-18T01:00:00+00:00", root=tmp_path)

    report = ledger.pending_report(now="2026-05-18T01:00:00+00:00", root=tmp_path)

    assert report["pending_total"] == 2
    assert report["pending_over_24h"] == 1
    assert report["promoted_today"] == 1
    assert report["oldest_pending"]["candidate_id"] == old_candidate.candidate_id


def test_candidate_receipt_marks_terminal_status_without_mutating_original(modules):
    _schema, ledger = modules
    candidate = {
        "candidate_id": "tcand_demo",
        "status": "pending",
        "receipt": None,
    }

    updated = ledger.attach_receipt(
        candidate,
        status="promoted",
        receipt={"provider": "scope-recall", "target": "user", "id": "mem-1"},
        reason="low-risk explicit preference promoted",
    )

    assert candidate["status"] == "pending"
    assert updated["status"] == "promoted"
    assert updated["candidate_status"] == "promoted"
    assert updated["receipt"]["provider"] == "scope-recall"
    assert updated["decision_reason"] == "low-risk explicit preference promoted"
    assert ledger.candidate_is_terminal(updated)
