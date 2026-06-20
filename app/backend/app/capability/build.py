"""Build the capability catalog from the active scenario.

Introspects ``scenario.yaml`` agents + their declared tool specs into a flat
list of :class:`CatalogEntry` records (agents + tools). Tool summaries come
from the resolved callable's docstring first line; tags are derived from id
tokens. The catalog is cached per process and rebuilt on scenario change.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.capability.search import CatalogEntry
from agents._config import iter_agents, load_agents_block
from agents._tools import resolve_tool

logger = logging.getLogger(__name__)

_catalog_cache: list[CatalogEntry] | None = None
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _split_id_tags(identifier: str) -> tuple[str, ...]:
    """Derive coarse tags from an id's word/camel tokens."""
    parts = re.split(r"[_\-./:]", identifier)
    out: set[str] = set()
    for p in parts:
        for tok in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", p):
            if len(tok) > 1:
                out.add(tok.lower())
    return tuple(sorted(out))


def _docstring_summary(fn: Any) -> str:
    doc = (getattr(fn, "__doc__", "") or "").strip()
    if not doc:
        # @tool-decorated callables may stash the description elsewhere.
        doc = (getattr(fn, "description", "") or "").strip()
    first = doc.split("\n", 1)[0].strip()
    return first[:240]


def build_catalog(*, force: bool = False) -> list[CatalogEntry]:
    """Build (and cache) the capability catalog from the active scenario."""
    global _catalog_cache
    if _catalog_cache is not None and not force:
        return _catalog_cache

    entries: list[CatalogEntry] = []
    tool_seen: dict[str, dict] = {}  # tool_id -> {summary, families:set, tags}

    try:
        block = load_agents_block()
    except Exception as exc:  # scenario not loaded / malformed
        logger.warning("capability.build: cannot load agents block: %s", exc)
        _catalog_cache = []
        return _catalog_cache

    for agent_id, cfg in iter_agents(block):
        name = cfg.get("name", agent_id)
        summary = " ".join((cfg.get("description") or "").split())[:240]
        entries.append(
            CatalogEntry(
                id=agent_id,
                kind="agent",
                name=name,
                summary=summary,
                tags=_split_id_tags(agent_id) + _split_id_tags(name),
                family="agents",
            )
        )
        for spec in cfg.get("tools", []) or []:
            if not isinstance(spec, str) or ":" not in spec:
                continue
            tool_id = spec.rsplit(":", 1)[1]
            slot = tool_seen.setdefault(
                tool_id, {"summary": "", "families": set(), "tags": set()}
            )
            slot["families"].add(agent_id)
            slot["tags"].update(_split_id_tags(tool_id))
            if not slot["summary"]:
                try:
                    fn = resolve_tool(spec)
                    slot["summary"] = _docstring_summary(fn)
                except Exception as exc:
                    logger.debug("capability.build: resolve %s failed: %s", spec, exc)

    for tool_id, slot in tool_seen.items():
        entries.append(
            CatalogEntry(
                id=tool_id,
                kind="tool",
                name=tool_id,
                summary=slot["summary"],
                tags=tuple(sorted(slot["tags"])),
                family=",".join(sorted(slot["families"])),
            )
        )

    # Skills (.skill.md) + recipes (.recipe.yaml) discovered from the scenario
    # data dir — the agent-authorable capability layer (lineage: vm_agent fabric).
    entries.extend(_discover_skills())
    entries.extend(_discover_recipes())

    logger.info(
        "capability.build: %d entries (%d agents, %d tools, %d skills, %d recipes)",
        len(entries),
        sum(1 for e in entries if e.kind == "agent"),
        sum(1 for e in entries if e.kind == "tool"),
        sum(1 for e in entries if e.kind == "skill"),
        sum(1 for e in entries if e.kind == "recipe"),
    )
    _catalog_cache = entries
    return _catalog_cache


def _scenario_data_dir():
    """Resolve the active scenario's data/ directory (or None)."""
    try:
        from app.foundation.config import settings
        from app.scenario._reader import get_scenario_dir

        sdir = get_scenario_dir(settings.scenario_name or None)
        if sdir is None:
            return None
        data = sdir / "data"
        return data if data.is_dir() else None
    except Exception as exc:
        logger.debug("capability.build: scenario data dir unresolved: %s", exc)
        return None


def _discover_skills() -> list[CatalogEntry]:
    data = _scenario_data_dir()
    if data is None:
        return []
    out: list[CatalogEntry] = []
    for p in sorted((data / "skills").glob("*.skill.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        first = next((ln for ln in text.splitlines() if ln.strip()), p.stem)
        name = first.lstrip("# ").strip() or p.stem
        tags: tuple[str, ...] = ()
        m = re.search(r"(?im)^##\s*tags\s*\n(.+)$", text)
        if m:
            tags = tuple(t.strip().lower() for t in re.split(r"[,\n]", m.group(1)) if t.strip())
        out.append(
            CatalogEntry(
                id=p.stem.replace(".skill", ""),
                kind="skill",
                name=name,
                summary=name,
                tags=tags or _split_id_tags(p.stem),
                family="skills",
            )
        )
    return out


def _discover_recipes() -> list[CatalogEntry]:
    data = _scenario_data_dir()
    if data is None:
        return []
    import yaml  # pyyaml is a base dependency

    out: list[CatalogEntry] = []
    for p in sorted((data / "recipes").glob("*.recipe.yaml")):
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            doc = {}
        rid = str(doc.get("id") or p.stem.replace(".recipe", ""))
        out.append(
            CatalogEntry(
                id=rid,
                kind="recipe",
                name=str(doc.get("name") or rid),
                summary=" ".join(str(doc.get("summary") or "").split())[:240],
                tags=tuple(str(t).lower() for t in (doc.get("tags") or [])) or _split_id_tags(rid),
                family="recipes",
            )
        )
    return out


def invalidate_catalog() -> None:
    global _catalog_cache
    _catalog_cache = None
