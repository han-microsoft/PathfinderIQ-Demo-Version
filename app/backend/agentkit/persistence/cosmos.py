"""agentkit.persistence.cosmos — Cosmos-backed store base (asyncio-fixed).

Module role:
    Domain-blind base class for Azure Cosmos DB NoSQL stores. Owns the shared
    plumbing every Cosmos-backed store needs — a circuit breaker, an async
    lock, the breaker-helper trio (``_check_breaker`` / ``_ok`` / ``_fail``),
    the bounded ``is_healthy`` probe, breaker registration, and lifecycle
    ``close``. Concrete stores (session / audit / evaluation in the consumer)
    subclass this and contribute only their domain-specific Cosmos calls
    (``create_item``, ``query_items``, ``patch_item``, ...).

Extra:
    ``[cosmos]`` — the concrete Cosmos *client* (``azure-cosmos``) is supplied
    by the consumer and **injected** into ``__init__`` as ``client`` +
    ``container``. This base therefore imports **no** azure package: it is
    pure stdlib + ``agentkit.resilience``. A consumer that wires an in-memory
    or test double satisfying the same duck-typed surface (``query_items``,
    ``close``) can reuse the breaker + health machinery without azure at all.

Layer rule:
    Imports ``agentkit.resilience`` only. Never imports a consumer package.

B-COSMOS-ASYNCIO (baked into the base):
    ``is_healthy`` wraps the probe query in ``asyncio.timeout(...)``. The
    ``import asyncio`` below is therefore **load-bearing** — if it were
    missing, the bare ``except Exception: return False`` in ``is_healthy``
    would silently swallow the resulting ``NameError`` and pin every consumer
    on its in-memory fallback forever (the store would never upgrade to
    Cosmos). The ``tests/`` regression for this lives consumer-side
    (``test_cosmos_store_is_healthy_regression.py``). Keeping the asyncio
    dependency in this one base file means the gotcha cannot recur per
    subclass.
"""

from __future__ import annotations

import asyncio  # noqa: F401  (load-bearing — see B-COSMOS-ASYNCIO in docstring)
import logging
from typing import Any

from agentkit.resilience import CircuitBreaker, CircuitBreakerRegistry

logger = logging.getLogger(__name__)


class CosmosStoreUnavailable(RuntimeError):
    """Raised when a Cosmos-backed store's circuit breaker is open.

    Domain stores subclass this to get a stable, dispatchable type::

        class SessionStoreUnavailable(CosmosStoreUnavailable):
            pass

    Routers continue to catch the domain-specific subclass; this base class
    lets shared code (the container store, logging middleware) handle every
    store-unavailable case uniformly. Inherits ``RuntimeError`` rather than
    bare ``Exception`` because that is the convention the consumer stores
    already use.
    """


class CosmosContainerStore:
    """Base class for Cosmos-backed RBAC stores.

    The credential + Cosmos client are **injected** (constructed by the
    consumer's composition root / shim and passed in) so this base stays
    azure-free and unit-testable. Subclasses contribute their domain-specific
    Cosmos calls and a :class:`CosmosStoreUnavailable` subclass (via
    ``unavailable_exc``) so the breaker helpers raise a type the consuming
    router can dispatch on.

    Subclasses MUST NOT:
        - Re-implement ``_check_breaker`` / ``_ok`` / ``_fail`` / ``is_healthy``.
        - Close the injected credential. ``close()`` tears down the Cosmos
          client only; the credential is a process-lifetime singleton owned
          by the consumer.
    """

    def __init__(
        self,
        *,
        client: Any,
        container: Any,
        breaker_name: str,
        unavailable_exc: type[CosmosStoreUnavailable],
        failure_threshold: int = 3,
        cooldown_secs: float = 30.0,
    ) -> None:
        """Wire up the breaker + lock around an injected Cosmos client/container.

        Args:
            client: An async Cosmos client (``azure.cosmos.aio.CosmosClient``
                or a compatible double). Held only so ``close()`` can release
                it; never re-resolved here.
            container: The async container client the subclass issues calls
                against (``query_items`` / ``create_item`` / ``patch_item``).
            breaker_name: Identifier registered with the resilience registry —
                used by the consumer to surface the breaker on its readiness
                endpoint.
            unavailable_exc: Concrete ``CosmosStoreUnavailable`` subclass to
                raise from the breaker helpers.
            failure_threshold: Consecutive failures before the breaker trips
                (default 3).
            cooldown_secs: Initial cooldown after the breaker opens
                (default 30 — Cosmos outages are usually transient failovers).
        """
        self._client = client
        self._container = container
        # Per-instance breaker (not registry-managed) for test isolation. The
        # consumer registers it into the shared registry via
        # ``register_breaker`` after construction.
        self._breaker = CircuitBreaker(
            breaker_name,
            failure_threshold=failure_threshold,
            cooldown_secs=cooldown_secs,
        )
        # Serialises multi-step operations for subclasses that need it.
        self._lock = asyncio.Lock()
        self._unavailable_exc = unavailable_exc

    # ── Circuit breaker helpers ──────────────────────────────────────

    def _check_breaker(self) -> None:
        """Raise the domain ``CosmosStoreUnavailable`` if the breaker is open."""
        if self._breaker.is_open():
            raise self._unavailable_exc("Cosmos store temporarily unavailable")

    def _ok(self) -> None:
        """Record a successful Cosmos operation on the breaker."""
        self._breaker.record_success()

    def _fail(self, exc: Exception) -> CosmosStoreUnavailable:
        """Record a Cosmos failure on the breaker and wrap the SDK exception.

        Returns the wrapper rather than raising it so call sites can
        ``raise self._fail(exc)`` and keep the chained ``__cause__`` link to
        the underlying SDK exception.
        """
        self._breaker.record_failure()
        err = self._unavailable_exc("Cosmos store temporarily unavailable")
        err.__cause__ = exc
        return err

    # ── Lifecycle ────────────────────────────────────────────────────

    async def is_healthy(self, timeout: float = 2.0) -> bool:
        """Probe the Cosmos container — validates connectivity + auth + RU.

        Runs a bounded ``SELECT TOP 1`` against the container inside an
        ``asyncio.timeout`` so the SDK's default retry policy (9 retries,
        30 s max) cannot block startup or a readiness probe.

        Args:
            timeout: Maximum seconds to wait for the probe query. Default 2.0;
                callers (warmup) may pass higher during cold-start.

        Returns:
            True if the container responds within ``timeout``; False otherwise.
            Returning False (not raising) is intentional so a consumer's
            warmup can transparently fall back to an in-memory store.

        Side effects:
            Logs a warning on timeout to distinguish "slow" from "firewalled".
            All other exceptions are swallowed by design — but see
            B-COSMOS-ASYNCIO in the module docstring: the swallow must never
            mask a missing-import ``NameError``.
        """
        try:
            async with asyncio.timeout(timeout):
                async for _ in self._container.query_items(
                    query="SELECT TOP 1 c.id FROM c", parameters=[]
                ):
                    break
            return True
        except TimeoutError:
            logger.warning(
                "cosmos.health_check.timeout",
                extra={"breaker": self._breaker.name, "timeout_s": timeout},
            )
            return False
        except Exception:
            return False

    def register_breaker(self, registry: CircuitBreakerRegistry) -> None:
        """Publish this store's per-instance breaker into a registry.

        Per-instance breakers are kept off the global registry so tests can
        build isolated stores without leaking state. Production wiring calls
        this once after construction so the health/readiness surface can
        report the breaker state.
        """
        registry.register(self._breaker)

    async def close(self) -> None:
        """Close the injected Cosmos client. Does NOT close the credential.

        The credential is owned by the consumer (a cached process-lifetime
        singleton); closing it here would break every other consumer in the
        process. The credential's lifetime is the process lifetime.
        """
        await self._client.close()


__all__ = ["CosmosContainerStore", "CosmosStoreUnavailable"]
