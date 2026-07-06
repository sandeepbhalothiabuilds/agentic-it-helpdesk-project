from __future__ import annotations

import importlib.util

import pytest

from app.backend.agents.common import confirmation_required_from_rule, normalize_label


class DummyDB:
    pass


def test_normalize_label_maps_unsupported_labels_to_clarify():
    assert normalize_label("password reset") == "password_reset"
    assert normalize_label("access_request") == "clarify"
    assert normalize_label("general_it_request") == "clarify"
    assert normalize_label("unknown") == "clarify"


def test_confirmation_required_from_rule_defaults_safely():
    assert confirmation_required_from_rule(None) is True
    assert confirmation_required_from_rule({"confirmation_required": "Yes"}) is True
    assert confirmation_required_from_rule({"confirmation_required": "No"}) is False
    assert confirmation_required_from_rule({"confirmation_required": "unexpected"}) is True


def _load_state_graph_or_skip():
    if importlib.util.find_spec("langgraph") is None:
        pytest.skip("langgraph is not installed in this lightweight test environment")
    from app.backend.agents import state_graph

    return state_graph


def test_graph_routes_clarify_without_retrieval(monkeypatch):
    state_graph = _load_state_graph_or_skip()
    called = {"retrieve": 0, "context": 0, "confirm": 0, "execute": 0}

    def fake_classify(db, state):
        return {
            "request_id": state["request_id"],
            "workflow": "clarify",
            "intent": "clarify",
            "current_node": "classify",
            "workflow_outcome": "completed",
        }

    def fake_retrieve(db, state):
        called["retrieve"] += 1
        return {}

    def fake_context(db, state):
        called["context"] += 1
        return {}

    def fake_confirm(db, state):
        called["confirm"] += 1
        return {}

    def fake_execute(db, state):
        called["execute"] += 1
        return {}

    monkeypatch.setattr(state_graph, "classify_intent", fake_classify)
    monkeypatch.setattr(state_graph, "retrieve_knowledge", fake_retrieve)
    monkeypatch.setattr(state_graph, "load_user_context", fake_context)
    monkeypatch.setattr(state_graph, "handle_confirmation", fake_confirm)
    monkeypatch.setattr(state_graph, "execute_action", fake_execute)

    graph = state_graph.build_workflow_graph(DummyDB())
    final_state = graph.invoke(
        {
            "message": "help",
            "employee_id": "E10231",
            "confirm": False,
            "request_id": "REQ-CLARIFY",
        }
    )

    assert final_state["current_node"] == "clarify"
    assert final_state["status"] == "needs_clarification"
    assert final_state["response"]["status"] == "needs_clarification"
    assert called == {"retrieve": 0, "context": 0, "confirm": 0, "execute": 0}


def test_graph_stops_at_confirmation_when_approval_is_pending(monkeypatch):
    state_graph = _load_state_graph_or_skip()
    called = {"execute": 0}

    def fake_classify(db, state):
        return {
            "request_id": state["request_id"],
            "workflow": "password_reset",
            "intent": "password_reset",
            "current_node": "classify",
            "workflow_outcome": "completed",
        }

    def fake_retrieve(db, state):
        return {"request_id": state["request_id"], "current_node": "retrieve", "evidence": {"results": []}}

    def fake_context(db, state):
        return {
            "request_id": state["request_id"],
            "current_node": "load_context",
            "user_found": True,
            "user": {"user_id": "USR-1"},
            "rule": {"confirmation_required": "Yes"},
            "workflow_outcome": "completed",
        }

    def fake_confirm(db, state):
        return {
            "request_id": state["request_id"],
            "current_node": "confirm_action",
            "status": "awaiting_confirmation",
            "needs_confirmation": True,
            "workflow_outcome": "waiting_for_confirmation",
            "response": {"status": "awaiting_confirmation", "needs_confirmation": True},
        }

    def fake_execute(db, state):
        called["execute"] += 1
        return {"current_node": "execute_action"}

    monkeypatch.setattr(state_graph, "classify_intent", fake_classify)
    monkeypatch.setattr(state_graph, "retrieve_knowledge", fake_retrieve)
    monkeypatch.setattr(state_graph, "load_user_context", fake_context)
    monkeypatch.setattr(state_graph, "handle_confirmation", fake_confirm)
    monkeypatch.setattr(state_graph, "execute_action", fake_execute)

    graph = state_graph.build_workflow_graph(DummyDB())
    final_state = graph.invoke(
        {
            "message": "reset my password",
            "employee_id": "E10231",
            "confirm": False,
            "request_id": "REQ-PENDING",
        }
    )

    assert final_state["current_node"] == "confirm_action"
    assert final_state["needs_confirmation"] is True
    assert called["execute"] == 0


def test_graph_executes_after_confirmation(monkeypatch):
    state_graph = _load_state_graph_or_skip()
    called = {"execute": 0}

    def fake_classify(db, state):
        return {
            "request_id": state["request_id"],
            "workflow": "password_reset",
            "intent": "password_reset",
            "current_node": "classify",
            "workflow_outcome": "completed",
        }

    def fake_retrieve(db, state):
        return {"request_id": state["request_id"], "current_node": "retrieve", "evidence": {"results": []}}

    def fake_context(db, state):
        return {
            "request_id": state["request_id"],
            "current_node": "load_context",
            "user_found": True,
            "user": {"user_id": "USR-1"},
            "rule": {"confirmation_required": "Yes"},
            "workflow_outcome": "completed",
        }

    def fake_confirm(db, state):
        return {
            "request_id": state["request_id"],
            "current_node": "confirm_action",
            "needs_confirmation": False,
            "workflow_outcome": "confirmed",
        }

    def fake_execute(db, state):
        called["execute"] += 1
        return {
            "request_id": state["request_id"],
            "current_node": "execute_action",
            "status": "completed",
            "result": {"status": "success", "message": "done"},
            "response": {"status": "success", "message": "done"},
            "workflow_outcome": "success",
        }

    monkeypatch.setattr(state_graph, "classify_intent", fake_classify)
    monkeypatch.setattr(state_graph, "retrieve_knowledge", fake_retrieve)
    monkeypatch.setattr(state_graph, "load_user_context", fake_context)
    monkeypatch.setattr(state_graph, "handle_confirmation", fake_confirm)
    monkeypatch.setattr(state_graph, "execute_action", fake_execute)

    graph = state_graph.build_workflow_graph(DummyDB())
    final_state = graph.invoke(
        {
            "message": "reset my password",
            "employee_id": "E10231",
            "confirm": True,
            "request_id": "REQ-CONFIRMED",
        }
    )

    assert final_state["current_node"] == "execute_action"
    assert final_state["status"] == "completed"
    assert called["execute"] == 1
