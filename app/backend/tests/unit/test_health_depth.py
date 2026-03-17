"""Health check depth — tests for status rollup, caching, breaker mapping.

Phase 1.5: DependencyStatus enum, overall health rollup, result caching,
and circuit breaker → dependency status mapping.
"""

from __future__ import annotations

import time

import pytest


class TestDependencyStatusEnum:
    """DependencyStatus enum structure."""

    def test_enum_exists(self):
        from app.foundation.resilience import DependencyStatus
        assert DependencyStatus is not None

    def test_expected_values(self):
        from app.foundation.resilience import DependencyStatus
        expected = {"up", "down", "degraded", "throttled", "not_configured"}
        actual = {e.value for e in DependencyStatus}
        assert actual == expected


class TestComputeOverallStatus:
    """_compute_overall_status() — pure function, table-driven."""

    def _compute(self, services):
        from app.routers.service_health import _compute_overall_status
        return _compute_overall_status(services)

    def test_all_up(self):
        """All services UP → healthy."""
        services = {
            "ai_foundry": {"status": "up"},
            "session_store": {"status": "up"},
            "fabric": {"status": "up"},
        }
        assert self._compute(services) == "healthy"

    def test_all_not_configured(self):
        """All services not_configured → healthy (nothing to be unhealthy about)."""
        services = {
            "fabric": {"status": "not_configured"},
            "ai_search": {"status": "not_configured"},
        }
        assert self._compute(services) == "healthy"

    def test_critical_down(self):
        """Critical service (ai_foundry) DOWN → unhealthy."""
        services = {
            "ai_foundry": {"status": "down"},
            "session_store": {"status": "up"},
        }
        assert self._compute(services) == "unhealthy"

    def test_session_store_down(self):
        """Critical service (session_store) DOWN → unhealthy."""
        services = {
            "ai_foundry": {"status": "up"},
            "session_store": {"status": "down"},
        }
        assert self._compute(services) == "unhealthy"

    def test_noncritical_down(self):
        """Non-critical service DOWN → degraded (not unhealthy)."""
        services = {
            "ai_foundry": {"status": "up"},
            "session_store": {"status": "up"},
            "fabric": {"status": "down"},
        }
        assert self._compute(services) == "degraded"

    def test_throttled(self):
        """Any service THROTTLED → degraded."""
        services = {
            "ai_foundry": {"status": "up"},
            "session_store": {"status": "up"},
            "fabric": {"status": "throttled"},
        }
        assert self._compute(services) == "degraded"

    def test_mixed_degraded_and_up(self):
        """Mix of UP and DEGRADED → degraded."""
        services = {
            "ai_foundry": {"status": "up"},
            "session_store": {"status": "up"},
            "ai_search": {"status": "degraded"},
        }
        assert self._compute(services) == "degraded"

    def test_empty_services(self):
        """No services → healthy (nothing to check)."""
        assert self._compute({}) == "healthy"


class TestBreakerToStatus:
    """_breaker_to_status() — combines live ping with circuit breaker state."""

    def _map(self, breaker_name, live_status):
        from app.routers.service_health import _breaker_to_status
        return _breaker_to_status(breaker_name, live_status)

    def test_no_breaker_connected(self):
        """No registered breaker + connected → up."""
        assert self._map("nonexistent_breaker", "connected") == "up"

    def test_no_breaker_disconnected(self):
        """No registered breaker + disconnected → down."""
        assert self._map("nonexistent_breaker", "disconnected") == "down"

    def test_no_breaker_not_configured(self):
        """No registered breaker + not_configured → not_configured."""
        assert self._map("nonexistent_breaker", "not_configured") == "not_configured"

    def test_breaker_open_overrides_connected(self):
        """Breaker OPEN → throttled, regardless of live ping."""
        from app.foundation.resilience import CircuitBreaker
        breaker = CircuitBreaker("test_open", failure_threshold=1, cooldown_secs=60)
        breaker.record_failure()  # Trip the breaker
        assert breaker.state.value == "open"

        from app.foundation.resilience import registry
        registry._breakers["test_open"] = breaker
        try:
            assert self._map("test_open", "connected") == "throttled"
        finally:
            del registry._breakers["test_open"]

    def test_breaker_closed_uses_live_status(self):
        """Breaker CLOSED → uses live ping status."""
        from app.foundation.resilience import CircuitBreaker, registry
        breaker = CircuitBreaker("test_closed")
        registry._breakers["test_closed"] = breaker
        try:
            assert self._map("test_closed", "connected") == "up"
            assert self._map("test_closed", "disconnected") == "down"
        finally:
            del registry._breakers["test_closed"]


class TestHealthCache:
    """_cached_check() — TTL-based result caching."""

    async def test_cache_hit(self):
        """Second call within TTL returns cached result."""
        from app.routers.service_health import _cached_check, _health_cache
        _health_cache.clear()

        call_count = 0
        async def check_fn():
            nonlocal call_count
            call_count += 1
            return {"status": "up"}

        result1 = await _cached_check("test_svc", check_fn)
        result2 = await _cached_check("test_svc", check_fn)

        assert result1 == result2
        assert call_count == 1  # Second call was cached
        _health_cache.clear()

    async def test_cache_miss_after_ttl(self):
        """Call after TTL expires invokes the check function again."""
        from app.routers.service_health import _cached_check, _health_cache, _CACHE_TTL_SECONDS
        _health_cache.clear()

        call_count = 0
        async def check_fn():
            nonlocal call_count
            call_count += 1
            return {"status": "up"}

        await _cached_check("test_svc2", check_fn)
        # Expire the cache by manipulating the timestamp
        _health_cache["test_svc2"] = (time.monotonic() - _CACHE_TTL_SECONDS - 1, {"status": "up"})
        await _cached_check("test_svc2", check_fn)

        assert call_count == 2
        _health_cache.clear()
