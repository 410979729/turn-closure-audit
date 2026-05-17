from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import get_hermes_home
from .redaction import preview

WRITE_TOOLS = {"memory", "hindsight_retain", "skill_manage", "write_file", "patch"}
KNOWLEDGE_PREFIXES = ("knowledge/", "memory/", "memories/")
MEMORY_MUTATIONS = {"add", "replace", "remove"}
SKILL_MUTATIONS = {"create", "patch", "edit", "delete", "write_file", "remove_file"}


def normalized_relative_text(path_value: str) -> str:
    text = path_value.replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


def is_retention_path(path_value: Any) -> bool:
    if not isinstance(path_value, str) or not path_value.strip():
        return False
    try:
        p = Path(path_value).expanduser()
    except Exception:
        return False

    hermes_home = get_hermes_home().resolve()
    raw_relative = normalized_relative_text(path_value)
    if raw_relative.startswith(KNOWLEDGE_PREFIXES):
        return True

    if not p.is_absolute():
        p = hermes_home / p

    try:
        resolved = p.resolve(strict=False)
    except Exception:
        resolved = p

    try:
        rel = resolved.relative_to(hermes_home)
    except Exception:
        return False

    rel_text = rel.as_posix()
    return rel_text.startswith(KNOWLEDGE_PREFIXES)


def extract_patch_paths(patch_text: Any) -> List[str]:
    if not isinstance(patch_text, str) or not patch_text.strip():
        return []

    paths: List[str] = []
    for line in patch_text.splitlines():
        for prefix in ("*** Add File: ", "*** Update File: ", "*** Delete File: "):
            if line.startswith(prefix):
                path = line[len(prefix):].strip()
                if path:
                    paths.append(path)
                break
    return paths


def result_dict(result: Any) -> Optional[Dict[str, Any]]:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        text = result.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = __import__("json").loads(text)
            except Exception:
                return None
            if isinstance(parsed, dict):
                return parsed
    return None


def tool_call_succeeded(result: Any) -> bool:
    payload = result_dict(result)
    if payload is None:
        return True

    if payload.get("success") is False:
        return False
    if payload.get("ok") is False:
        return False
    if payload.get("error"):
        return False
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return False
    if isinstance(errors, str) and errors.strip():
        return False
    if isinstance(payload.get("exit_code"), int) and int(payload.get("exit_code", 0)) != 0:
        return False

    status = str(payload.get("status", "") or "").strip().lower()
    if status in {"error", "failed", "failure"}:
        return False
    return True


def extract_write_event(tool_name: str, args: Optional[Dict[str, Any]], result: Any) -> Optional[Dict[str, Any]]:
    if tool_name not in WRITE_TOOLS:
        return None
    if not tool_call_succeeded(result):
        return None
    safe_args = args if isinstance(args, dict) else {}

    if tool_name == "memory":
        action = str(safe_args.get("action", "") or "")
        if action not in MEMORY_MUTATIONS:
            return None
        return {
            "kind": "memory",
            "action": action,
            "target": safe_args.get("target", ""),
            "content_preview": preview(safe_args.get("content", ""), 160),
        }

    if tool_name == "hindsight_retain":
        return {
            "kind": "hindsight_retain",
            "context": preview(safe_args.get("context", ""), 120),
            "content_preview": preview(safe_args.get("content", ""), 160),
            "tags": safe_args.get("tags", []),
        }

    if tool_name == "skill_manage":
        action = str(safe_args.get("action", "") or "")
        if action not in SKILL_MUTATIONS:
            return None
        return {
            "kind": "skill_manage",
            "action": action,
            "name": safe_args.get("name", ""),
            "file_path": safe_args.get("file_path", ""),
        }

    if tool_name == "write_file":
        path = safe_args.get("path", "")
        if is_retention_path(path):
            return {"kind": "knowledge_write", "tool": "write_file", "path": path}
        return None

    if tool_name == "patch":
        mode = str(safe_args.get("mode", "replace") or "replace")
        if mode == "patch":
            matched_paths = [path for path in extract_patch_paths(safe_args.get("patch", "")) if is_retention_path(path)]
            if matched_paths:
                return {
                    "kind": "knowledge_write",
                    "tool": "patch",
                    "path": matched_paths[0],
                    "paths": matched_paths,
                }
            return None
        path = safe_args.get("path", "")
        if is_retention_path(path):
            return {"kind": "knowledge_write", "tool": "patch", "path": path}
        return None

    return None
