from __future__ import annotations

from collections import Counter
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from app.frontend.utils.api_client import api_get
from app.frontend.utils.ui_components import (
    apply_app_theme,
    card,
    chip,
    empty_state,
    kpi_card,
    page_header,
    render_table,
    section_heading,
    soft_divider,
)
from app.frontend.utils.ui_helpers import format_local_datetime, format_status, format_workflow


st.set_page_config(page_title="Tickets", page_icon="🎫", layout="wide")
apply_app_theme()
page_header(
    "Tickets",
    "Search, filter, and review service tickets created by the agentic workflow. Use this page as the service desk operator view.",
    eyebrow="Service desk • Ticket browser",
    icon="🎫",
)


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("tickets") or payload.get("items") or payload.get("results") or []
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return []


def _status_tone(value: Any) -> str:
    text = str(value or "").lower()
    if text in {"open", "new", "in_progress", "assigned"}:
        return "info"
    if text in {"closed", "resolved", "complete", "completed"}:
        return "success"
    if text in {"pending", "waiting", "awaiting_confirmation"}:
        return "warning"
    if text in {"failed", "error", "cancelled"}:
        return "danger"
    return "neutral"


def _priority_tone(value: Any) -> str:
    text = str(value or "").lower()
    if text in {"critical", "p1"}:
        return "danger"
    if text in {"high", "p2"}:
        return "warning"
    if text in {"medium", "p3"}:
        return "info"
    return "neutral"


def _filter_tickets(tickets: list[dict[str, Any]], search: str) -> list[dict[str, Any]]:
    needle = search.strip().lower()
    if not needle:
        return tickets
    searchable_fields = (
        "ticket_id",
        "employee_id",
        "full_name",
        "status",
        "priority",
        "category",
        "summary",
        "assigned_group",
    )
    return [ticket for ticket in tickets if any(needle in str(ticket.get(field) or "").lower() for field in searchable_fields)]


with st.container(border=True):
    section_heading("Filters", "Narrow the result set before reviewing tickets.")
    c1, c2, c3, c4, c5 = st.columns([1.15, 1, 1, 1, 0.75])
    with c1:
        employee_id = st.text_input("Employee ID", value="", placeholder="E10231")
    with c2:
        status_filter = st.selectbox("Status", ["All", "open", "in_progress", "pending", "resolved", "closed"], index=0)
    with c3:
        priority_filter = st.selectbox("Priority", ["All", "low", "medium", "high", "critical"], index=0)
    with c4:
        category_filter = st.text_input("Category", value="", placeholder="password_reset")
    with c5:
        limit = st.number_input("Limit", min_value=1, max_value=200, value=50, step=1)
    search = st.text_input("Search returned tickets", value="", placeholder="Ticket ID, employee, name, status, summary, assignment group...")

if st.button("Refresh tickets", use_container_width=True):
    st.rerun()

try:
    params: dict[str, Any] = {"limit": int(limit)}
    if employee_id.strip():
        params["employee_id"] = employee_id.strip()
    if status_filter != "All":
        params["status"] = status_filter
    if priority_filter != "All":
        params["priority"] = priority_filter
    if category_filter.strip():
        params["category"] = category_filter.strip()

    response = api_get("/tickets", params=params, timeout=30)
    response.raise_for_status()
    tickets = _filter_tickets(_as_list(response.json()), search)

    status_counts = Counter(str(ticket.get("status") or "unknown").lower() for ticket in tickets)
    priority_counts = Counter(str(ticket.get("priority") or "unknown").lower() for ticket in tickets)
    unique_employees = len({ticket.get("employee_id") or ticket.get("user_id") for ticket in tickets if ticket.get("employee_id") or ticket.get("user_id")})

    metrics = st.columns(4)
    with metrics[0]:
        kpi_card("Returned Tickets", len(tickets), detail="Records matching filters", tone="info")
    with metrics[1]:
        kpi_card("Open", status_counts.get("open", 0), detail="Tickets still in progress", tone="warning" if status_counts.get("open", 0) else "neutral")
    with metrics[2]:
        kpi_card("High / Critical", priority_counts.get("high", 0) + priority_counts.get("critical", 0), detail="High urgency queue", tone="danger" if priority_counts.get("critical", 0) else "warning")
    with metrics[3]:
        kpi_card("Employees", unique_employees, detail="Employees represented", tone="neutral")

    soft_divider()

    if not tickets:
        empty_state("No tickets found", "Adjust the filters or run a workflow that creates a service ticket.")
    else:
        tabs = st.tabs(["Table", "Cards", "Distribution"])

        with tabs[0]:
            rows = []
            for ticket in tickets:
                rows.append(
                    {
                        "ticket_id": ticket.get("ticket_id"),
                        "employee_id": ticket.get("employee_id"),
                        "full_name": ticket.get("full_name"),
                        "status": format_status(ticket.get("status")),
                        "priority": format_status(ticket.get("priority")),
                        "category": format_workflow(ticket.get("category")),
                        "assigned_group": ticket.get("assigned_group"),
                        "last_updated": format_local_datetime(ticket.get("last_updated")),
                        "summary": ticket.get("summary"),
                    }
                )
            render_table(rows, empty_title="No ticket rows", empty_text="No rows matched the filters.")

        with tabs[1]:
            section_heading("Ticket cards", "Readable review cards for operators and demos.")
            for ticket in tickets:
                status = format_status(ticket.get("status"))
                priority = format_status(ticket.get("priority"))
                category = format_workflow(ticket.get("category"))
                last_updated = format_local_datetime(ticket.get("last_updated"))
                created_at = format_local_datetime(ticket.get("created_at"))
                summary = ticket.get("summary") or "—"
                with st.container(border=True):
                    st.markdown(f"### {escape(str(ticket.get('ticket_id', 'Unknown Ticket')))}")
                    st.markdown(
                        chip("Status", status, tone=_status_tone(ticket.get("status")))
                        + chip("Priority", priority, tone=_priority_tone(ticket.get("priority")))
                        + chip("Category", category, tone="info")
                        + chip("Group", ticket.get("assigned_group", "Unknown"), tone="neutral")
                    )
                    st.write(summary)
                    st.caption(
                        f"Employee: {ticket.get('employee_id', ticket.get('user_id', 'Unknown'))}  ·  "
                        f"Name: {ticket.get('full_name', 'Unknown')}  ·  "
                        f"Created: {created_at}  ·  Updated: {last_updated}"
                    )

        with tabs[2]:
            left, right = st.columns(2)
            with left:
                section_heading("Status mix")
                render_table(
                    [{"status": format_status(key), "count": value} for key, value in status_counts.items()],
                    empty_title="No status data",
                    empty_text="No ticket status values were returned.",
                )
            with right:
                section_heading("Priority mix")
                render_table(
                    [{"priority": format_status(key), "count": value} for key, value in priority_counts.items()],
                    empty_title="No priority data",
                    empty_text="No ticket priority values were returned.",
                )

except Exception as exc:
    st.error(f"Failed to load tickets: {exc}")
