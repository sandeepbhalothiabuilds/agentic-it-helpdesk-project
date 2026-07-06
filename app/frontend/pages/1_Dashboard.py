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
    value_card,
)
from app.frontend.utils.ui_helpers import format_local_datetime, format_status, format_workflow


st.set_page_config(page_title="Operations Dashboard", page_icon="📊", layout="wide")
apply_app_theme()
page_header(
    "Operations Dashboard",
    "A command-center view of request volume, ticket outcomes, retrieval activity, workflow events, and recent system movement.",
    eyebrow="Operations • Live snapshot",
    icon="📊",
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def _percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0%"
    return f"{round((numerator / denominator) * 100)}%"


def _workflow_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        normalized.append(
            {
                "intent": format_workflow(row.get("intent")),
                "status": format_status(row.get("status")),
                "request_count": row.get("request_count"),
                "last_updated": format_local_datetime(row.get("last_updated")),
            }
        )
    return normalized


if st.button("Refresh dashboard", use_container_width=True):
    st.rerun()

try:
    response = api_get("/dashboard", timeout=30)
    response.raise_for_status()
    payload = _safe_dict(response.json())

    summary = _safe_dict(payload.get("summary"))
    health = _safe_dict(payload.get("health"))
    status = payload.get("status") or health.get("status") or "ok"
    generated_at = payload.get("generated_at")
    last_indexed = summary.get("last_indexed")

    active = _number(summary.get("active_requests"))
    awaiting = _number(summary.get("awaiting_confirmation"))
    completed = _number(summary.get("completed_requests"))
    failed = _number(summary.get("failed_requests"))
    total_requests = active + awaiting + completed + failed
    completion_rate = _percent(completed, total_requests)
    failure_rate = _percent(failed, total_requests)

    top = st.columns([1.2, 1, 1, 1, 1])
    with top[0]:
        status_card("Backend", status, detail="Dashboard data source health")
    with top[1]:
        kpi_card("Active Requests", active, detail="Open workflow sessions", tone="info")
    with top[2]:
        kpi_card("Awaiting Approval", awaiting, detail="Approval queue", tone="warning")
    with top[3]:
        kpi_card("Completion Rate", completion_rate, detail=f"{completed} completed", tone="success")
    with top[4]:
        kpi_card("Failure Rate", failure_rate, detail=f"{failed} failed", tone="danger" if failed else "neutral")

    second = st.columns(4)
    with second[0]:
        kpi_card("Open Tickets", summary.get("open_tickets", 0), detail=f"{summary.get('total_tickets', 0)} total tickets", tone="info")
    with second[1]:
        kpi_card("Knowledge Documents", summary.get("total_documents", 0), detail=f"{summary.get('total_chunks', 0)} chunks", tone="accent")
    with second[2]:
        kpi_card("Retrieval Logs", summary.get("total_retrieval_logs", 0), detail="Knowledge retrieval events", tone="neutral")
    with second[3]:
        kpi_card("Workflow Events", summary.get("total_workflow_events", 0), detail="LangGraph timeline records", tone="neutral")

    st.caption(
        f"Generated: {format_local_datetime(generated_at) if generated_at else 'unknown'}  ·  "
        f"Last indexed: {format_local_datetime(last_indexed) if last_indexed else 'unknown'}"
    )

    soft_divider()

    tabs = st.tabs(["Overview", "Requests", "Tickets", "Audit & Events", "Raw"])

    with tabs[0]:
        left, right = st.columns([1.15, 1])
        with left:
            section_heading("Workflow breakdown", "Grouped by intent and status so operators can spot stuck workflows.")
            rows = _workflow_rows(_safe_rows(payload.get("workflow_breakdown")))
            render_table(rows, empty_title="No workflow breakdown", empty_text="No workflow session aggregates were returned.")
        with right:
            section_heading("Operational pulse", "Quick interpretation of the current snapshot.")
            value_card("Request Health", f"{completion_rate} complete", detail=f"Failure rate: {failure_rate}", tone="success" if failed == 0 else "warning")
            value_card("Approval Queue", awaiting, detail="Review these in the chat or workflow history pages.", tone="warning" if awaiting else "neutral")
            value_card("Knowledge Freshness", format_local_datetime(last_indexed) if last_indexed else "unknown", detail="Most recent indexed KB revision", tone="accent")

    with tabs[1]:
        section_heading("Recent workflow sessions", "Latest persisted request sessions from the LangGraph workflow.")
        sessions = []
        for row in _safe_rows(payload.get("recent_sessions")):
            sessions.append(
                {
                    "request_id": row.get("request_id"),
                    "employee_id": row.get("employee_id"),
                    "intent": format_workflow(row.get("intent")),
                    "current_node": row.get("current_node"),
                    "status": format_status(row.get("status")),
                    "needs_confirmation": row.get("needs_confirmation"),
                    "ticket_id": row.get("ticket_id"),
                    "updated_at": format_local_datetime(row.get("updated_at")),
                }
            )
        render_table(sessions, empty_title="No recent workflow sessions", empty_text="Submit a chat request to populate this table.")

    with tabs[2]:
        section_heading("Recent tickets", "Newest service desk records created or updated by the workflow.")
        tickets = []
        for row in _safe_rows(payload.get("recent_tickets")):
            tickets.append(
                {
                    "ticket_id": row.get("ticket_id"),
                    "employee_id": row.get("employee_id"),
                    "full_name": row.get("full_name"),
                    "status": format_status(row.get("status")),
                    "priority": format_status(row.get("priority")),
                    "category": format_workflow(row.get("category")),
                    "assigned_group": row.get("assigned_group"),
                    "last_updated": format_local_datetime(row.get("last_updated")),
                    "summary": row.get("summary"),
                }
            )
        render_table(tickets, empty_title="No recent tickets", empty_text="Tickets appear here after an approved workflow creates one.")

    with tabs[3]:
        left, right = st.columns(2)
        with left:
            section_heading("Recent audit logs", "Execution and workflow audit evidence.")
            audit_rows = []
            for row in _safe_rows(payload.get("recent_audit")):
                audit_rows.append(
                    {
                        "created_at": format_local_datetime(row.get("created_at")),
                        "request_id": row.get("request_id"),
                        "stage": format_status(row.get("stage")),
                        "status": format_status(row.get("status")),
                        "message": row.get("message"),
                    }
                )
            render_table(audit_rows, empty_title="No audit logs", empty_text="No audit records were returned.")
        with right:
            section_heading("Recent workflow events", "Agent-by-agent timeline events.")
            event_rows = []
            for row in _safe_rows(payload.get("recent_events")):
                event_rows.append(
                    {
                        "created_at": format_local_datetime(row.get("created_at")),
                        "request_id": row.get("request_id"),
                        "employee_id": row.get("employee_id"),
                        "node_name": row.get("node_name"),
                        "stage": format_status(row.get("stage")),
                        "outcome": format_status(row.get("outcome")),
                    }
                )
            render_table(event_rows, empty_title="No workflow events", empty_text="No workflow events were returned.")

    with tabs[4]:
        section_heading("Raw payload", "Useful when validating backend contract changes.")
        st.json(payload)

except Exception as exc:
    st.error(f"Failed to load dashboard: {exc}")
