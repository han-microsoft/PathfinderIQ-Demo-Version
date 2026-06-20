"""Batteries-included Azure MAF ``AgentClient`` factory — the one-line wiring.

Module role:
    A consumer wiring a real Azure model behind the agentkit runtime would
    otherwise hand-write the ~50-line ``AzureAIAgentClient`` construction that
    GridIQ keeps in ``hosting/fastapi/runtime/agent_client_factories.py``. This
    module generalises that shape into a single call:

        from agentkit.sdk.azure_client import azure_openai_agent_client

        factory = azure_openai_agent_client(
            endpoint="https://my-project.services.ai.azure.com/...",
            model_deployment="gpt-4o",
        )
        # inject ``factory`` straight into AgentRegistry.configure / AgentApp.

    The returned value is a ZERO-ARG factory ``() -> client`` (the registry
    caches one client per ``agent_id`` to prevent SDK identity bleed, so it
    needs a factory, not an instance).

Import-light / zero-SDK-at-load:
    Mirrors ``agentkit/sdk/maf_client.py`` — the heavy SDK imports
    (``agent_framework`` = the ``[maf]`` extra, ``azure.identity`` = the
    ``[azure]`` extra) happen lazily INSIDE the factory call, never at module
    load. Importing this module costs nothing; the base wheel imports it without
    either SDK installed.

One-credential pattern:
    ``credential`` defaults to a single cached ``DefaultAzureCredential()`` built
    on the first factory call and reused across every cached client — the same
    code path local (CLI login) and in cloud (workload identity), no key
    material, no env branching.

Layer rule:
    Imports ``agentkit.*`` only at load (none needed) + stdlib. Imports ZERO
    consumer (GridIQ) package. The SDK imports are lazy and isolated here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Shown verbatim when the SDK extras are missing — names the exact pip extras so
# the consumer can self-serve the fix.
_MAF_IMPORT_HINT = (
    "azure_openai_agent_client requires the Microsoft Agent Framework SDK "
    "(the [maf] extra). Install it with: pip install 'agentkit[maf,azure]'"
)
_AZURE_IMPORT_HINT = (
    "azure_openai_agent_client needs azure-identity (the [azure] extra) to build "
    "the default credential. Install it with: pip install 'agentkit[azure]' "
    "— or pass an explicit credential=."
)


def azure_openai_agent_client(
    *,
    endpoint: str,
    model_deployment: str,
    credential: Any | None = None,
    api_version: str | None = None,
) -> Callable[[], Any]:
    """Build a zero-arg Azure AI ``AgentClient`` factory ready to inject.

    Generalises GridIQ's ``build_client_factories`` Agents-API factory: a fresh
    ``agent_framework.azure.AzureAIAgentClient`` wired to the project endpoint,
    model deployment, and credential. Each call to the returned factory produces
    a fresh client (the registry caches one per ``agent_id``).

    Args:
        endpoint: The Azure AI Foundry **project endpoint** (e.g.
            ``https://<name>.services.ai.azure.com/api/projects/<project>``).
            Required; a blank value raises ``ValueError`` eagerly here rather
            than at first agent build.
        model_deployment: The model deployment name (e.g. ``gpt-4o``). Required.
        credential: An Azure credential (any ``TokenCredential``). ``None`` (the
            default) builds and caches one ``DefaultAzureCredential()`` lazily on
            the first factory call — the one-credential pattern.
        api_version: Optional Azure API version string. When provided it is
            passed through to the SDK client; ``None`` leaves the SDK default.

    Returns:
        A zero-arg callable ``() -> AzureAIAgentClient`` suitable for
        ``AgentRegistry.configure(...)`` / ``AgentApp(agent_client=...)``.

    Raises:
        ValueError: If ``endpoint`` or ``model_deployment`` is empty.
        ImportError: Raised by the returned factory (not here) when
            ``agent_framework`` / ``azure-identity`` are not installed — the
            message names the missing extra.
    """
    if not endpoint:
        raise ValueError(
            "azure_openai_agent_client requires a non-empty 'endpoint' "
            "(the Azure AI Foundry project endpoint)."
        )
    if not model_deployment:
        raise ValueError(
            "azure_openai_agent_client requires a non-empty 'model_deployment'."
        )

    # Cache slot for the default credential so it is built at most once across
    # every client this factory produces (the one-credential pattern). A dict
    # holder keeps the closure assignable without ``nonlocal`` ceremony.
    _cred_holder: dict[str, Any] = {"credential": credential}

    def _factory() -> Any:
        """Build a fresh Azure Agents-API client (SDK imported lazily here)."""
        try:
            from agent_framework.azure import AzureAIAgentClient
        except ImportError as exc:
            # Name the [maf] extra so the consumer can self-serve the install.
            raise ImportError(_MAF_IMPORT_HINT) from exc

        cred = _cred_holder["credential"]
        if cred is None:
            try:
                from azure.identity import DefaultAzureCredential
            except ImportError as exc:
                raise ImportError(_AZURE_IMPORT_HINT) from exc
            cred = DefaultAzureCredential()
            _cred_holder["credential"] = cred  # reuse across subsequent builds

        kwargs: dict[str, Any] = {
            "project_endpoint": endpoint,
            "model_deployment_name": model_deployment,
            "credential": cred,
        }
        if api_version is not None:
            kwargs["api_version"] = api_version

        client = AzureAIAgentClient(**kwargs)
        logger.info(
            "azure_openai_agent_client.built: endpoint=%s deployment=%s",
            endpoint,
            model_deployment,
        )
        return client

    return _factory


__all__ = ["azure_openai_agent_client"]
