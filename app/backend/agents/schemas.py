from __future__ import annotations

from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    message: str
    employee_id: str
    confirm: bool
    request_id: str
    workflow: str
    intent: str
    evidence: dict[str, Any]
    retrieved_documents: list[dict[str, Any]]
    retrievals: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    chunks: list[dict[str, Any]]
    retrieval_confidence: str
    retrieval_strategy: str
    user_found: bool
    user: dict[str, Any]
    account: dict[str, Any]
    rule: dict[str, Any]
    needs_confirmation: bool
    approval_status: str
    result: dict[str, Any]
    response: dict[str, Any]
    llm_trace: dict[str, Any]
    current_node: str
    workflow_outcome: str
    status: str
