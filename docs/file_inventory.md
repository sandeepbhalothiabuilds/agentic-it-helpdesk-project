# File Inventory

## Backend

- `app/backend/main.py` — FastAPI app setup, middleware, exception handlers, router registration.
- `app/backend/config.py` — environment-backed settings, safe defaults, redacted config helpers.
- `app/backend/observability.py` — JSON logging, request IDs, API-key gate, security headers.
- `app/backend/security.py` — API-key extraction and constant-time validation.
- `app/backend/api/*` — route modules for chat, retrieval, KB, workflow, operations, tickets, audit, health.
- `app/backend/agents/*` — LangGraph nodes and prompt/response helpers.
- `app/backend/services/*` — orchestration, retrieval, KB lifecycle, dashboard/admin/preflight, ticket/audit/state persistence.
- `app/backend/db/*` — SQLAlchemy models/session helpers and CRUD helpers.
- `app/backend/rag/*` — chunking, embedding, document loading, legacy retriever helpers.
- `app/backend/tools/*` — mock IAM and ticket tool facades.

## Frontend

- `app/frontend/Streamlit_App.py` — chat experience and case summary.
- `app/frontend/pages/1_Dashboard.py` — operational dashboard.
- `app/frontend/pages/2_Tickets.py` — ticket browser.
- `app/frontend/pages/3_Audit.py` — audit browser.
- `app/frontend/pages/4_Architecture.py` — architecture and proof view.
- `app/frontend/pages/4_Knowledge_Base.py` — KB upload, search, revisions, lifecycle actions.
- `app/frontend/pages/5_Workflow_History.py` — sessions and timeline view.
- `app/frontend/pages/6_System_Admin.py` — admin health/config/preflight view.
- `app/frontend/utils/api_client.py` — backend URL, request headers, optional API-key support.
- `app/frontend/utils/ui_helpers.py` — timestamp, label, status, and pill formatting.

## Scripts

- `scripts/start_backend.sh` — container/local backend entrypoint.
- `scripts/start_frontend.sh` — container/local frontend entrypoint.
- `scripts/preflight_check.py` — final runtime readiness check.
- `scripts/ingest_documents.py` — seed or refresh knowledge-base documents.
- `scripts/build_chunks.py` — rebuild active chunk/vector store.
- `scripts/load_structured_data.py` — load CSV seed data into PostgreSQL.
- `scripts/rebuild_index.py` — compatibility wrapper for active chunk rebuild.

## Tests

- `tests/test_health.py`
- `tests/test_snapshot_services.py`
- `tests/test_workflows.py`
- `tests/test_workflow_routes.py`
- `tests/test_retrieval.py`
- `tests/test_knowledge_base.py`
- `tests/test_graph_routing.py`

## Config/deployment

- `.env.example` — safe placeholder configuration.
- `.gitignore` and `.dockerignore` — exclude secrets, local artifacts, uploads.
- `docker-compose.yml` — backend/frontend services and upload volume.
- `Dockerfile.backend` and `Dockerfile.frontend` — image build definitions.
- `requirements.txt` and `pyproject.toml` — dependencies/package metadata.
