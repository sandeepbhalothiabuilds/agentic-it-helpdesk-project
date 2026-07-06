from __future__ import annotations

from app.backend.agents import state_graph


class DummyDB:
    pass


def test_graph_routes_ambiguous_intent_to_clarification(monkeypatch):
    called = {"retrieve": False, "context": False, "confirm": False, "execute": False}

    def fake_classify(db, state):
        return {
            "request_id": state["request_id"],
            "workflow": "clarify",
            "intent": "clarify",
            "current_node": "classify",
            "workflow_outcome": "needs_clarification",
        }

    def should_not_run(name):
        def inner(db, state):
            called[name] = True
            raise AssertionError(f"{name} should not run for clarification route")
        return inner

    monkeypatch.setattr(state_graph, "classify_intent", fake_classify)
    monkeypatch.setattr(state_graph, "retrieve_knowledge", should_not_run("retrieve"))
    monkeypatch.setattr(state_graph, "load_user_context", should_not_run("context"))
    monkeypatch.setattr(state_graph, "handle_confirmation", should_not_run("confirm"))
    monkeypatch.setattr(state_graph, "execute_action", should_not_run("execute"))

    graph = state_graph.build_workflow_graph(DummyDB())
    result = graph.invoke(
        {
            "request_id": "REQ-CLARIFY",
            "employee_id": "E10231",
            "message": "help me with something",
            "confirm": False,
        }
    )

    assert result["current_node"] == "clarify"
    assert result["status"] == "needs_clarification"
    assert result["response"]["status"] == "needs_clarification"
    assert called == {"retrieve": False, "context": False, "confirm": False, "execute": False}


def test_graph_stops_before_execution_when_confirmation_is_required(monkeypatch):
    called = {"execute": False}

    def fake_classify(db, state):
        return {
            "request_id": state["request_id"],
            "workflow": "password_reset",
            "intent": "password_reset",
            "current_node": "classify",
            "workflow_outcome": "completed",
        }

    def fake_retrieve(db, state):
        return {
            "request_id": state["request_id"],
            "current_node": "retrieve",
            "evidence": {"results": []},
            "workflow_outcome": "completed",
        }

    def fake_context(db, state):
        return {
            "request_id": state["request_id"],
            "current_node": "load_context",
            "user_found": True,
            "user": {"user_id": "U1"},
            "workflow_outcome": "completed",
        }

    def fake_confirm(db, state):
        return {
            "request_id": state["request_id"],
            "current_node": "confirm_action",
            "needs_confirmation": True,
            "workflow_outcome": "waiting_for_confirmation",
            "response": {
                "status": "awaiting_confirmation",
                "message": "Please confirm.",
            },
        }

    def fake_execute(db, state):
        called["execute"] = True
        raise AssertionError("execute should not run until confirmation is provided")

    monkeypatch.setattr(state_graph, "classify_intent", fake_classify)
    monkeypatch.setattr(state_graph, "retrieve_knowledge", fake_retrieve)
    monkeypatch.setattr(state_graph, "load_user_context", fake_context)
    monkeypatch.setattr(state_graph, "handle_confirmation", fake_confirm)
    monkeypatch.setattr(state_graph, "execute_action", fake_execute)

    graph = state_graph.build_workflow_graph(DummyDB())
    result = graph.invoke(
        {
            "request_id": "REQ-WAIT",
            "employee_id": "E10231",
            "message": "reset my password",
            "confirm": False,
        }
    )

    assert result["current_node"] == "confirm_action"
    assert result["needs_confirmation"] is True
    assert result["response"]["status"] == "awaiting_confirmation"
    assert called["execute"] is False


def test_graph_executes_after_confirmation(monkeypatch):
    called = {"execute": False}

    def fake_classify(db, state):
        return {
            "request_id": state["request_id"],
            "workflow": "password_reset",
            "intent": "password_reset",
            "current_node": "classify",
            "workflow_outcome": "completed",
        }

    def fake_retrieve(db, state):
        return {
            "request_id": state["request_id"],
            "current_node": "retrieve",
            "evidence": {"results": []},
            "workflow_outcome": "completed",
        }

    def fake_context(db, state):
        return {
            "request_id": state["request_id"],
            "current_node": "load_context",
            "user_found": True,
            "user": {"user_id": "U1"},
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
        called["execute"] = True
        return {
            "request_id": state["request_id"],
            "current_node": "execute_action",
            "result": {"status": "completed", "message": "Done."},
            "response": {"status": "completed", "message": "Done."},
            "workflow_outcome": "completed",
        }

    monkeypatch.setattr(state_graph, "classify_intent", fake_classify)
    monkeypatch.setattr(state_graph, "retrieve_knowledge", fake_retrieve)
    monkeypatch.setattr(state_graph, "load_user_context", fake_context)
    monkeypatch.setattr(state_graph, "handle_confirmation", fake_confirm)
    monkeypatch.setattr(state_graph, "execute_action", fake_execute)

    graph = state_graph.build_workflow_graph(DummyDB())
    result = graph.invoke(
        {
            "request_id": "REQ-CONFIRMED",
            "employee_id": "E10231",
            "message": "reset my password",
            "confirm": True,
        }
    )

    assert result["current_node"] == "execute_action"
    assert result["response"]["status"] == "completed"
    assert called["execute"] is True
