# Phase 2: CloudWatch / Agent Observability

This phase adds application-level telemetry for the AWS Bedrock and AgentCore migration while preserving the existing PostgreSQL audit and workflow-event records.

## What changed

The new telemetry layer emits two types of observability data:

1. **Structured JSON events** for local debugging and CloudWatch Logs inspection.
2. **Optional CloudWatch Embedded Metrics Format (EMF)** metric log events for ECS/CloudWatch deployments.

This gives the team operational signals without requiring a new metrics dependency or a sidecar during the first AWS rollout.

## Files added or changed

- `app/backend/telemetry.py` — shared telemetry helpers. It records operation events, CloudWatch EMF metrics, redacts sensitive payload-like fields, and exposes telemetry status.
- `app/backend/observability.py` — JSON log formatter now lets EMF payloads pass through as top-level JSON so CloudWatch can extract metrics.
- `app/backend/config.py` — adds observability environment variables and public config fields.
- `app/backend/llm/bedrock_client.py` — records Bedrock Converse latency, token usage, stop reason, and errors.
- `app/backend/llm/provider.py` — records provider-level LLM success, fallback, and failure events.
- `app/backend/rag/embedding_service.py` — records embedding latency, provider, vector dimension, fallback, and errors.
- `app/backend/rag/bedrock_kb_service.py` — records Bedrock Knowledge Bases retrieval latency and result counts.
- `app/backend/services/retrieval_service.py` — records selected retrieval provider, fallback to DB, confidence, and result counts.
- `app/backend/agentcore/client.py` — records AgentCore Runtime invocation latency and status.
- `app/backend/agentcore/memory.py` — records AgentCore Memory create/retrieve latency and status. This file also removes the duplicate `record_conversation_turn` implementation and avoids recursion.
- `app/backend/agentcore/gateway.py` — records AgentCore Gateway tool invocation latency, tool name, identity status, and errors.
- `app/backend/services/workflow_service.py` — records local LangGraph workflow duration, status, evidence count, ticket status, and approval status.
- `app/backend/services/admin_service.py` — exposes observability status through `/admin/status`.
- `app/backend/services/preflight_service.py` — surfaces observability readiness warnings.
- `app/frontend/pages/6_System_Admin.py` — adds an Observability tab to the admin page.

## Runtime flow

```text
Streamlit / Chat
  -> FastAPI /chat
  -> AgentCore Runtime or local LangGraph
  -> Bedrock / retrieval / memory / gateway operations
  -> app.backend.telemetry.record_operation(...)
  -> JSON logs
  -> optional CloudWatch EMF metrics
  -> System Admin status view
```

## Configuration

Local-safe defaults:

```bash
OBSERVABILITY_ENABLED=true
OBSERVABILITY_LOG_EVENTS=true
OBSERVABILITY_EMF_ENABLED=false
OBSERVABILITY_NAMESPACE=AgenticITServiceDesk
OBSERVABILITY_REDACT_PAYLOADS=true
OBSERVABILITY_TRACE_PROMPTS=false
OBSERVABILITY_SAMPLE_RATE=1.0
```

AWS/ECS target:

```bash
OBSERVABILITY_ENABLED=true
OBSERVABILITY_LOG_EVENTS=true
OBSERVABILITY_EMF_ENABLED=true
OBSERVABILITY_NAMESPACE=AgenticITServiceDesk
OBSERVABILITY_REDACT_PAYLOADS=true
OBSERVABILITY_TRACE_PROMPTS=false
OBSERVABILITY_SAMPLE_RATE=1.0
```

`OBSERVABILITY_TRACE_PROMPTS=true` should only be used temporarily in a controlled debugging environment because prompts and conversation text may contain sensitive information.

## Local testing without AWS

Run the normal regression suite:

```bash
python -m compileall -q app/backend app/frontend tests
pytest -q
```

Run the admin status endpoint:

```bash
uvicorn app.backend.main:app --reload --host 0.0.0.0 --port 8000
curl http://localhost:8000/admin/status
```

Check that the payload includes:

```json
{
  "health": {
    "observability": {
      "enabled": true,
      "cloudwatch_emf_enabled": false,
      "namespace": "AgenticITServiceDesk"
    }
  }
}
```

Trigger a chat request locally. You should see structured JSON log lines for request completion and operation telemetry. With EMF disabled, no CloudWatch metric object is emitted.

## Local EMF smoke test

You can enable EMF locally to inspect the metric-shaped log event:

```bash
OBSERVABILITY_EMF_ENABLED=true pytest -q tests/test_phase2_observability.py
```

The test checks that the logger receives a top-level `_aws` EMF payload.

## AWS validation

After deploying to ECS / CloudWatch Logs with `OBSERVABILITY_EMF_ENABLED=true`:

1. Open CloudWatch Logs for the backend task.
2. Search for `OperationLatencyMs`, `OperationCount`, or `OperationErrors`.
3. Open CloudWatch Metrics and inspect namespace `AgenticITServiceDesk`.
4. Confirm dimensions include `Service`, `Environment`, `Operation`, `Provider`, and `Status`.
5. Submit one chat request and verify metrics for `workflow.handle_request`, retrieval, LLM, and memory/gateway operations depending on enabled providers.

## Rollback

Disable metrics while keeping normal JSON logs:

```bash
OBSERVABILITY_EMF_ENABLED=false
```

Disable all application telemetry events:

```bash
OBSERVABILITY_ENABLED=false
```

The database audit trail, workflow events, and retrieval logs continue to work independently of the telemetry layer.
