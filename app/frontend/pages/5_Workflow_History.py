from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app.frontend.utils.api_client import api_get
from app.frontend.utils.ui_components import (
    apply_app_theme,
    chip,
    empty_state,
    kpi_card,
    page_header,
    render_table,
    section_heading,
    soft_divider,
    status_card,
    timeline_item,
    value_card,
)
from app.frontend.utils.ui_helpers import format_label, format_local_datetime, format_status, format_workflow, shorten


st.set_page_config(page_title="Workflow History", page_icon="🧬", layout="wide")
apply_app_theme()
page_header(
    "Workflow History",
    "Inspect the full request trace: session state, agent timeline, retrieval evidence, approval path, execution result, and LLM proof.",
    eyebrow="Traceability • LangGraph run history",
    icon="🧬",
)


def _safe_list(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _event_tone(outcome: Any) -> str:
    outcome_raw = str(outcome or "").lower()
    if "success" in outcome_raw or outcome_raw in {"completed", "confirmed", "ok"}:
        return "success"
    if "fail" in outcome_raw or "error" in outcome_raw or "blocked" in outcome_raw:
        return "danger"
    if "waiting" in outcome_raw or "pending" in outcome_raw:
        return "warning"
    return "neutral"


def _render_recent_sessions(sessions: list[dict[str, Any]]) -> None:
    section_heading("Recent workflow sessions", "Select a request from here or enter one manually below.")
    if not sessions:
        empty_state("No recent workflow sessions", "Run a chat request to populate workflow history.")
        return

    rows = []
    for row in sessions:
        rows.append(
            {
                "request_id": row.get("request_id"),
                "employee_id": row.get("employee_id"),
                "intent": format_workflow(row.get("intent")),
                "status": format_status(row.get("status")),
                "current_node": format_label(row.get("current_node")),
                "needs_confirmation": row.get("needs_confirmation"),
                "ticket_id": row.get("ticket_id"),
                "updated_at": format_local_datetime(row.get("updated_at")),
            }
        )
    render_table(rows, empty_title="No sessions", empty_text="No recent sessions matched the filters.")


def _render_events(events: list[dict[str, Any]]) -> None:
    if not events:
        empty_state("No workflow events", "No agent timeline events were recorded for this request.")
        return

    for index, event in enumerate(events, start=1):
        node = format_label(event.get("node_name", "unknown"))
        stage = format_label(event.get("stage", "unknown"))
        outcome = format_status(event.get("outcome", "unknown"))
        created_at = format_local_datetime(event.get("created_at"))
        details = event.get("details", {})
        timeline_item(
            index,
            node,
            stage,
            chips=chip("Outcome", outcome, tone=_event_tone(event.get("outcome"))) + chip("Time", created_at, tone="neutral"),
        )
        if details:
            with st.expander(f"Event {index} details", expanded=False):
                st.json(details)


def _render_retrieval_logs(retrieval_logs: list[dict[str, Any]]) -> None:
    if not retrieval_logs:
        empty_state("No retrieval logs", "No evidence retrieval records were associated with this request.")
        return

    table_rows = []
    for row in retrieval_logs:
        table_rows.append(
            {
                "created_at": format_local_datetime(row.get("created_at")),
                "query_text": row.get("query_text"),
                "document_name": row.get("document_name"),
                "chunk_id": row.get("chunk_id"),
                "score": row.get("score"),
            }
        )
    render_table(table_rows, empty_title="No retrieval rows", empty_text="No retrieval rows were returned.")

    section_heading("Retrieval cards")
    for row in retrieval_logs:
        with st.container(border=True):
            st.markdown(f"**{shorten(row.get('query_text', 'Unknown Query'), 90)}**")
            st.markdown(
                chip("Document", row.get("document_name", "Unknown"), tone="info")
                + chip("Chunk", row.get("chunk_id", "Unknown"), tone="neutral")
                + chip("Score", row.get("score", "N/A"), tone="accent")
                + chip("Time", format_local_datetime(row.get("created_at")), tone="neutral")
            )
            if row.get("retrieved_metadata"):
                with st.expander("Retrieved metadata", expanded=False):
                    st.json(row.get("retrieved_metadata"))


with st.container(border=True):
    section_heading("Recent sessions filter", "Load recent workflow sessions, then drill into a specific request.")
    f1, f2, f3 = st.columns([1, 1, 0.7])
    with f1:
        recent_employee_id = st.text_input("Employee filter", value="", placeholder="Optional employee ID")
    with f2:
        recent_status = st.selectbox("Status", ["All", "in_progress", "awaiting_confirmation", "completed", "error"], index=0)
    with f3:
        recent_limit = st.number_input("Recent limit", min_value=5, max_value=200, value=25, step=5)

recent_sessions: list[dict[str, Any]] = []
try:
    session_params: dict[str, Any] = {"limit": int(recent_limit)}
    if recent_employee_id.strip():
        session_params["employee_id"] = recent_employee_id.strip()
    if recent_status != "All":
        session_params["status"] = recent_status
    session_response = api_get("/workflow/sessions", params=session_params, timeout=30)
    session_response.raise_for_status()
    recent_sessions = _safe_list(_safe_dict(session_response.json()).get("sessions"))
except Exception as exc:
    st.warning(f"Could not load recent workflow sessions: {exc}")

_render_recent_sessions(recent_sessions)
soft_divider()

recent_ids = [str(row.get("request_id")) for row in recent_sessions if row.get("request_id")]
with st.container(border=True):
    section_heading("Load detailed trace", "Pick a recent request or paste a request ID from the chat case summary.")
    c1, c2 = st.columns([1, 1])
    with c1:
        selected_request_id = st.selectbox("Select recent request", [""] + recent_ids, index=0)
    with c2:
        manual_request_id = st.text_input("Or enter Request ID", value="", placeholder="REQ-...")

request_id = manual_request_id.strip() or selected_request_id.strip()
load = st.button("Load History", use_container_width=True)

if load and request_id:
    try:
        response = api_get(f"/workflow/history/{request_id}", timeout=30)
        response.raise_for_status()
        payload = _safe_dict(response.json())

        summary = _safe_dict(payload.get("summary"))
        session = _safe_dict(payload.get("session"))
        events = _safe_list(payload.get("events"))
        retrieval_logs = _safe_list(payload.get("retrieval_logs"))

        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            status_card("Status", summary.get("status") or session.get("status") or "unknown", detail="Current workflow run state")
        with m2:
            value_card("Intent", format_workflow(summary.get("intent") or session.get("intent")), detail="Workflow selected by intent routing", tone="info")
        with m3:
            kpi_card("Events", summary.get("event_count", len(events)), detail="Agent timeline entries", tone="accent")
        with m4:
            kpi_card("Retrieval Logs", summary.get("retrieval_count", len(retrieval_logs)), detail="Evidence retrieval records", tone="accent")
        with m5:
            duration = summary.get("duration_seconds")
            value_card("Duration", f"{duration}s" if duration is not None else "unknown", detail="Elapsed time from creation to last update")

        soft_divider()

        tabs = st.tabs(["Session", "Timeline", "Retrieval", "LLM Proof", "Raw Payload"])

        with tabs[0]:
            section_heading("Session", "Persisted workflow session state.")
            if session:
                session_table = [
                    {
                        "request_id": session.get("request_id"),
                        "employee_id": session.get("employee_id"),
                        "intent": format_workflow(session.get("intent")),
                        "current_node": format_label(session.get("current_node")),
                        "status": format_status(session.get("status")),
                        "needs_confirmation": session.get("needs_confirmation"),
                        "ticket_id": session.get("ticket_id"),
                        "created_at": format_local_datetime(session.get("created_at")),
                        "updated_at": format_local_datetime(session.get("updated_at")),
                        "message": session.get("message"),
                    }
                ]
                render_table(session_table, empty_title="No session", empty_text="No session row was returned.")
                with st.expander("Session JSON", expanded=False):
                    st.json(session)
            else:
                empty_state("No session found", "No session exists for this request ID.")

        with tabs[1]:
            section_heading("Workflow timeline", "Agent and service events in execution order.")
            _render_events(events)

        with tabs[2]:
            section_heading("Retrieval logs", "Evidence records used by the retrieval agent.")
            _render_retrieval_logs(retrieval_logs)

        with tabs[3]:
            response_payload = session.get("response_payload") or {}
            final_state = session.get("final_state") or {}
            llm_trace = None
            if isinstance(response_payload, dict):
                llm_trace = response_payload.get("llm_trace")
            if not llm_trace and isinstance(final_state, dict):
                llm_trace = final_state.get("llm_trace")
            if llm_trace:
                st.json(llm_trace)
            else:
                empty_state("No LLM trace found", "This workflow session does not contain final response LLM proof.")

        with tabs[4]:
            st.json(payload)

    except Exception as exc:
        st.error(f"Failed to load workflow history: {exc}")
elif load:
    st.warning("Please select or enter a Request ID.")
