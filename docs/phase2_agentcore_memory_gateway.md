# Phase 2: AgentCore Memory, Gateway, and Identity

This phase extends the AWS-native migration beyond Bedrock model, embedding, storage, and Knowledge Bases support. The application can now keep the current FastAPI/LangGraph runtime while progressively enabling AgentCore-managed memory and governed tool access.

## Goals

- Record governed conversation turns in Amazon Bedrock AgentCore Memory.
- Retrieve relevant memory records and pass them into the chat/runtime context.
- Route sensitive IAM-style tools through an AgentCore Gateway-compatible adapter.
- Preserve local mock IAM fallback until real Gateway targets are deployed.
- Surface Memory, Gateway, and Identity readiness in `/admin/status`, `/ready`, and the Architecture page.

## Runtime behavior

### Memory

When `AGENTCORE_MEMORY_ENABLED=true` and `AGENTCORE_MEMORY_ID` is set, the backend writes the user and assistant turn after each chat request.

The write is best-effort. A Memory outage does not fail a completed service desk workflow; the result is returned in the response under `agentcore_memory` and appears in system status diagnostics.

Actor IDs are derived from employee IDs:

```text
E10231 -> employee_E10231
```

The default namespace keeps records grouped by actor:

```text
/service-desk/{actorId}/
```

The namespace supports these placeholders:

```text
{actorId}
{employeeId}
{sessionId}
{requestId}
```

When `AGENTCORE_MEMORY_RETRIEVE_ENABLED=true`, the backend performs best-effort retrieval before local workflow execution and passes the normalized records into the workflow state as `memory_context`.

### Gateway

When `AGENTCORE_GATEWAY_ENABLED=true`, the Execution Agent attempts to call the configured gateway endpoint before using local mock IAM functions.

Workflow-to-tool mapping:

```text
password_reset  -> reset_password
account_unlock  -> unlock_account
vpn_reenable    -> reenable_vpn
```

The gateway adapter calls:

```text
<AGENTCORE_GATEWAY_URL>/<AGENTCORE_GATEWAY_TOOL_PREFIX>/<tool_name>
```

`AGENTCORE_GATEWAY_TOOL_PREFIX` may be empty. For example:

```text
AGENTCORE_GATEWAY_URL=https://gateway.example.com
AGENTCORE_GATEWAY_TOOL_PREFIX=tools

=> https://gateway.example.com/tools/unlock_account
```

If the gateway is unavailable and `AGENTCORE_GATEWAY_FALLBACK_TO_MOCK=true`, the existing mock tools are used. If fallback is disabled, the tool execution response fails clearly and is logged in workflow history.

### Identity

The gateway adapter supports either:

- bearer-token authentication through `AGENTCORE_GATEWAY_BEARER_TOKEN`, or
- API-key style authentication through `AGENTCORE_GATEWAY_API_KEY` and `AGENTCORE_GATEWAY_API_KEY_HEADER`.

This is a deploy-time adapter so the app can later move to AgentCore Identity-managed credentials without changing the workflow interface.

## Environment variables

```bash
AGENTCORE_MEMORY_ENABLED=true
AGENTCORE_MEMORY_ID=<memory-id>
AGENTCORE_MEMORY_ACTOR_PREFIX=employee
AGENTCORE_MEMORY_WRITE_EVENTS=true
AGENTCORE_MEMORY_RETRIEVE_ENABLED=true
AGENTCORE_MEMORY_NAMESPACE=/service-desk/{actorId}/
AGENTCORE_MEMORY_STRATEGY_ID=<optional-strategy-id>
AGENTCORE_MEMORY_TOP_K=3

AGENTCORE_GATEWAY_ENABLED=true
AGENTCORE_GATEWAY_URL=<gateway-url>
AGENTCORE_GATEWAY_TIMEOUT_SECONDS=30
AGENTCORE_GATEWAY_FALLBACK_TO_MOCK=true
AGENTCORE_GATEWAY_TOOL_PREFIX=<optional-prefix>

AGENTCORE_IDENTITY_ENABLED=true
AGENTCORE_GATEWAY_BEARER_TOKEN=<token>
# or
AGENTCORE_GATEWAY_API_KEY=<api-key>
AGENTCORE_GATEWAY_API_KEY_HEADER=X-API-Key
AGENTCORE_GATEWAY_AUTH_HEADER=Authorization
```

## Rollback

Disable Memory and Gateway without changing application code:

```bash
AGENTCORE_MEMORY_ENABLED=false
AGENTCORE_GATEWAY_ENABLED=false
AGENTCORE_GATEWAY_FALLBACK_TO_MOCK=true
```

The application will continue to use RDS workflow persistence and local mock IAM tools.

## Validation

Run:

```bash
python -m compileall -q app/backend app/frontend tests
pytest -q
```

Check:

- `/admin/status` includes `health.agentcore_memory`, `health.agentcore_gateway`, and `health.agentcore_identity`.
- `/ready` reports configuration warnings/errors for enabled-but-missing AgentCore settings.
- Chat responses include `agentcore_memory` when memory writes are attempted.
- Workflow history records Gateway tool runtime metadata when Gateway is used.
- The System Admin page shows AgentCore Memory, Gateway, and Identity status.
