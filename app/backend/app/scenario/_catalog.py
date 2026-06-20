"""Scenario catalog — discover the available scenario packs on disk.

Module role:
    Read-only enumeration of the scenario packs under
    ``graph_data/data/scenarios/``. Powers the runtime scenario-swap selector
    (``GET /api/scenarios``) and the middleware allowlist that validates the
    ``X-Scenario-Name`` header. Pure filesystem read — no Azure, no SDK.

Layer: 1 (imports only from Layer 0 + sibling _reader).

Dependents:
    - app.routers.scenarios   — GET /api/scenarios
    - app._middleware         — header allowlist validation
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

from app.scenario._reader import _graph_data_root

logger = logging.getLogger(__name__)


def _scenarios_root():
    return _graph_data_root() / "data" / "scenarios"


def _scan() -> list[dict[str, Any]]:
    """Scan the scenarios directory and return pack summaries (uncached).

    A fresh filesystem scan each call keeps the catalog truthful when packs are
    added/removed at runtime (and during tests that create temp packs). The
    scan is a small directory listing — negligible cost on the swap paths.
    """
    root = _scenarios_root()
    packs: list[dict[str, Any]] = []
    if not root.is_dir():
        logger.warning("scenario_catalog.root_missing: %s", root)
        return packs

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        manifest = child / "scenario.yaml"
        if not manifest.is_file():
            continue
        meta: dict[str, Any] = {
            "name": child.name,
            "display_name": child.name,
            "description": "",
            "domain": "",
        }
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            meta["display_name"] = str(data.get("display_name") or child.name)
            meta["description"] = str(data.get("description") or "").strip()
            meta["domain"] = str(data.get("domain") or "").strip()
        except (yaml.YAMLError, OSError) as exc:
            logger.warning("scenario_catalog.parse_failed name=%s err=%s", child.name, exc)
        packs.append(meta)
    return packs


def list_available_scenarios() -> list[dict[str, Any]]:
    """Return summaries of every valid scenario pack on disk."""
    return list(_scan())


def available_scenario_names() -> frozenset[str]:
    """Return the set of valid scenario folder names (header allowlist)."""
    return frozenset(p["name"] for p in _scan())


def invalidate_catalog() -> None:
    """No-op retained for API stability (the scan is now uncached)."""
    return None
