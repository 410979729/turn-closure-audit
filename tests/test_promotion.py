from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_package():
    module_name = f"turn_closure_audit_promotion_test_{id(object())}"
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
    return (
        import_module(f"{package_name}.candidate_schema"),
        import_module(f"{package_name}.candidate_ledger"),
        import_module(f"{package_name}.promotion"),
        import_module(f"{package_name}.receipts"),
    )


def candidate(schema, *, content: str, final_sink="user", risk="low", classification="user-preference-or-boundary"):
    return schema.CandidateRecord.from_dict(
        {
            "record_id": content,
            "session_id": "session-1",
            "created_at": "2026-05-17T00:00:00+00:00",
            "updated_at": "2026-05-17T00:00:00+00:00",
            "status": "pending",
            "classification": classification,
            "final_sink": final_sink,
            "risk": risk,
            "confidence": 0.9,
            "candidate_content": content,
            "evidence_summary": content,
            "decision_reason": "awaiting review",
        }
    )


def test_receipt_helpers_validate_actions(modules):
    _schema, _ledger, _promotion, receipts = modules

    rec = receipts.promotion_receipt(provider="scope-recall", target="user", id="mem-1", scope_mode="shared")

    assert rec["action"] == "promoted"
    assert rec["provider"] == "scope-recall"
    assert rec["scope_mode"] == "shared"
    with pytest.raises(ValueError):
        receipts.receipt("unknown")


def test_dry_run_buckets_default_rules(modules):
    schema, _ledger, promotion, _receipts = modules
    candidates = [
        candidate(schema, content="Remember that Joy prefers concise summaries", final_sink="user", risk="low"),
        candidate(schema, content="Workflow: first inspect, then patch, then verify", final_sink="skill", risk="medium", classification="task-outcome-or-diagnostic"),
        candidate(schema, content="Knowledge: release gate requires pytest", final_sink="knowledge", risk="medium", classification="governance-or-knowledge"),
        candidate(schema, content="Current port 443 is open right now", final_sink="ops", risk="medium"),
        candidate(schema, content="token-shaped credential placeholder", final_sink="user", risk="medium"),
        candidate(schema, content="Joy now prefers X instead of Y", final_sink="user", risk="low"),
        candidate(schema, content="Remember existing preference", final_sink="user", risk="low"),
    ]

    report = promotion.dry_run_promotion(candidates, existing_memories=[{"id": "mem-existing", "content": "Remember existing preference"}])

    assert len(report["would_promote"]) == 1
    assert len(report["suggest_skill"]) == 1
    assert len(report["suggest_knowledge"]) == 1
    assert len(report["would_reject"]) == 2
    assert len(report["conflicts"]) == 1
    assert len(report["already_satisfied"]) == 1


def test_promote_candidate_is_idempotent_and_requires_injected_writer(modules, tmp_path):
    schema, ledger, promotion, _receipts = modules
    item = candidate(schema, content="Remember that Joy prefers concise summaries", final_sink="user", risk="low")
    ledger.append_candidate_created(item, root=tmp_path)

    no_writer = promotion.promote_candidate(item.candidate_id, root=tmp_path, dry_run=False, allow_write=True)
    writer = promotion.InMemoryPromotionWriter()
    first = promotion.promote_candidate(item.candidate_id, root=tmp_path, dry_run=False, allow_write=True, writer=writer)
    second = promotion.promote_candidate(item.candidate_id, root=tmp_path, dry_run=False, allow_write=True, writer=writer)

    assert no_writer["error"] == "writer_required"
    assert first["status"] == "promoted"
    assert len(writer.writes) == 1
    assert second["deduped"] is True
    assert second["status"] == "promoted"
    assert len(writer.writes) == 1


def test_promote_candidate_rejections_and_merge_are_terminal(modules, tmp_path):
    schema, ledger, promotion, _receipts = modules
    temp = candidate(schema, content="Current service is running right now", final_sink="ops", risk="medium")
    secret = candidate(schema, content="password-shaped credential placeholder", final_sink="user", risk="medium")
    existing = candidate(schema, content="Remember existing preference", final_sink="user", risk="low")
    for item in [temp, secret, existing]:
        ledger.append_candidate_created(item, root=tmp_path)

    temp_result = promotion.promote_candidate(temp.candidate_id, root=tmp_path, dry_run=False, allow_write=True)
    secret_result = promotion.promote_candidate(secret.candidate_id, root=tmp_path, dry_run=False, allow_write=True)
    merge_result = promotion.promote_candidate(
        existing.candidate_id,
        root=tmp_path,
        dry_run=False,
        allow_write=True,
        existing_memories=[{"id": "mem-existing", "content": "Remember existing preference"}],
    )

    assert temp_result["status"] == "rejected_temporary"
    assert secret_result["status"] == "rejected_sensitive"
    assert merge_result["status"] == "merged"
