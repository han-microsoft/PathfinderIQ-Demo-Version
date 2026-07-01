#!/usr/bin/env python3
"""circuit_breaker — resilience as a pure state machine. Standalone, self-proving.

Reference exemplar (PATTERNS.md §2). Lifted from a production agentkit where two
teams independently converged on this exact shape. The breaker owns ONLY the
Closed -> Open -> Half-Open lifecycle. Retry, fallback, and concurrency are the
caller's concern — kept out so the primitive stays a reusable leaf (P2).

What good looks like:
    - one concern: the state transitions, nothing else;
    - thread-safe via a plain lock (no await inside) -> works sync AND async;
    - fails fast + loud when open; the caller decides the fallback;
    - removable without breaking anything (optional leaf).

Call-site shape:
    if breaker.is_open():
        return degraded_response()
    try:
        r = call_external(); breaker.record_success(); return r
    except Exception:
        breaker.record_failure(); return error_response()

Stdlib only. Run `python3 circuit_breaker.py` for the self-proof.
"""
from __future__ import annotations

import threading
import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"        # normal — all calls allowed
    OPEN = "open"            # tripped — reject immediately (fail fast)
    HALF_OPEN = "half-open"  # probing — one call allowed to test recovery


class CircuitBreaker:
    """Thread-safe circuit breaker. One breaker per external dependency.

    threading.Lock (not asyncio.Lock): state transitions are pure CPU (counter +
    timestamp compare) with no await inside, so the same instance is safe from
    sync callers (e.g. work offloaded to a thread) and async callers alike.
    """

    def __init__(self, name: str, *, failure_threshold: int = 3,
                 cooldown_secs: float = 60.0, max_cooldown_secs: float = 300.0,
                 _clock=time.monotonic) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._base_cooldown = cooldown_secs
        self._max_cooldown = max_cooldown_secs
        self._clock = _clock  # injectable for deterministic tests
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._open_until = 0.0
        self._cooldown = cooldown_secs
        self._probe_allowed = True
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        return self._state

    def is_open(self) -> bool:
        """True = reject the call. Drives OPEN->HALF_OPEN when cooldown expires."""
        with self._lock:
            if self._state is CircuitState.CLOSED:
                return False
            if self._state is CircuitState.OPEN:
                if self._clock() >= self._open_until:
                    self._state = CircuitState.HALF_OPEN
                    self._probe_allowed = True
                else:
                    return True
            if self._state is CircuitState.HALF_OPEN:
                if self._probe_allowed:
                    self._probe_allowed = False  # grant exactly one probe
                    return False
                return True
            return True

    def record_success(self) -> None:
        """Reset failures. HALF_OPEN probe success -> close + reset cooldown."""
        with self._lock:
            self._failures = 0
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._cooldown = self._base_cooldown

    def record_failure(self) -> None:
        """Count failure. Threshold -> OPEN. Probe failure -> OPEN, double cooldown."""
        with self._lock:
            self._failures += 1
            if self._state is CircuitState.HALF_OPEN:
                self._cooldown = min(self._cooldown * 2, self._max_cooldown)
                self._open_until = self._clock() + self._cooldown
                self._state = CircuitState.OPEN
            elif self._failures >= self._failure_threshold:
                self._open_until = self._clock() + self._cooldown
                self._state = CircuitState.OPEN

    def status(self) -> dict:
        """Health snapshot — feed a /health endpoint or dashboard."""
        return {"name": self._name, "state": self._state.value,
                "failures": self._failures}


__all__ = ["CircuitState", "CircuitBreaker"]


def _selfproof() -> None:
    clock = [1000.0]
    cb = CircuitBreaker("db", failure_threshold=3, cooldown_secs=30.0,
                        _clock=lambda: clock[0])

    assert not cb.is_open() and cb.state is CircuitState.CLOSED

    # Threshold failures trip it open -> fail fast.
    for _ in range(3):
        cb.record_failure()
    assert cb.state is CircuitState.OPEN
    assert cb.is_open()  # rejected during cooldown

    # After cooldown, exactly one probe is allowed (HALF_OPEN).
    clock[0] += 31.0
    assert not cb.is_open()   # first caller = the probe
    assert cb.is_open()       # second caller rejected while probe in flight

    # Probe failure reopens with doubled cooldown (30 -> 60).
    cb.record_failure()
    assert cb.state is CircuitState.OPEN
    clock[0] += 31.0
    assert cb.is_open()       # 31s < 60s doubled cooldown -> still open
    clock[0] += 30.0
    assert not cb.is_open()   # probe again
    cb.record_success()       # recovered
    assert cb.state is CircuitState.CLOSED
    assert cb.status()["state"] == "closed"

    print("circuit_breaker self-proof: PASS")


if __name__ == "__main__":
    _selfproof()
