from __future__ import annotations

from collections import Counter
from html import escape
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
)
from app.frontend.utils.ui_helpers import format_local_datetime, format_status


st.set_page_config(page_title="Audit Logs", page_icon="🧾", layout="wide")
apply_app_theme()
page_header(
    "Audit Logs",
    "Review approval, execution, retrieval, and response audit records with filters designed for operational triage.",
    eyebrow="Governance • Audit trail",
    icon="🧾",
)


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("audit_logs") or payload.get("audit") or payload.get("items") or payload.get("results") or []
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return []


def _status_bucket(value: Any) -> str:
    text = str(value or "").lower()
    if any(token in text for token in ("error", "fail", "blocked", "denied")):
        return "error"
    if any(token in text for token in ("warn", "pending", "waiting")):
        return "warning"
    if any(token in text for token in ("ok", "success", "complete", "completed", "approved")):
        return "success"
    return "other"


def _bucket_tone(bucket: str) -> str:
    return {"success": "success", "warning": "warning", "error": "danger"}.get(bucket, "neutral")


with st.container(border=True):
    section_heading("Filters", "Use request, stage, and status filters to isolate a specific workflow trace.")
    c1, c2, c3, c4 = st.columns([1.25, 1, 1, 0.7])
    with c1:
        request_id = st.text_input("Request ID", value="", placeholder="REQ-...")
    with c2:
        stage = st.text_input("Stage", value="", placeholder="execution")
    with c3:
        status = st.text_input("Status", value="", placeholder="completed")
    with c4:
        limit = st.number_input("Limit", min_value=10, max_value=500, value=100, step=10)

if st.button("Refresh audit logs", use_container_width=True):
    st.rerun()

try:
    params: dict[str, Any] = {"limit": int(limit)}
    if request_id.strip():
        params["request_id"] = request_id.strip()
    if stage.strip():
        params["stage"] = stage.strip()
    if status.strip():
        params["status"] = status.strip()

    response = api_get("/audit", params=params, timeout=30)
    response.raise_for_status()
    audit_logs = _as_list(response.json())

    buckets = Counter(_status_bucket(row.get("status")) for row in audit_logs)
    unique_requests = len({row.get("request_id") for row in audit_logs if row.get("request_id")})
    stages = len({row.get("stage") for row in audit_logs if row.get("stage")})

    metrics = st.columns(4)
    with metrics[0]:
        kpi_card("Returned Records", len(audit_logs), detail="Records matching filters", tone="info")
    with metrics[1]:
        kpi_card("Successful", buckets.get("success", 0), detail="Completed or approved records", tone="success")
    with metrics[2]:
        kpi_card("Warnings / Errors", buckets.get("warning", 0) + buckets.get("error", 0), detail="Warnings and errors to review", tone="warning" if buckets.get("error", 0) == 0 else "danger")
    with metrics[3]:
        kpi_card("Requests", unique_requests, detail=f"{stages} stages", tone="neutral")

    soft_divider()

    if not audit_logs:
        empty_state("No audit records found", "Try increasing the limit or clearing one of the filters.")
    else:
        tabs = st.tabs(["Table", "Audit Cards", "Status Mix"])

        with tabs[0]:
            table_rows = []
            for row in audit_logs:
                table_rows.append(
                    {
                        "created_at": format_local_datetime(row.get("created_at")),
                        "request_id": row.get("request_id"),
                        "stage": format_status(row.get("stage")),
                        "status": format_status(row.get("status")),
                        "message": row.get("message"),
                        "created_by": row.get("created_by"),
                        "audit_id": row.get("audit_id"),
                    }
                )
            render_table(table_rows, empty_title="No audit rows", empty_text="No audit table rows matched the filters.")

        with tabs[1]:
            section_heading("Audit cards", "Readable cards for demos, screenshots, and governance reviews.")
            for row in audit_logs:
                stage_label = format_status(row.get("stage"))
                status_label = format_status(row.get("status"))
                created_at = format_local_datetime(row.get("created_at"))
                message = row.get("message") or "—"
                bucket = _status_bucket(row.get("status"))
                with st.container(border=True):
                    st.markdown(f"### {escape(str(row.get('request_id', 'Unknown Request')))}")
                    st.markdown(
                        chip("Stage", stage_label, tone="info")
                        + chip("Status", status_label, tone=_bucket_tone(bucket))
                        + chip("Time", created_at, tone="neutral")
                        + chip("By", row.get("created_by", "system"), tone="neutral")
                    )
                    st.write(message)
                    if row.get("audit_id"):
                        st.caption(f"Audit ID: {row.get('audit_id')}")

        with tabs[2]:
            section_heading("Status distribution")
            render_table(
                [{"bucket": key, "count": value} for key, value in buckets.items()],
                empty_title="No bucket data",
                empty_text="No status values were available.",
            )

except Exception as exc:
    st.error(f"Failed to load audit logs: {exc}")
