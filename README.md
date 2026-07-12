# Agentic IT Service Desk

Enterprise-style IT service desk assistant built with FastAPI, LangGraph, Streamlit, PostgreSQL, Mistral, and Hugging Face/Ollama embeddings.

The application accepts an employee request, classifies the intent, retrieves knowledge-base evidence, loads employee/account context, asks for approval when required, executes a mock IAM action, writes workflow/audit records, creates a ticket, and returns a user-facing response.

## Current status

This codebase is prepared for the final deployment phase. The remaining project step is to deploy the validated backend, frontend, database schema, seed data, secrets, and persistent knowledge-base storage into AWS.

Implemented before AWS deployment:

- FastAPI backend with request IDs, CORS, security headers, optional API-key protection, health/readiness/version/metrics endpoints, and JSON logging.
- Streamlit frontend with chat, dashboard, tickets, audit, architecture, knowledge base, workflow history, and system admin pages.
- LangGraph workflow with conditional routing, clarification handling, confirmation gating, execution, and response generation.
- Hybrid retrieval with semantic and lexical scoring, citations, confidence, matched terms, and deterministic lexical fallback.
- Database-backed knowledge base with document upload, revisioning, activate/deactivate, metadata update, download, search, and vector refresh.
- Workflow/session/retrieval/audit persistence.
- Docker Compose setup with health checks and persistent upload volume.
- Preflight checks and regression tests.

## Local quickstart

```bash
python -m venv .venv
# Activate the virtual environment for your OS
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set real values for database and Mistral credentials.

Start the backend:

```bash
uvicorn app.backend.main:app --reload --host 0.0.0.0 --port 8000
```

Start the frontend:

```bash
streamlit run app/frontend/Streamlit_App.py
```

Run validation:

```bash
python -m compileall app scripts tests
pytest -q
python scripts/preflight_check.py
```

## Docker quickstart

```bash
cp .env.example .env
# Edit .env first
docker compose build
docker compose up
```

Backend: `http://localhost:8000`

Frontend: `http://localhost:8501`

## Important endpoints

- `GET /health` — lightweight liveness.
- `GET /ready` — readiness and preflight status.
- `GET /metrics` — JSON operational counters.
- `GET /admin/status` — system health, config proof, counts, preflight.
- `POST /chat` — main agentic workflow endpoint.
- `POST /retrieve` — retrieval test endpoint.
- `GET /dashboard` — operations dashboard payload.
- `GET /tickets` — ticket list with filters.
- `GET /audit` — audit list with filters.
- `GET /workflow/sessions` — recent workflow sessions.
- `GET /workflow/history/{request_id}` — trace for one request.
- `GET /knowledge-base/summary` — KB overview.
- `POST /knowledge-base/upload` — upload and index document.
- `POST /knowledge-base/refresh` — rebuild active vector store.

## Documentation

- `docs/INDEX.md`
- `docs/architecture.md`
- `docs/workflow_design.md`
- `docs/api_spec.md`
- `docs/configuration.md`
- `docs/pre_aws_runbook.md`
- `docs/final_validation.md`

## Security notes

Do not commit `.env` or any real secrets. `.env.example` contains placeholders only. For shared or production-like environments, set:

```bash
API_KEY_REQUIRED=true
BACKEND_API_KEY=<secret value>
```

The Streamlit frontend sends the same key when `BACKEND_API_KEY`, `FRONTEND_API_KEY`, or `APP_API_KEY` is set.

## AWS Bedrock + AgentCore migration

Phase 2 introduces AWS-native agent runtime support while keeping the current local LangGraph path available.

Key environment variables:

```bash
LLM_PROVIDER=bedrock
AWS_REGION=us-east-1
BEDROCK_TEXT_MODEL_ID=<your-bedrock-chat-model-id>

# AWS-native knowledge path
EMBEDDING_PROVIDER=bedrock
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
KB_STORAGE_BACKEND=s3
KB_S3_BUCKET=<your-knowledge-bucket>
RETRIEVAL_PROVIDER=bedrock_kb
BEDROCK_KNOWLEDGE_BASE_ID=<your-bedrock-kb-id>
RETRIEVAL_FALLBACK_TO_DB=true

AGENT_RUNTIME_PROVIDER=local
# After deploying AgentCore Runtime:
# AGENT_RUNTIME_PROVIDER=agentcore
# AGENTCORE_RUNTIME_ARN=<your-agentcore-runtime-arn>
```

See `docs/phase2_bedrock_agentcore.md`, `docs/phase2_bedrock_storage_retrieval.md`, and `docs/phase2_agentcore_memory_gateway.md` for the migration sequence, IAM permissions, managed memory, governed tool access, and rollback approach.
