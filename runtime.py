from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from .classification import classify_candidate, reason_from_status, status_from_state
from .clock import now_iso
from .commands import handle_command
from .events import extract_write_event
from .paths import audit_log_path, latest_dir, memory_day_path, record_id, review_candidate_path, safe_session_filename, session_key
from .redaction import preview
from .storage import append_audit_record, auto_sink, write_latest

TURN_LOCK = threading.Lock()
TURN_STATE: Dict[str, Dict[str, Any]] = {}


def ensure_state(session_id: str) -> Dict[str, Any]:
    key = session_key(session_id)
    with TURN_LOCK:
        state = TURN_STATE.setdefault(
            key,
            {
                "opened_at": now_iso(),
                "writes": [],
                "write_targets": [],
                "tool_events": 0,
                "user_preview": "",
                "assistant_preview": "",
                "platform": "",
                "model": "",
                "judgment_basis": "tool-evidence-plus-auto-routing-v2",
            },
        )
        return state


def drain_state(session_id: str) -> Dict[str, Any]:
    key = session_key(session_id)
    with TURN_LOCK:
        return TURN_STATE.pop(
            key,
            {
                "opened_at": now_iso(),
                "writes": [],
                "write_targets": [],
                "tool_events": 0,
                "user_preview": "",
                "assistant_preview": "",
                "platform": "",
                "model": "",
                "judgment_basis": "tool-evidence-plus-auto-routing-v2",
            },
        )


def on_post_tool_call(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    result: Any = None,
    session_id: str = "",
    **_: Any,
) -> None:
    state = ensure_state(session_id)
    event = extract_write_event(tool_name, args, result)
    with TURN_LOCK:
        state["tool_events"] = int(state.get("tool_events", 0)) + 1
        if event is not None:
            state.setdefault("writes", []).append(event)
            targets = event.get("paths") if isinstance(event.get("paths"), list) else None
            if targets:
                state.setdefault("write_targets", []).extend(str(target) for target in targets if target)
            else:
                target = event.get("target") or event.get("path") or event.get("name") or event.get("kind")
                if target:
                    state.setdefault("write_targets", []).append(str(target))


def on_post_llm_call(
    session_id: str = "",
    user_message: Any = None,
    assistant_response: Any = None,
    model: str = "",
    platform: str = "",
    **_: Any,
) -> None:
    state = ensure_state(session_id)
    with TURN_LOCK:
        state["user_preview"] = preview(user_message)
        state["assistant_preview"] = preview(assistant_response)
        state["model"] = model or state.get("model", "")
        state["platform"] = platform or state.get("platform", "")
        state["judged_at"] = now_iso()


def on_session_end(
    session_id: str = "",
    completed: bool = True,
    interrupted: bool = False,
    model: str = "",
    platform: str = "",
    **_: Any,
) -> None:
    state = drain_state(session_id)
    writes = list(state.get("writes", []) or [])
    judged_at = now_iso()
    classification = classify_candidate(state, writes, interrupted)
    status = status_from_state(completed, interrupted, writes, bool(classification.get("candidate")))
    record = {
        "assistant_preview": state.get("assistant_preview", ""),
        "candidate": bool(classification.get("candidate")),
        "candidate_reason": classification.get("candidate_reason", ""),
        "classification": classification.get("classification", "routine"),
        "completed": bool(completed),
        "interrupted": bool(interrupted),
        "judged_at": judged_at,
        "judgment_basis": state.get("judgment_basis", "tool-evidence-plus-auto-routing-v2"),
        "model": model or state.get("model", ""),
        "opened_at": state.get("opened_at", ""),
        "platform": platform or state.get("platform", ""),
        "reason": reason_from_status(status, writes, classification.get("candidate_reason", "")),
        "recommended_sinks": list(classification.get("recommended_sinks", []) or []),
        "session_id": session_key(session_id),
        "status": status,
        "tool_events": int(state.get("tool_events", 0)),
        "user_preview": state.get("user_preview", ""),
        "write_targets": list(state.get("write_targets", []) or []),
        "writes": writes,
    }
    record["record_id"] = record_id(record["session_id"], record["opened_at"], record["judged_at"])
    record["auto_writes"] = auto_sink(record)
    append_audit_record(record)
    write_latest(session_id, record)


def register(ctx) -> None:
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("post_llm_call", on_post_llm_call)
    ctx.register_hook("on_session_end", on_session_end)
    ctx.register_command(
        "turn-closure",
        handler=handle_command,
        description="Inspect the per-turn closure audit trail.",
        args_hint="[recent|last|status] [N] | path",
    )


__all__ = [
    "TURN_STATE",
    "audit_log_path",
    "drain_state",
    "ensure_state",
    "extract_write_event",
    "handle_command",
    "latest_dir",
    "memory_day_path",
    "on_post_llm_call",
    "on_post_tool_call",
    "on_session_end",
    "preview",
    "register",
    "review_candidate_path",
    "safe_session_filename",
]
