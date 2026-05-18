from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_package():
    module_name = f"turn_closure_audit_distillation_test_{id(object())}"
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


def test_extract_semantic_candidates_with_fake_model_returns_records_only():
    from importlib import import_module

    package_name = _load_package()
    distillation = import_module(f"{package_name}.distillation")
    schema = import_module(f"{package_name}.candidate_schema")

    class FakeModel:
        def extract_candidates(self, turn):
            return {
                "candidates": [
                    {
                        "candidate_content": "Remember that Joy prefers concise summaries",
                        "classification": "user-preference-or-boundary",
                        "final_sink": "user",
                        "risk": "low",
                        "confidence": 0.91,
                        "evidence_summary": "redacted model summary",
                        "decision_reason": "fake model output",
                    }
                ]
            }

    result = distillation.extract_semantic_candidates(
        {
            "record_id": "record-1",
            "session_id": "session-1",
            "judged_at": "2026-05-17T00:00:00+00:00",
            "platform": "telegram",
        },
        model_client=FakeModel(),
    )

    assert len(result) == 1
    assert isinstance(result[0], schema.CandidateRecord)
    assert result[0].candidate_content == "Remember that Joy prefers concise summaries"
    assert result[0].final_sink == "user"


def test_extract_semantic_candidates_without_model_uses_no_write_fallback():
    from importlib import import_module

    package_name = _load_package()
    distillation = import_module(f"{package_name}.distillation")

    result = distillation.extract_semantic_candidates(
        {
            "candidate": True,
            "record_id": "record-1",
            "session_id": "session-1",
            "judged_at": "2026-05-17T00:00:00+00:00",
            "classification": "user-preference-or-boundary",
            "user_preview": "记住：Joy prefers concise summaries",
            "candidate_reason": "user message says remember",
        }
    )

    assert len(result) == 1
    assert result[0].candidate_id.startswith("tcand_")
