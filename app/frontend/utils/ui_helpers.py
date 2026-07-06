from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any


TIMESTAMP_KEYS = {
    "created_at",
    "updated_at",
    "last_updated",
    "first_indexed",
    "last_indexed",
    "timestamp",
    "time",
}


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone()


def format_local_datetime(value: Any, *, include_seconds: bool = False) -> str:
    dt = _parse_datetime(value)
    if not dt:
        return "—" if value in (None, "") else str(value)

    fmt = "%d %b %Y, %I:%M:%S %p" if include_seconds else "%d %b %Y, %I:%M %p"
    return dt.strftime(fmt).lstrip("0").replace(" 0", " ")


def shorten(value: Any, max_len: int = 28) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _title_case_from_snake(value: str) -> str:
    text = (value or "").replace("_", " ").strip()
    if not text:
        return "Unknown"
    return " ".join(word.capitalize() for word in text.split())


def format_status(value: Any) -> str:
    text = ("" if value is None else str(value)).strip().lower()

    mapping = {
        "ok": "OK",
        "completed": "Completed",
        "complete": "Completed",
        "success": "Success",
        "failed": "Failed",
        "error": "Error",
        "in_progress": "In Progress",
        "inprogress": "In Progress",
        "awaiting_confirmation": "Awaiting Confirmation",
        "waiting_for_confirmation": "Awaiting Confirmation",
        "confirm_required": "Awaiting Confirmation",
        "pending": "Pending",
        "skipped": "Skipped",
        "skipped_no_confirmation": "Skipped",
        "user_not_found": "User Not Found",
        "needs_clarification": "Needs Clarification",
    }

    if text in mapping:
        return mapping[text]

    return _title_case_from_snake(text)


def format_workflow(value: Any) -> str:
    text = ("" if value is None else str(value)).strip().lower()

    mapping = {
        "general_it_request": "General IT Request",
        "password_reset": "Password Reset",
        "account_unlock": "Account Unlock",
        "vpn_reenable": "VPN Re-enable",
        "vpn_issue": "VPN Issue",
        "access_request": "Access Request",
        "device_compliance": "Device Compliance",
        "clarify": "Clarify",
        "general": "General",
    }

    if text in mapping:
        return mapping[text]

    return _title_case_from_snake(text)


def format_label(value: Any) -> str:
    if value is None:
        return "Unknown"

    text = str(value).strip()
    if not text:
        return "Unknown"

    return _title_case_from_snake(text.lower())


def pill(label: str, value: Any, *, tone: str = "neutral") -> str:
    icons = {
        "neutral": "•",
        "success": "✅",
        "warning": "⚠️",
        "danger": "🚨",
        "info": "ℹ️",
        "accent": "✨",
    }
    icon = icons.get(tone, icons["neutral"])
    return f"{icon} **{escape(str(label))}:** {escape(str(value))}  \n"


def format_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []

    for row in records or []:
        if not isinstance(row, dict):
            formatted.append(row)
            continue

        new_row: dict[str, Any] = {}
        for key, value in row.items():
            if key in TIMESTAMP_KEYS or key.endswith("_at") or key.endswith("_time"):
                new_row[key] = format_local_datetime(value)
            else:
                new_row[key] = value
        formatted.append(new_row)

    return formatted