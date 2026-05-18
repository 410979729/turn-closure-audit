from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional

from .candidate_ledger import append_candidate_jsonl
from .candidate_schema import build_review_candidate
from .clock import today_str
from .paths import audit_log_path, display_path, latest_dir, locked_file, memory_day_path, review_candidate_path, safe_session_filename

FILE_LOCK = threading.RLock()


def append_jsonl(path, record: Dict[str, Any]) -> None:
    with FILE_LOCK:
        with locked_file(path) as fh:
            fh.seek(0, 2)
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_latest(session_id: str, record: Dict[str, Any]) -> None:
    target = latest_dir() / f"{safe_session_filename(session_id)}.json"
    with FILE_LOCK:
        with locked_file(target) as fh:
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def append_daily_note(record: Dict[str, Any]) -> Dict[str, Any]:
    day = record.get("judged_at", "")[:10] or today_str()
    path = memory_day_path(day)
    with FILE_LOCK:
        with locked_file(path) as fh:
            record_id = record.get("record_id", "")
            sentinel = f"<!-- turn-closure:{record_id} -->"
            existing = fh.read()
            if sentinel in existing:
                return {"kind": "daily-note", "path": display_path(path), "deduped": True}

            if not existing:
                existing = f"# {day} 日记\n\n## 自动沉淀记录\n"
            elif "## 自动沉淀记录" not in existing:
                if not existing.endswith("\n"):
                    existing += "\n"
                existing += "\n## 自动沉淀记录\n"

            time_label = ""
            judged_at = record.get("judged_at", "")
            if len(judged_at) >= 19:
                time_label = judged_at[11:19]

            recommended = "、".join(record.get("recommended_sinks", []) or ["无"])
            block = (
                f"\n{sentinel}\n"
                f"### {time_label or 'unknown'} | {record.get('status', '')}\n"
                f"- session: `{record.get('session_id', '')}`\n"
                f"- platform/model: `{record.get('platform', '')}` / `{record.get('model', '')}`\n"
                f"- 工具事件: {record.get('tool_events', 0)}\n"
                f"- 用户：{record.get('user_preview', '') or '（空）'}\n"
                f"- 回复：{record.get('assistant_preview', '') or '（空）'}\n"
                f"- 判定：{record.get('reason', '') or '（空）'}\n"
                f"- 推荐落点：{recommended}\n"
            )
            fh.seek(0)
            fh.truncate()
            fh.write(existing.rstrip() + "\n" + block)
            return {"kind": "daily-note", "path": display_path(path), "deduped": False}


def append_review_candidate(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not record.get("candidate"):
        return None

    candidate = build_review_candidate(record)
    if candidate is None:
        return None

    day = record.get("judged_at", "")[:10] or today_str()
    path = review_candidate_path(day)
    review_deduped = False
    with FILE_LOCK:
        with locked_file(path) as fh:
            record_id = str(record.get("record_id", "") or "")
            existing = fh.read()
            if (record_id and record_id in existing) or candidate.candidate_id in existing:
                review_deduped = True
            else:
                append_candidate_jsonl(fh, candidate)

    from .candidate_ledger import append_candidate_created

    ledger_result = append_candidate_created(candidate)
    return {
        "kind": "review-candidate",
        "path": display_path(path),
        "deduped": review_deduped,
        "candidate_id": candidate.candidate_id,
        "candidate_status": candidate.status,
        "final_sink": candidate.final_sink,
        "ledger": ledger_result,
    }


def auto_sink(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    auto_writes: List[Dict[str, Any]] = []
    auto_writes.append(append_daily_note(record))
    maybe_candidate = append_review_candidate(record)
    if maybe_candidate is not None:
        auto_writes.append(maybe_candidate)
    return auto_writes


def append_audit_record(record: Dict[str, Any]) -> None:
    append_jsonl(audit_log_path(), record)
