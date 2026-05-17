from __future__ import annotations

from typing import Any, Dict, List

PREFERENCE_HINTS = (
    "记住",
    "别再",
    "不要",
    "必须",
    "偏好",
    "希望",
    "以后",
    "边界",
    "纠正",
    "暗号",
)
GOVERNANCE_HINTS = (
    "沉淀",
    "知识库",
    "记忆库",
    "manual mapping",
    "review",
    "acceptance",
    "risk",
    "真值",
    "规则",
    "流程",
    "机制",
    "自动",
)
OUTCOME_HINTS = (
    "根因",
    "结论",
    "验收",
    "风险",
    "修复",
    "升级",
    "验证",
    "排查",
    "故障",
)


def contains_any(text: str, hints: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in hints)


def classify_candidate(state: Dict[str, Any], writes: List[Dict[str, Any]], interrupted: bool) -> Dict[str, Any]:
    user_preview = state.get("user_preview", "")
    assistant_preview = state.get("assistant_preview", "")
    combined = f"{user_preview}\n{assistant_preview}"
    tool_events = int(state.get("tool_events", 0))

    classification = "routine"
    candidate = False
    candidate_reason = ""
    recommended_sinks = ["memory/day"]

    if writes:
        return {
            "classification": "already-written",
            "candidate": False,
            "candidate_reason": "retention writes already observed during this turn",
            "recommended_sinks": recommended_sinks,
        }

    if interrupted:
        classification = "interrupted-turn"
        candidate = True
        candidate_reason = "turn ended abnormally and should remain reviewable"
    elif contains_any(user_preview, PREFERENCE_HINTS):
        classification = "user-preference-or-boundary"
        candidate = True
        candidate_reason = "user message contains preference/boundary style hints"
    elif contains_any(combined, GOVERNANCE_HINTS):
        classification = "governance-or-knowledge"
        candidate = True
        candidate_reason = "turn discusses governance / memory / knowledge mechanics"
    elif tool_events >= 5 or contains_any(combined, OUTCOME_HINTS):
        classification = "task-outcome-or-diagnostic"
        candidate = True
        candidate_reason = "turn looks like a substantive outcome/diagnostic that may deserve manual promotion"

    if candidate:
        recommended_sinks.append("knowledge/review candidate")

    return {
        "classification": classification,
        "candidate": candidate,
        "candidate_reason": candidate_reason or "no special candidate conditions matched",
        "recommended_sinks": recommended_sinks,
    }


def status_from_state(
    completed: bool,
    interrupted: bool,
    writes: List[Dict[str, Any]],
    candidate: bool,
) -> str:
    if interrupted and not completed:
        return "judged_interrupted"
    if writes:
        return "judged_written"
    if candidate:
        return "judged_not_written_candidate"
    return "judged_not_written"


def reason_from_status(status: str, writes: List[Dict[str, Any]], candidate_reason: str) -> str:
    if status == "judged_written":
        kinds = sorted({str(w.get('kind', 'write')) for w in writes})
        return f"observed {len(writes)} retention write event(s): {', '.join(kinds)}"
    if status == "judged_interrupted":
        return "turn ended before normal completion; audit record preserved as interrupted"
    if status == "judged_not_written_candidate":
        return candidate_reason or "candidate detected but no retention write events were observed"
    return "no retention write events observed during this turn"
