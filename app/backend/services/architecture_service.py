from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.backend.config import settings
from app.backend.services.admin_service import get_system_status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_architecture_summary(db: Session) -> dict[str, Any]:
    system = get_system_status(db)

    agents = [
        {
            "name": "Intent Agent",
            "responsibility": "Classifies the user request into a supported IT workflow.",
            "model": settings.mistral_model,
            "source": "Mistral",
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
            "source": "PostgreSQL",
        },
        {
            "name": "Confirmation Agent",
            "responsibility": "Applies the approval gate before any sensitive action is executed.",
            "model": "workflow logic",
            "source": "LangGraph",
        },
        {
            "name": "Execution Agent",
            "responsibility": "Invokes the IAM tool and writes audit records.",
            "model": "tool execution",
            "source": "Workflow toolchain",
        },
        {
            "name": "Response Agent",
            "responsibility": "Turns the operational result into a user-friendly final answer.",
            "model": settings.mistral_model,
            "source": "Mistral",
        },
        {
            "name": "Ticket Agent",
            "responsibility": "Creates the service ticket after approval and execution.",
            "model": "Service desk logic",
            "source": "PostgreSQL",
        },
    ]

    flow = [
        "1. User submits a request in Streamlit.",
        "2. FastAPI receives the request and starts the LangGraph workflow.",
        "3. Intent Agent classifies the workflow.",
        "4. Retrieval Agent fetches the best chunks from PostgreSQL.",
        "5. Context Agent loads the employee and account context.",
        "6. Confirmation Agent requests approval if required.",
        "7. Execution Agent performs the IAM action.",
        "8. Response Agent uses Mistral to craft the final user-facing response.",
        "9. Ticket creation and audit logging persist the operational record.",
    ]

    return {
        "status": system.get("status", "unknown"),
        "generated_at": _now(),
        "system": system,
        "agents": agents,
        "flow": flow,
        "proof": {
            "llm_used_for_final_response": True,
            "llm_model": settings.mistral_model,
            "embedding_provider": system["config"].get("embedding_provider"),
            "embedding_model": system["config"].get("embedding_model"),
        },
    }
