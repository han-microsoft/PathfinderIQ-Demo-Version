"""Sandbox tools — cloud-free, scenario-scoped demo tooling.

Module role:
    Self-contained tools used by the ``demo-sandbox`` placeholder scenario to
    prove the scenario-swap logistics end-to-end WITHOUT any Azure dependency.
    Data is read from a static JSON bundled inside the active scenario pack
    (``data/sandbox/dataset.json``), resolved per-request through the same
    scenario-scoping the cloud tools use — so a swap visibly changes the data
    these tools return.

    These tools deliberately avoid Cosmos / Search so the swap can be regressed
    locally and deterministically.

Dependents:
    Wired via scenario.yaml ``tools: [tools.sandbox:sandbox_status]`` etc.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_framework import tool

logger = logging.getLogger(__name__)


def _load_dataset() -> dict[str, Any]:
    """Load the active scenario's static sandbox dataset (or empty)."""
    try:
        from app.scenario import get_scenario_file
        path = get_scenario_file("data/sandbox/dataset.json")
        if path is None:
            return {}
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 — tools return structured, never raise
        logger.warning("sandbox.dataset_load_failed: %s", exc)
        return {}


@tool
def sandbox_status() -> dict[str, Any]:
    """Report the active sandbox dataset summary (name, item count, generated time)."""
    data = _load_dataset()
    items = data.get("items", []) if isinstance(data.get("items"), list) else []
    return {
        "ok": True,
        "dataset": data.get("name", "unknown"),
        "scenario": data.get("scenario", ""),
        "item_count": len(items),
        "generated_at": data.get("generated_at", ""),
    }


@tool
def sandbox_list_items() -> dict[str, Any]:
    """List the items in the active sandbox dataset as {columns, rows}."""
    data = _load_dataset()
    items = data.get("items", []) if isinstance(data.get("items"), list) else []
    columns = ["id", "label", "value"]
    rows = [[it.get("id", ""), it.get("label", ""), it.get("value", "")] for it in items]
    return {"columns": columns, "rows": rows, "row_count": len(rows)}


@tool
def sandbox_echo(text: str) -> dict[str, Any]:
    """Echo the supplied text back — proves a scenario-owned tool is reachable.

    Args:
        text: Arbitrary text to echo.
    """
    return {"ok": True, "echo": text}
