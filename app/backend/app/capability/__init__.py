"""Capability fabric — unified discovery over agents, tools, and skills.

Read/discovery half of the vm_agent capability-fabric pattern, ported to
PathfinderIQ. See ``search.py`` (ranking) and ``build.py`` (catalog build).
"""

from app.capability.build import build_catalog, invalidate_catalog
from app.capability.search import CatalogEntry, rank_entries

__all__ = ["CatalogEntry", "rank_entries", "build_catalog", "invalidate_catalog"]
