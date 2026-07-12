from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.backend.agentcore.memory import create_conversation_event, retrieve_memory_context
from app.backend.agentcore.provider import invoke_chat_if_configured
from app.backend.db.session import get_db
from app.backend.services.workflow_state_service import log_workflow_event, upsert_workflow_session

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    employee_id: str | None = Field(default=None, max_length=64)
    confirm: bool = False
    request_id: str | None = Field(default=None, max_length=128)

    @field_validator("message", "employee_id", "request_id", mode="before")
    @classmethod
    def _strip_strings(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


def _persist_agentcore_response(db: Session, *, request_id: str, employee_id: str, message: str, response: dict) -> None:
    try:
        status = str(response.get("status") or "completed")
        intent = str(response.get("intent") or response.get("workflow") or "agentcore")
        ticket = response.get("ticket") if isinstance(response.get("ticket"), dict) else {}
        ticket_id = response.get("ticket_id") or ticket.get("ticket_id")
        upsert_workflow_session(
            db,
            request_id=request_id,
            employee_id=employee_id,
            message=message,
            intent=intent,
            current_node="agentcore_runtime",
            status=status,
            needs_confirmation=bool(response.get("needs_confirmation", False)),
            ticket_id=ticket_id,
            response_payload=response,
            final_state={"agent_runtime": response.get("agent_runtime"), "response": response},
        )
        log_workflow_event(
            db,
            request_id=request_id,
            employee_id=employee_id,
            node_name="agentcore_runtime",
            stage="agent_runtime",
            outcome=status,
            details=response.get("agent_runtime") or {},
        )
    except Exception:
        # Persistence failure must not hide a successful AgentCore response.
        pass


def _record_agentcore_memory(*, request_id: str, employee_id: str, message: str, response: dict) -> None:
    memory_result = create_conversation_event(
        employee_id=employee_id,
        request_id=request_id,
        user_message=message,
        assistant_message=str(response.get("message") or response.get("response") or ""),
        metadata={
            "runtime": "agentcore" if response.get("agent_runtime") else "local",
            "status": response.get("status", "completed"),
            "workflow": response.get("workflow") or response.get("intent") or "agentcore",
        },
    )
    response["agentcore_memory"] = memory_result


def handle_request(*args, **kwargs):
    from app.backend.services.workflow_service import handle_request as workflow_handle_request

    return workflow_handle_request(*args, **kwargs)


@router.post("")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    employee_id = (req.employee_id or "").strip()
    if not employee_id:
        raise HTTPException(
            status_code=400,
            detail="Employee ID is required. Enter an employee ID in the UI before submitting a request.",
        )

    request_id = req.request_id or f"REQ-{uuid4().hex[:10].upper()}"
    memory_context = retrieve_memory_context(
        employee_id=employee_id,
        query=req.message,
        request_id=request_id,
    )
    agentcore_response = invoke_chat_if_configured(
        message=req.message,
        employee_id=employee_id,
        confirm=req.confirm,
        request_id=request_id,
        memory_context=memory_context,
    )
    if agentcore_response is not None:
        agentcore_response.setdefault("memory_context", memory_context)
        _record_agentcore_memory(
            request_id=request_id,
            employee_id=employee_id,
            message=req.message,
            response=agentcore_response,
        )
        _persist_agentcore_response(
            db,
            request_id=request_id,
            employee_id=employee_id,
            message=req.message,
            response=agentcore_response,
        )
        return agentcore_response

    return handle_request(
        message=req.message,
        employee_id=employee_id,
        db=db,
        confirm=req.confirm,
        request_id=request_id,
    )
