"""Cross-cutting input validators (shape gates).

Module role:
    Single home for shape rules that previously lived inline in N router
    files. Promoted here in inquisitor audit 2026-05-22 R5 + R9 so the
    detector, topology, and session-id checks have one definition.

Behaviour preserved exactly:
    - ``STATION_RE`` matches the prior ``^[A-Za-z0-9_]{1,32}$`` shape used
      by the situations and topology routers (CHAOS-013 parity).
    - ``validate_station`` returns ``None`` for empty / ``None`` so the
      "no filter" semantics of the GET handler are preserved.
    - ``SESSION_ID_MAX_LEN = 64`` matches the prior CHAOS-044 cap (32-hex
      uuid + slack). Anything longer is a probe.

These helpers raise ``ValueError`` — the router boundary translates
to ``HTTPException`` (422 / 404 per existing contract).
"""

from __future__ import annotations

import re

# Per-request semantic tool-call ledger (lifted from foundation.tool_guard,
# Inc11b). Re-exported so consumers use ``agentkit.validation`` as the single
# validation entry point.
from agentkit.validation.tool_guard import (
    record_tool_call_once,
    reset_tool_call_ledger,
    set_tool_call_ledger,
)

# Station shape gate (R5).
STATION_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")

# Session-id length gate (R9, replaces in-store CHAOS-044 cap).
SESSION_ID_MAX_LEN = 64


def validate_station(value: str | None) -> str | None:
    """Return ``value`` if it matches ``STATION_RE``; raise ``ValueError`` otherwise.

    ``None`` and empty string both pass through as ``None`` so the GET handler
    default behaviour ("no filter") is preserved exactly.
    """
    if value is None or value == "":
        return None
    if not STATION_RE.match(value):
        raise ValueError("station must match ^[A-Za-z0-9_]{1,32}$")
    return value


def validate_session_id(value: str) -> str:
    """Return ``value`` if it is a plausible session id; raise ``ValueError`` otherwise.

    Cosmos partition-key values are bounded at 2 048 bytes; anything longer
    than ``SESSION_ID_MAX_LEN`` is a probe (CHAOS-044). Router boundary
    translates ``ValueError`` to 404 to avoid signalling existence.
    """
    if not isinstance(value, str) or not value or len(value) > SESSION_ID_MAX_LEN:
        raise ValueError("invalid session id")
    return value


def require_station(value: str | None, *, allow_empty: bool = True) -> str | None:
    """Shape-gate a station code; raise ``ValueError`` on a malformed value.

    Promoted from the per-router ``_require_station`` helpers in
    ``hosting/fastapi/routers/{situations,topology}.py`` (hygiene
    2026-05-24 §A2). When ``allow_empty`` is True (situations default),
    ``None``/empty pass through as ``None``. When False (topology
    default), missing values raise ``ValueError`` — every topology
    handler requires a concrete station.

    The router boundary translates ``ValueError`` to 422 via the
    app-level handler in ``hosting/fastapi/error_handlers.py``.
    """
    normalised = validate_station(value)
    if normalised is None and not allow_empty:
        raise ValueError("station must match ^[A-Za-z0-9_]{1,32}$")
    return normalised


__all__ = [
    "STATION_RE",
    "SESSION_ID_MAX_LEN",
    "validate_station",
    "validate_session_id",
    "require_station",
    "record_tool_call_once",
    "reset_tool_call_ledger",
    "set_tool_call_ledger",
]
