from __future__ import annotations

import json
import re
from typing import Any


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def redact_sensitive_text(text: str) -> str:
    if not text:
        return text

    redacted = text
    redacted = re.sub(
        r"(?i)(?<![A-Za-z0-9_])(api[_ -]?key|secret|token|password|passwd|passcode|暗号|session(?:id)?|cookie)(\s*[:=：]\s*|\s+)([^\s,，;；\"'}\]]+)",
        lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(auth(?:orization)?|set-cookie)\s*[:=：]\s*(bearer\s+[A-Za-z0-9._\-~+/=]+|basic\s+[A-Za-z0-9+/=]+|[^\s,，;；\"'}\]]+)",
        lambda m: f"{m.group(1)}: [REDACTED]",
        redacted,
    )
    redacted = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/=]+", "Bearer [REDACTED]", redacted)
    redacted = re.sub(r"(?i)\bbasic\s+[A-Za-z0-9+/=]+", "Basic [REDACTED]", redacted)
    return redacted


def looks_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.strip().lower()
    compact = lowered.replace("_", "").replace("-", "").replace(" ", "")
    if lowered == "暗号":
        return True
    return compact.startswith((
        "apikey",
        "secret",
        "token",
        "password",
        "passwd",
        "passcode",
        "session",
        "cookie",
        "authorization",
        "setcookie",
    ))


def sanitize_preview_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[Any, Any] = {}
        for key, inner in value.items():
            if looks_sensitive_key(key):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_preview_value(inner)
        return sanitized
    if isinstance(value, list):
        return [sanitize_preview_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_preview_value(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def preview(value: Any, limit: int = 220) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in {"{", "["} and stripped[-1:] in {"}", "]"}:
            try:
                parsed = json.loads(stripped)
            except Exception:
                text = redact_sensitive_text(value)
            else:
                text = json.dumps(sanitize_preview_value(parsed), ensure_ascii=False, sort_keys=True)
        else:
            text = redact_sensitive_text(value)
    else:
        try:
            text = json.dumps(sanitize_preview_value(value), ensure_ascii=False, sort_keys=True)
        except Exception:
            text = redact_sensitive_text(repr(value))
    text = normalize_text(text)
    return text[:limit]
