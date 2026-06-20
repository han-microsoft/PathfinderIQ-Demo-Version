"""agentkit.config.settings — generic agent-runtime settings base.

Module role:
    The domain-blind half of GridIQ's former monolithic ``Settings`` class
    (TIER1_EXTRACTION_PLAN §7 increment 2). Holds only fields that any agent
    application needs — LLM provider selection, agent-runtime knobs, context
    window, session persistence, auth, CORS, observability, SSE tuning — plus
    the two cross-app validators and the ``running_in_azure()`` platform
    sensor. GridIQ's ``foundation.config.Settings`` subclasses this and adds
    the domain fields (Fabric / Eventhouse / AI Search / scenario).

Why this is the env-reading module now:
    Before the split, ``foundation/config.py`` was "the only module that reads
    os.environ". That invariant transfers here for the generic half:
    pydantic-settings reads env for every field, and ``running_in_azure()``
    reads platform env vars. GridIQ's subclass keeps the dotenv-file binding
    (the path is repo-specific, so it stays in ``foundation/config.py``).

Settings access for agentkit internals:
    ``agentkit`` code (e.g. ``agentkit.resilience.get_model_fallback_queue``)
    must read settings without importing a GridIQ package. It calls
    ``get_settings()``, which returns the process-wide instance registered by
    the composition root via ``configure_settings(...)``. GridIQ registers its
    ``Settings()`` singleton at import time of ``foundation/config.py``. When
    ``agentkit`` runs standalone (no GridIQ), ``get_settings()`` lazily
    constructs a bare ``BaseAgentSettings``.

Layer rule:
    Imports stdlib + pydantic / pydantic-settings only. Never a GridIQ package.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field, SecretStr, model_validator


def _first_env_alias(validation_alias: Any) -> str:
    """Return the first string env-var name from a field's ``validation_alias``.

    A ``validation_alias`` is either a bare ``str`` or an ``AliasChoices`` whose
    ``.choices`` lists the accepted env-var names (and possibly ``AliasPath``
    objects). ``from_env`` routes an override for such a field through its env
    var, so it needs the canonical (first) string alias.
    """
    if isinstance(validation_alias, str):
        return validation_alias
    choices = getattr(validation_alias, "choices", None)
    if choices:
        for choice in choices:
            if isinstance(choice, str):
                return choice
    return str(validation_alias)


class BaseAgentSettings(BaseSettings):
    """Generic, domain-blind settings shared by every agent application.

    All fields default to local-dev-safe values. ``env_prefix=""`` so env
    vars are read by their bare names (``LLM_PROVIDER``, not
    ``APP_LLM_PROVIDER``). No ``env_file`` here — the dotenv path is
    application-specific and is bound by the consuming subclass.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file_encoding="utf-8",
        extra="ignore",            # subclass adds domain fields; ignore unknown env
    )

    # ── LLM provider ─────────────────────────────────────────────────────
    # "openai" (direct API), "agent" (Azure AI Agent Framework),
    # "echo" (parrots input), "mock" (canned rich response).
    llm_provider: str = "openai"
    llm_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_BASE_URL", "AZURE_OPENAI_ENDPOINT"),
    )   # OpenAI-compatible endpoint; empty = official OpenAI API
    llm_api_key: SecretStr = SecretStr("")    # Required for "openai"; unused by "agent"
    llm_model: str = ""  # Model deployment name — per-agent in config or via LLM_MODEL
    # Fast-tier deployment used when an agent declares ``model: fast``.
    llm_model_fast: str = Field(
        default="",
        validation_alias=AliasChoices(
            "LLM_MODEL_FAST",
            "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME_FAST",
        ),
    )
    # Optional simulated wall-clock anchor for demo scenarios. ISO-8601 with
    # timezone. Empty = real UTC.
    simulated_time: str = ""

    # ── Azure AI / OpenAI Responses API ──────────────────────────────────
    azure_ai_project_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("AZURE_AI_PROJECT_ENDPOINT"),
    )
    azure_openai_responses_deployment_name: str = Field(
        default="",
        validation_alias=AliasChoices("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"),
    )
    # Comma-separated fallback model deployments tried after the primary model
    # exhausts retries. CSV string (deploy env ships bare CSV, not JSON).
    llm_fallback_models_raw: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_FALLBACK_MODELS"),
    )

    @property
    def llm_fallback_models(self) -> list[str]:
        """Parsed list view of ``LLM_FALLBACK_MODELS`` (comma-separated)."""
        return [item.strip() for item in self.llm_fallback_models_raw.split(",") if item.strip()]

    # ── Agent runtime knobs ──────────────────────────────────────────────
    # Per-run silent-update deadline before revival.
    agent_stall_timeout_seconds: float = Field(
        default=45.0,
        validation_alias=AliasChoices("AGENT_STALL_TIMEOUT_SECONDS"),
    )
    # Maximum automatic revivals for one stalled run. Clamped to >=0 at consumer.
    agent_max_revivals: int = Field(
        default=1,
        validation_alias=AliasChoices("AGENT_MAX_REVIVALS"),
    )

    # ── Build metadata ───────────────────────────────────────────────────
    # Surfaced via the OTel Resource. Set at container build time.
    app_version: str = Field(
        default="0.1.0-dev",
        validation_alias=AliasChoices("APP_VERSION"),
    )

    # ── LLMOps export backend ────────────────────────────────────────────
    # Selects the LLMOps trace exporter. Empty disables LLMOps tracing.
    llmops_backend: str = Field(
        default="",
        validation_alias=AliasChoices("LLMOPS_BACKEND"),
    )

    # ── Context window ───────────────────────────────────────────────────
    # Budget = max_context_tokens - max_response_tokens.
    max_context_tokens: int = 120_000   # Total input window budget (tokens)
    max_response_tokens: int = 4_096    # Reserved for completion output (tokens)
    system_prompt: str = "You are a helpful assistant."  # Default; overridden by prompts

    # ── Session persistence (Cosmos NoSQL) ───────────────────────────────
    # If set, a durable session store is used; empty/unreachable falls back to
    # in-memory. RBAC-only auth — DefaultAzureCredential, no keys.
    cosmos_session_endpoint: str = ""
    cosmos_session_database: str = "sessions"
    cosmos_session_container: str = "conversations"
    cosmos_session_ttl: int = -1  # -1 = no expiration (persist forever)
    # Legacy Cosmos endpoint fallback used when ``cosmos_session_endpoint`` unset.
    cosmos_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("COSMOS_ENDPOINT"),
    )

    # ── Authentication ───────────────────────────────────────────────────
    # AUTH_ENABLED=false (local dev) → anonymous user. true (prod) → JWT Bearer
    # validated against Entra ID JWKS. Multi-tenant: AUTH_TENANT_ID="common".
    auth_enabled: bool = True
    auth_client_id: str = ""          # REQUIRED when AUTH_ENABLED=true
    auth_tenant_id: str = "common"    # "common" for multi-tenant

    # ── Local dev signing (opt-in, removable) ────────────────────────────
    # ED25519 public key (base64, raw 32 bytes). Non-empty + both signing
    # headers present → devauth middleware grants a synthetic identity.
    # Public key only — nothing exploitable in this value.
    dev_public_key_ed25519: str = ""

    # ── Server ───────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    debug: bool = False  # Enables DEBUG-level logging when true

    # ── Observability ────────────────────────────────────────────────────
    # OTel export target: "" / "noop" (drop), "console", "azure" (App
    # Insights), "otlp" (Collector / Jaeger / Datadog).
    otel_export_target: str = "console"
    applicationinsights_connection_string: str = ""  # Required when target=azure
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        validation_alias=AliasChoices("OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"),
    )  # Required when target=otlp

    # ── SSE streaming (hosting layer tuning) ─────────────────────────────
    # Max time a single chat request may run before forced termination.
    chat_timeout_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("CHAT_TIMEOUT_SECONDS"),
    )
    # Polling interval for request.is_disconnected() inside the chat SSE gen.
    disconnect_poll_seconds: float = 1.0
    # Application-level KEEPALIVE event cadence during long tool executions.
    chat_keepalive_seconds: int = 15
    # EventSourceResponse(ping=N) transport heartbeat cadence.
    sse_keepalive_ping_seconds: int = 20
    # Min interval between successive DELEGATION_ERROR overflow markers per
    # (session_id, agent_id).
    delegation_overflow_marker_seconds: float = 5.0
    # Max encoded-JSON size of a single SSE frame's data field; larger frames
    # are replaced with a categorical truncation envelope.
    max_sse_frame_bytes: int = 65_536

    @model_validator(mode="after")
    def _validate_provider_config(self):
        """Validate required config for the selected LLM provider.

        For 'openai', LLM_API_KEY or LLM_BASE_URL must be set. For 'agent',
        AZURE_AI_PROJECT_ENDPOINT may arrive later via ConfigResolver — warn
        instead of failing at import time.
        """
        if self.llm_provider == "openai":
            if not self.llm_api_key.get_secret_value() and not self.llm_base_url:
                raise ValueError(
                    "LLM_PROVIDER=openai requires either LLM_API_KEY or "
                    "LLM_BASE_URL. Set in control/.env."
                )
        elif self.llm_provider == "agent":
            if not self.azure_ai_project_endpoint:
                import logging
                logging.getLogger(__name__).info(
                    "AZURE_AI_PROJECT_ENDPOINT not set at import time — "
                    "ConfigResolver will populate at startup"
                )
        return self

    @model_validator(mode="after")
    def _validate_auth_config(self):
        """Fail fast if auth is enabled but client ID is missing."""
        if self.auth_enabled and not self.auth_client_id:
            raise ValueError(
                "AUTH_ENABLED=true requires AUTH_CLIENT_ID. "
                "Set AUTH_CLIENT_ID to your Entra app registration's "
                "Application (client) ID."
            )
        return self

    @classmethod
    def from_env(cls, **overrides: Any) -> "BaseAgentSettings":
        """Build settings from the environment with explicit overrides applied.

        Quickstart-friendly constructor: ``BaseSettings`` already reads every
        field from the environment, so this returns ``cls(**overrides)`` with one
        correctness fix for a pydantic-settings footgun.

        **Trap 1 — ``validation_alias``-only fields silently ignore kwargs.**
        A field declared with ``validation_alias`` (and no ``populate_by_name``),
        e.g. ``llmops_backend = Field(validation_alias=AliasChoices("LLMOPS_BACKEND"))``,
        can be set *only* via its env-var alias. A plain ``llmops_backend="..."``
        kwarg to ``cls(...)`` is dropped without error. ``from_env`` detects such
        overrides and routes them through ``os.environ`` (set → build → restore)
        so the override actually takes effect. Non-aliased fields are passed as
        normal kwargs (kwarg beats env, the documented pydantic-settings rule).

        **Trap 2 — the lazy bare-build / ``get_settings()`` trap.** Constructing
        a bare ``BaseAgentSettings()`` (which ``get_settings()`` does when nothing
        is registered) ``ValidationError``s on required provider/auth fields in
        an isolated context. ``from_env`` does NOT register the result — call
        ``configure_settings(BaseAgentSettings.from_env(...))`` to register it.
        In tests, snapshot/restore the raw ``agentkit.config.settings._active_settings``
        module global around ``configure_settings`` rather than ``get_settings()``.

        Args:
            **overrides: Field values to force regardless of the environment.

        Returns:
            A fully-built settings instance (not registered process-wide).
        """
        # populate_by_name (rare) would let aliased fields accept kwargs too; if
        # it is set we don't need the env-routing workaround.
        populate_by_name = bool(cls.model_config.get("populate_by_name", False))

        direct_kwargs: dict[str, Any] = {}
        env_routed: list[tuple[str, str]] = []
        for name, value in overrides.items():
            field = cls.model_fields.get(name)
            alias = getattr(field, "validation_alias", None) if field is not None else None
            if alias is not None and not populate_by_name:
                # validation_alias-only field: a kwarg would be silently ignored,
                # so route the override through its env-var alias instead.
                env_routed.append((_first_env_alias(alias), str(value)))
            else:
                direct_kwargs[name] = value

        if not env_routed:
            return cls(**direct_kwargs)

        # Temporarily set the env aliases, build, then restore the prior env so
        # this call has no lasting process side effect.
        saved: dict[str, str | None] = {
            env_name: os.environ.get(env_name) for env_name, _ in env_routed
        }
        try:
            for env_name, env_value in env_routed:
                os.environ[env_name] = env_value
            return cls(**direct_kwargs)
        finally:
            for env_name, original in saved.items():
                if original is None:
                    os.environ.pop(env_name, None)
                else:
                    os.environ[env_name] = original


def running_in_azure() -> bool:
    """True when the process is hosted by an Azure workload identity surface.

    Sensed from platform-injected env vars (``WEBSITE_INSTANCE_ID``,
    ``KUBERNETES_SERVICE_HOST``, ``CONTAINER_APP_NAME``, ``AZURE_CLIENT_ID``).
    The credential factory reads this instead of touching ``os.environ``
    directly — env-reading stays inside this settings module.
    """
    return bool(
        os.environ.get("WEBSITE_INSTANCE_ID")
        or os.environ.get("KUBERNETES_SERVICE_HOST")
        or os.environ.get("CONTAINER_APP_NAME")
        or os.environ.get("AZURE_CLIENT_ID")
    )


# ── Process-wide settings accessor ───────────────────────────────────────────
# The composition root registers its concrete (possibly subclassed) settings
# instance via ``configure_settings``. agentkit internals read it via
# ``get_settings`` so they never import a GridIQ package. Standalone agentkit
# use lazily constructs a bare ``BaseAgentSettings``.
_active_settings: BaseAgentSettings | None = None


def configure_settings(instance: BaseAgentSettings) -> None:
    """Register the process-wide settings instance (called by composition root)."""
    global _active_settings
    _active_settings = instance


def get_settings() -> BaseAgentSettings:
    """Return the registered settings instance, or a lazy default if unset."""
    global _active_settings
    if _active_settings is None:
        _active_settings = BaseAgentSettings()
    return _active_settings
