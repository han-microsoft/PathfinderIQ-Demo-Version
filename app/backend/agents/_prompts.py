"""Prompt file loading — concatenation with placeholder resolution.

Module role:
    Loads prompt .md files from a scenario's data/prompts/ directory,
    resolves the ``{graph_backend_prompt}`` placeholder, and concatenates
    them into a single instruction string. This module owns prompt I/O
    only — no YAML parsing, no tool resolution, no SDK objects.

Key collaborators:
    - tools.graph_explorer._registry — for ``{graph_backend_prompt}`` resolution

Dependents:
    Imported by: agents/_builder.py, agents/__init__.py (AgentRegistry.get_prompt)
"""

from __future__ import annotations

import logging
from pathlib import Path

from agents._config import get_default_id, iter_agents, load_agents_block

logger = logging.getLogger(__name__)


def _build_agent_roster_block() -> str:
    """Render a scenario-derived agent roster block for prompt assembly.

    Purpose:
        Keeps available-agent knowledge sourced from ``scenario.yaml`` instead
        of duplicated markdown. This gives every agent an up-to-date roster for
        direct factual questions such as "what agents are available?".

    Returns:
        Markdown text describing the current scenario's available agent IDs, or
        an empty string when the scenario config is unavailable.
    """
    try:
        config = load_agents_block()
    except Exception as exc:
        logger.debug("Skipping generated agent roster block: %s", exc)
        return ""

    entries = list(iter_agents(config))
    if not entries:
        return ""

    default_id = get_default_id(config)
    valid_ids = {agent_id for agent_id, _ in entries}

    lines = [
        "## Available Agents",
        "",
        "The following agent IDs are available in the active scenario:",
    ]

    for agent_id, agent_cfg in entries:
        name = str(agent_cfg.get("name", agent_id)).strip() or agent_id
        description = str(agent_cfg.get("description", "")).strip()
        suffix = " (default)" if agent_id == default_id and agent_id in valid_ids else ""
        line = f"- `{agent_id}`{suffix} — {name}"
        if description:
            line += f": {description}"
        lines.append(line)

    lines.extend([
        "",
        "Do not invent agent IDs or reuse agents from other scenarios.",
    ])
    return "\n".join(lines)


def load_instructions(
    paths: str | list[str],
    prompts_dir: Path,
    preamble_path: Path | None = None,
) -> str:
    """Load and concatenate prompt files, optionally prepending a preamble.

    Args:
        paths: Prompt file paths, relative to prompts_dir.
        prompts_dir: The scenario's data/prompts/ directory.
        preamble_path: Path to the generic preamble file (prepended first).

    Returns:
        Concatenated prompt text, separated by double newlines.
    """
    if isinstance(paths, str):
        paths = [paths]

    parts: list[str] = []

    # Prepend generic preamble if it exists
    if preamble_path and preamble_path.exists():
        text = preamble_path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(text)
            logger.debug("Loaded generic preamble: %s", preamble_path)

    # Inject the current scenario's available-agent roster so agent identity
    # and delegation answers stay aligned with scenario.yaml without relying on
    # hand-maintained prompt text.
    roster_block = _build_agent_roster_block()
    if roster_block:
        parts.append(roster_block)
        logger.debug("Injected generated agent roster block")

    # Load scenario-specific prompt files
    for p in paths:
        # Resolve graph backend prompt placeholder — Cosmos DB Gremlin
        if p == "{graph_backend_prompt}":
            p = "query_language/gremlin.md"
            logger.debug("Resolved {graph_backend_prompt} → %s", p)

        # Resolve telemetry backend prompt placeholder — Cosmos DB NoSQL
        if p == "{telemetry_backend_prompt}":
            p = "tool_query_telemetry.md"
            logger.debug("Resolved {telemetry_backend_prompt} → %s", p)

        # Resolve alerts backend prompt placeholder — Cosmos DB NoSQL
        if p == "{alerts_backend_prompt}":
            p = "tool_query_alerts.md"
            logger.debug("Resolved {alerts_backend_prompt} → %s", p)

        filepath = prompts_dir / p
        # Path traversal guard — reject paths that escape the prompts directory
        if not filepath.resolve().is_relative_to(prompts_dir.resolve()):
            raise ValueError(f"Prompt path escapes prompts directory: {p}")
        if filepath.is_dir():
            # If path is a directory, glob *.md and sort
            md_files = sorted(filepath.glob("*.md"))
            for md in md_files:
                text = md.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)
                    logger.debug("Loaded prompt: %s", md)
        elif filepath.exists():
            text = filepath.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
                logger.debug("Loaded prompt: %s", filepath)
        else:
            logger.warning("Prompt file not found: %s", filepath)

    if not parts:
        logger.error("No prompt files loaded — agent will have empty instructions")

    result = "\n\n".join(parts)

    # Append a strict language instruction when the user has selected a
    # non-English locale. Placed LAST so it overrides any English-default
    # assumptions embedded in the prompt files. Technical identifiers
    # (node IDs, query syntax, tool names, JSON keys) are explicitly
    # exempted so tool calls and graph queries remain functional.
    try:
        from app.foundation.request_context import get_language
        language = get_language()
        if language and language != "en":
            _LANG_NAMES = {
                "ja": "Japanese", "ko": "Korean", "zh": "Chinese (Simplified)",
                "ms": "Malay", "th": "Thai",
            }
            lang_name = _LANG_NAMES.get(language, language)
            result += (
                f"\n\n## Response Language\n\n"
                f"You MUST respond entirely in {lang_name}. "
                f"All text output — analysis, summaries, explanations, "
                f"recommendations, and natural language — must be in {lang_name}. "
                f"When delegating tasks to other agents, write the task "
                f"description in {lang_name} as well. "
                f"When reporting findings back to the orchestrator, write "
                f"your report in {lang_name}. "
                f"Technical identifiers (node IDs, query syntax, tool names, "
                f"JSON keys, function arguments) remain in their original form. "
                f"Do not mix languages in your natural language output."
            )
    except Exception:
        pass  # Outside request context (startup, tests) — skip injection

    return result
