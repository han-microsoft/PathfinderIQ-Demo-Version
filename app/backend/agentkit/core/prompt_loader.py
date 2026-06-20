"""Prompt file loading (K5) — concatenation with placeholder resolution.

Module role:
    Loads prompt ``.md`` files from a prompts directory, resolves template
    placeholders, and concatenates them into a single instruction string. Owns
    prompt I/O only — no YAML parsing, no tool resolution.

Layering:
    stdlib only + ``agentkit.core.config_loader`` (lazy). Imports no GridIQ
    package. Was ``agent/prompt_loader.py``.

Note (domain residue):
    The two ``{telemetry_backend_prompt}`` / ``{alerts_backend_prompt}``
    placeholder substitutions are inert generic string maps — they fire only if
    a consumer's config references those tokens. They import nothing; left in
    place as harmless residue (tracked for a future config-driven placeholder
    map).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FOUNDATION_TEXT: str | None = None


class PromptLoadError(ValueError):
    """Raised when a non-empty ``instructions:`` spec list resolves to no text.

    Converts the failure mode where a typo or stale reference in the config
    produces an agent booted with no system prompt into a boot-time exception.
    Empty spec lists (caller explicitly listed nothing) do NOT raise — only
    non-empty lists where every entry was missing or empty.

    Attributes:
        spec: The original ``instructions:`` list as configured.
        missing: Concrete filesystem paths the loader looked for and did not
            find or found empty.
    """

    def __init__(self, spec: list[str], missing: list[Path]) -> None:
        self.spec = list(spec)
        self.missing = list(missing)
        joined = ", ".join(str(p) for p in missing) or "(none resolved)"
        super().__init__(
            f"Non-empty instructions spec resolved to empty text. "
            f"Spec={spec!r}; unresolved/empty paths: {joined}"
        )


def invalidate_foundation_prompt_cache() -> None:
    """Clear the cached shared foundation prompt bundle."""
    global _FOUNDATION_TEXT
    _FOUNDATION_TEXT = None


def load_instructions(
    paths: str | list[str],
    prompts_dir: Path,
    preamble_path: Path | None = None,
) -> str:
    """Load and concatenate prompt files, optionally prepending a preamble.

    Args:
        paths: Prompt file paths (relative to prompts_dir), or a single path.
        prompts_dir: The prompts directory (e.g., control/prompts/).
        preamble_path: Path to the generic preamble file (prepended first).

    Returns:
        Concatenated prompt text, separated by double newlines.
    """
    if isinstance(paths, str):
        paths = [paths]

    parts: list[str] = []
    # Track concrete filesystem paths that were specified but did not yield any
    # text — distinguishes "caller said nothing" (empty ``paths``) from "caller
    # named files but loader could not load any of them" (the latter raises).
    unresolved: list[Path] = []

    # Prepend generic preamble if it exists
    if preamble_path and preamble_path.exists():
        text = preamble_path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(text)
            logger.debug("Loaded generic preamble: %s", preamble_path)

    for p in paths:
        # Inert generic placeholder substitutions (domain residue — see header).
        if p == "{telemetry_backend_prompt}":
            p = "tool_query_telemetry.md"
            logger.debug("Resolved {telemetry_backend_prompt} → %s", p)
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
            loaded_any = False
            for md in md_files:
                text = md.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)
                    loaded_any = True
                    logger.debug("Loaded prompt: %s", md)
            if not loaded_any:
                unresolved.append(filepath)
        elif filepath.exists():
            text = filepath.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
                logger.debug("Loaded prompt: %s", filepath)
            else:
                # File exists but is empty — treat as unresolved so a stale
                # entry cannot silently strip the prompt.
                unresolved.append(filepath)
                logger.warning("Prompt file is empty: %s", filepath)
        else:
            logger.warning("Prompt file not found: %s", filepath)
            unresolved.append(filepath)

    # Fail loud when a non-empty spec list resolves to no text. Empty spec list
    # intentionally returns "" (test fixtures + placeholder agents rely on this).
    if paths and not parts:
        raise PromptLoadError(spec=list(paths), missing=unresolved)

    return "\n\n".join(parts)


def load_foundation_prompts() -> str:
    """Load and cache foundation prompt text from agent_config.yaml.

    Foundation prompts are shared-knowledge files every agent receives, listed
    under the top-level ``foundation_prompts`` key and resolved relative to the
    prompts directory.

    Returns:
        Concatenated foundation prompt text, or an empty string when none are
        configured.

    Side effects:
        Caches the loaded prompt text after the first successful read.
    """
    global _FOUNDATION_TEXT
    if _FOUNDATION_TEXT is not None:
        return _FOUNDATION_TEXT

    from agentkit.core.config_loader import get_prompts_dir, load_agent_config

    config = load_agent_config()
    foundation_files = config.get("foundation_prompts", [])
    if not foundation_files:
        _FOUNDATION_TEXT = ""
        return _FOUNDATION_TEXT

    # Single source of truth for the prompts directory.
    prompts_dir = get_prompts_dir()

    parts: list[str] = []
    for filename in foundation_files:
        filepath = prompts_dir / filename
        if not filepath.resolve().is_relative_to(prompts_dir.resolve()):
            logger.warning("Foundation prompt path escapes prompts dir: %s", filename)
            continue
        if filepath.exists():
            text = filepath.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
                logger.info("Loaded foundation prompt: %s", filepath.name)
        else:
            logger.warning("Foundation prompt not found: %s", filepath)

    _FOUNDATION_TEXT = "\n\n".join(parts)
    return _FOUNDATION_TEXT
