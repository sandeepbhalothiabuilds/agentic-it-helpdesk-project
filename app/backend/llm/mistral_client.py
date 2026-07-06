from __future__ import annotations

import os
import re
from typing import Any

import requests

from app.backend.config import settings

try:
    import truststore
except Exception:  # pragma: no cover
    truststore = None


MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"


def _use_os_trust_store_session() -> requests.Session:
    session = requests.Session()
    if truststore is not None:
        try:
            truststore.inject_into_ssl()
            print("INFO:app.backend.llm.mistral_client:[MISTRAL] Using OS trust store via truststore")
        except Exception:
            pass
    return session


def _normalize_messages(messages: Any) -> list[dict[str, str]]:
    """
    Accept:
    - a plain string prompt
    - a list of chat messages [{"role": "...", "content": "..."}]
    """
    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]

    if isinstance(messages, list):
        normalized: list[dict[str, str]] = []
        for item in messages:
            if isinstance(item, dict):
                role = str(item.get("role", "user"))
                content = str(item.get("content", ""))
                normalized.append({"role": role, "content": content})
            else:
                normalized.append({"role": "user", "content": str(item)})
        return normalized

    return [{"role": "user", "content": str(messages)}]


def _get_last_user_text(messages: list[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _local_fallback_text(messages: Any) -> str:
    normalized = _normalize_messages(messages)
    text = _get_last_user_text(normalized).strip().lower()

    # Intent classification fallback
    if "password" in text:
        return "password_reset"
    if "unlock" in text or "locked" in text:
        return "account_unlock"
    if "vpn" in text or "remote access" in text:
        return "vpn_reenable"
    if "access" in text or "permission" in text or "role" in text:
        return "access_request"

    # Generic fallback for final response generation
    user_text = _get_last_user_text(normalized)
    return (
        "Dear user,\n\n"
        f"Your request has been processed.\n\n"
        f"Request: {user_text}\n\n"
        f"Thank you,\nIT Service Desk"
    )


def chat_completion(
    messages: Any,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    model: str | None = None,
) -> str:
    """
    Compatible with:
    - chat_completion("some prompt")
    - chat_completion([{"role": "user", "content": "..."}])
    """
    normalized_messages = _normalize_messages(messages)

    if settings.mistral_disable == "1":
        print("[MISTRAL] disabled -> using local fallback")
        return _local_fallback_text(normalized_messages)

    api_key = (settings.mistral_api_key or "").strip()
    if not api_key:
        print("[MISTRAL] no API key -> using local fallback")
        return _local_fallback_text(normalized_messages)

    payload: dict[str, Any] = {
        "model": model or settings.mistral_model,
        "messages": normalized_messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    session = _use_os_trust_store_session()

    try:
        print("[MISTRAL] calling API...")
        response = session.post(
            MISTRAL_API_URL,
            headers=headers,
            json=payload,
            timeout=60,
            verify=True,
        )
        response.raise_for_status()

        data = response.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        if content:
            print("[MISTRAL] success -> used Mistral")
            return content.strip()

        print("[MISTRAL] empty API response -> using fallback")
        return _local_fallback_text(normalized_messages)

    except requests.exceptions.SSLError as exc:
        print(f"[MISTRAL] SSL error -> using local fallback: {exc}")
        return _local_fallback_text(normalized_messages)
    except Exception as exc:
        print(f"[MISTRAL] error -> using local fallback: {exc}")
        return _local_fallback_text(normalized_messages)