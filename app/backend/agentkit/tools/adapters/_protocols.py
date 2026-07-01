"""Adaptor protocols + shared seams.

Defines the structural contracts every datasource adaptor honours and the
small injection seams (resilience gate, projection hook) the concrete
adaptors share. Pure typing + stdlib — zero SDK imports.

Design seams (the two binding constraints):
    1. PROJECTION stays consumer-side. Every adaptor accepts an optional
       ``project`` hook (``Callable[[raw_shaped], Any]``). The adaptor shapes
       the raw transport result into a generic envelope
       (``{columns, rows}`` / ``{results, count}`` / ``{columns, data}`` /
       a bare list) and, only if the consumer supplied ``project``, calls it
       to apply the consumer's domain projection. The adaptor never embeds a
       domain projection itself.
    2. CONFIG/CREDENTIAL via INJECTED resolver. Adaptors do not read a
       consumer request scope. Endpoint / database / index / credential are
       supplied either as explicit constructor arguments or via a zero-arg
       ``resolve_target`` callable the consumer closes over its own current
       scope and the adaptor invokes at execute-time.
"""

from __future__ import annotations

from typing import Any, Awaitable, Protocol, runtime_checkable


@runtime_checkable
class DataSourceAdapter(Protocol):
    """Structural contract for a read-only datasource adaptor.

    ``execute`` runs the transport spine and returns the agent-facing result.
    Most adaptors return a JSON ``str`` (the tool's wire payload). The Fabric
    GQL adaptor is the deliberate exception: it returns the raw ``dict``
    (``{columns, data}`` / ``{error, detail}``) because its consumers each
    apply a different CIM projection before serialising — that dict return IS
    the consumer-side projection seam.
    """

    async def execute(self, query: str, /, **kwargs: Any) -> Any:
        """Run the query through the adaptor's transport spine."""
        ...

    async def is_healthy(self) -> bool:
        """Lightweight liveness probe for the backend (best-effort)."""
        ...


@runtime_checkable
class ResilienceGate(Protocol):
    """Duck-typed concurrency/circuit gate the consumer injects.

    Matches the surface of GridIQ's ``FabricThrottleGate`` (semaphore +
    circuit breaker) so an adaptor can acquire/release a slot and report
    success / 429 / server-error outcomes without importing the consumer's
    gate implementation. Adaptors that do not need a gate simply skip it.
    """

    async def acquire(self) -> bool:  # returns True for a half-open probe
        ...

    def release(self, *, _was_probe: bool = False) -> None:
        ...

    async def record_success(self) -> None:
        ...

    async def record_429(self) -> None:
        ...

    async def record_server_error(self) -> None:
        ...
