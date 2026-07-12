# Phase 2: AWS Bedrock + AgentCore Migration

This phase introduces AWS-native AI runtime support while preserving the existing FastAPI, Streamlit, PostgreSQL, LangGraph, and audit architecture.

## What this batch changes

This first migration batch adds three compatibility layers:

1. **LLM provider facade**
   - `LLM_PROVIDER=mistral` keeps the existing behavior.
   - `LLM_PROVIDER=bedrock` routes intent classification and final response generation through Amazon Bedrock Converse.
   - `LLM_FALLBACK_PROVIDER` and `LLM_FALLBACK_ENABLED` keep a safe fallback path during migration.

2. **Amazon Bedrock client**
   - Uses the Bedrock Runtime `Converse` API.
   - Normalizes existing prompt/message shapes into Bedrock message format.
   - Returns trace metadata such as provider, model, latency, usage, metrics, and stop reason.

3. **Amazon Bedrock AgentCore Runtime facade**
   - `AGENT_RUNTIME_PROVIDER=local` keeps the local FastAPI/LangGraph runtime.
   - `AGENT_RUNTIME_PROVIDER=agentcore` delegates `/chat` to AgentCore Runtime when `AGENTCORE_RUNTIME_ARN` is set.
   - `AGENTCORE_FALLBACK_TO_LOCAL=true` lets the app fall back to the local LangGraph workflow while the AgentCore runtime is being configured.

## AWS environment variables

```bash
LLM_PROVIDER=bedrock
LLM_FALLBACK_PROVIDER=mistral
LLM_FALLBACK_ENABLED=true
AWS_REGION=us-east-1
BEDROCK_TEXT_MODEL_ID=<your-bedrock-chat-model-id>
BEDROCK_MAX_TOKENS=1024
BEDROCK_TEMPERATURE=0.2
```

Optional Bedrock guardrail support:

```bash
BEDROCK_GUARDRAIL_IDENTIFIER=<guardrail-id>
BEDROCK_GUARDRAIL_VERSION=<guardrail-version>
```

AgentCore transition variables:

```bash
AGENT_RUNTIME_PROVIDER=agentcore
AGENTCORE_RUNTIME_ARN=<your-agentcore-runtime-arn>
AGENTCORE_RUNTIME_QUALIFIER=<optional-endpoint-qualifier>
AGENTCORE_FALLBACK_TO_LOCAL=true
```

## Required IAM permissions

For Bedrock Converse:

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel"
  ],
  "Resource": "*"
}
```

For AgentCore Runtime invocation:

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock-agentcore:InvokeAgentRuntime"
  ],
  "Resource": "*"
}
```

Scope resources to approved model ARNs and AgentCore Runtime ARNs before production.

## Migration sequence

1. Deploy this batch with `LLM_PROVIDER=mistral` and confirm no regression.
2. Add `AWS_REGION` and `BEDROCK_TEXT_MODEL_ID`.
3. Switch `LLM_PROVIDER=bedrock`.
4. Confirm `/admin/status`, `/architecture/summary`, and chat `llm_trace` show Bedrock.
5. Deploy the AgentCore runtime package separately.
6. Set `AGENT_RUNTIME_PROVIDER=agentcore` and `AGENTCORE_RUNTIME_ARN`.
7. Keep `AGENTCORE_FALLBACK_TO_LOCAL=true` until AgentCore is validated.
8. Turn fallback off only after observability and rollback are confirmed.

## Batch 2: Bedrock embeddings, S3 storage, and Bedrock Knowledge Bases

This batch moves the knowledge and retrieval path toward AWS-native services while keeping the PostgreSQL vector-store path available as a fallback.

### Bedrock embeddings

Set the embedding provider to Bedrock:

```bash
EMBEDDING_PROVIDER=bedrock
EMBEDDING_FALLBACK_PROVIDER=huggingface
AWS_REGION=us-east-1
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
BEDROCK_EMBEDDING_NORMALIZE=true
# Optional for supported embedding models:
BEDROCK_EMBEDDING_DIMENSIONS=
```

When enabled, uploaded documents and vector refreshes call Bedrock Runtime `InvokeModel` for embeddings. The local Hugging Face/Ollama providers still work for local development and fallback.

Required IAM permission:

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "*"
}
```

### S3-backed knowledge storage

Set the storage backend to S3:

```bash
KB_STORAGE_BACKEND=s3
KB_S3_BUCKET=<your-knowledge-bucket>
KB_S3_PREFIX=knowledge-base/uploads
KB_S3_VALIDATE=false
# Optional if your bucket requires server-side encryption:
KB_S3_SSE=aws:kms
KB_S3_KMS_KEY_ID=<optional-kms-key-id>
```

Uploaded document bytes are stored as:

```text
s3://<bucket>/<prefix>/<logical-document>/rev_<n>/<original-filename>
```

The `case4.knowledge_documents.storage_type` field stores `s3`, and `storage_path` stores the `s3://...` URI. The download endpoint continues to work for both local and S3-backed files.

Required IAM permissions:

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject",
    "s3:GetObject",
    "s3:HeadObject"
  ],
  "Resource": "arn:aws:s3:::<your-knowledge-bucket>/knowledge-base/uploads/*"
}
```

### Bedrock Knowledge Bases retrieval

The app can now query Bedrock Knowledge Bases directly:

```bash
RETRIEVAL_PROVIDER=bedrock_kb
RETRIEVAL_FALLBACK_TO_DB=true
BEDROCK_KNOWLEDGE_BASE_ID=<your-bedrock-kb-id>
BEDROCK_KB_NUMBER_OF_RESULTS=5
BEDROCK_KB_SEARCH_TYPE=HYBRID
```

When `RETRIEVAL_FALLBACK_TO_DB=true`, a Bedrock KB retrieval failure falls back to the existing PostgreSQL `document_chunks` search. This keeps production traffic resilient while AWS Knowledge Bases are being tuned.

Required IAM permission:

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:Retrieve"],
  "Resource": "*"
}
```

### Recommended AWS cutover sequence

1. Deploy with `KB_STORAGE_BACKEND=local`, `EMBEDDING_PROVIDER=huggingface`, and `RETRIEVAL_PROVIDER=db` to verify no regression.
2. Enable `KB_STORAGE_BACKEND=s3` and upload a new test document.
3. Enable `EMBEDDING_PROVIDER=bedrock` and refresh the active vector store.
4. Create/configure the Bedrock Knowledge Base separately in AWS.
5. Enable `RETRIEVAL_PROVIDER=bedrock_kb` with `RETRIEVAL_FALLBACK_TO_DB=true`.
6. Confirm chat evidence shows `retrieval_strategy=bedrock_kb`.
7. Disable DB fallback only after Bedrock KB quality and IAM are validated.

## What remains after Batch 2

- AgentCore Memory for managed multi-turn session memory.
- AgentCore Gateway and Identity for governed IAM / ITSM tool access.
- CloudWatch / OpenTelemetry dashboards for Bedrock, AgentCore, retrieval, and workflow traces.
- Optional cutover from custom PostgreSQL chunk search to Bedrock Knowledge Bases as the primary retrieval path once retrieval quality is validated.
