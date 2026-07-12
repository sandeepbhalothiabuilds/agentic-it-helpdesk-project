from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.backend.llm.provider import active_model_name, active_provider_name
from app.backend.services.admin_service import get_system_status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider_source(provider: str) -> str:
    if provider == "bedrock":
        return "Amazon Bedrock"
    if provider == "local":
        return "Local fallback"
    return "Mistral"


def get_architecture_summary(db: Session) -> dict[str, Any]:
    system = get_system_status(db)
    config = system.get("config", {}) if isinstance(system, dict) else {}
    llm_provider = str(config.get("llm_provider") or active_provider_name())
    llm_model = str(config.get("llm_model") or active_model_name())
    agent_runtime = str(config.get("agent_runtime_provider") or "local")
    runtime_source = "Amazon Bedrock AgentCore Runtime" if agent_runtime == "agentcore" else "FastAPI + LangGraph"

    agents = [
        {
            "name": "Intent Agent",
            "responsibility": "Classifies the user request into a supported IT workflow.",
            "model": llm_model,
            "source": _provider_source(llm_provider),
        },
        {
            "name": "Retrieval Agent",
            "responsibility": "Retrieves relevant chunks from the vector-backed PostgreSQL knowledge base.",
            "model": system["config"].get("embedding_model"),
            "source": system["config"].get("embedding_provider"),
        },
        {
            "name": "Context Agent",
            "responsibility": "Loads employee, account, and rule context from PostgreSQL.",
            "model": "database lookup",
            "source": "PostgreSQL / Amazon RDS",
        },
        {
            "name": "Confirmation Agent",
            "responsibility": "Applies the approval gate before any sensitive action is executed.",
            "model": "workflow policy",
            "source": runtime_source,
        },
        {
            "name": "Execution Agent",
            "responsibility": "Invokes IAM tooling and writes audit records.",
            "model": "tool execution",
            "source": "AgentCore Gateway" if config.get("agentcore_gateway_enabled") else "Local mock IAM toolchain",
        },
        {
            "name": "Response Agent",
            "responsibility": "Turns the operational result into a user-friendly final answer.",
            "model": llm_model,
            "source": _provider_source(llm_provider),
        },
        {
            "name": "Ticket Agent",
            "responsibility": "Creates the service ticket after approval and execution.",
            "model": "Service desk logic",
            "source": "PostgreSQL / Amazon RDS",
        },
        {
            "name": "AgentCore Memory",
            "responsibility": "Stores governed conversation turns and optional long-term memory context for agent sessions.",
            "model": "managed memory",
            "source": "Amazon Bedrock AgentCore Memory" if config.get("agentcore_memory_enabled") else "disabled",
        },
        {
            "name": "AgentCore Gateway",
            "responsibility": "Provides the migration path from mock IAM tools to governed enterprise tool access.",
            "model": "managed tool gateway",
            "source": "Amazon Bedrock AgentCore Gateway" if config.get("agentcore_gateway_enabled") else "disabled",
        },
        {
            "name": "Observability Layer",
            "responsibility": "Emits JSON events and optional CloudWatch Embedded Metrics for LLM, retrieval, memory, gateway, and workflow operations.",
            "model": config.get("observability_namespace") or "AgenticITServiceDesk",
            "source": "CloudWatch EMF" if config.get("observability_emf_enabled") else "structured application logs",
        },
    ]

    if agent_runtime == "agentcore":
        flow = [
            "1. User submits a request in Streamlit.",
            "2. FastAPI validates the request and delegates the agent session to Amazon Bedrock AgentCore Runtime.",
            "3. AgentCore maintains the runtime session and invokes the LangGraph-compatible agent package.",
            "4. Amazon Bedrock provides the LLM calls for intent and final response generation.",
            "5. AgentCore Memory can provide prior session context to the agent payload.",
            "6. AgentCore Gateway can execute governed enterprise tools instead of local mock tools.",
            "7. Retrieval, context, approval, execution, ticketing, and audit events are returned to FastAPI for persistence.",
            "8. Streamlit displays the final response, evidence, ticket state, and workflow proof.",
        ]
    else:
        flow = [
            "1. User submits a request in Streamlit.",
            "2. FastAPI receives the request and starts the local LangGraph workflow.",
            "3. Intent Agent classifies the workflow using the configured LLM provider.",
            "4. AgentCore Memory optionally retrieves prior context for continuity.",
            "5. Retrieval Agent fetches the best chunks from the configured retrieval provider.",
            "6. Context Agent loads the employee and account context.",
            "7. Confirmation Agent requests approval if required.",
            "8. Execution Agent performs the IAM action through AgentCore Gateway when configured, otherwise through the local mock tool.",
            "9. Response Agent uses the configured LLM provider to craft the final user-facing response.",
            "10. Ticket creation, audit logging, and telemetry persist the operational record and emit runtime metrics.",
        ]

    return {
        "status": system.get("status", "unknown"),
        "generated_at": _now(),
        "system": system,
        "agents": agents,
        "flow": flow,
        "proof": {
            "llm_used_for_final_response": True,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "agent_runtime_provider": agent_runtime,
            "agentcore_enabled": bool(config.get("agentcore_enabled")),
            "agentcore_memory_enabled": bool(config.get("agentcore_memory_enabled")),
            "agentcore_gateway_enabled": bool(config.get("agentcore_gateway_enabled")),
            "agentcore_identity_enabled": bool(config.get("agentcore_identity_enabled")),
            "observability_enabled": bool(config.get("observability_enabled")),
            "observability_emf_enabled": bool(config.get("observability_emf_enabled")),
            "observability_namespace": config.get("observability_namespace"),
            "embedding_provider": system["config"].get("embedding_provider"),
            "embedding_model": system["config"].get("embedding_model"),
        },
    }
