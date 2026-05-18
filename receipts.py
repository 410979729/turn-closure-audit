from __future__ import annotations

from typing import Any

from .clock import now_iso

VALID_RECEIPT_ACTIONS = {
    "promoted",
    "merged",
    "rejected_noise",
    "rejected_temporary",
    "rejected_sensitive",
    "needs_user_confirmation",
    "expired",
    "dry_run",
    "already_satisfied",
}


def receipt(
    action: str,
    *,
    provider: str = "turn-closure-audit",
    target: str = "",
    reason: str = "",
    id: str = "",
    at: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    if action not in VALID_RECEIPT_ACTIONS:
        raise ValueError(f"invalid receipt action: {action}")
    data: dict[str, Any] = {"action": action, "at": at or now_iso()}
    if provider:
        data["provider"] = provider
    if target:
        data["target"] = target
    if id:
        data["id"] = id
    if reason:
        data["reason"] = reason
    data.update({key: value for key, value in extra.items() if value is not None and value != ""})
    return data


def promotion_receipt(*, provider: str, target: str, id: str, at: str | None = None, **extra: Any) -> dict[str, Any]:
    return receipt("promoted", provider=provider, target=target, id=id, at=at, **extra)


def merge_receipt(*, target: str, target_id: str, provider: str = "scope-recall", at: str | None = None, **extra: Any) -> dict[str, Any]:
    return receipt("merged", provider=provider, target=target, target_id=target_id, at=at, **extra)


def rejection_receipt(action: str, *, reason: str, at: str | None = None, **extra: Any) -> dict[str, Any]:
    if not action.startswith("rejected_") and action not in {"needs_user_confirmation", "expired"}:
        raise ValueError(f"invalid rejection action: {action}")
    return receipt(action, reason=reason, at=at, **extra)
