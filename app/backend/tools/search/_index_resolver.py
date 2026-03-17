"""Search index name resolution from scenario.yaml.

Module role:
    Provides ``get_search_index_name()`` which reads index names from the
    active scenario's ``data_sources.search_indexes`` block. Falls back to
    env vars for backward compatibility.

Key collaborators:
    - ``app.scenario`` — loads scenario.yaml
    - ``_azureaisearch_runbooks.py`` etc. — call this at query time

Usage:
    from tools.search._index_resolver import get_search_index_name
    index = get_search_index_name("runbooks", "RUNBOOKS_INDEX_NAME", "runbooks-index")
"""

from __future__ import annotations

import os


def get_search_index_name(
    key: str,
    env_var: str = "",
    default: str = "",
) -> str:
    """Resolve a search index name from RequestScope, falling back to env var.

    The scope pre-extracts all search index names from scenario.yaml once
    per request. This function reads the pre-extracted value.

    Parameters:
        key: Key in search_indexes dict (e.g. ``"runbooks"``, ``"tickets"``).
        env_var: Env var name to fall back to (e.g. ``"RUNBOOKS_INDEX_NAME"``).
        default: Final fallback value.

    Returns:
        Index name string.
    """
    from app.foundation.request_scope import get_request_scope
    name = get_request_scope().search_indexes.get(key, "")
    if name:
        return name
    if env_var:
        return os.getenv(env_var, default)
    return default


def get_semantic_config_name(key: str, default: str = "") -> str:
    """Resolve a semantic configuration name from RequestScope.

    The scope pre-extracts semantic config names from scenario.yaml once per
    request. This function reads the pre-extracted value.

    Parameters:
        key: Key in search_indexes dict (e.g. ``"runbooks"``).
        default: Fallback if resolution fails.

    Returns:
        Semantic config name string (e.g. ``"airline-ops-procedures-semantic"``).
    """
    from app.foundation.request_scope import get_request_scope
    name = get_request_scope().search_semantic_configs.get(key, "")
    return name or default
