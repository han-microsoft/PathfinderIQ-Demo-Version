"""Capability catalog — unified discovery over agents, tools, and skills.

Ports the vm_agent capability-fabric pattern (``vmagent/catalog``) to
PathfinderIQ: a single keyword-ranked catalog built from the active scenario's
agent + tool definitions, queryable by the agent (``find_capabilities`` tool)
and over HTTP (``/api/catalog/search``). No vector layer — in-process keyword +
token-overlap ranking, the same scoring shape vm_agent uses.

This is the read/discovery half of the capability fabric. Runtime authoring of
new tools/skills/recipes (vm_agent D5 full) remains future work; PathfinderIQ
tools are still declared in ``scenario.yaml``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


@dataclass(frozen=True)
class CatalogEntry:
    """One discoverable capability (agent | tool | skill)."""

    id: str
    kind: str  # "agent" | "tool" | "skill"
    name: str
    summary: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    family: str = ""  # owning agent id for tools, or domain

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "summary": self.summary,
            "tags": list(self.tags),
            "family": self.family,
        }


def rank_entries(
    entries: list[CatalogEntry],
    query: str,
    *,
    kind: str | None = None,
    tags: list[str] | None = None,
    family: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Rank catalog entries against a free-text query (vm_agent scoring).

    Scoring: exact id (+100), id-token overlap (+10/token), tag overlap
    (+6/token), name/summary overlap (+4/token), summary substring (+1).
    Entries scoring 0 are dropped; ties break by id. Optional kind/tags/family
    filters are applied before ranking.
    """
    q = (query or "").strip().lower()
    q_tokens = _tokens(q)
    want_tags = {t.lower() for t in (tags or [])}
    scored: list[tuple[int, str, CatalogEntry]] = []

    for e in entries:
        if kind and e.kind != kind:
            continue
        if family and e.family != family:
            continue
        e_tags = {t.lower() for t in e.tags}
        if want_tags and not (want_tags & e_tags):
            continue

        score = 0
        if q:
            if e.id.lower() == q:
                score += 100
            id_tokens = _tokens(e.id)
            score += 10 * len(q_tokens & id_tokens)
            score += 6 * len(q_tokens & e_tags)
            score += 4 * len(q_tokens & _tokens(e.name + " " + e.summary))
            if q in e.summary.lower():
                score += 1
        else:
            score = 1  # no query → list (filtered) catalog
        if score > 0:
            scored.append((score, e.id, e))

    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{**e.as_dict(), "score": s} for s, _, e in scored[:limit]]
