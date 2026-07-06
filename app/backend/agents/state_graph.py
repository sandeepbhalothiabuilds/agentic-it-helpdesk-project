from __future__ import annotations

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.backend.agents.clarification_agent import build_clarification_response
from app.backend.agents.common import CLARIFY_WORKFLOW, get_or_create_request_id
from app.backend.agents.confirmation_agent import handle_confirmation
from app.backend.agents.context_agent import load_user_context
from app.backend.agents.execution_agent import execute_action
from app.backend.agents.intent_agent import classify_intent
from app.backend.agents.retrieval_agent import retrieve_knowledge
from app.backend.agents.schemas import WorkflowState

ROUTE_RETRIEVE = "retrieve"
ROUTE_CLARIFY = "clarify"
ROUTE_CONFIRM = "confirm_action"
ROUTE_EXECUTE = "execute_action"
ROUTE_END = "end"


def _route_after_classify(state: WorkflowState) -> str:
    workflow = str(state.get("workflow") or state.get("intent") or "").strip().lower()
    if workflow == CLARIFY_WORKFLOW:
        return ROUTE_CLARIFY
    return ROUTE_RETRIEVE


def _route_after_context(state: WorkflowState) -> str:
    if state.get("user_found") is False:
        return ROUTE_END
    if str(state.get("workflow") or "").strip().lower() == CLARIFY_WORKFLOW:
        return ROUTE_CLARIFY
    return ROUTE_CONFIRM


def _route_after_confirmation(state: WorkflowState) -> str:
    outcome = str(state.get("workflow_outcome") or "").strip().lower()
    response = state.get("response") or {}
    response_status = str(response.get("status") or "").strip().lower() if isinstance(response, dict) else ""

    if outcome in {"error", "user_not_found", "needs_clarification", "clarify"}:
        return ROUTE_END
    if response_status in {"error", "needs_clarification"}:
        return ROUTE_END
    if state.get("needs_confirmation") is True and not state.get("confirm", False):
        return ROUTE_END
    return ROUTE_EXECUTE


def build_workflow_graph(db: Session):
    def classify(state: WorkflowState) -> dict:
        state["request_id"] = get_or_create_request_id(state)
        return classify_intent(db, state)

    def clarify(state: WorkflowState) -> dict:
        state["request_id"] = get_or_create_request_id(state)
        return build_clarification_response(db, state)

    def retrieve(state: WorkflowState) -> dict:
        state["request_id"] = get_or_create_request_id(state)
        return retrieve_knowledge(db, state)

    def load_context(state: WorkflowState) -> dict:
        state["request_id"] = get_or_create_request_id(state)
        return load_user_context(db, state)

    def confirm_action(state: WorkflowState) -> dict:
        state["request_id"] = get_or_create_request_id(state)
        return handle_confirmation(db, state)

    def execute_action_node(state: WorkflowState) -> dict:
        state["request_id"] = get_or_create_request_id(state)
        return execute_action(db, state)

    graph = StateGraph(WorkflowState)

    graph.add_node("classify", classify)
    graph.add_node("clarify", clarify)
    graph.add_node("retrieve", retrieve)
    graph.add_node("load_context", load_context)
    graph.add_node("confirm_action", confirm_action)
    graph.add_node("execute_action", execute_action_node)

    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            ROUTE_CLARIFY: "clarify",
            ROUTE_RETRIEVE: "retrieve",
        },
    )
    graph.add_edge("clarify", END)
    graph.add_edge("retrieve", "load_context")
    graph.add_conditional_edges(
        "load_context",
        _route_after_context,
        {
            ROUTE_CONFIRM: "confirm_action",
            ROUTE_CLARIFY: "clarify",
            ROUTE_END: END,
        },
    )
    graph.add_conditional_edges(
        "confirm_action",
        _route_after_confirmation,
        {
            ROUTE_EXECUTE: "execute_action",
            ROUTE_END: END,
        },
    )
    graph.add_edge("execute_action", END)

    return graph.compile()
