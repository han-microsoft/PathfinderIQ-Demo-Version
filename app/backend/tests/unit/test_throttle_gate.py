"""FabricThrottleGate — circuit breaker state machine."""

import pytest

from tools._fabric_throttle import (
    CircuitState,
    FabricThrottleError,
    FabricThrottleGate,
)


@pytest.mark.asyncio
async def test_starts_closed():
    """Gate initialises in CLOSED state."""
    gate = FabricThrottleGate()
    assert gate.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_opens_after_threshold_429s():
    """CLOSED → OPEN after FABRIC_CB_THRESHOLD consecutive 429 recordings."""
    gate = FabricThrottleGate()
    for _ in range(gate._breaker._failure_threshold):
        await gate.record_429()
    assert gate.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_rejects_with_error():
    """Acquiring from an OPEN gate raises FabricThrottleError."""
    gate = FabricThrottleGate()
    for _ in range(gate._breaker._failure_threshold):
        await gate.record_429()
    with pytest.raises(FabricThrottleError):
        await gate.acquire()


@pytest.mark.asyncio
async def test_success_resets_counter():
    """A successful response resets the consecutive failure counter."""
    gate = FabricThrottleGate()
    await gate.record_429()
    assert gate._breaker._consecutive_failures == 1
    await gate.record_success()
    assert gate._breaker._consecutive_failures == 0


@pytest.mark.asyncio
async def test_success_in_half_open_closes():
    """HALF_OPEN → CLOSED when a probe request succeeds."""
    gate = FabricThrottleGate()
    # Trip the circuit
    for _ in range(gate._breaker._failure_threshold):
        await gate.record_429()
    assert gate.state == CircuitState.OPEN
    # Force cooldown expired by setting open_until in the past
    import time
    gate._breaker._open_until = time.monotonic() - 1
    # Acquire triggers HALF_OPEN transition
    was_probe = await gate.acquire()
    assert gate.state == CircuitState.HALF_OPEN
    assert was_probe is True
    # Probe succeeds → CLOSED
    await gate.record_success()
    assert gate.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_status_returns_dict():
    """status() returns a dict with expected keys from generic breaker + semaphore."""
    gate = FabricThrottleGate()
    s = gate.status()
    assert "state" in s
    assert "consecutive_failures" in s
    assert "cooldown_secs" in s
    assert "semaphore_available" in s
    assert s["state"] == "closed"
