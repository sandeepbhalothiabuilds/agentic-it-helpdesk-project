from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app.frontend.utils.api_client import api_get
from app.frontend.utils.ui_components import (
    apply_app_theme,
    card,
    chip,
    page_header,
    render_table,
    section_heading,
    soft_divider,
    status_card,
    timeline_item,
    value_card,
)
from app.frontend.utils.ui_helpers import format_status


st.set_page_config(page_title="Architecture & Agents", page_icon="🧭", layout="wide")
apply_app_theme()
page_header(
    "Architecture & Agents",
    "A readable product-style view of the multi-agent workflow, runtime models, retrieval layer, and health proof.",
    eyebrow="Architecture • Agent map",
    icon="🧭",
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_text(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _status_text(value: Any) -> str:
    text = _safe_text(value, "unknown").lower()
    if text in {"ok", "success", "completed", "complete"}:
        return "ok"
    if text in {"degraded", "warning", "warn", "pending"}:
        return "degraded"
    if text in {"failed", "error"}:
        return "error"
    return text


try:
    response = api_get("/architecture/summary", timeout=30)
    response.raise_for_status()
    payload = _safe_dict(response.json())

    proof = _safe_dict(payload.get("proof"))
    system = _safe_dict(payload.get("system"))
    agents = payload.get("agents", []) or []
    flow = payload.get("flow", []) or []
    config = _safe_dict(system.get("config"))
    health = _safe_dict(system.get("health"))
    counts = _safe_dict(system.get("counts"))

    llm_used = "Yes" if proof.get("llm_used_for_final_response") else "No"
    llm_model = _safe_text(proof.get("llm_model"), "unknown")
    embedding_provider = _safe_text(proof.get("embedding_provider"), "unknown")
    embedding_model = _safe_text(proof.get("embedding_model"), "unknown")

    cols = st.columns([0.8, 1.25, 1, 1.45])
    with cols[0]:
        value_card("LLM Used", llm_used, detail="Used by response generation", tone="success" if llm_used == "Yes" else "warning")
    with cols[1]:
        value_card("LLM Model", llm_model, detail="Intent and response model", mono=True, tone="info")
    with cols[2]:
        value_card("Embedding Provider", embedding_provider, detail="Embedding provider for retrieval", mono=True, tone="accent")
    with cols[3]:
        value_card("Embedding Model", embedding_model, detail="Embedding model used for vectors", mono=True, tone="accent")

    soft_divider()

    section_heading("Runtime architecture", "The request moves left-to-right through specialized agents and persistence services.")
    card(
        "End-to-end path",
        "Streamlit Chat → FastAPI /chat → LangGraph → Retrieval + Context → Confirmation → IAM Tool → Ticket + Audit → Final Response",
        tone="accent",
        mono=True,
    )

    if flow:
        for start in range(0, len(flow), 3):
            flow_cols = st.columns(3)
            for offset, col in enumerate(flow_cols):
                idx = start + offset + 1
                if idx > len(flow):
                    continue
                with col:
                    timeline_item(idx, f"Step {idx}", _safe_text(flow[idx - 1]))
    else:
        card("Flow unavailable", "The architecture endpoint did not return flow information.", tone="warning")

    soft_divider()

    section_heading("Agents", "Each agent has a narrow responsibility so the workflow is easier to debug and audit.")
    agent_rows = []
    for agent in agents if isinstance(agents, list) else []:
        if not isinstance(agent, dict):
            continue
        agent_rows.append(
            {
                "Agent": agent.get("name", "Agent"),
                "Responsibility": agent.get("responsibility", ""),
                "Model": agent.get("model", "unknown"),
                "Source": agent.get("source", "unknown"),
            }
        )

    if agent_rows:
        render_table(
            agent_rows,
            empty_title="No agents found",
            empty_text="The architecture endpoint did not return agent metadata.",
            column_config={
                "Agent": st.column_config.TextColumn("Agent", width="medium"),
                "Responsibility": st.column_config.TextColumn("Responsibility", width="large"),
                "Model": st.column_config.TextColumn("Model", width="large"),
                "Source": st.column_config.TextColumn("Source", width="medium"),
            },
        )
        for start in range(0, len(agent_rows), 3):
            row_cols = st.columns(3)
            for offset, col in enumerate(row_cols):
                index = start + offset
                if index >= len(agent_rows):
                    continue
                item = agent_rows[index]
                with col:
                    card(
                        str(item["Agent"]),
                        str(item["Responsibility"]),
                        footer=f"Model: {item['Model']} | Source: {item['Source']}",
                        tone="info" if index in {0, 1, 5} else "neutral",
                    )
    else:
        card("No agents found", "No agent metadata was returned.", tone="warning")

    soft_divider()

    section_heading("System health & proof", "Proof values are shown as full wrapped text so long model names remain readable.")
    db_ok = bool(_safe_dict(health.get("database")).get("ok"))
    ollama_ok = bool(_safe_dict(health.get("ollama")).get("ok"))
    embedding_provider_lower = embedding_provider.lower()
    ollama_required = embedding_provider_lower == "ollama"
    ollama_value = "ok" if ollama_ok else "error" if ollama_required else "optional"

    health_cols = st.columns(4)
    with health_cols[0]:
        status_card("Backend", _status_text(payload.get("status", "unknown")), detail="Architecture API health")
    with health_cols[1]:
        status_card("Database", "ok" if db_ok else "error", detail="Database connectivity")
    with health_cols[2]:
        status_card("Ollama", ollama_value, detail="Optional unless Ollama provider is selected")
    with health_cols[3]:
        status_card("Mistral", "enabled" if config.get("mistral_enabled") else "disabled", detail=_safe_text(config.get("mistral_model"), "LLM completion"), tone="info" if config.get("mistral_enabled") else "warning")

    count_cols = st.columns(4)
    with count_cols[0]:
        value_card("Workflow Sessions", counts.get("workflow_sessions", 0), detail="Persisted workflow runs")
    with count_cols[1]:
        value_card("Workflow Events", counts.get("workflow_events", 0), detail="LangGraph timeline entries")
    with count_cols[2]:
        value_card("Retrieval Logs", counts.get("retrieval_logs", 0), detail="Knowledge retrieval events")
    with count_cols[3]:
        value_card("Documents", counts.get("documents", 0), detail="Active knowledge sources")

    tabs = st.tabs(["Configuration", "Health Details", "Raw Proof"])
    with tabs[0]:
        config_rows = [{"setting": key, "value": value} for key, value in config.items()]
        render_table(config_rows, empty_title="No configuration", empty_text="No configuration fields were returned.")
    with tabs[1]:
        st.json(health)
    with tabs[2]:
        st.json({"status": format_status(payload.get("status")), "proof": proof, "counts": counts, "config": config})

except Exception as exc:
    st.error(f"Failed to load architecture summary: {exc}")
