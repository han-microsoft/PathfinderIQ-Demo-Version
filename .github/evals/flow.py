"""flow — the eval flow contract. One home for what an eval IS.

An eval flow is a NAMED, TAGGED user-journey that mirrors one expected UX flow on
the live deploy. It runs as a chain of atomic steps, each gated on the prior, each
emitting one digest line. A flow that cannot fail is broken (P7): every flow
exercises at least one falsifiable assertion against the live target.

Stack assumption: Python/Azure. The HTTP helpers use stdlib urllib (zero-dep) and
hit the live target resolved from PROJECT.md §1. Synthetic data only; every
created artefact carries the run nonce and is cleaned up (Ownership And Deletion
Law, regression_protocol.md).

Layer rule: stdlib only.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class StepFailed(Exception):
    """Raised by a step when its assertion does not hold — fails the flow."""


@dataclass
class EvalContext:
    """Per-run state handed to every step. Carries target, nonce, cleanup list."""

    live_target: str
    nonce: str
    timeout_s: float = 15.0
    created: list[tuple[str, str]] = field(default_factory=list)  # (kind, id)
    store: dict[str, Any] = field(default_factory=dict)           # step-to-step data

    # ── HTTP helpers (stdlib urllib; live target is PROJECT.md §1) ──────────

    def request(self, method: str, path: str, *, body: dict | None = None,
                headers: dict | None = None) -> tuple[int, str]:
        """One HTTP call to the live target. Returns (status, text). Never raises
        on a non-2xx — returns the status so a step can assert on it."""
        url = path if path.startswith("http") else self.live_target.rstrip("/") + path
        data = json.dumps(body).encode() if body is not None else None
        hdrs = {"content-type": "application/json", **(headers or {})}
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            raise StepFailed(f"transport error to {url}: {e.reason}") from e

    def get(self, path: str, **kw) -> tuple[int, str]:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw) -> tuple[int, str]:
        return self.request("POST", path, **kw)

    def track(self, kind: str, ident: str) -> None:
        """Register a created artefact for nonce-scoped cleanup."""
        self.created.append((kind, ident))

    def expect(self, condition: bool, msg: str) -> None:
        """Assert inside a step. Falsifiable — the negative path P7 requires."""
        if not condition:
            raise StepFailed(msg)


@dataclass
class Step:
    """One atomic, gated check. `run` returns a digest string or raises StepFailed."""

    name: str
    run: Callable[[EvalContext], str]


@dataclass
class Flow:
    """A named, tagged user-journey mirrored on the live deploy.

    setup/cleanup are optional; cleanup ALWAYS runs (pass or fail) so nonce-owned
    synthetic artefacts never leak. Tags drive selective runs (`eval run --tag X`).
    """

    name: str
    description: str
    tags: tuple[str, ...] = ()
    steps: list[Step] = field(default_factory=list)
    setup: Callable[[EvalContext], None] | None = None
    cleanup: Callable[[EvalContext], None] | None = None


@dataclass
class StepResult:
    name: str
    ok: bool
    digest: str
    wall_ms: int


@dataclass
class FlowResult:
    name: str
    ok: bool
    steps: list[StepResult]
    cleanup_ok: bool
    retained: list[tuple[str, str]]
    wall_ms: int


def run_flow(flow: Flow, ctx: EvalContext) -> FlowResult:
    """Execute a flow: setup -> gated steps -> cleanup (always). One digest/step."""
    t0 = time.monotonic()
    results: list[StepResult] = []
    ok = True
    try:
        if flow.setup is not None:
            flow.setup(ctx)
        for step in flow.steps:
            s0 = time.monotonic()
            try:
                digest = step.run(ctx)
                results.append(StepResult(step.name, True, digest or "ok",
                                          int((time.monotonic() - s0) * 1000)))
            except StepFailed as e:
                results.append(StepResult(step.name, False, str(e),
                                          int((time.monotonic() - s0) * 1000)))
                ok = False
                break  # gate: stop at first failed step
            except Exception as e:  # noqa: BLE001 — surface any step crash as fail
                results.append(StepResult(step.name, False, f"crash: {e}",
                                          int((time.monotonic() - s0) * 1000)))
                ok = False
                break
    finally:
        cleanup_ok = True
        if flow.cleanup is not None:
            try:
                flow.cleanup(ctx)
            except Exception:  # noqa: BLE001 — cleanup failure is reported, not raised
                cleanup_ok = False
    return FlowResult(flow.name, ok, results, cleanup_ok, list(ctx.created),
                      int((time.monotonic() - t0) * 1000))


__all__ = ["Flow", "Step", "EvalContext", "StepFailed", "StepResult",
           "FlowResult", "run_flow"]
