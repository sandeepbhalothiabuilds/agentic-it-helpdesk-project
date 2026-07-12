from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

_TRUE_VALUES = {"1", "true", "t", "yes", "y", "on", "enabled"}
_FALSE_VALUES = {"0", "false", "f", "no", "n", "off", "disabled"}


def truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return default


def _split_csv(value: str | None) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return []
    if raw == "*":
        return ["*"]
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    # Application metadata
    service_name: str = Field(default="agentic-it-service-desk", validation_alias=AliasChoices("SERVICE_NAME", "APP_NAME"))
    service_version: str = Field(default="0.1.0", validation_alias=AliasChoices("SERVICE_VERSION", "APP_VERSION"))
    app_env: str = Field(default="local", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # API/security/runtime controls
    cors_allowed_origins: str = Field(
        default="http://localhost:8501,http://127.0.0.1:8501,http://localhost:8000,http://127.0.0.1:8000",
        validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "CORS_ORIGINS"),
    )
    trusted_hosts: str = Field(default="*", validation_alias=AliasChoices("TRUSTED_HOSTS", "ALLOWED_HOSTS"))
    api_key: str = Field(default="", validation_alias=AliasChoices("BACKEND_API_KEY", "API_KEY", "APP_API_KEY"))
    require_api_key: str = Field(default="0", validation_alias=AliasChoices("API_KEY_REQUIRED", "REQUIRE_API_KEY"))
    api_key_header: str = Field(default="X-API-Key", validation_alias="API_KEY_HEADER")
    request_timeout_seconds: int = Field(default=90, validation_alias="REQUEST_TIMEOUT_SECONDS")
    docs_enabled: str = Field(default="1", validation_alias="DOCS_ENABLED")
    max_upload_mb: int = Field(default=25, validation_alias="MAX_UPLOAD_MB")

    # Database. DATABASE_URL is preferred. DATABASE_URL_ENV is kept for backward compatibility.
    database_url_env: str = Field(default="", validation_alias=AliasChoices("DATABASE_URL", "DATABASE_URL_ENV"))
    db_user: str = Field(default="service_desk", validation_alias="DB_USER")
    db_password: str = Field(default="", validation_alias="DB_PASSWORD")
    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=5432, validation_alias="DB_PORT")
    db_name: str = Field(default="postgres", validation_alias="DB_NAME")
    db_sslmode: str = Field(default="prefer", validation_alias="DB_SSLMODE")
    allow_sqlite_fallback: str = Field(default="1", validation_alias=AliasChoices("ALLOW_SQLITE_FALLBACK", "ENABLE_SQLITE_FALLBACK"))
    sqlite_fallback_path: str = Field(default=".agentic_it_service_desk_test.db", validation_alias="SQLITE_FALLBACK_PATH")

    # LLM provider routing. Mistral stays available for local/dev compatibility.
    llm_provider: str = Field(default="mistral", validation_alias="LLM_PROVIDER")
    llm_fallback_provider: str = Field(default="mistral", validation_alias="LLM_FALLBACK_PROVIDER")
    llm_fallback_enabled: str = Field(default="1", validation_alias="LLM_FALLBACK_ENABLED")

    # Mistral
    mistral_api_key: str = Field(default="", validation_alias="MISTRAL_API_KEY")
    mistral_model: str = Field(default="mistral-small-latest", validation_alias="MISTRAL_MODEL")
    mistral_disable: str = Field(default="0", validation_alias="MISTRAL_DISABLE")
    mistral_insecure_ssl: str = Field(default="0", validation_alias="MISTRAL_INSECURE_SSL")

    # AWS / Amazon Bedrock
    aws_region: str = Field(default="us-east-1", validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION"))
    aws_profile: str = Field(default="", validation_alias="AWS_PROFILE")
    bedrock_text_model_id: str = Field(default="", validation_alias=AliasChoices("BEDROCK_TEXT_MODEL_ID", "BEDROCK_MODEL_ID"))
    bedrock_temperature: float = Field(default=0.2, validation_alias="BEDROCK_TEMPERATURE")
    bedrock_max_tokens: int = Field(default=1024, validation_alias="BEDROCK_MAX_TOKENS")
    bedrock_request_timeout_seconds: int = Field(default=60, validation_alias="BEDROCK_REQUEST_TIMEOUT_SECONDS")
    bedrock_validate_on_status: str = Field(default="0", validation_alias="BEDROCK_VALIDATE_ON_STATUS")
    bedrock_guardrail_identifier: str = Field(default="", validation_alias="BEDROCK_GUARDRAIL_IDENTIFIER")
    bedrock_guardrail_version: str = Field(default="", validation_alias="BEDROCK_GUARDRAIL_VERSION")

    # Embeddings. AWS deployments should use EMBEDDING_PROVIDER=bedrock.
    embedding_provider: str = Field(default="huggingface", validation_alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", validation_alias="EMBEDDING_MODEL")
    embedding_fallback_provider: str = Field(default="ollama", validation_alias="EMBEDDING_FALLBACK_PROVIDER")
    huggingface_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", validation_alias="HUGGINGFACE_MODEL")
    ollama_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_URL")
    ollama_model: str = Field(default="nomic-embed-text", validation_alias="OLLAMA_MODEL")
    ollama_timeout_seconds: int = Field(default=120, validation_alias=AliasChoices("OLLAMA_TIMEOUT", "OLLAMA_TIMEOUT_SECONDS"))
    bedrock_embedding_model_id: str = Field(default="amazon.titan-embed-text-v2:0", validation_alias="BEDROCK_EMBEDDING_MODEL_ID")
    bedrock_embedding_dimensions: int = Field(default=1024, validation_alias="BEDROCK_EMBEDDING_DIMENSIONS")
    bedrock_embedding_normalize: str = Field(default="1", validation_alias="BEDROCK_EMBEDDING_NORMALIZE")

    # Retrieval provider. The DB-backed retriever remains available as fallback.
    retrieval_provider: str = Field(default="db", validation_alias="RETRIEVAL_PROVIDER")
    retrieval_fallback_to_db: str = Field(default="1", validation_alias="RETRIEVAL_FALLBACK_TO_DB")
    bedrock_knowledge_base_id: str = Field(default="", validation_alias=AliasChoices("BEDROCK_KNOWLEDGE_BASE_ID", "BEDROCK_KB_ID"))
    bedrock_kb_data_source_id: str = Field(default="", validation_alias=AliasChoices("BEDROCK_KB_DATA_SOURCE_ID", "BEDROCK_KNOWLEDGE_BASE_DATA_SOURCE_ID"))
    bedrock_kb_number_of_results: int = Field(default=5, validation_alias="BEDROCK_KB_NUMBER_OF_RESULTS")
    bedrock_kb_search_type: str = Field(default="HYBRID", validation_alias="BEDROCK_KB_SEARCH_TYPE")

    # Agent runtime routing. "local" keeps FastAPI/LangGraph as the runtime. "agentcore"
    # lets /chat delegate to Amazon Bedrock AgentCore Runtime when an ARN is configured.
    agent_runtime_provider: str = Field(default="local", validation_alias=AliasChoices("AGENT_RUNTIME_PROVIDER", "AGENT_PROVIDER"))
    agentcore_runtime_arn: str = Field(default="", validation_alias=AliasChoices("AGENTCORE_RUNTIME_ARN", "BEDROCK_AGENTCORE_RUNTIME_ARN"))
    agentcore_runtime_qualifier: str = Field(default="", validation_alias=AliasChoices("AGENTCORE_RUNTIME_QUALIFIER", "BEDROCK_AGENTCORE_QUALIFIER"))
    agentcore_account_id: str = Field(default="", validation_alias=AliasChoices("AGENTCORE_ACCOUNT_ID", "AWS_ACCOUNT_ID"))
    agentcore_timeout_seconds: int = Field(default=90, validation_alias="AGENTCORE_TIMEOUT_SECONDS")
    agentcore_fallback_to_local: str = Field(default="1", validation_alias="AGENTCORE_FALLBACK_TO_LOCAL")
    agentcore_content_type: str = Field(default="application/json", validation_alias="AGENTCORE_CONTENT_TYPE")
    agentcore_accept: str = Field(default="application/json", validation_alias="AGENTCORE_ACCEPT")

    # AgentCore Memory. Optional in local mode; recommended once AgentCore is used in AWS.
    agentcore_memory_enabled: str = Field(default="0", validation_alias=AliasChoices("AGENTCORE_MEMORY_ENABLED", "BEDROCK_AGENTCORE_MEMORY_ENABLED"))
    agentcore_memory_id: str = Field(default="", validation_alias=AliasChoices("AGENTCORE_MEMORY_ID", "BEDROCK_AGENTCORE_MEMORY_ID"))
    agentcore_memory_actor_prefix: str = Field(default="employee", validation_alias="AGENTCORE_MEMORY_ACTOR_PREFIX")
    agentcore_memory_write_events: str = Field(default="1", validation_alias="AGENTCORE_MEMORY_WRITE_EVENTS")
    agentcore_memory_retrieve_enabled: str = Field(default="0", validation_alias="AGENTCORE_MEMORY_RETRIEVE_ENABLED")
    agentcore_memory_namespace: str = Field(default="/service-desk/{actorId}/", validation_alias="AGENTCORE_MEMORY_NAMESPACE")
    agentcore_memory_strategy_id: str = Field(default="", validation_alias="AGENTCORE_MEMORY_STRATEGY_ID")
    agentcore_memory_top_k: int = Field(default=3, validation_alias="AGENTCORE_MEMORY_TOP_K")

    # AgentCore Gateway / Identity. Gateway can front real enterprise tools while
    # local mock IAM stays available as a fallback during migration.
    agentcore_gateway_enabled: str = Field(default="0", validation_alias=AliasChoices("AGENTCORE_GATEWAY_ENABLED", "BEDROCK_AGENTCORE_GATEWAY_ENABLED"))
    agentcore_gateway_url: str = Field(default="", validation_alias=AliasChoices("AGENTCORE_GATEWAY_URL", "BEDROCK_AGENTCORE_GATEWAY_URL"))
    agentcore_gateway_timeout_seconds: int = Field(default=30, validation_alias="AGENTCORE_GATEWAY_TIMEOUT_SECONDS")
    agentcore_gateway_fallback_to_mock: str = Field(default="1", validation_alias="AGENTCORE_GATEWAY_FALLBACK_TO_MOCK")
    agentcore_gateway_auth_header: str = Field(default="Authorization", validation_alias="AGENTCORE_GATEWAY_AUTH_HEADER")
    agentcore_gateway_bearer_token: str = Field(default="", validation_alias=AliasChoices("AGENTCORE_GATEWAY_BEARER_TOKEN", "AGENTCORE_IDENTITY_TOKEN"))
    agentcore_gateway_api_key: str = Field(default="", validation_alias=AliasChoices("AGENTCORE_GATEWAY_API_KEY", "AGENTCORE_IDENTITY_API_KEY"))
    agentcore_gateway_api_key_header: str = Field(default="X-API-Key", validation_alias="AGENTCORE_GATEWAY_API_KEY_HEADER")
    agentcore_gateway_tool_prefix: str = Field(default="", validation_alias="AGENTCORE_GATEWAY_TOOL_PREFIX")
    agentcore_identity_enabled: str = Field(default="0", validation_alias=AliasChoices("AGENTCORE_IDENTITY_ENABLED", "BEDROCK_AGENTCORE_IDENTITY_ENABLED"))
    agentcore_identity_workload_token: str = Field(default="", validation_alias="AGENTCORE_IDENTITY_WORKLOAD_TOKEN")
    agentcore_identity_resource_credential_provider_name: str = Field(default="", validation_alias="AGENTCORE_IDENTITY_RESOURCE_CREDENTIAL_PROVIDER_NAME")
    agentcore_identity_scopes: str = Field(default="", validation_alias="AGENTCORE_IDENTITY_SCOPES")
    agentcore_identity_oauth2_flow: str = Field(default="M2M", validation_alias="AGENTCORE_IDENTITY_OAUTH2_FLOW")
    agentcore_identity_session_uri: str = Field(default="", validation_alias="AGENTCORE_IDENTITY_SESSION_URI")
    agentcore_identity_return_url: str = Field(default="", validation_alias="AGENTCORE_IDENTITY_RETURN_URL")
    agentcore_identity_force_authentication: str = Field(default="0", validation_alias="AGENTCORE_IDENTITY_FORCE_AUTHENTICATION")

    # Observability / telemetry. CloudWatch EMF is disabled by default so local
    # logs stay small. Enable OBSERVABILITY_EMF_ENABLED=true in ECS/CloudWatch.
    observability_enabled: str = Field(default="1", validation_alias=AliasChoices("OBSERVABILITY_ENABLED", "TELEMETRY_ENABLED"))
    observability_log_events: str = Field(default="1", validation_alias=AliasChoices("OBSERVABILITY_LOG_EVENTS", "TELEMETRY_LOG_EVENTS"))
    observability_emf_enabled: str = Field(default="0", validation_alias=AliasChoices("OBSERVABILITY_EMF_ENABLED", "CLOUDWATCH_EMF_ENABLED", "AWS_EMF_ENABLED"))
    observability_namespace: str = Field(default="AgenticITServiceDesk", validation_alias=AliasChoices("OBSERVABILITY_NAMESPACE", "CLOUDWATCH_METRIC_NAMESPACE"))
    observability_redact_payloads: str = Field(default="1", validation_alias=AliasChoices("OBSERVABILITY_REDACT_PAYLOADS", "TELEMETRY_REDACT_PAYLOADS"))
    observability_trace_prompts: str = Field(default="0", validation_alias=AliasChoices("OBSERVABILITY_TRACE_PROMPTS", "TELEMETRY_TRACE_PROMPTS"))
    observability_sample_rate: float = Field(default=1.0, validation_alias=AliasChoices("OBSERVABILITY_SAMPLE_RATE", "TELEMETRY_SAMPLE_RATE"))

    # Knowledge base storage. Use KB_STORAGE_BACKEND=s3 for AWS/ECS/RDS deployments.
    kb_storage_backend: str = Field(default="local", validation_alias=AliasChoices("KB_STORAGE_BACKEND", "STORAGE_BACKEND"))
    kb_storage_root: str = Field(default="data/knowledge_base/uploads", validation_alias="KB_STORAGE_ROOT")
    kb_s3_bucket: str = Field(default="", validation_alias="KB_S3_BUCKET")
    kb_s3_prefix: str = Field(default="knowledge-base/uploads/", validation_alias="KB_S3_PREFIX")
    kb_s3_presign_seconds: int = Field(default=900, validation_alias="KB_S3_PRESIGN_SECONDS")
    kb_s3_validate: str = Field(default="0", validation_alias=AliasChoices("KB_S3_VALIDATE", "KB_S3_VALIDATE_ON_STATUS"))
    kb_s3_sse: str = Field(default="", validation_alias=AliasChoices("KB_S3_SSE", "KB_S3_SERVER_SIDE_ENCRYPTION"))
    kb_s3_kms_key_id: str = Field(default="", validation_alias="KB_S3_KMS_KEY_ID")
    structured_data_root: str = Field(default="data/raw/structured", validation_alias="STRUCTURED_DATA_ROOT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    @property
    def database_url(self):
        db_url_env = (self.database_url_env or "").strip()
        if db_url_env:
            return make_url(db_url_env)

        password = (self.db_password or "").strip()
        if not password:
            raise ValueError("Set DATABASE_URL or DB_PASSWORD before starting the backend.")

        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.db_user,
            password=password,
            host=self.db_host,
            port=int(self.db_port),
            database=self.db_name,
            query={"sslmode": self.db_sslmode} if self.db_sslmode else {},
        )

    @property
    def app_name(self) -> str:
        return self.service_name

    @property
    def app_version(self) -> str:
        return self.service_version

    @property
    def api_key_required(self) -> bool:
        return truthy(self.require_api_key)

    @property
    def api_key_is_configured(self) -> bool:
        return bool((self.api_key or "").strip())

    @property
    def backend_api_key(self) -> str:
        return self.api_key

    @backend_api_key.setter
    def backend_api_key(self, value: str) -> None:
        object.__setattr__(self, "api_key", value or "")

    @property
    def sqlite_fallback_enabled(self) -> bool:
        return truthy(self.allow_sqlite_fallback, default=True)

    @property
    def openapi_docs_enabled(self) -> bool:
        return truthy(self.docs_enabled, default=True)

    @property
    def mistral_enabled(self) -> bool:
        return not truthy(self.mistral_disable)

    @property
    def llm_provider_normalized(self) -> str:
        value = (self.llm_provider or "mistral").strip().lower()
        if value in {"bedrock", "amazon_bedrock", "aws_bedrock"}:
            return "bedrock"
        if value in {"mistral", "mistral_ai"}:
            return "mistral"
        if value in {"local", "fallback"}:
            return "local"
        return value or "mistral"

    @property
    def llm_fallback_provider_normalized(self) -> str:
        value = (self.llm_fallback_provider or "mistral").strip().lower()
        if value in {"none", "off", "disabled", ""}:
            return "none"
        if value in {"bedrock", "amazon_bedrock", "aws_bedrock"}:
            return "bedrock"
        if value in {"local", "fallback"}:
            return "local"
        return "mistral"

    @property
    def llm_can_fallback(self) -> bool:
        return truthy(self.llm_fallback_enabled, default=True)

    @property
    def bedrock_configured(self) -> bool:
        return bool((self.aws_region or "").strip() and (self.bedrock_text_model_id or "").strip())

    @property
    def bedrock_status_probe_enabled(self) -> bool:
        return truthy(self.bedrock_validate_on_status)

    @property
    def embedding_provider_normalized(self) -> str:
        value = (self.embedding_provider or "huggingface").strip().lower()
        if value in {"bedrock", "amazon_bedrock", "aws_bedrock"}:
            return "bedrock"
        if value in {"ollama", "local_ollama"}:
            return "ollama"
        if value in {"hf", "huggingface", "sentence_transformers", "sentence-transformers"}:
            return "huggingface"
        return value or "huggingface"

    @property
    def embedding_fallback_provider_normalized(self) -> str:
        value = (self.embedding_fallback_provider or "ollama").strip().lower()
        if value in {"none", "off", "disabled", ""}:
            return "none"
        if value in {"bedrock", "amazon_bedrock", "aws_bedrock"}:
            return "bedrock"
        if value in {"hf", "huggingface", "sentence_transformers", "sentence-transformers"}:
            return "huggingface"
        return "ollama"

    @property
    def bedrock_embedding_configured(self) -> bool:
        return bool((self.aws_region or "").strip() and (self.bedrock_embedding_model_id or "").strip())

    @property
    def bedrock_embedding_normalize_enabled(self) -> bool:
        return truthy(self.bedrock_embedding_normalize, default=True)

    @property
    def retrieval_provider_normalized(self) -> str:
        value = (self.retrieval_provider or "db").strip().lower()
        if value in {"bedrock_kb", "bedrock", "amazon_bedrock_kb", "aws_bedrock_kb"}:
            return "bedrock_kb"
        return "db"

    @property
    def retrieval_db_fallback_enabled(self) -> bool:
        return truthy(self.retrieval_fallback_to_db, default=True)

    @property
    def bedrock_kb_configured(self) -> bool:
        return bool((self.aws_region or "").strip() and (self.bedrock_knowledge_base_id or "").strip())

    @property
    def agent_runtime_provider_normalized(self) -> str:
        value = (self.agent_runtime_provider or "local").strip().lower()
        if value in {"agentcore", "bedrock_agentcore", "aws_agentcore"}:
            return "agentcore"
        return "local"

    @property
    def agentcore_enabled(self) -> bool:
        return self.agent_runtime_provider_normalized == "agentcore"

    @property
    def agentcore_configured(self) -> bool:
        return self.agentcore_enabled and bool((self.agentcore_runtime_arn or "").strip())

    @property
    def agentcore_local_fallback_enabled(self) -> bool:
        return truthy(self.agentcore_fallback_to_local, default=True)

    @property
    def agentcore_memory_is_enabled(self) -> bool:
        return truthy(self.agentcore_memory_enabled, default=False)

    @property
    def agentcore_memory_configured(self) -> bool:
        return self.agentcore_memory_is_enabled and bool((self.agentcore_memory_id or "").strip())

    @property
    def agentcore_memory_write_enabled(self) -> bool:
        return self.agentcore_memory_is_enabled and truthy(self.agentcore_memory_write_events, default=True)

    @property
    def agentcore_memory_retrieval_enabled(self) -> bool:
        return self.agentcore_memory_configured and truthy(self.agentcore_memory_retrieve_enabled, default=False)

    @property
    def agentcore_gateway_is_enabled(self) -> bool:
        return truthy(self.agentcore_gateway_enabled, default=False)

    @property
    def agentcore_gateway_configured(self) -> bool:
        return self.agentcore_gateway_is_enabled and bool((self.agentcore_gateway_url or "").strip())

    @property
    def agentcore_gateway_mock_fallback_enabled(self) -> bool:
        return truthy(self.agentcore_gateway_fallback_to_mock, default=True)

    @property
    def agentcore_identity_is_enabled(self) -> bool:
        return truthy(self.agentcore_identity_enabled, default=False)

    @property
    def agentcore_identity_scopes_list(self) -> list[str]:
        return _split_csv(self.agentcore_identity_scopes)

    @property
    def agentcore_identity_force_authentication_enabled(self) -> bool:
        return truthy(self.agentcore_identity_force_authentication, default=False)

    @property
    def agentcore_identity_configured(self) -> bool:
        static_token_configured = bool((self.agentcore_gateway_bearer_token or "").strip() or (self.agentcore_gateway_api_key or "").strip())
        managed_identity_configured = (
            bool((self.agentcore_identity_workload_token or "").strip())
            and bool((self.agentcore_identity_resource_credential_provider_name or "").strip())
            and bool(self.agentcore_identity_scopes_list)
        )
        return (not self.agentcore_identity_is_enabled) or static_token_configured or managed_identity_configured

    @property
    def kb_storage_backend_normalized(self) -> str:
        value = (self.kb_storage_backend or "local").strip().lower()
        if value in {"s3", "amazon_s3", "aws_s3"}:
            return "s3"
        return "local"

    @property
    def kb_s3_configured(self) -> bool:
        return self.kb_storage_backend_normalized == "s3" and bool((self.kb_s3_bucket or "").strip())

    @property
    def kb_s3_validate_enabled(self) -> bool:
        return truthy(self.kb_s3_validate, default=False)

    @property
    def allowed_origins(self) -> list[str]:
        return self.cors_origins()

    @property
    def cors_origins_list(self) -> list[str]:
        return self.cors_origins()

    @property
    def allowed_hosts(self) -> list[str]:
        hosts = _split_csv(self.trusted_hosts)
        return hosts or ["*"]

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb) * 1024 * 1024

    def cors_origins(self) -> list[str]:
        return _split_csv(self.cors_allowed_origins)

    def redacted_database_url(self) -> str:
        try:
            url = urlsplit(str(self.database_url))
        except Exception:
            return "not_configured"

        if not url.scheme:
            return "not_configured"

        host = url.hostname or ""
        netloc = host
        if url.port:
            netloc = f"{host}:{url.port}"
        return urlunsplit((url.scheme, netloc, url.path or "", url.query, ""))

    @property
    def observability_is_enabled(self) -> bool:
        return truthy(self.observability_enabled, default=True)

    @property
    def observability_event_logging_enabled(self) -> bool:
        return self.observability_is_enabled and truthy(self.observability_log_events, default=True)

    @property
    def observability_emf_logging_enabled(self) -> bool:
        return self.observability_is_enabled and truthy(self.observability_emf_enabled, default=False)

    @property
    def observability_payload_redaction_enabled(self) -> bool:
        return truthy(self.observability_redact_payloads, default=True)

    @property
    def observability_prompt_tracing_enabled(self) -> bool:
        return self.observability_is_enabled and truthy(self.observability_trace_prompts, default=False)

    @property
    def observability_sampling_rate(self) -> float:
        try:
            return max(0.0, min(float(self.observability_sample_rate), 1.0))
        except Exception:
            return 1.0

    @property
    def security_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.api_key_required and not self.api_key_is_configured:
            warnings.append("API_KEY_REQUIRED is enabled but BACKEND_API_KEY/API_KEY is empty.")
        if not (self.database_url_env or self.db_password):
            warnings.append("DATABASE_URL or DB_PASSWORD is not set; SQLite fallback may be used if enabled.")
        if not self.cors_origins():
            warnings.append("No CORS origins are configured.")
        if self.allowed_origins == ["*"] and self.app_env.lower() in {"prod", "production"}:
            warnings.append("CORS allows all origins in production; restrict CORS_ALLOWED_ORIGINS.")

        provider = self.llm_provider_normalized
        if provider == "mistral" and self.mistral_enabled and not self.mistral_api_key:
            warnings.append("LLM_PROVIDER is mistral but MISTRAL_API_KEY is empty; fallback behavior may be used.")
        if provider == "bedrock" and not self.bedrock_configured:
            warnings.append("LLM_PROVIDER is bedrock but AWS_REGION or BEDROCK_TEXT_MODEL_ID is missing.")
        if self.embedding_provider_normalized == "bedrock" and not self.bedrock_embedding_configured:
            warnings.append("EMBEDDING_PROVIDER is bedrock but AWS_REGION or BEDROCK_EMBEDDING_MODEL_ID is missing.")
        if self.retrieval_provider_normalized == "bedrock_kb" and not self.bedrock_kb_configured:
            warnings.append("RETRIEVAL_PROVIDER is bedrock_kb but AWS_REGION or BEDROCK_KNOWLEDGE_BASE_ID is missing.")
        if self.kb_storage_backend_normalized == "s3" and not self.kb_s3_bucket:
            warnings.append("KB_STORAGE_BACKEND is s3 but KB_S3_BUCKET is missing.")
        if self.agentcore_enabled and not self.agentcore_runtime_arn:
            warnings.append("AGENT_RUNTIME_PROVIDER is agentcore but AGENTCORE_RUNTIME_ARN is missing.")
        if self.agentcore_memory_is_enabled and not self.agentcore_memory_id:
            warnings.append("AGENTCORE_MEMORY_ENABLED is true but AGENTCORE_MEMORY_ID is missing.")
        if self.agentcore_gateway_is_enabled and not self.agentcore_gateway_url:
            warnings.append("AGENTCORE_GATEWAY_ENABLED is true but AGENTCORE_GATEWAY_URL is missing.")
        if self.agentcore_identity_is_enabled and not self.agentcore_identity_configured:
            warnings.append("AGENTCORE_IDENTITY_ENABLED is true but neither static gateway credentials nor AgentCore Identity OAuth settings are configured.")
        return warnings

    def public_config(self) -> dict[str, Any]:
        return {
            "service_name": self.service_name,
            "service_version": self.service_version,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "app_env": self.app_env,
            "log_level": self.log_level,
            "cors_allowed_origins": self.cors_origins(),
            "trusted_hosts": self.allowed_hosts,
            "api_key_required": self.api_key_required,
            "api_key_configured": self.api_key_is_configured,
            "api_key_header": self.api_key_header,
            "docs_enabled": self.openapi_docs_enabled,
            "database_url_redacted": self.redacted_database_url(),
            "sqlite_fallback_enabled": self.sqlite_fallback_enabled,
            "llm_provider": self.llm_provider_normalized,
            "llm_fallback_provider": self.llm_fallback_provider_normalized,
            "llm_fallback_enabled": self.llm_can_fallback,
            "mistral_model": self.mistral_model,
            "mistral_enabled": self.mistral_enabled,
            "mistral_key_set": bool(self.mistral_api_key),
            "aws_region": self.aws_region,
            "aws_profile_set": bool(self.aws_profile),
            "bedrock_text_model_id": self.bedrock_text_model_id,
            "bedrock_configured": self.bedrock_configured,
            "bedrock_temperature": self.bedrock_temperature,
            "bedrock_max_tokens": self.bedrock_max_tokens,
            "bedrock_guardrail_configured": bool(self.bedrock_guardrail_identifier and self.bedrock_guardrail_version),
            "embedding_provider": self.embedding_provider_normalized,
            "embedding_model": self.embedding_model,
            "embedding_fallback_provider": self.embedding_fallback_provider_normalized,
            "huggingface_model": self.huggingface_model,
            "bedrock_embedding_model_id": self.bedrock_embedding_model_id,
            "bedrock_embedding_configured": self.bedrock_embedding_configured,
            "bedrock_embedding_dimensions": self.bedrock_embedding_dimensions,
            "bedrock_embedding_normalize": self.bedrock_embedding_normalize_enabled,
            "ollama_url": self.ollama_url,
            "ollama_model": self.ollama_model,
            "retrieval_provider": self.retrieval_provider_normalized,
            "retrieval_fallback_to_db": self.retrieval_db_fallback_enabled,
            "bedrock_knowledge_base_id_set": bool(self.bedrock_knowledge_base_id),
            "bedrock_kb_data_source_id_set": bool(self.bedrock_kb_data_source_id),
            "bedrock_kb_number_of_results": self.bedrock_kb_number_of_results,
            "bedrock_kb_search_type": self.bedrock_kb_search_type,
            "agent_runtime_provider": self.agent_runtime_provider_normalized,
            "agentcore_enabled": self.agentcore_enabled,
            "agentcore_configured": self.agentcore_configured,
            "agentcore_runtime_arn_set": bool(self.agentcore_runtime_arn),
            "agentcore_runtime_qualifier": self.agentcore_runtime_qualifier,
            "agentcore_account_id_set": bool(self.agentcore_account_id),
            "agentcore_fallback_to_local": self.agentcore_local_fallback_enabled,
            "agentcore_memory_enabled": self.agentcore_memory_is_enabled,
            "agentcore_memory_configured": self.agentcore_memory_configured,
            "agentcore_memory_id_set": bool(self.agentcore_memory_id),
            "agentcore_memory_write_events": self.agentcore_memory_write_enabled,
            "agentcore_memory_retrieve_enabled": self.agentcore_memory_retrieval_enabled,
            "agentcore_memory_namespace": self.agentcore_memory_namespace,
            "agentcore_memory_strategy_id_set": bool(self.agentcore_memory_strategy_id),
            "agentcore_memory_top_k": self.agentcore_memory_top_k,
            "agentcore_gateway_enabled": self.agentcore_gateway_is_enabled,
            "agentcore_gateway_configured": self.agentcore_gateway_configured,
            "agentcore_gateway_url_set": bool(self.agentcore_gateway_url),
            "agentcore_gateway_fallback_to_mock": self.agentcore_gateway_mock_fallback_enabled,
            "agentcore_gateway_tool_prefix": self.agentcore_gateway_tool_prefix,
            "agentcore_identity_enabled": self.agentcore_identity_is_enabled,
            "agentcore_identity_configured": self.agentcore_identity_configured,
            "agentcore_identity_provider_set": bool(self.agentcore_identity_resource_credential_provider_name),
            "agentcore_identity_scopes": self.agentcore_identity_scopes_list,
            "agentcore_identity_static_token_set": bool(self.agentcore_gateway_bearer_token or self.agentcore_gateway_api_key),
            "kb_storage_backend": self.kb_storage_backend_normalized,
            "kb_storage_root": self.kb_storage_root,
            "kb_s3_bucket_set": bool(self.kb_s3_bucket),
            "kb_s3_prefix": self.kb_s3_prefix,
            "kb_s3_presign_seconds": self.kb_s3_presign_seconds,
            "kb_s3_validate": self.kb_s3_validate_enabled,
            "kb_s3_sse": self.kb_s3_sse,
            "kb_s3_kms_key_set": bool(self.kb_s3_kms_key_id),
            "kb_s3_configured": self.kb_s3_configured,
            "observability_enabled": self.observability_is_enabled,
            "observability_log_events": self.observability_event_logging_enabled,
            "observability_emf_enabled": self.observability_emf_logging_enabled,
            "observability_namespace": self.observability_namespace,
            "observability_redact_payloads": self.observability_payload_redaction_enabled,
            "observability_trace_prompts": self.observability_prompt_tracing_enabled,
            "observability_sample_rate": self.observability_sampling_rate,
            "structured_data_root": self.structured_data_root,
            "max_upload_mb": self.max_upload_mb,
            "request_timeout_seconds": self.request_timeout_seconds,
            "security_warnings": self.security_warnings,
        }


settings = Settings()
