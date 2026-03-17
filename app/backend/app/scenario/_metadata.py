"""Scenario metadata — listing, metadata extraction, consistency checks.

Module role:
    Higher-level scenario functions that consume ``_reader.py`` and serve
    routers / main.py. These include listing all scenarios, extracting
    display metadata, loading graph schema summaries, and checking
    scenario consistency between deployed and runtime config.

Layer: 1 (imports from Layer 0 + sibling _reader.py)

Dependents:
    Called by: app.routers.scenario, app.main (consistency check)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import yaml

from app.foundation.config import settings
from app.scenario._deployment_registry import get_scenario_deployment
from app.scenario._reader import (
    get_scenario_dir,
    get_scenario_file,
    load_scenario_yaml,
)

logger = logging.getLogger(__name__)


def get_scenario_metadata() -> dict[str, Any]:
    """Return a JSON-safe dict of scenario metadata for /api/scenario.

    Includes identity fields, use cases, example questions, and a compact
    representation of the graph ontology parsed from graph_schema.yaml.

    Returns:
        Dict with scenario_name, display_name, description, use_cases,
        example_questions, graph_schema, and demo_flows.
    """
    # Read scenario name from per-request context to prevent cross-user bleed
    from app.foundation.request_scope import get_request_scope
    ctx_scenario = get_request_scope().scenario_name or settings.scenario_name or ""

    meta = load_scenario_yaml()
    if not meta:
        return {
            "scenario_name": ctx_scenario,
            "display_name": ctx_scenario or "Unknown Scenario",
            "description": "",
            "use_cases": [],
            "example_questions": [],
            "is_ready": False,
            "readiness_status": "unregistered",
        }
    deployment = get_scenario_deployment(meta.get("name", ctx_scenario))
    return {
        "scenario_name": meta.get("name", ctx_scenario),
        "display_name": meta.get("display_name", meta.get("name", ctx_scenario)),
        "description": meta.get("description", ""),
        "domain": meta.get("domain", ""),
        "version": meta.get("version", ""),
        "use_cases": meta.get("use_cases", []),
        "example_questions": meta.get("example_questions", []),
        "graph_schema": _load_graph_schema_summary(),
        "demo_flows": _extract_demo_flows(meta),
        "replay_tour": _load_replay_tour(meta),
        "replay_tour_detailed": _load_replay_tour_variant(
            meta,
            inline_key="replay_tour_detailed",
            file_key="replay_tour_detailed_file",
            fallback=_load_replay_tour(meta),
        ),
        "replay_highlights": _load_replay_highlights(meta),
        "replay_conversation_url": _resolve_locale_replay_url(meta),
        "is_ready": deployment.get("status") == "ready",
        "readiness_status": deployment.get("status", "unregistered"),
        "deployed_version": deployment.get("version", ""),
    }


def _resolve_asset_scenario_name(scenario_name: str | None = None) -> str:
    """Resolve the scenario name that should be embedded in asset URLs.

    Browser image and JSON asset requests do not automatically carry the
    per-request scenario header that authenticated API calls use. Embedding the
    scenario name directly in generated asset URLs keeps scenario-local UI
    assets stable after a scenario switch and across replay fetches.

    Args:
        scenario_name: Explicit scenario name when the caller already has it.

    Returns:
        The active scenario name, or an empty string when unavailable.
    """
    if scenario_name:
        return scenario_name

    from app.foundation.request_scope import get_request_scope

    return get_request_scope().scenario_name or settings.scenario_name or ""


def build_scenario_asset_url(
    relative_path: str | None,
    scenario_name: str | None = None,
) -> str | None:
    """Convert a scenario-relative asset path into a loadable API URL.

    Args:
        relative_path: Path relative to the active scenario root.

    Returns:
        API URL for the asset when the file exists, else None.
    """
    if not relative_path:
        return None

    resolved_scenario_name = _resolve_asset_scenario_name(scenario_name)

    asset_file = get_scenario_file(relative_path, resolved_scenario_name)
    if asset_file is None:
        return None

    normalized = str(Path(relative_path).as_posix()).lstrip("/")
    query = urlencode({"scenario": resolved_scenario_name}) if resolved_scenario_name else ""
    suffix = f"?{query}" if query else ""
    return f"/api/scenario/assets/{quote(normalized, safe='/')}{suffix}"


def _load_graph_schema_summary() -> dict[str, Any]:
    """Parse graph_schema.yaml and return a compact ontology summary.

    Returns:
        Dict with ``vertices`` (label + properties list) and ``edges``
        (label + source label + target label). Returns empty lists if
        the file is missing or unparseable.
    """
    scenario_dir = get_scenario_dir()
    if not scenario_dir:
        return {"vertices": [], "edges": []}
    schema_path = scenario_dir / "graph_schema.yaml"
    if not schema_path.exists():
        return {"vertices": [], "edges": []}
    try:
        with open(schema_path) as f:
            schema = yaml.safe_load(f) or {}
    except Exception:
        logger.warning("Failed to parse graph_schema.yaml")
        return {"vertices": [], "edges": []}

    vertices = [
        {"label": v.get("label", ""), "properties": v.get("properties", [])}
        for v in schema.get("vertices", [])
    ]
    edges = []
    for e in schema.get("edges", []):
        src = e.get("source", "")
        tgt = e.get("target", "")
        edges.append({
            "label": e.get("label", ""),
            "source": src.get("label", "") if isinstance(src, dict) else str(src),
            "target": tgt.get("label", "") if isinstance(tgt, dict) else str(tgt),
        })
    return {"vertices": vertices, "edges": edges}


def _extract_demo_flows(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract demo flows from scenario metadata for the frontend picker.

    Returns a compact list of flows with title and step prompts only.

    Returns:
        List of dicts: ``[{title, steps: [{prompt}]}]``
    """
    flows = meta.get("demo_flows", [])
    result = []
    for flow in flows:
        steps = []
        for step in flow.get("steps", []):
            prompt = step.get("prompt", "").strip()
            if prompt:
                steps.append({"prompt": prompt})
        if steps:
            result.append({"title": flow.get("title", "Untitled"), "steps": steps})
    return result


def _load_replay_tour(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Load replay tour steps from scenario metadata or a scenario-local file.

    The scenario author may either inline ``ui.replay_tour`` in ``scenario.yaml``
    or point ``ui.replay_tour_file`` at a YAML file within the scenario folder.

    Args:
        meta: Parsed scenario.yaml contents.

    Returns:
        List of frontend-ready replay tour step dicts.
    """
    return _load_replay_tour_variant(
        meta,
        inline_key="replay_tour",
        file_key="replay_tour_file",
    )


def _get_ui_block(meta: dict[str, Any]) -> dict[str, Any]:
    """Return the scenario UI block as a dict.

    The scenario author may omit the block entirely or provide a non-dict
    value accidentally. Normalising here keeps the downstream loaders simple.
    """
    return meta.get("ui", {}) if isinstance(meta.get("ui"), dict) else {}


def _load_replay_tour_variant(
    meta: dict[str, Any],
    *,
    inline_key: str,
    file_key: str,
    fallback: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Load one replay-tour variant from inline metadata or a scenario file.

    Args:
        meta: Parsed scenario.yaml contents.
        inline_key: UI block key containing inline replay steps.
        file_key: UI block key pointing at a YAML file under the scenario root.
        fallback: Value returned when the scenario does not define this variant.

    Returns:
        List of frontend-ready replay tour step dicts.
    """
    ui_block = _get_ui_block(meta)

    raw_steps = ui_block.get(inline_key, [])
    replay_tour_file = ui_block.get(file_key)
    if replay_tour_file:
        replay_tour_path = get_scenario_file(str(replay_tour_file))
        if replay_tour_path:
            try:
                loaded = yaml.safe_load(replay_tour_path.read_text()) or []
                if isinstance(loaded, list):
                    raw_steps = loaded
            except Exception as exc:
                logger.warning("Failed to parse replay tour file '%s': %s", file_key, exc)

    result: list[dict[str, Any]] = []
    for step in raw_steps if isinstance(raw_steps, list) else []:
        if not isinstance(step, dict):
            continue

        title = str(step.get("title", "")).strip()
        body = str(step.get("body", "")).strip()
        cta = str(step.get("cta", "Continue")).strip() or "Continue"
        if not title or not body:
            continue

        entry: dict[str, Any] = {
            "title": title,
            "body": body,
            "cta": cta,
        }

        agent_image_url = build_scenario_asset_url(step.get("agent_image"))
        if agent_image_url:
            entry["agentImage"] = agent_image_url

        powered_by = step.get("powered_by")
        if isinstance(powered_by, dict):
            logo_url = build_scenario_asset_url(powered_by.get("logo"))
            label = str(powered_by.get("label", "")).strip()
            description = str(powered_by.get("description", "")).strip()
            if logo_url and label:
                entry["poweredBy"] = {
                    "logoSrc": logo_url,
                    "label": label,
                    "description": description,
                }

        result.append(entry)

    if result:
        return result
    return list(fallback or [])


def _resolve_locale_replay_url(meta: dict[str, Any]) -> str | None:
    """Return a locale-aware replay conversation asset URL.

    When the request language is not English, checks if a locale-specific
    replay conversation file exists (e.g. ``replay_conversation_ja.json``).
    Falls back to the default English file if no locale variant is found.

    This allows scenario authors to provide translated replay conversations
    by simply placing ``replay_conversation_ja.json`` next to the default file.
    """
    ui_block = _get_ui_block(meta)
    default_file = ui_block.get("replay_conversation_file")
    if not default_file:
        return None

    from app.foundation.request_context import get_language
    lang = get_language()

    if lang and lang != "en":
        base, ext = str(default_file).rsplit(".", 1) if "." in str(default_file) else (str(default_file), "json")
        locale_file = f"{base}_{lang}.{ext}"
        locale_path = get_scenario_file(locale_file)
        if locale_path:
            return build_scenario_asset_url(locale_file)

    return build_scenario_asset_url(default_file)


def _load_replay_highlights(meta: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Load replay highlight callouts keyed by tool call ID.

    The detailed replay uses these callouts to pause on key tool results.
    Highlights are kept scenario-local so each scenario owns both its copy and
    its tool-call bindings.

    Locale-aware: when the request language is not English, looks for a
    locale-specific file first (e.g. replay_highlights_ja.yaml). Falls
    back to the default English file if the locale variant doesn't exist.
    """
    ui_block = _get_ui_block(meta)

    # Try locale-specific highlights file first
    from app.foundation.request_context import get_language
    lang = get_language()
    raw_entries = ui_block.get("replay_highlights", [])
    replay_highlights_file = ui_block.get("replay_highlights_file")

    if replay_highlights_file and lang and lang != "en":
        # e.g. replay_highlights.yaml → replay_highlights_ja.yaml
        base, ext = str(replay_highlights_file).rsplit(".", 1) if "." in str(replay_highlights_file) else (str(replay_highlights_file), "yaml")
        locale_file = f"{base}_{lang}.{ext}"
        locale_path = get_scenario_file(locale_file)
        if locale_path:
            try:
                loaded = yaml.safe_load(locale_path.read_text()) or []
                if isinstance(loaded, list):
                    raw_entries = loaded
                    replay_highlights_file = None  # skip default loading below
            except Exception:
                pass  # fall through to default file

    if replay_highlights_file:
        replay_highlights_path = get_scenario_file(str(replay_highlights_file))
        if replay_highlights_path:
            try:
                loaded = yaml.safe_load(replay_highlights_path.read_text()) or []
                if isinstance(loaded, list):
                    raw_entries = loaded
            except Exception as exc:
                logger.warning("Failed to parse replay highlights file: %s", exc)

    highlights: dict[str, dict[str, str]] = {}
    for entry in raw_entries if isinstance(raw_entries, list) else []:
        if not isinstance(entry, dict):
            continue
        tool_call_id = str(entry.get("tool_call_id", "")).strip()
        title = str(entry.get("title", "")).strip()
        body = str(entry.get("body", "")).strip()
        if not tool_call_id or not title or not body:
            continue
        highlights[tool_call_id] = {
            "title": title,
            "body": body,
        }
    return highlights
