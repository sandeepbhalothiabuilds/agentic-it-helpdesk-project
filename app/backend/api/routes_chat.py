from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.backend.db.session import get_db

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

    return handle_request(
        message=req.message,
        employee_id=employee_id,
        db=db,
        confirm=req.confirm,
        request_id=req.request_id,
    )
