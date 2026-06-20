"""Canonical tool error/degraded envelope helpers.

Module role:
    Single chokepoint for the agent-callable tool error contract
    documented in ``tools/README.md`` §4. Every ``@tool`` that
    returns a JSON string MUST emit error responses via one of the
    helpers in this module instead of open-coding
    ``json.dumps({"error": True, "detail": ...})`` at the call site.

    Why this module exists (R8, inquisitor audit 2026-05-17):
        - Before R8, 20+ sites across ``tools/`` open-coded the
          envelope literal. Detail-string sanitisation drifted per
          site: some applied ``str(exc)[:500]``, some embedded the
          raw exception message, some prepended ``type(e).__name__``.
        - The ``README.md`` §4 contract — "sanitised message, never
          raw SDK exceptions, never internal URLs, never secrets" —
          was enforced by convention, not by a chokepoint. Any future
          envelope-shape change (new key, different cap) cost 20+
          edits.
        - This module is the chokepoint: cap, URL-strip, serialise.

Public surface:
    - ``error_envelope(detail, *, exc=None) -> str``
    - ``degraded_envelope(detail) -> str``
    - ``from_value_error(exc) -> str``

Output contract:
    - ``error_envelope``  → ``{"error": True, "detail": "<sanitised>"}``
    - ``degraded_envelope`` → ``{"degraded": True, "detail": "<sanitised>"}``
    JSON-serialised via stdlib ``json.dumps`` (Python ``True`` →
    JSON ``true``; key insertion order preserved).
"""

from __future__ import annotations

import json
import re
from typing import Final

# Hard cap on the operator-visible detail string. Matches the historical
# ``str(exc)[:500]`` cap used at the most disciplined existing call
# sites (notably ``tools/watcher/_graph_extras.py``).
_DETAIL_CAP: Final[int] = 500

# Strip absolute URLs from the detail message before serialising.
# Internal Azure endpoints (``*.azure.com``, Cosmos / Search / Fabric
# hostnames) routinely leak through SDK exception messages; surfacing
# them to the agent leaks deployment topology. Only URL-shaped tokens
# are stripped — bare hostnames, MRIDs, and station codes are
# preserved verbatim because the agent legitimately needs to reason
# about them.
_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"https?://\S+")


def _sanitize_detail(detail: str) -> str:
    """Cap + URL-strip a tool-facing detail string.

    Single source of truth for the README §4 envelope sanitisation
    rule. Applied uniformly by every helper in this module so the
    chokepoint guarantee holds.
    """
    if not isinstance(detail, str):
        # Defensive: callers may hand us a non-string by accident
        # (e.g. an ``Exception`` instance). Force ``str`` so
        # ``json.dumps`` cannot raise downstream.
        detail = str(detail)
    detail = _URL_PATTERN.sub("<redacted-url>", detail)
    if len(detail) > _DETAIL_CAP:
        detail = detail[:_DETAIL_CAP]
    return detail


def error_envelope(detail: str, *, exc: BaseException | None = None) -> str:
    """Canonical error envelope.

    Args:
        detail: Operator-readable explanation of what failed. Capped
            and URL-stripped by ``_sanitize_detail`` before
            serialisation.
        exc: Optional exception whose ``type.__name__`` and ``str``
            representation are appended to ``detail`` in the historic
            ``"<detail>: <ExcType>: <msg>"`` shape kept for
            compatibility with pre-R8 sites.
    """
    if exc is not None:
        if detail:
            detail = f"{detail}: {type(exc).__name__}: {exc}"
        else:
            detail = f"{type(exc).__name__}: {exc}"
    detail = _sanitize_detail(detail)
    return json.dumps({"error": True, "detail": detail})


def degraded_envelope(detail: str) -> str:
    """Canonical degraded envelope.

    Used when a tool can answer at reduced fidelity (e.g. the
    AI Search circuit breaker is open) — distinct from an outright
    error so the agent can keep going without flagging the run as
    failed.
    """
    return json.dumps({"degraded": True, "detail": _sanitize_detail(detail)})


def from_value_error(exc: ValueError) -> str:
    """Wrap a tool-input ``ValueError`` in the canonical error envelope.

    Validator failures (CIM MRID, station name, voltage class, etc.)
    consistently raise ``ValueError`` with an operator-readable
    message. This helper preserves that message field verbatim
    (subject to the standard sanitisation pass) so existing tests
    that assert on ``"station cannot be empty"`` etc. continue to
    pass.
    """
    return error_envelope(str(exc))


__all__ = [
    "error_envelope",
    "degraded_envelope",
    "from_value_error",
]
