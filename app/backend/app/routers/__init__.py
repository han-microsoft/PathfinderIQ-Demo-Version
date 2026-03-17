"""Router package — groups all FastAPI APIRouter modules.

Module role:
    Consolidates route definitions that were previously flat in ``app/``.
    Each sub-module owns one APIRouter instance exposed as ``router``.

Package contents:
    - chat             — SSE streaming chat + abort
    - config           — resolved config API for frontend
    - feedback         — bug report submission
    - models           — AI Foundry model listing + switching
    - observability    — SSE log streams + agent metadata
    - scenario         — scenario metadata + topology + health
    - service_health   — Azure service connectivity checks
    - sessions         — session CRUD + save/load

Dependents:
    Called by: ``app.main`` — imports each router and includes it on the app.
"""
