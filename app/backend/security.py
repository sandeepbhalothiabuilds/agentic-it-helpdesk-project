from __future__ import annotations

import hmac
from typing import Iterable

from starlette.requests import Request

from app.backend.config import settings

PUBLIC_PATH_PREFIXES = (
    "/",
    "/health",
    "/health/live",
    "/health/ready",
    "/live",
    "/ready",
    "/version",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _normalize_token(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip()
    if text.lower().startswith("bearer "):
        return text[7:].strip()
    return text


def is_public_path(path: str, public_prefixes: Iterable[str] = PUBLIC_PATH_PREFIXES) -> bool:
    if path == "/":
        return True
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in public_prefixes if prefix != "/")


def extract_api_key(request: Request) -> str:
    configured_header = settings.api_key_header or "X-API-Key"
    return _normalize_token(
        request.headers.get(configured_header)
        or request.headers.get(configured_header.lower())
        or request.headers.get("x-api-key")
        or request.headers.get("authorization")
        or request.query_params.get("api_key")
    )


def api_key_required() -> bool:
    return bool(settings.api_key_required)


def api_key_configured() -> bool:
    return settings.api_key_is_configured


def api_key_matches(provided: str) -> bool:
    expected = (settings.backend_api_key or "").strip()
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)
