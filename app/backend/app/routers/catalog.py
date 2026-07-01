"""Catalog router — HTTP surface for the capability fabric.

GET /api/catalog          → full catalog (agents + tools).
GET /api/catalog/search   → ranked discovery by free-text query.

Mirrors vm_agent's catalog-search surface so an operator UI (or external
caller) can browse/search capabilities the same way the agent does.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.capability import build_catalog, rank_entries

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("")
async def catalog(kind: str | None = Query(None, description="agent|tool")):
    """Return the full capability catalog (optionally filtered by kind)."""
    entries = build_catalog()
    items = [e.as_dict() for e in entries if not kind or e.kind == kind]
    return {"count": len(items), "items": items}


@router.get("/search")
async def catalog_search(
    q: str = Query("", description="Free-text capability query"),
    kind: str | None = Query(None, description="agent|tool"),
    limit: int = Query(20, ge=1, le=100),
):
    """Rank the capability catalog against a free-text query."""
    results = rank_entries(build_catalog(), q, kind=kind, limit=limit)
    return {"query": q, "count": len(results), "results": results}
