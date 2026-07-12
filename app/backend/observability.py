from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.backend.config import settings
from app.backend.security import api_key_matches, api_key_required, extract_api_key, is_public_path

REQUEST_ID_HEADER = "X-Request-ID"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        emf_payload = getattr(record, "emf_payload", None)
        if isinstance(emf_payload, dict):
            # CloudWatch Embedded Metrics Format must be the top-level JSON object.
            return json.dumps(emf_payload, default=str)

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "agentic-it-service-desk",
            "environment": settings.app_env,
        }

        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client",
            "event",
            "operation",
            "provider",
            "status",
            "session_id",
            "tool",
            "model_id",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        telemetry = getattr(record, "telemetry", None)
        if isinstance(telemetry, dict):
            payload["telemetry"] = telemetry

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(str(settings.log_level or "INFO").upper())

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").disabled = True


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or f"REQ-{uuid4().hex[:12].upper()}"
        request.state.request_id = request_id
        start = time.perf_counter()

        if api_key_required() and not is_public_path(request.url.path):
            provided_key = extract_api_key(request)
            if not api_key_matches(provided_key):
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                logging.getLogger("app.requests").warning(
                    "Unauthorized API request",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": 401,
                        "duration_ms": duration_ms,
                        "client": request.client.host if request.client else None,
                        "event": "unauthorized",
                    },
                )
                response = JSONResponse(
                    status_code=401,
                    content={
                        "status": "error",
                        "message": "A valid API key is required for this endpoint.",
                        "request_id": request_id,
                    },
                )
                response.headers[REQUEST_ID_HEADER] = request_id
                return response

        try:
            response: Response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logging.getLogger("app.requests").exception(
                "Unhandled request error",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "client": request.client.host if request.client else None,
                    "event": "request_error",
                },
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        logging.getLogger("app.requests").info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client": request.client.host if request.client else None,
                "event": "request_completed",
            },
        )
        return response
