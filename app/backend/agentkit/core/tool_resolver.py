"""Tool resolution (K3) — importlib-based callable loading from spec strings.

Module role:
    Parses tool specs from ``agent_config.yaml`` and resolves them to Python
    callables or platform tool objects. Two spec formats:

    1. ``"module.path:function_name"`` — importlib-resolved local @tool callables
    2. ``"@server:tool_name"`` / ``"@server:tool_name:{json}"`` — Azure AI
       platform tools passed through to the Foundry API.

Fail-closed default (§3.4):
    ``DEFAULT_ALLOWED_TOOL_PREFIXES`` is the empty tuple ``()`` — by default no
    module prefix is importable, forcing the consumer to declare its own
    allowlist. The consumer either passes ``allowed_prefixes=`` per call or
    registers a process-wide default via :func:`set_default_allowed_prefixes`.

Fail-loud resolution (B-RESOLVER-SILENT):
    ``resolve_tools`` raises on the first unresolvable spec by default. A typo
    or stale reference no longer silently drops a tool. Callers that genuinely
    want best-effort behaviour pass ``on_missing="skip"``.

Layering:
    stdlib only (azure SDK imports are lazy, inside server-tool factories).
    Imports no GridIQ package. Was ``agent/tool_resolver.py``.
"""

from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Fail-closed generic default — no prefix is importable until the consumer
# declares one. GridIQ registers ``("tools.",)`` from its composition root.
DEFAULT_ALLOWED_TOOL_PREFIXES: tuple[str, ...] = ()

# Process-wide default allowlist (configured by the consumer). Distinct from the
# constant above so a consumer can register its prefixes once without rebinding
# the public constant other code/tests may read.
_default_allowed_prefixes: tuple[str, ...] = DEFAULT_ALLOWED_TOOL_PREFIXES


def set_default_allowed_prefixes(prefixes: tuple[str, ...]) -> None:
    """Register the process-wide default importable tool-module prefixes."""
    global _default_allowed_prefixes
    _default_allowed_prefixes = tuple(prefixes)


# ── Server-side tool factories ───────────────────────────────────────────────


def _create_web_search_tool(params: dict) -> Any:
    """Create a WebSearchTool instance for the Responses API."""
    from azure.ai.projects.models import WebSearchTool, WebSearchApproximateLocation

    country = params.get("country", "AU")
    city = params.get("city", "")
    region = params.get("region", "")

    kwargs: dict[str, Any] = {}
    if country or city or region:
        kwargs["user_location"] = WebSearchApproximateLocation(
            country=country, city=city, region=region,
        )

    tool = WebSearchTool(**kwargs)
    logger.info("server_tool.web_search: location=%s", country)
    return tool


def _create_azure_ai_search_tool(params: dict) -> Any:
    """Create an AzureAISearchTool instance for the Agents API."""
    from azure.ai.projects.models import (
        AzureAISearchTool,
        AzureAISearchToolResource,
        AzureAISearchIndex,
    )

    connection_name = params.get("connection_name", "aisearch-connection")
    index_name = params.get("index_name", "")
    if not index_name:
        raise ValueError("azure_ai_search requires 'index_name' in params")

    tool = AzureAISearchTool(
        azure_ai_search=AzureAISearchToolResource(
            indexes=[
                AzureAISearchIndex(
                    connection_name=connection_name,
                    index_name=index_name,
                )
            ]
        )
    )
    logger.info("server_tool.azure_ai_search: index=%s, connection=%s", index_name, connection_name)
    return tool


# Explicit factory allowlist — maps the ``@server:<name>`` token to the concrete
# Python callable that builds the platform-tool object. Direct ``Callable``
# values keep allowlist semantics explicit: no ``getattr``/``globals()`` string
# eval. A new server tool is added by editing this dict.
_SERVER_TOOL_FACTORIES: dict[str, Callable[[dict], Any]] = {
    "web_search": _create_web_search_tool,
    "azure_ai_search": _create_azure_ai_search_tool,
}


def _resolve_server_tool(spec: str) -> Any:
    """Resolve a ``@server:`` prefixed tool spec to a platform tool object.

    Raises:
        ValueError: If the tool_name is not in the factory registry.
    """
    parts = spec.split(":", 2)
    tool_name = parts[1] if len(parts) > 1 else ""
    params_json = parts[2] if len(parts) > 2 else "{}"

    factory_fn = _SERVER_TOOL_FACTORIES.get(tool_name)
    if factory_fn is None:
        raise ValueError(
            f"Unknown server tool: '{tool_name}'. "
            f"Available: {list(_SERVER_TOOL_FACTORIES)}"
        )

    params = json.loads(params_json) if params_json else {}
    tool_obj = factory_fn(params)

    logger.info("server_tool.resolved: %s → %s", spec, type(tool_obj).__name__)
    return tool_obj


def resolve_tool(
    spec: str,
    *,
    allowed_prefixes: tuple[str, ...] | None = None,
) -> Any:
    """Resolve a tool spec to a callable or platform tool object.

    Args:
        spec: Tool specification string.
        allowed_prefixes: Module prefixes permitted for importlib resolution.
            ``None`` = use the registered process-wide default (fail-closed
            empty tuple unless the consumer configured one).

    Returns:
        The resolved tool (callable or platform tool object).

    Raises:
        ValueError: If the spec format is invalid or module prefix disallowed.
        ImportError: If the module cannot be imported.
        AttributeError: If the function does not exist in the module.
        TypeError: If the named attribute is not callable.
    """
    if spec.startswith("@server:"):
        return _resolve_server_tool(spec)

    if ":" not in spec:
        raise ValueError(
            f"Invalid tool spec '{spec}' — expected 'module.path:function_name'"
        )
    module_path, func_name = spec.rsplit(":", 1)

    prefixes = allowed_prefixes if allowed_prefixes is not None else _default_allowed_prefixes
    if not any(module_path.startswith(p) for p in prefixes):
        # Diagnostic-only (B-RESOLVER-SILENT UX): name the offending spec and
        # tell the consumer exactly how to allow it. Control flow / fail-closed
        # default are unchanged — this branch still raises ValueError.
        empty_hint = (
            " The allowlist is currently empty (the fail-closed default), so no "
            "tool module can be imported until you declare a prefix."
            if not prefixes
            else ""
        )
        raise ValueError(
            f"Tool spec '{spec}' resolves to module '{module_path}', which is not "
            f"in the allowed tool-import prefix list {tuple(prefixes)!r}. Add its "
            f"package to the allowlist, e.g. "
            f"allowed_tool_prefixes=('your_package.',)." + empty_hint
        )

    try:
        mod = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(f"Cannot import tool module '{module_path}': {e}") from e

    func = getattr(mod, func_name, None)
    if func is None:
        raise AttributeError(
            f"Module '{module_path}' has no attribute '{func_name}'"
        )
    if not callable(func):
        raise TypeError(
            f"Module '{module_path}' attribute '{func_name}' is not callable"
        )
    return func


def resolve_tools(
    specs: list[str],
    *,
    allowed_prefixes: tuple[str, ...] | None = None,
    on_missing: str = "raise",
) -> list[Any]:
    """Batch-resolve tool specs.

    B-RESOLVER-SILENT: the default ``on_missing="raise"`` propagates the first
    unresolvable spec's error so a typo/stale reference fails loud at agent-build
    time instead of silently shipping an agent with a missing tool. Pass
    ``on_missing="skip"`` to restore the prior best-effort log-and-continue.

    Args:
        specs: List of tool specification strings.
        allowed_prefixes: Module prefixes permitted for importlib resolution.
        on_missing: ``"raise"`` (default) or ``"skip"``.

    Returns:
        List of resolved tools.

    Raises:
        ValueError | ImportError | AttributeError | TypeError: When
        ``on_missing="raise"`` and a spec cannot be resolved.
    """
    if on_missing not in ("raise", "skip"):
        raise ValueError(
            f"on_missing must be 'raise' or 'skip', got {on_missing!r}"
        )
    tools: list[Any] = []
    for spec in specs:
        try:
            tools.append(resolve_tool(spec, allowed_prefixes=allowed_prefixes))
        except (ImportError, AttributeError, TypeError, ValueError) as e:
            if on_missing == "raise":
                # Fail loud: a misconfigured tool must not be silently dropped.
                logger.error("Failed to resolve tool '%s': %s", spec, e)
                raise
            logger.error("Failed to resolve tool '%s' (skipped): %s", spec, e)
    return tools
