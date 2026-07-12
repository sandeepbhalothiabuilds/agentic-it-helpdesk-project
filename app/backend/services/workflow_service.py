from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.backend.agentcore.memory import create_conversation_event, retrieve_memory_context
from app.backend.agents.state_graph import build_workflow_graph
from app.backend.telemetry import record_operation
from app.backend.services.workflow_state_service import (
    log_retrieval_event,
    log_workflow_event,
    upsert_workflow_session,
)
from app.backend.tools.ticket_tool import create_incident_ticket

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower()


def classify_intent(message: str) -> str:
    text = _normalize_text(message)

    if any(k in text for k in ["vpn", "connectivity", "tunnel", "remote access"]):
        return "vpn_issue"
    if any(k in text for k in ["password", "reset password", "forgot password"]):
        return "password_reset"
    if any(k in text for k in ["unlock account", "account locked", "locked out"]):
        return "account_unlock"
    if any(k in text for k in ["access", "permission", "grant access", "role"]):
        return "access_request"

    return "general_it_request"


def determine_priority(message: str) -> str:
    text = _normalize_text(message)

    if any(k in text for k in ["down", "urgent", "critical", "cannot work", "prod issue"]):
        return "high"
    if any(k in text for k in ["blocked", "asap", "important", "broken"]):
        return "medium"

    return "low"


def assign_group(intent: str) -> str:
    mapping = {
        "vpn_issue": "network-support",
        "vpn_reenable": "network-support",
        "password_reset": "identity-access-management",
        "account_unlock": "identity-access-management",
        "access_request": "service-desk",
        "general_it_request": "service-desk",
        "clarify": "service-desk",
    }
    return mapping.get(intent, "service-desk")


def _extract_response(final_state: dict[str, Any]) -> dict[str, Any]:
    response = final_state.get("response")
    if isinstance(response, dict):
        return dict(response)

    return {
        "status": "error",
        "message": "No response generated",
    }


def _extract_llm_trace(final_state: dict[str, Any]) -> dict[str, Any]:
    trace = final_state.get("llm_trace")
    if isinstance(trace, dict):
        return trace

    response = final_state.get("response") or {}
    if isinstance(response, dict):
        trace = response.get("llm_trace")
        if isinstance(trace, dict):
            return trace

    return {}


def _normalize_evidence_items(items: Any) -> list[dict[str, Any]]:
    if not items:
        return []

    if isinstance(items, list):
        normalized: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                normalized.append(item)
            else:
                normalized.append({"content": str(item)})
        return normalized

    return []


def _collect_evidence(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = final_state.get("evidence")

    if isinstance(evidence, dict):
        results = evidence.get("results")
        normalized = _normalize_evidence_items(results)
        if normalized:
            return normalized

    candidates = (
        final_state.get("retrieved_documents"),
        final_state.get("retrievals"),
        final_state.get("chunks"),
        final_state.get("documents"),
    )

    for candidate in candidates:
        normalized = _normalize_evidence_items(candidate)
        if normalized:
            return normalized

    return []


def _waiting_for_confirmation(final_state: dict[str, Any], confirm: bool) -> bool:
    if confirm:
        return False

    if final_state.get("needs_confirmation") is True:
        return True

    response = final_state.get("response") or {}
    if isinstance(response, dict) and response.get("needs_confirmation") is True:
        return True

    status = _normalize_text(str(final_state.get("status", "")))
    if status in {"waiting_for_confirmation", "awaiting_confirmation", "confirm_required"}:
        return True

    response_status = _normalize_text(str(response.get("status", ""))) if isinstance(response, dict) else ""
    if response_status in {"waiting_for_confirmation", "awaiting_confirmation", "confirm_required"}:
        return True

    return False


def _state_status_candidates(result: dict[str, Any], final_state: dict[str, Any]) -> list[str]:
    response = final_state.get("response") or {}
    response_status = response.get("status") if isinstance(response, dict) else None
    return [
        str(result.get("status") or ""),
        str(final_state.get("status") or ""),
        str(response_status or ""),
        str(final_state.get("workflow_outcome") or ""),
    ]


def _derive_ui_status(result: dict[str, Any], final_state: dict[str, Any], confirm: bool) -> str:
    if _waiting_for_confirmation(final_state, confirm):
        return "awaiting_confirmation"

    candidates = [_normalize_text(value) for value in _state_status_candidates(result, final_state)]

    if any(raw in {"needs_clarification", "clarify"} for raw in candidates):
        return "needs_clarification"
    if any(raw in {"failed", "error"} for raw in candidates):
        return "failed"
    if any(raw in {"awaiting_confirmation", "waiting_for_confirmation", "confirm_required"} for raw in candidates):
        return "awaiting_confirmation"
    if any(raw in {"completed", "success", "ok", "done"} for raw in candidates):
        return "completed"

    if confirm:
        return "completed"

    return "in_progress"


def _derive_execution_status(result: dict[str, Any], final_state: dict[str, Any]) -> str:
    candidates = [_normalize_text(value) for value in _state_status_candidates(result, final_state)]

    if any(raw in {"completed", "success", "ok", "done"} for raw in candidates):
        return "completed"
    if any(raw in {"failed", "error"} for raw in candidates):
        return "failed"
    if any(raw in {"needs_clarification", "clarify"} for raw in candidates):
        return "needs_clarification"
    if any(raw in {"awaiting_confirmation", "waiting_for_confirmation", "confirm_required"} for raw in candidates):
        return "pending_confirmation"

    for raw in candidates:
        if raw:
            return raw
    return "in_progress"


def _build_data_payload(final_state: dict[str, Any]) -> dict[str, Any]:
    evidence_chunks = _collect_evidence(final_state)
    llm_trace = _extract_llm_trace(final_state)
    evidence = final_state.get("evidence") if isinstance(final_state.get("evidence"), dict) else {}

    return {
        "evidence_chunks": evidence_chunks,
        "retrieved_documents": evidence_chunks,
        "retrievals": evidence_chunks,
        "raw_state_keys": list(final_state.keys()),
        "llm_trace": llm_trace,
        "retrieval_strategy": evidence.get("retrieval_strategy") if isinstance(evidence, dict) else None,
        "retrieval_confidence": evidence.get("confidence") if isinstance(evidence, dict) else None,
        "retrieval_result_count": evidence.get("result_count") if isinstance(evidence, dict) else len(evidence_chunks),
        "memory_context": final_state.get("memory_context", {}),
    }


def _should_create_ticket(*, confirm: bool, ui_status: str, execution_status: str) -> bool:
    if not confirm:
        return False
    return ui_status == "completed" and execution_status == "completed"


def _persist_workflow_session_safely(db: Session, **kwargs: Any) -> None:
    try:
        upsert_workflow_session(db, **kwargs)
    except Exception:
        logger.exception("Failed to persist workflow session", extra={"event": "workflow_persist_error"})


def _log_retrievals_safely(
    db: Session,
    *,
    request_id: str,
    employee_id: str,
    message: str,
    evidence_chunks: list[dict[str, Any]],
) -> None:
    for item in evidence_chunks:
        try:
            log_retrieval_event(
                db,
                request_id=request_id,
                employee_id=employee_id,
                query_text=str(item.get("query_text") or message),
                document_name=item.get("document_name") or item.get("source_document"),
                chunk_id=item.get("chunk_id") or item.get("id"),
                score=item.get("score"),
                retrieved_metadata=item,
            )
        except Exception:
            logger.exception("Failed to log retrieval event", extra={"event": "retrieval_log_error"})


def _record_memory_safely(
    *,
    employee_id: str,
    request_id: str,
    user_message: str,
    assistant_message: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return create_conversation_event(
            employee_id=employee_id,
            request_id=request_id,
            user_message=user_message,
            assistant_message=assistant_message,
            metadata=metadata,
        )
    except Exception as exc:
        logger.warning(
            "AgentCore Memory recording failed",
            extra={"event": "agentcore_memory_record_error", "request_id": request_id, "employee_id": employee_id},
            exc_info=True,
        )
        return {"status": "error", "error": str(exc)}


def _failure_response(
    *,
    db: Session,
    request_id: str,
    employee_id: str,
    message: str,
    started_at: float,
    exc: Exception,
) -> dict[str, Any]:
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    error_message = "The workflow could not be completed because an internal error occurred."

    final_state = {
        "request_id": request_id,
        "employee_id": employee_id,
        "message": message,
        "status": "failed",
        "workflow_outcome": "error",
        "error": str(exc),
    }

    response_payload = {
        "status": "failed",
        "message": error_message,
        "request_id": request_id,
        "duration_ms": duration_ms,
        "error": str(exc),
    }

    _persist_workflow_session_safely(
        db,
        request_id=request_id,
        employee_id=employee_id,
        message=message,
        intent=classify_intent(message),
        current_node="workflow_error",
        status="failed",
        needs_confirmation=False,
        ticket_id=None,
        response_payload=response_payload,
        final_state=final_state,
    )

    try:
        log_workflow_event(
            db,
            request_id=request_id,
            employee_id=employee_id,
            node_name="workflow_service",
            stage="workflow_execution",
            outcome="error",
            details={"error": str(exc), "duration_ms": duration_ms},
        )
    except Exception:
        logger.exception("Failed to log workflow error event", extra={"event": "workflow_event_log_error"})

    memory_result = _record_memory_safely(
        employee_id=employee_id,
        request_id=request_id,
        user_message=message,
        assistant_message=error_message,
    )
    response_payload["agentcore_memory"] = memory_result
    record_operation(
        "workflow.handle_request",
        provider="local_langgraph",
        status="failed",
        duration_ms=duration_ms,
        request_id=request_id,
        properties={"employee_id": employee_id, "intent": classify_intent(message)},
        error=str(exc),
    )
    return response_payload


def handle_request(
    message: str,
    employee_id: str,
    db: Session,
    confirm: bool = False,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Run the LangGraph workflow and return the UI-facing response payload."""
    started_at = time.perf_counter()
    request_id = request_id or f"REQ-{uuid4().hex[:10].upper()}"
    clean_message = (message or "").strip()
    clean_employee_id = (employee_id or "").strip()

    if not clean_employee_id:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        record_operation(
            "workflow.handle_request",
            provider="local_langgraph",
            status="failed",
            duration_ms=duration_ms,
            request_id=request_id,
            properties={"confirm": confirm, "message_length": len(clean_message)},
            error="missing_employee_id",
        )
        return {
            "status": "failed",
            "message": "Employee ID is required. Enter an employee ID in the sidebar before submitting a request.",
            "request_id": request_id,
            "needs_confirmation": False,
            "error": "missing_employee_id",
            "duration_ms": duration_ms,
        }

    memory_context = retrieve_memory_context(
        employee_id=clean_employee_id,
        query=clean_message,
        request_id=request_id,
    )

    try:
        graph = build_workflow_graph(db)
        final_state = graph.invoke(
            {
                "message": clean_message,
                "employee_id": clean_employee_id,
                "confirm": confirm,
                "request_id": request_id,
                "memory_context": memory_context,
            }
        )
    except Exception as exc:
        logger.exception("Workflow execution failed", extra={"request_id": request_id, "event": "workflow_error"})
        return _failure_response(
            db=db,
            request_id=request_id,
            employee_id=clean_employee_id,
            message=clean_message,
            started_at=started_at,
            exc=exc,
        )

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response = _extract_response(final_state)
    intent = final_state.get("intent") or classify_intent(clean_message)
    data_payload = _build_data_payload(final_state)
    llm_trace = data_payload.get("llm_trace") or {}

    result = final_state.get("result") or response.get("result") or {}
    execution_status = _derive_execution_status(result, final_state)
    ui_status = _derive_ui_status(result, final_state, confirm)

    response.setdefault("message", final_state.get("result", {}).get("message", "Completed"))
    response["status"] = ui_status
    response["duration_ms"] = duration_ms

    waiting_for_confirmation = _waiting_for_confirmation(final_state, confirm)
    approval_status = "confirmed" if confirm and not waiting_for_confirmation else (
        "awaiting_confirmation" if waiting_for_confirmation else "not_required"
    )

    _persist_workflow_session_safely(
        db,
        request_id=request_id,
        employee_id=clean_employee_id,
        message=clean_message,
        intent=str(intent),
        current_node=str(final_state.get("current_node", "workflow")),
        status=ui_status,
        needs_confirmation=waiting_for_confirmation,
        ticket_id=final_state.get("ticket_id"),
        response_payload={
            **response,
            "data": data_payload,
            "llm_trace": llm_trace,
            "execution_status": execution_status,
            "approval_status": approval_status,
            "ticket_status": "not_created",
            "duration_ms": duration_ms,
        },
        final_state=final_state,
    )

    _log_retrievals_safely(
        db,
        request_id=request_id,
        employee_id=clean_employee_id,
        message=clean_message,
        evidence_chunks=data_payload["evidence_chunks"],
    )

    if waiting_for_confirmation:
        awaiting_response = {
            "status": "awaiting_confirmation",
            "message": response.get(
                "message",
                "I found the relevant procedure. Please confirm to continue.",
            ),
            "request_id": request_id,
            "needs_confirmation": True,
            "intent": intent,
            "workflow": final_state.get("workflow", intent),
            "data": data_payload,
            "llm_trace": llm_trace,
            "user": final_state.get("user"),
            "account": final_state.get("account"),
            "rule": final_state.get("rule"),
            "evidence": final_state.get("evidence", {}),
            "execution_status": execution_status,
            "approval_status": "awaiting_confirmation",
            "ticket_status": "not_created",
            "duration_ms": duration_ms,
        }
        awaiting_response["agentcore_memory"] = _record_memory_safely(
            employee_id=clean_employee_id,
            request_id=request_id,
            user_message=clean_message,
            assistant_message=str(awaiting_response.get("message") or ""),
        )
        record_operation(
            "workflow.handle_request",
            provider="local_langgraph",
            status="awaiting_confirmation",
            duration_ms=duration_ms,
            request_id=request_id,
            properties={
                "employee_id": clean_employee_id,
                "intent": str(intent),
                "workflow": str(final_state.get("workflow", intent)),
                "evidence_count": len(data_payload.get("evidence_chunks") or []),
                "execution_status": execution_status,
                "approval_status": "awaiting_confirmation",
            },
        )
        return awaiting_response

    ticket = None
    ticket_status = "not_created"
    if _should_create_ticket(confirm=confirm, ui_status=ui_status, execution_status=execution_status):
        try:
            ticket = create_incident_ticket(
                db=db,
                employee_id=clean_employee_id,
                category=str(intent),
                summary=clean_message,
                priority=determine_priority(clean_message),
                assigned_group=assign_group(str(intent)),
            )
            ticket_status = "created"
        except Exception as exc:
            ticket_status = "failed"
            logger.exception("Ticket creation failed", extra={"request_id": request_id, "event": "ticket_creation_error"})
            response.setdefault("warnings", [])
            response["warnings"].append(f"Ticket creation failed: {exc}")

        _persist_workflow_session_safely(
            db,
            request_id=request_id,
            employee_id=clean_employee_id,
            message=clean_message,
            intent=str(intent),
            current_node="ticket_created" if ticket else "ticket_creation_failed",
            status="completed" if ticket else ui_status,
            needs_confirmation=False,
            ticket_id=ticket.get("ticket_id") if isinstance(ticket, dict) else None,
            response_payload={
                **response,
                "data": data_payload,
                "ticket": ticket,
                "llm_trace": llm_trace,
                "execution_status": execution_status,
                "approval_status": "confirmed",
                "ticket_status": ticket_status,
                "duration_ms": duration_ms,
            },
            final_state=final_state,
        )

    final_status = "completed" if ui_status == "completed" else ui_status
    final_response = {
        **response,
        "status": final_status,
        "request_id": request_id,
        "intent": intent,
        "workflow": final_state.get("workflow", intent),
        "ticket": ticket,
        "data": data_payload,
        "llm_trace": llm_trace,
        "user": final_state.get("user"),
        "account": final_state.get("account"),
        "rule": final_state.get("rule"),
        "evidence": final_state.get("evidence", {}),
        "execution_status": execution_status,
        "approval_status": "confirmed" if confirm else ("not_required" if not waiting_for_confirmation else "awaiting_confirmation"),
        "ticket_status": ticket_status,
        "duration_ms": duration_ms,
    }
    final_response["agentcore_memory"] = _record_memory_safely(
        employee_id=clean_employee_id,
        request_id=request_id,
        user_message=clean_message,
        assistant_message=str(final_response.get("message") or ""),
    )

    record_operation(
        "workflow.handle_request",
        provider="local_langgraph",
        status=final_status,
        duration_ms=duration_ms,
        request_id=request_id,
        properties={
            "employee_id": clean_employee_id,
            "intent": str(intent),
            "workflow": str(final_state.get("workflow", intent)),
            "evidence_count": len(data_payload.get("evidence_chunks") or []),
            "execution_status": execution_status,
            "approval_status": final_response.get("approval_status"),
            "ticket_status": ticket_status,
            "llm_provider": llm_trace.get("provider"),
            "llm_fallback": llm_trace.get("fallback"),
        },
        extra_metrics={
            "EvidenceCount": (float(len(data_payload.get("evidence_chunks") or [])), "Count"),
        },
    )
    return final_response
