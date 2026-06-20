"""System time context provider (K6) — injects current timestamp.

Module role:
    Injects the current time (real or simulated) as a context instruction. The
    simulated-clock anchor comes from ``settings.simulated_time`` (resolved via
    the registered ``agentkit`` settings; absent on the generic base settings, in
    which case real-clock mode is used). An optional domain note (e.g. a source
    timezone convention) is appended when the consumer registers one via
    :func:`set_time_context_note` — empty by default so the generic provider is
    domain-blind.

Layering:
    stdlib + ``agentkit.config`` (settings accessor). No GridIQ package. Was
    ``agent/providers/time.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from agentkit.config import get_settings

logger = logging.getLogger(__name__)

# Optional consumer-supplied note appended to the time instruction (e.g. source
# timezone convention). Empty = domain-blind. GridIQ sets its AEST/SCADA note
# from ``agent/_compose.py`` so runtime prompt content is unchanged.
_time_context_note: str = ""


def set_time_context_note(note: str) -> None:
    """Register an optional domain note appended to the time instruction."""
    global _time_context_note
    _time_context_note = note or ""


def _simulated_time_setting() -> str:
    """Read ``simulated_time`` from the registered settings, blank if absent."""
    return (getattr(get_settings(), "simulated_time", "") or "").strip()


# ── Simulated-clock anchor (per-provider, no module mutable state) ────────────


@dataclass(frozen=True)
class _SimulatedClock:
    """Resolved simulated-clock state for one ``SystemTimeProvider``."""

    offset: timedelta
    tz: timezone
    tz_label: str


def _resolve_simulated_clock() -> _SimulatedClock | None:
    """Resolve the simulated-clock anchor from ``settings.simulated_time``.

    Returns ``None`` when no anchor is configured (real-clock mode).
    """
    raw = _simulated_time_setting()
    if not raw:
        return None

    try:
        simulated_start = datetime.fromisoformat(raw)
        if simulated_start.tzinfo is None:
            simulated_start = simulated_start.replace(tzinfo=timezone.utc)
        now_real = datetime.now(timezone.utc)
        offset = simulated_start - now_real
        tz = simulated_start.tzinfo
        utcoff = tz.utcoffset(simulated_start) if tz else None
        if utcoff:
            total_secs = int(utcoff.total_seconds())
            sign = "+" if total_secs >= 0 else "-"
            hours, mins = divmod(abs(total_secs), 3600)
            tz_label = f"UTC{sign}{hours:02d}:{mins // 60:02d}"
        else:
            tz_label = "UTC"
        logger.info(
            "clock.simulated: start=%s, offset=%.0fs, tz=%s",
            simulated_start.isoformat(), offset.total_seconds(), tz_label,
        )
        return _SimulatedClock(offset=offset, tz=tz or timezone.utc, tz_label=tz_label)
    except Exception as e:
        logger.warning("clock.simulated.invalid: '%s' — %s. Using real time.", raw, e)
        return None


# ── Module-level helper retained for back-compat with tools/tests ─────────────

_module_clock: _SimulatedClock | None = None
_module_clock_resolved: bool = False


def get_current_time() -> str:
    """Return the current time string (real or simulated)."""
    global _module_clock, _module_clock_resolved
    if not _module_clock_resolved:
        _module_clock = _resolve_simulated_clock()
        _module_clock_resolved = True
    if _module_clock is not None:
        simulated_now = datetime.now(timezone.utc) + _module_clock.offset
        return simulated_now.astimezone(_module_clock.tz).strftime(
            f"%Y-%m-%d %H:%M:%S {_module_clock.tz_label}"
        )
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ── System Time Provider ─────────────────────────────────────────────────────


class SystemTimeProvider:
    """Injects the current time as a context instruction.

    The simulated-clock anchor is resolved once at construction. Per-provider
    state — no module-level mutable globals.

    Attributes:
        source_id: Provider identifier for message attribution.
    """

    def __init__(self, simulated_clock: _SimulatedClock | None = None) -> None:
        """Initialise the provider.

        Args:
            simulated_clock: Pre-resolved clock anchor. ``None`` resolves from
                settings (the common path); tests pass an explicit value to
                exercise the simulated branch deterministically.
        """
        self.source_id = "system_time"
        self._clock = simulated_clock if simulated_clock is not None else _resolve_simulated_clock()

    def _current_time_str(self) -> str:
        """Return the current time string — simulated or real."""
        if self._clock is not None:
            simulated_now = datetime.now(timezone.utc) + self._clock.offset
            simulated_local = simulated_now.astimezone(self._clock.tz)
            return simulated_local.strftime(f"%Y-%m-%d %H:%M:%S {self._clock.tz_label}")
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    async def before_run(self, *, agent: Any, session: Any, context: Any, state: dict) -> None:
        """Inject current time (real or simulated) as instruction."""
        now_str = self._current_time_str()
        label = "Current date and time"
        if self._clock is not None:
            label = "Current date and time (simulated scenario clock)"
        # Optional domain note (e.g. source timezone convention) sits between the
        # timestamp and the upper-bound directive; empty unless the consumer set it.
        note_line = f"{_time_context_note}\n" if _time_context_note else ""
        context.extend_instructions(
            self.source_id,
            (
                f"{label}: {now_str}\n"
                f"{note_line}"
                "Use this as the upper bound for any event search or causal analysis. "
                "Do not assume access to future events beyond this timestamp."
            ),
        )

    async def after_run(self, *, agent: Any, session: Any, context: Any, state: dict) -> None:
        """No-op — time is read-only context."""
        pass
