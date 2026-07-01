"""example_health — reference eval flow. Mirrors a typical Azure service journey.

"What good looks like" for an eval: a named, tagged user-journey that exercises
the live deploy end-to-end on synthetic, nonce-owned data, with a falsifiable
assertion at every step and cleanup that always runs.

This is a REFERENCE. Copy + adapt to your real journeys; delete if not applicable.
The journey modelled (a generic authed CRUD service on Azure Container Apps):
    1. health endpoint returns ok + a build id
    2. unauthenticated write is rejected (auth gate holds)
    3. authenticated write succeeds and echoes the nonce (core write path)
    4. read-back returns the just-written record (round-trip)
    5. cleanup deletes the nonce-owned record

Proven against a fake in-process server by ../selftest.py — run that to see the
runner + this flow exercise the full pass path AND a forced negative path.
"""
from __future__ import annotations

import json

from flow import EvalContext, Flow, Step

# A real flow would read a dev token from the env/managed-identity per PROJECT.md
# §6; the reference uses a fixed synthetic token the fake server accepts.
_AUTH = {"authorization": "Bearer synthetic-dev-token"}


def _health(ctx: EvalContext) -> str:
    status, body = ctx.get("/health")
    ctx.expect(status == 200, f"health status {status}, want 200")
    data = json.loads(body)
    ctx.expect(data.get("ok") is True, "health did not report ok")
    return f"healthy build={data.get('build', '?')}"


def _unauth_rejected(ctx: EvalContext) -> str:
    status, _ = ctx.post("/items", body={"name": f"x-{ctx.nonce}"})
    ctx.expect(status in (401, 403), f"unauth write got {status}, want 401/403")
    return f"unauth rejected ({status})"


def _authed_write(ctx: EvalContext) -> str:
    status, body = ctx.post("/items", body={"name": ctx.nonce}, headers=_AUTH)
    ctx.expect(status in (200, 201), f"authed write got {status}, want 200/201")
    item_id = json.loads(body).get("id", "")
    ctx.expect(bool(item_id), "write returned no id")
    ctx.store["item_id"] = item_id
    ctx.track("item", item_id)  # register for nonce-scoped cleanup
    return f"wrote item {item_id}"


def _read_back(ctx: EvalContext) -> str:
    item_id = ctx.store.get("item_id", "")
    status, body = ctx.get(f"/items/{item_id}", headers=_AUTH)
    ctx.expect(status == 200, f"read-back got {status}, want 200")
    ctx.expect(json.loads(body).get("name") == ctx.nonce,
               "read-back name does not match the written nonce")
    return f"round-trip ok for {item_id}"


def _cleanup(ctx: EvalContext) -> None:
    item_id = ctx.store.get("item_id")
    if item_id:
        ctx.request("DELETE", f"/items/{item_id}", headers=_AUTH)


FLOWS = [
    Flow(
        name="authed_crud_journey",
        description="health -> auth gate -> write -> read-back (reference)",
        tags=("smoke", "auth", "crud"),
        steps=[
            Step("health", _health),
            Step("unauth_rejected", _unauth_rejected),
            Step("authed_write", _authed_write),
            Step("read_back", _read_back),
        ],
        cleanup=_cleanup,
    ),
]
