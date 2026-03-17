"""Tool resolution — importlib-based callable loading from spec strings.

Module role:
    Parses ``"module.path:function_name"`` specs from scenario.yaml and
    resolves them to callable Python objects via importlib. Handles the
    graph_explorer registry special case. This module owns tool resolution
    only — no YAML parsing, no prompt loading, no SDK objects.

Key collaborators:
    - importlib — dynamic module loading
    - tools.graph_explorer._registry — registry-based resolution for query_graph

Dependents:
    Imported by: agents/_builder.py only.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Allowed tool module prefixes — prevents arbitrary module imports from
# scenario.yaml. Only modules under tools/ are permitted.
_ALLOWED_TOOL_PREFIXES = ("tools.",)


def resolve_tool(spec: str) -> Any:
    """Import a tool function from a ``module.path:function_name`` spec.

    Args:
        spec: Tool specification string (e.g. ``"tools.graph_explorer:query_graph"``).

    Returns:
        The resolved callable.

    Raises:
        ValueError: If the spec format is invalid or module prefix disallowed.
        ImportError: If the module cannot be imported.
        AttributeError: If the function does not exist in the module.
    """
    if ":" not in spec:
        raise ValueError(
            f"Invalid tool spec '{spec}' — expected 'module.path:function_name'"
        )
    module_path, func_name = spec.rsplit(":", 1)

    # Security: reject module paths outside the allowed prefix list
    if not any(module_path.startswith(p) for p in _ALLOWED_TOOL_PREFIXES):
        raise ValueError(
            f"Tool module '{module_path}' is not in the allowed prefix list"
        )

    # Standard resolution for all tools
    try:
        mod = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(f"Cannot import tool module '{module_path}': {e}") from e

    func = getattr(mod, func_name, None)
    if func is None:
        raise AttributeError(
            f"Module '{module_path}' has no attribute '{func_name}'"
        )
    return func


def resolve_tools(specs: list[str]) -> list[Any]:
    """Batch-resolve tool specs with per-tool error handling.

    Args:
        specs: List of tool specification strings.

    Returns:
        List of resolved callables. Failed specs are logged and skipped.
    """
    tools: list[Any] = []
    for spec in specs:
        try:
            tools.append(resolve_tool(spec))
        except (ImportError, AttributeError, ValueError) as e:
            logger.error("Failed to resolve tool '%s': %s", spec, e)
    return tools
