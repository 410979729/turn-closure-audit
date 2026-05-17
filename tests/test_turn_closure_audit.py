from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
HERMES_HOME_ROOT = Path(__file__).resolve().parents[3]
HERMES_AGENT_ROOT = HERMES_HOME_ROOT / "hermes-agent"

if str(HERMES_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_AGENT_ROOT))


def _load_plugin_module():
    module_name = f"turn_closure_audit_test_{id(object())}"
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_DIR / "__init__.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    module = _load_plugin_module()
    for loaded in [module.paths, module.events]:
        monkeypatch.setattr(loaded, "get_hermes_home", lambda: tmp_path, raising=False)
    module.TURN_STATE.clear()
    return module


def test_preview_redacts_sensitive_values(plugin):
    preview = plugin.preview(
        {
            "token": "public-test-token",
            "nested": {"Authorization": "Bearer public-test-bearer"},
            "note": "暗号: PUBLIC-TEST-CODE",
        }
    )

    assert "[REDACTED]" in preview
    assert "public-test-token" not in preview
    assert "public-test-bearer" not in preview
    assert "PUBLIC-TEST-CODE" not in preview


def test_extract_write_event_keeps_only_retention_patch_paths(plugin):
    event = plugin.extract_write_event(
        "patch",
        {
            "mode": "patch",
            "patch": "\n".join(
                [
                    "*** Update File: knowledge/review/foo.md",
                    "@@",
                    "+new line",
                    "*** Update File: src/app.py",
                    "@@",
                    "+ignored",
                ]
            ),
        },
        {"success": True},
    )

    assert event == {
        "kind": "knowledge_write",
        "tool": "patch",
        "path": "knowledge/review/foo.md",
        "paths": ["knowledge/review/foo.md"],
    }


def test_on_session_end_writes_audit_daily_note_and_review_candidate(plugin):
    plugin.on_post_llm_call(
        session_id="session-governance",
        user_message="请把这个结论沉淀到知识库，并注意边界。",
        assistant_response="我会先 review 风险，再做知识沉淀。",
        model="gpt-test",
        platform="telegram",
    )

    plugin.on_session_end(
        session_id="session-governance",
        completed=True,
        interrupted=False,
        model="gpt-test",
        platform="telegram",
    )

    audit_rows = [json.loads(line) for line in plugin.audit_log_path().read_text(encoding="utf-8").splitlines()]
    assert len(audit_rows) == 1
    record = audit_rows[0]
    assert record["status"] == "judged_not_written_candidate"
    assert record["candidate"] is True
    assert record["classification"] in {"user-preference-or-boundary", "governance-or-knowledge"}

    day = record["judged_at"][:10]
    daily_note = plugin.memory_day_path(day).read_text(encoding="utf-8")
    assert "## 自动沉淀记录" in daily_note
    assert record["record_id"] in daily_note
    assert "knowledge/review candidate" in daily_note

    candidate_rows = [
        json.loads(line)
        for line in plugin.review_candidate_path(day).read_text(encoding="utf-8").splitlines()
    ]
    assert len(candidate_rows) == 1
    assert candidate_rows[0]["record_id"] == record["record_id"]


def test_latest_snapshot_sanitizes_session_id_and_stays_under_latest_dir(plugin):
    session_id = "../../outside/probe"
    plugin.on_post_llm_call(
        session_id=session_id,
        user_message="hello",
        assistant_response="world",
        model="gpt-test",
        platform="telegram",
    )
    plugin.on_session_end(
        session_id=session_id,
        completed=True,
        interrupted=False,
        model="gpt-test",
        platform="telegram",
    )

    latest_files = list(plugin.latest_dir().glob("*.json"))
    assert len(latest_files) == 1
    assert latest_files[0].parent == plugin.latest_dir()
    assert latest_files[0].name == f"{plugin.safe_session_filename(session_id)}.json"
    assert not (plugin.paths.get_hermes_home() / "outside" / "probe.json").exists()



def test_memory_write_event_marks_turn_as_written_and_redacts_preview(plugin):
    plugin.on_post_tool_call(
        tool_name="memory",
        args={"action": "add", "target": "user", "content": "暗号: PUBLIC-TEST-CODE"},
        result={"success": True},
        session_id="session-written",
    )
    plugin.on_post_llm_call(
        session_id="session-written",
        user_message="记住我的偏好",
        assistant_response="好的，我记下了。",
        model="gpt-test",
        platform="telegram",
    )

    plugin.on_session_end(
        session_id="session-written",
        completed=True,
        interrupted=False,
        model="gpt-test",
        platform="telegram",
    )

    audit_rows = [json.loads(line) for line in plugin.audit_log_path().read_text(encoding="utf-8").splitlines()]
    record = audit_rows[-1]
    assert record["status"] == "judged_written"
    assert record["write_targets"] == ["user"]
    assert record["writes"][0]["kind"] == "memory"
    assert record["writes"][0]["content_preview"] == "暗号: [REDACTED]"
