from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app.frontend.utils.api_client import api_get
from app.frontend.utils.ui_components import (
    apply_app_theme,
    chip,
    kpi_card,
    page_header,
    render_table,
    section_heading,
    soft_divider,
    status_card,
    value_card,
)


st.set_page_config(page_title="System Admin", page_icon="🛡️", layout="wide")
apply_app_theme()
page_header(
    "System Admin",
    "Operational health, runtime counts, configuration proof, and pre-deployment diagnostics without duplicate status clutter.",
    eyebrow="Admin • Runtime diagnostics",
    icon="🛡️",
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_text(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _status_value(value: bool | None) -> str:
    if value is True:
        return "ok"
    if value is False:
        return "error"
    return "unknown"


def _count_rows(counts: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {
        "workflow_sessions": "Workflow Sessions",
        "workflow_events": "Workflow Events",
        "retrieval_logs": "Retrieval Logs",
        "document_chunks": "Document Chunks",
        "service_tickets": "Service Tickets",
        "audit_logs": "Audit Logs",
        "documents": "Documents",
        "knowledge_documents": "KB Revisions",
    }
    return [{"metric": labels.get(key, key), "value": value} for key, value in counts.items()]


def _render_counts(counts: dict[str, Any]) -> None:
    cards = [
        ("Workflow Sessions", counts.get("workflow_sessions", 0), "Persisted workflow runs", "info"),
        ("Workflow Events", counts.get("workflow_events", 0), "Agent timeline events", "accent"),
        ("Retrieval Logs", counts.get("retrieval_logs", 0), "Evidence lookups", "accent"),
        ("Document Chunks", counts.get("document_chunks", 0), "Indexed KB chunks", "info"),
        ("Service Tickets", counts.get("service_tickets", 0), "Created records", "neutral"),
        ("Audit Logs", counts.get("audit_logs", 0), "Governance records", "neutral"),
        ("Documents", counts.get("documents", 0), "Logical sources", "neutral"),
        ("KB Revisions", counts.get("knowledge_documents", 0), "Revision registry", "neutral"),
    ]
    cols = st.columns(4)
    for idx, (label, value, detail, tone) in enumerate(cards):
        with cols[idx % 4]:
            kpi_card(label, value, detail=detail, tone=tone)


def _render_config_table(config: dict[str, Any]) -> None:
    config_rows = [
        {"setting": "service_name", "value": config.get("service_name")},
        {"setting": "service_version", "value": config.get("service_version")},
        {"setting": "app_env", "value": config.get("app_env")},
        {"setting": "log_level", "value": config.get("log_level")},
        {"setting": "api_key_required", "value": config.get("api_key_required")},
        {"setting": "api_key_configured", "value": config.get("api_key_configured")},
        {"setting": "docs_enabled", "value": config.get("docs_enabled")},
        {"setting": "mistral_model", "value": config.get("mistral_model")},
        {"setting": "mistral_enabled", "value": config.get("mistral_enabled")},
        {"setting": "mistral_key_set", "value": config.get("mistral_key_set")},
        {"setting": "embedding_provider", "value": config.get("embedding_provider")},
        {"setting": "embedding_model", "value": config.get("embedding_model")},
        {"setting": "huggingface_model", "value": config.get("huggingface_model")},
        {"setting": "ollama_url", "value": config.get("ollama_url")},
        {"setting": "ollama_model", "value": config.get("ollama_model")},
        {"setting": "database_url_redacted", "value": config.get("database_url_redacted")},
        {"setting": "kb_storage_root", "value": config.get("kb_storage_root")},
    ]
    render_table(
        config_rows,
        empty_title="No configuration",
        empty_text="No runtime configuration was returned.",
        column_config={
            "setting": st.column_config.TextColumn("Setting", width="medium"),
            "value": st.column_config.TextColumn("Value", width="large"),
        },
    )


def _render_preflight(preflight: dict[str, Any]) -> None:
    preflight_summary = _safe_dict(preflight.get("summary"))
    status = preflight.get("status", "unknown")

    cols = st.columns(4)
    with cols[0]:
        status_card("Preflight", status, detail="Pre-AWS readiness checks")
    with cols[1]:
        kpi_card("Passed", preflight_summary.get("pass", 0), detail="Checks passing", tone="success")
    with cols[2]:
        kpi_card("Warnings", preflight_summary.get("warn", 0), detail="Warnings to review", tone="warning")
    with cols[3]:
        kpi_card("Errors", preflight_summary.get("error", 0), detail="Blocking errors", tone="danger" if preflight_summary.get("error", 0) else "neutral")

    checks = preflight.get("checks") if isinstance(preflight.get("checks"), list) else []
    rows = []
    for item in checks:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "check": item.get("name"),
                "status": item.get("status"),
                "message": item.get("message"),
                "details": item.get("details"),
            }
        )
    render_table(rows, empty_title="No preflight checks", empty_text="No preflight checks were returned.")


if st.button("Refresh status", use_container_width=True):
    st.rerun()

try:
    response = api_get("/admin/status", timeout=30)
    response.raise_for_status()
    payload = _safe_dict(response.json())

    health = _safe_dict(payload.get("health"))
    counts = _safe_dict(payload.get("counts"))
    config = _safe_dict(payload.get("config"))
    proof = _safe_dict(payload.get("proof"))

    db_health = _safe_dict(health.get("database"))
    ollama_health = _safe_dict(health.get("ollama"))
    preflight = _safe_dict(payload.get("preflight") or health.get("preflight"))

    embedding_provider = _safe_text(config.get("embedding_provider"), "unknown").lower()
    ollama_required = embedding_provider == "ollama"
    db_ok = bool(db_health.get("ok"))
    ollama_ok = bool(ollama_health.get("ok"))

    if db_ok and (ollama_ok or not ollama_required):
        backend_display = "ok"
    elif db_ok:
        backend_display = "degraded"
    else:
        backend_display = "error"

    if ollama_ok:
        ollama_display = "ok"
        ollama_detail = "Ollama is reachable."
    elif ollama_required:
        ollama_display = "error"
        ollama_detail = "Required because EMBEDDING_PROVIDER=ollama."
    else:
        ollama_display = "optional"
        ollama_detail = f"Not required while embedding provider is {embedding_provider}."

    section_heading("System health", "A single clean status row; optional dependencies are clearly labeled.")
    status_cols = st.columns(4)
    with status_cols[0]:
        status_card("Backend", backend_display, detail="API and required dependencies")
    with status_cols[1]:
        status_card("Database", _status_value(db_ok), detail=_safe_text(db_health.get("message"), "PostgreSQL health probe"))
    with status_cols[2]:
        status_card("Ollama", ollama_display, detail=ollama_detail)
    with status_cols[3]:
        status_card("Mistral", "enabled" if config.get("mistral_enabled") else "disabled", detail=_safe_text(config.get("mistral_model"), "Final response LLM"), tone="info" if config.get("mistral_enabled") else "warning")

    st.caption(f"Generated at: {payload.get('generated_at', 'unknown')}")
    soft_divider()

    section_heading("Runtime counts", "Core operating totals across workflows, retrieval, tickets, audit, and documents.")
    _render_counts(counts)

    tabs = st.tabs(["Preflight", "Configuration", "Counts Table", "Health Details", "Proof", "Raw"])
    with tabs[0]:
        _render_preflight(preflight)
    with tabs[1]:
        _render_config_table(config)
    with tabs[2]:
        render_table(_count_rows(counts), empty_title="No count data", empty_text="The admin endpoint did not return counts.")
    with tabs[3]:
        st.json(health)
    with tabs[4]:
        st.json(proof)
    with tabs[5]:
        st.json(payload)

except Exception as exc:
    st.error(f"Failed to load system status: {exc}")
