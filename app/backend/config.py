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

    # LLM
    mistral_api_key: str = Field(default="", validation_alias="MISTRAL_API_KEY")
    mistral_model: str = Field(default="mistral-small-latest", validation_alias="MISTRAL_MODEL")
    mistral_disable: str = Field(default="0", validation_alias="MISTRAL_DISABLE")
    mistral_insecure_ssl: str = Field(default="0", validation_alias="MISTRAL_INSECURE_SSL")

    # Embeddings / Ollama
    embedding_provider: str = Field(default="huggingface", validation_alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", validation_alias="EMBEDDING_MODEL")
    huggingface_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", validation_alias="HUGGINGFACE_MODEL")
    ollama_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_URL")
    ollama_model: str = Field(default="nomic-embed-text", validation_alias="OLLAMA_MODEL")

    # Knowledge base storage
    kb_storage_root: str = Field(default="data/knowledge_base/uploads", validation_alias="KB_STORAGE_ROOT")
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
    def allowed_origins(self) -> list[str]:
        return self.cors_origins()

    @property
    def cors_origins_list(self) -> list[str]:
        return self.cors_origins()

    @property
    def allowed_hosts(self) -> list[str]:
        raw = (self.trusted_hosts or "").strip()
        if not raw:
            return ["*"]
        if raw == "*":
            return ["*"]
        return [host.strip() for host in raw.split(",") if host.strip()] or ["*"]

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb) * 1024 * 1024

    def cors_origins(self) -> list[str]:
        raw = (self.cors_allowed_origins or "").strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

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
    def security_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.api_key_required and not self.api_key_is_configured:
            warnings.append("REQUIRE_API_KEY is enabled but BACKEND_API_KEY / APP_API_KEY is not set.")
        if "*" in self.allowed_origins and self.app_env.lower() in {"prod", "production"}:
            warnings.append("CORS is configured with '*' in a production environment.")
        if self.mistral_enabled and not self.mistral_api_key:
            warnings.append("Mistral is enabled but MISTRAL_API_KEY is not set; fallback behavior may be used.")
        if not (self.database_url_env or self.db_password):
            warnings.append("DATABASE_URL or DB_PASSWORD is not set; SQLite fallback may be used if enabled.")
        return warnings


    @property
    def security_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.api_key_required and not self.api_key_is_configured:
            warnings.append("API_KEY_REQUIRED is enabled but BACKEND_API_KEY/API_KEY is empty.")
        if self.mistral_enabled and not self.mistral_api_key:
            warnings.append("MISTRAL is enabled but MISTRAL_API_KEY is empty; fallback behavior may be used.")
        if not self.cors_origins():
            warnings.append("No CORS origins are configured.")
        if self.allowed_origins == ["*"]:
            warnings.append("CORS allows all origins; restrict this before production.")
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
            "mistral_model": self.mistral_model,
            "mistral_enabled": self.mistral_enabled,
            "mistral_key_set": bool(self.mistral_api_key),
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "huggingface_model": self.huggingface_model,
            "ollama_url": self.ollama_url,
            "ollama_model": self.ollama_model,
            "kb_storage_root": self.kb_storage_root,
            "structured_data_root": self.structured_data_root,
            "max_upload_mb": self.max_upload_mb,
            "request_timeout_seconds": self.request_timeout_seconds,
            "security_warnings": self.security_warnings,
        }


settings = Settings()
