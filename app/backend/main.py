from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.backend.api.routes_admin import router as admin_router
from app.backend.api.routes_architecture import router as architecture_router
from app.backend.api.routes_audit import router as audit_router
from app.backend.api.routes_chat import router as chat_router
from app.backend.api.routes_dashboard import router as dashboard_router
from app.backend.api.routes_health import router as health_router
from app.backend.api.routes_knowledge_base import router as knowledge_base_router
from app.backend.api.routes_retrieval import router as retrieval_router
from app.backend.api.routes_tickets import router as tickets_router
from app.backend.api.routes_workflow import router as workflow_router
from app.backend.config import settings
from app.backend.observability import REQUEST_ID_HEADER, RequestContextMiddleware, setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Agentic IT service desk backend API with workflow orchestration, retrieval, audit, and ticketing.",
)

allow_credentials = "*" not in settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(RequestContextMiddleware)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(retrieval_router)
app.include_router(audit_router)
app.include_router(tickets_router)
app.include_router(workflow_router)
app.include_router(dashboard_router)
app.include_router(knowledge_base_router)
app.include_router(admin_router)
app.include_router(architecture_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail,
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "status": "validation_error",
            "message": "Request validation failed.",
            "errors": exc.errors(),
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled API error",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "method": request.method,
            "path": request.url.path,
            "event": "api_error",
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An unexpected server error occurred.",
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "agentic-it-service-desk",
        "environment": settings.app_env,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
    }
