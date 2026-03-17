"""CircuitBreaker — generic circuit breaker state machine tests.

Tests written BEFORE implementation (TDD). Each test validates a specific
state transition or API contract from the plan in PLAN_CIRCUIT_BREAKER.md.

The tests exercise:
    - State lifecycle: CLOSED → OPEN → HALF_OPEN → CLOSED
    - Failure threshold tripping
    - Success resetting
    - Cooldown expiry and probe semantics
    - Exponential backoff with cap
    - Force reset
    - Status dict contract
    - Registry idempotency and bulk operations
    - Thread safety under concurrent access
"""

import threading
import time

import pytest

from app.foundation.resilience import CircuitBreaker, CircuitBreakerRegistry, CircuitState, registry


# ── CircuitBreaker state transitions ─────────────────────────────────────────


class TestCircuitBreakerLifecycle:
    """Validates the Closed → Open → Half-Open → Closed state machine."""

    def test_starts_closed(self):
        """New breaker initialises in CLOSED state with is_open() == False."""
        cb = CircuitBreaker("test_closed", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.is_open() is False

    def test_opens_after_threshold_failures(self):
        """CLOSED → OPEN after failure_threshold consecutive failures."""
        cb = CircuitBreaker("test_open", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # Not yet
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_open() is True

    def test_success_resets_failure_counter(self):
        """A success in CLOSED state resets the failure counter to 0."""
        cb = CircuitBreaker("test_reset", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb._consecutive_failures == 2
        cb.record_success()
        assert cb._consecutive_failures == 0
        assert cb.state == CircuitState.CLOSED

    def test_open_transitions_to_half_open_after_cooldown(self):
        """OPEN → HALF_OPEN when cooldown expires, signalled by is_open()."""
        cb = CircuitBreaker("test_half", failure_threshold=1, cooldown_secs=0.01)
        cb.record_failure()  # Trip to OPEN
        assert cb.state == CircuitState.OPEN
        assert cb.is_open() is True
        # Wait for cooldown to expire
        time.sleep(0.02)
        # is_open() should transition to HALF_OPEN and return False (probe allowed)
        assert cb.is_open() is False
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        """HALF_OPEN + record_success() → CLOSED with cooldown reset."""
        cb = CircuitBreaker("test_close", failure_threshold=1, cooldown_secs=0.01)
        cb.record_failure()  # → OPEN
        time.sleep(0.02)
        cb.is_open()  # → HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb._consecutive_failures == 0
        # Cooldown should be reset to base value
        assert cb._current_cooldown == cb._base_cooldown

    def test_half_open_failure_reopens_with_doubled_cooldown(self):
        """HALF_OPEN + record_failure() → OPEN with doubled cooldown."""
        base_cooldown = 10.0
        cb = CircuitBreaker(
            "test_reopen", failure_threshold=1,
            cooldown_secs=base_cooldown, max_cooldown_secs=300.0,
        )
        cb.record_failure()  # → OPEN
        # Force cooldown expired
        cb._open_until = time.monotonic() - 1
        cb.is_open()  # → HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()  # → OPEN again
        assert cb.state == CircuitState.OPEN
        assert cb._current_cooldown == base_cooldown * 2

    def test_cooldown_caps_at_max(self):
        """Repeated half-open failures cap cooldown at max_cooldown_secs."""
        cb = CircuitBreaker(
            "test_cap", failure_threshold=1,
            cooldown_secs=100.0, max_cooldown_secs=200.0,
        )
        cb.record_failure()  # → OPEN, cooldown=100
        # First half-open failure: cooldown doubles to 200
        cb._open_until = time.monotonic() - 1
        cb.is_open()  # → HALF_OPEN
        cb.record_failure()  # → OPEN, cooldown=200
        assert cb._current_cooldown == 200.0
        # Second half-open failure: cooldown would be 400 but caps at 200
        cb._open_until = time.monotonic() - 1
        cb.is_open()  # → HALF_OPEN
        cb.record_failure()  # → OPEN, cooldown capped at 200
        assert cb._current_cooldown == 200.0

    def test_reset_forces_closed(self):
        """reset() returns breaker to CLOSED regardless of current state."""
        cb = CircuitBreaker("test_force", failure_threshold=1)
        cb.record_failure()  # → OPEN
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._consecutive_failures == 0
        assert cb.is_open() is False

    def test_only_first_caller_after_cooldown_gets_probe(self):
        """After OPEN → HALF_OPEN, subsequent is_open() calls return True
        until the probe resolves (preventing multiple probes)."""
        cb = CircuitBreaker("test_probe", failure_threshold=1, cooldown_secs=0.01)
        cb.record_failure()  # → OPEN
        time.sleep(0.02)
        # First call transitions to HALF_OPEN and allows probe
        assert cb.is_open() is False
        assert cb.state == CircuitState.HALF_OPEN
        # Second call should return True — probe already in flight
        assert cb.is_open() is True


# ── Status dict contract ────────────────────────────────────────────────────


class TestCircuitBreakerStatus:
    """Validates the status() dict shape for health endpoints."""

    def test_status_returns_expected_keys(self):
        """status() dict contains all documented keys."""
        cb = CircuitBreaker("test_status", failure_threshold=5, cooldown_secs=30)
        s = cb.status()
        assert s["name"] == "test_status"
        assert s["state"] == "closed"
        assert s["consecutive_failures"] == 0
        assert s["cooldown_secs"] == 30.0
        assert s["failure_threshold"] == 5
        assert s["seconds_until_probe"] is None

    def test_status_shows_seconds_until_probe_when_open(self):
        """When OPEN, seconds_until_probe is a positive float."""
        cb = CircuitBreaker("test_probe_time", failure_threshold=1, cooldown_secs=60)
        cb.record_failure()
        s = cb.status()
        assert s["state"] == "open"
        assert s["seconds_until_probe"] is not None
        assert s["seconds_until_probe"] > 0


# ── Registry ────────────────────────────────────────────────────────────────


class TestCircuitBreakerRegistry:
    """Validates registry idempotency and bulk operations."""

    def test_get_or_create_idempotent(self):
        """Same name returns same instance, ignoring kwargs on second call."""
        reg = CircuitBreakerRegistry()
        cb1 = reg.get_or_create("svc_a", failure_threshold=3)
        cb2 = reg.get_or_create("svc_a", failure_threshold=99)
        assert cb1 is cb2
        assert cb1._failure_threshold == 3  # First caller wins

    def test_get_returns_existing(self):
        """get() returns existing breaker or None."""
        reg = CircuitBreakerRegistry()
        assert reg.get("nonexistent") is None
        reg.get_or_create("exists")
        assert reg.get("exists") is not None

    def test_all_statuses(self):
        """all_statuses() returns dict keyed by breaker name."""
        reg = CircuitBreakerRegistry()
        reg.get_or_create("alpha")
        reg.get_or_create("beta")
        statuses = reg.all_statuses()
        assert "alpha" in statuses
        assert "beta" in statuses
        assert statuses["alpha"]["state"] == "closed"

    def test_reset_all(self):
        """reset_all() returns all breakers to CLOSED."""
        reg = CircuitBreakerRegistry()
        cb = reg.get_or_create("tripped", failure_threshold=1)
        cb.record_failure()  # → OPEN
        assert cb.state == CircuitState.OPEN
        reg.reset_all()
        assert cb.state == CircuitState.CLOSED

    def test_module_level_registry_exists(self):
        """Module-level singleton ``registry`` is importable and functional."""
        assert registry is not None
        # Should be able to create breakers on it
        cb = registry.get_or_create("module_test")
        assert cb.name == "module_test"
        # Clean up — don't pollute other tests
        cb.reset()


# ── Thread safety ────────────────────────────────────────────────────────────


class TestCircuitBreakerThreadSafety:
    """Validates that concurrent access doesn't corrupt state."""

    def test_concurrent_failures_count_correctly(self):
        """100 threads recording failures — counter reaches exactly 100."""
        cb = CircuitBreaker("test_threads", failure_threshold=200)
        barrier = threading.Barrier(100)

        def worker():
            barrier.wait()
            cb.record_failure()

        threads = [threading.Thread(target=worker) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert cb._consecutive_failures == 100

    def test_concurrent_mixed_operations(self):
        """50 failures + 50 successes concurrently — no crash, valid state."""
        cb = CircuitBreaker("test_mixed", failure_threshold=200)
        barrier = threading.Barrier(100)

        def fail_worker():
            barrier.wait()
            cb.record_failure()

        def success_worker():
            barrier.wait()
            cb.record_success()

        threads = (
            [threading.Thread(target=fail_worker) for _ in range(50)]
            + [threading.Thread(target=success_worker) for _ in range(50)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # State must be valid — either CLOSED or OPEN, not corrupted
        assert cb.state in (CircuitState.CLOSED, CircuitState.OPEN)
        assert cb._consecutive_failures >= 0
