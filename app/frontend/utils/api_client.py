from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
BACKEND_API_KEY = (
    os.getenv("BACKEND_API_KEY")
    or os.getenv("FRONTEND_API_KEY")
    or os.getenv("APP_API_KEY")
    or ""
).strip()
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
DEFAULT_TIMEOUT = int(os.getenv("FRONTEND_REQUEST_TIMEOUT", "90"))


def backend_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{BACKEND_URL}{normalized}"


def backend_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"X-Request-ID": f"UI-{uuid4().hex[:12].upper()}"}
    if BACKEND_API_KEY:
        headers[API_KEY_HEADER] = BACKEND_API_KEY
    if extra:
        headers.update(extra)
    return headers


def backend_get(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int | None = None,
    stream: bool = False,
    headers: dict[str, str] | None = None,
):
    return requests.get(
        backend_url(path),
        params=params or {},
        headers=backend_headers(headers),
        timeout=timeout or DEFAULT_TIMEOUT,
        stream=stream,
    )


def backend_post(
    path: str,
    *,
    json: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout: int | None = None,
    headers: dict[str, str] | None = None,
):
    return requests.post(
        backend_url(path),
        json=json,
        data=data,
        files=files,
        headers=backend_headers(headers),
        timeout=timeout or DEFAULT_TIMEOUT,
    )


def backend_patch(
    path: str,
    *,
    json: dict[str, Any] | None = None,
    timeout: int | None = None,
    headers: dict[str, str] | None = None,
):
    return requests.patch(
        backend_url(path),
        json=json or {},
        headers=backend_headers(headers),
        timeout=timeout or DEFAULT_TIMEOUT,
    )


def backend_delete(
    path: str,
    *,
    timeout: int | None = None,
    headers: dict[str, str] | None = None,
):
    return requests.delete(
        backend_url(path),
        headers=backend_headers(headers),
        timeout=timeout or DEFAULT_TIMEOUT,
    )


# Backwards-compatible aliases for pages/scripts that used the previous helper names.
api_url = backend_url
api_headers = backend_headers
api_get = backend_get
api_post = backend_post
api_patch = backend_patch
api_delete = backend_delete
