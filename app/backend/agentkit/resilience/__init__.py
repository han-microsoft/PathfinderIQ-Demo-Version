"""Centralized circuit breaker — generic resilience primitive.

Module role:
    Provides a reusable ``CircuitBreaker`` class and a ``CircuitBreakerRegistry``
    singleton for centralized access and health reporting. Implements the Azure
    Architecture Circuit Breaker pattern:
      Closed → Open → Half-Open → Closed

    This module owns ONLY the state machine. It does NOT own:
      - Retry logic (caller's responsibility)
      - Fallback behavior (caller decides what to return when open)
      - Concurrency control (separate concern — see ``_fabric_throttle.py``)

    Each external dependency registers its own breaker via
    ``registry.get_or_create(name, **kwargs)`` at import time. The registry
    provides ``all_statuses()`` for the ``/api/services/health`` endpoint.

Key collaborators:
    - ``tools/_fabric/throttle.py``           — composes CircuitBreaker + asyncio.Semaphore
    - ``tools/search/_aisearch/client.py``    — breaker for AI Search
    - ``foundation/cosmos_store.py``          — breaker for every Cosmos NoSQL store
    - ``hosting/fastapi/session/cosmos.py``   — session store subclass
    - ``hosting/fastapi/health/service_health.py`` — reads ``registry.all_statuses()``

Dependents:
    Any module that makes external service calls.

Thread safety:
    Uses ``threading.Lock`` (not ``asyncio.Lock``) because:
    - State transitions are pure CPU (counter increment + timestamp compare)
    - Must work from both sync (asyncio.to_thread) and async contexts
    - No await points inside the lock — no risk of deadlock
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Three-state circuit breaker lifecycle.

    CLOSED:    Normal operation — all calls allowed through.
    OPEN:      Tripped — all calls rejected immediately (fail fast).
    HALF_OPEN: Probing — one call allowed to test if the service recovered.
    """
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class DependencyStatus(str, Enum):
    """Unified dependency health status for /api/services/health.

    Maps live ping results + circuit breaker state to a single status
    that operators and dashboards can interpret uniformly.

    UP:             Healthy, responding normally.
    DOWN:           Unreachable or failing.
    DEGRADED:       Responding but with errors or slowness.
    THROTTLED:      Rate-limited or circuit breaker is OPEN.
    NOT_CONFIGURED: Not enabled for this deployment.
    """
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    THROTTLED = "throttled"
    NOT_CONFIGURED = "not_configured"


class CircuitBreaker:
    """Generic circuit breaker — thread-safe, sync + async compatible.

    State machine:
        CLOSED:    Consecutive failures counted. Threshold reached → OPEN.
        OPEN:      All ``is_open()`` calls return True. After cooldown → HALF_OPEN.
        HALF_OPEN: First ``is_open()`` returns False (probe allowed).
                   Subsequent calls return True until probe resolves.
                   Success → CLOSED (reset). Failure → OPEN (doubled cooldown).

    Usage pattern (at call sites)::

        if breaker.is_open():
            return degraded_response()
        try:
            result = call_external_service()
            breaker.record_success()
            return result
        except Exception:
            breaker.record_failure()
            return error_response()

    Parameters:
        name:              Identifier for logging and registry lookup.
        failure_threshold: Consecutive failures before tripping (default: 3).
        cooldown_secs:     Initial cooldown in OPEN state (default: 60).
        max_cooldown_secs: Cooldown cap after exponential backoff (default: 300).

    Lifecycle:
        Created once per service via ``registry.get_or_create()``.
        Lives for the process lifetime. Not destroyed or recycled.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_secs: float = 60.0,
        max_cooldown_secs: float = 300.0,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._base_cooldown = cooldown_secs
        self._max_cooldown = max_cooldown_secs

        # Mutable state — all protected by self._lock
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._open_until = 0.0                # monotonic timestamp when OPEN expires
        self._current_cooldown = cooldown_secs # current cooldown (doubles on half-open failure)
        self._probe_allowed = True             # False after first probe caller in HALF_OPEN

        # threading.Lock — not asyncio.Lock — because state transitions are
        # pure CPU work (counter + timestamp) and must work from sync contexts
        # (e.g., tools running in asyncio.to_thread)
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        """Breaker identifier — used in logging and registry keys."""
        return self._name

    @property
    def state(self) -> CircuitState:
        """Current state — CLOSED, OPEN, or HALF_OPEN."""
        return self._state

    def is_open(self) -> bool:
        """Check if the breaker is open (calls should be rejected).

        Returns:
            True  — reject the call (breaker is OPEN or HALF_OPEN with probe in flight).
            False — allow the call (breaker is CLOSED or this is the probe in HALF_OPEN).

        Side effects:
            - OPEN → HALF_OPEN transition when cooldown expires.
            - Sets ``_probe_allowed = False`` when granting the probe.

        Thread safety:
            Acquires ``self._lock`` for the duration of the check.
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return False

            if self._state == CircuitState.OPEN:
                # Check if cooldown has expired — transition to HALF_OPEN
                if time.monotonic() >= self._open_until:
                    self._state = CircuitState.HALF_OPEN
                    self._probe_allowed = True  # Allow one probe caller
                    logger.info(
                        "circuit_breaker.transition",
                        extra={
                            "breaker": self._name,
                            "from": "open",
                            "to": "half_open",
                            "cooldown_s": self._current_cooldown,
                        },
                    )
                    # Fall through to HALF_OPEN check below
                else:
                    return True  # Still in cooldown — reject

            # HALF_OPEN: allow exactly one probe caller
            if self._state == CircuitState.HALF_OPEN:
                if self._probe_allowed:
                    self._probe_allowed = False  # Subsequent callers rejected
                    return False  # Probe allowed
                return True  # Probe already in flight — reject

            return True  # Defensive fallback — should not reach here

    def record_success(self) -> None:
        """Record a successful external call.

        Effects:
            CLOSED:    Resets consecutive failure counter to 0.
            HALF_OPEN: Transitions to CLOSED. Resets cooldown to base value.
            OPEN:      No-op (calls are rejected when OPEN).
        """
        with self._lock:
            self._consecutive_failures = 0

            if self._state == CircuitState.HALF_OPEN:
                # Probe succeeded — service is back, close the breaker
                self._state = CircuitState.CLOSED
                self._current_cooldown = self._base_cooldown
                logger.info(
                    "circuit_breaker.transition",
                    extra={
                        "breaker": self._name,
                        "from": "half_open",
                        "to": "closed",
                        "cooldown_s": self._base_cooldown,
                    },
                )

    def record_failure(self) -> None:
        """Record a failed external call.

        Effects:
            CLOSED:    Increments failure counter. If >= threshold → OPEN.
            HALF_OPEN: Transitions to OPEN with doubled cooldown (capped).
            OPEN:      No-op (calls are rejected when OPEN).
        """
        with self._lock:
            self._consecutive_failures += 1

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — service still down, reopen with backoff
                self._current_cooldown = min(
                    self._current_cooldown * 2, self._max_cooldown
                )
                self._open_until = time.monotonic() + self._current_cooldown
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker.transition",
                    extra={
                        "breaker": self._name,
                        "from": "half_open",
                        "to": "open",
                        "consecutive_failures": self._consecutive_failures,
                        "cooldown_s": self._current_cooldown,
                        "reason": "probe_failed",
                    },
                )

            elif (
                self._state == CircuitState.CLOSED
                and self._consecutive_failures >= self._failure_threshold
            ):
                # Threshold reached — trip the breaker
                self._open_until = time.monotonic() + self._current_cooldown
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker.transition",
                    extra={
                        "breaker": self._name,
                        "from": "closed",
                        "to": "open",
                        "consecutive_failures": self._consecutive_failures,
                        "cooldown_s": self._current_cooldown,
                        "reason": "threshold_reached",
                    },
                )

    def reset(self) -> None:
        """Force-reset to CLOSED state. For testing and manual recovery.

        Resets all counters and cooldown to base values.
        """
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._open_until = 0.0
            self._current_cooldown = self._base_cooldown
            self._probe_allowed = True

    def status(self) -> dict:
        """Return diagnostic dict for health endpoints.

        Returns:
            Dict with keys: name, state, consecutive_failures, cooldown_secs,
            failure_threshold, seconds_until_probe. The seconds_until_probe
            field is None when not in OPEN state, otherwise a positive float
            indicating seconds until the next probe attempt.
        """
        with self._lock:
            seconds_until_probe = None
            if self._state == CircuitState.OPEN:
                remaining = self._open_until - time.monotonic()
                seconds_until_probe = round(max(0.0, remaining), 1)

            return {
                "name": self._name,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "cooldown_secs": self._current_cooldown,
                "failure_threshold": self._failure_threshold,
                "seconds_until_probe": seconds_until_probe,
            }


class CircuitBreakerRegistry:
    """Named breaker collection — ``get_or_create()`` is idempotent.

    Thread-safe. Designed for module-level singleton usage::

        from agentkit.resilience import registry
        my_breaker = registry.get_or_create("my_service", failure_threshold=5)

    If ``get_or_create()`` is called twice with the same name, returns the
    existing instance (ignores kwargs on second call — first caller wins).

    Lifecycle:
        Created once at module level (``registry = CircuitBreakerRegistry()``).
        Lives for the process lifetime. Breakers are never removed.

    Dependents:
        - ``hosting/fastapi/health/service_health.py`` reads ``all_statuses()``
        - Each service module calls ``get_or_create()`` at import time
    """

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_or_create(self, name: str, **kwargs) -> CircuitBreaker:
        """Return existing breaker by name, or create one with given kwargs.

        First caller's kwargs win — subsequent calls with the same name
        return the existing instance regardless of kwargs. This is safe
        because each service should register its breaker exactly once.

        Args:
            name:   Unique identifier (e.g., "fabric", "ai_search", "cosmos_sessions").
            kwargs: Forwarded to ``CircuitBreaker.__init__`` on first call only.
                    Supports: failure_threshold, cooldown_secs, max_cooldown_secs.

        Returns:
            The CircuitBreaker instance for the given name.
        """
        if name in self._breakers:
            return self._breakers[name]
        with self._lock:
            # Double-checked locking — another thread may have created it
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, **kwargs)
            return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        """Return existing breaker by name, or None if not registered."""
        return self._breakers.get(name)

    def register(self, breaker: CircuitBreaker) -> None:
        """Publish an externally-constructed breaker under its own name.

        Used by per-instance breakers — every ``CosmosContainerStore``
        builds its own ``CircuitBreaker`` so unit tests can isolate
        breaker state, and the composition root calls
        ``store.register_breaker(registry)`` (R2 — inquisitor audit
        2026-05-23 session_cosmos) which dispatches here. Replaces the
        prior private-dict write ``registry._breakers[name] = breaker``
        that leaked the storage shape across module boundaries.

        Idempotent — re-registering the same breaker instance is a
        no-op; re-registering a different instance under the same name
        overwrites (matches the prior ``registry._breakers[name] = ...``
        semantics that warmup relied on).

        Args:
            breaker: The :class:`CircuitBreaker` instance to publish.
                Registered under ``breaker.name``.
        """
        with self._lock:
            self._breakers[breaker.name] = breaker

    def all_statuses(self) -> dict[str, dict]:
        """Return status dicts for all registered breakers.

        Returns:
            Dict keyed by breaker name, values are ``CircuitBreaker.status()`` dicts.
        """
        return {name: cb.status() for name, cb in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all breakers to CLOSED. For testing only."""
        for cb in self._breakers.values():
            cb.reset()


# ── Module-level singleton ───────────────────────────────────────────────────
# Import and use: ``from agentkit.resilience import registry``
registry = CircuitBreakerRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# LLM-streaming retry helpers (R3 — inquisitor audit 2026-05-17 tools;
# R3 — inquisitor audit 2026-05-23 agent_runtime).
#
# These helpers used to live in ``agent/_retry.py`` (after the 2026-05-16
# foundation R3 moved them out of this file). The 2026-05-17 tools R3
# audit reversed that decision because ``tools/delegation`` must run a
# retry loop and ``tools/`` cannot import from ``agent/`` (layering
# rule). The 2026-05-23 agent_runtime R3 audit folded the remaining
# ``get_model_fallback_queue`` helper down here too so the shim could be
# deleted outright — every consumer (hosting runtime, tools.delegation,
# unit tests) now imports from ``foundation.resilience`` directly.
# ─────────────────────────────────────────────────────────────────────────────

import re as _re  # local alias — keep `re` out of the breaker namespace docs

_RATE_LIMIT_PATTERNS = ("429", "rate limit", "retry after", "throttl", "token rate limit")
_FATAL_PATTERNS = ("content_filter", "content management policy", "unauthorized", "forbidden")
_TRANSIENT_PATTERNS = (
    "sorry, something went wrong",
    "internal server error",
    "502", "503", "504",
    "service unavailable",
    "gateway timeout",
)


def is_rate_limit(exc: Exception) -> bool:
    """Detect rate-limit errors from exception text."""
    err_str = str(exc).lower()
    return any(p in err_str for p in _RATE_LIMIT_PATTERNS)


def is_fatal(exc: Exception) -> bool:
    """Detect fatal errors that should never be retried (content filter, auth)."""
    err_str = str(exc).lower()
    return any(p in err_str for p in _FATAL_PATTERNS)


def is_transient(exc: Exception) -> bool:
    """Detect transient server errors that may succeed on retry."""
    err_str = str(exc).lower()
    return any(p in err_str for p in _TRANSIENT_PATTERNS)


def parse_retry_seconds(error_text: str, default: int = 15) -> int:
    """Extract retry-after seconds from error message. Clamps to [5, 60]."""
    text = error_text.lower()
    match = _re.search(r"retry\s*(?:after|in)\s*(\d+)", text)
    if not match:
        match = _re.search(r"(\d+)\s*second", text)
    if match:
        val = int(match.group(1))
        return max(5, min(60, val))
    return default


def should_retry(exc: Exception, attempt: int, max_retries: int) -> tuple[bool, float]:
    """Determine whether to retry and how long to wait.

    Decision logic:
        1. Fatal error (content filter, auth) → never retry
        2. Attempts exhausted → don't retry
        3. Rate limit → retry with parsed retry-after
        4. Transient or unknown error → retry with exponential backoff
    """
    if is_fatal(exc):
        return False, 0.0
    if attempt >= max_retries - 1:
        return False, 0.0
    if is_rate_limit(exc):
        return True, float(parse_retry_seconds(str(exc)))
    # Exponential backoff capped at 30 s. Used for both transient and unknown.
    return True, float(min(2 ** attempt * 2, 30))


def log_retry(
    context: str,
    attempt: int,
    max_retries: int,
    exc: Exception,
    sleep_secs: float,
    model: str = "",
) -> None:
    """Structured log for retry attempts.

    Emits at WARNING level with the classified error type so observability
    pipelines can split rate-limit retries from transient retries from
    unknown retries.
    """
    error_type = (
        "rate_limit" if is_rate_limit(exc)
        else "transient" if is_transient(exc)
        else "unknown"
    )
    logger.warning(
        "retry: context=%s, attempt=%d/%d, type=%s, sleep=%.1fs, model=%s, error=%s",
        context, attempt + 1, max_retries, error_type, sleep_secs, model or "default",
        str(exc)[:200],
    )


def get_model_fallback_queue() -> list[str]:
    """Return the ordered list of LLM deployments to try.

    Reads the primary deployment from
    ``settings.azure_openai_responses_deployment_name`` (falling back to
    ``settings.llm_model``), then appends ``settings.llm_fallback_models``.
    All values resolve through the single Settings entry point — no direct
    env reads (R1 / R3 inquisitor audit 2026-05-16 foundation).

    Lives in ``agentkit.resilience`` so both the hosting-layer
    agent runtime and ``tools.delegation`` reach it through one layer-clean
    import. Reads the process-wide settings via
    ``agentkit.config.get_settings()`` (registered by the
    composition root) so agentkit never imports a consumer package.
    """
    from agentkit.config import get_settings
    settings = get_settings()

    primary = (
        settings.azure_openai_responses_deployment_name
        or settings.llm_model
        or "gpt-5.2"
    )
    fallbacks = [m for m in (settings.llm_fallback_models or []) if m]
    return [primary] + fallbacks

