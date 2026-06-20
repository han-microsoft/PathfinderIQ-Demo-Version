"""Canonical Server-Sent Events frame formatters + generic event vocabulary.

Module role:
    The generic SSE spine (S1). Two responsibilities:

    1. **Frame formatters** — ``format_sse`` / ``format_sse_wire`` turn an
       ``(event_name, data)`` pair into the two wire shapes the FastAPI app
       uses (sse-starlette dict frame and raw ``StreamingResponse`` string).
       Both share one JSON serialisation and one oversize-frame guard so a
       runaway tool payload cannot stall the loop on ``json.dumps`` of a
       multi-MB structure.

    2. **Event-name vocabulary table** — ``GENERIC_EVENT_NAMES`` is the
       domain-blind core event set (sourced from
       ``agentkit.contracts.models.StreamEventType`` so there is exactly
       one source of truth, never a hand-duplicated fork). A consumer
       (e.g. GridIQ) registers its own domain event names on top via
       ``register_domain_events`` — the vocabulary is **data the consumer
       extends, not a code-fork**. ``known_event_names`` returns the union
       and ``GENERIC_TERMINALS`` names the terminal frames that end a
       stream. The live contract probe (``agentkit.hosting.probe``)
       consults this table to flag any unregistered event name on the wire.

Two output shapes exist because the FastAPI app uses two different SSE
transports:

- ``format_sse`` returns a ``{"event": str, "data": str}`` dict consumed
  by ``sse-starlette``'s ``EventSourceResponse``.
- ``format_sse_wire`` returns the raw wire string (``event: x\\ndata:
  y\\n\\n``) consumed by ``starlette.responses.StreamingResponse``.

Frame-size guard:
    Any frame whose encoded ``data`` JSON exceeds
    ``get_settings().max_sse_frame_bytes`` is rewritten to a categorical
    truncation envelope so a runaway tool payload cannot block the wire
    behind a single oversized chunk. The truncation envelope carries an
    ASCII-safe preview of the original JSON so the frontend can still
    render a hint.

Layer note:
    Imports ``agentkit.config`` (settings accessor) and
    ``agentkit.contracts.models`` (the event enum) only. Imports zero
    GridIQ packages — domain event names live in the consumer's
    composition root, never here.
"""

from __future__ import annotations

import json
from typing import Any

from agentkit.config import get_settings
from agentkit.contracts.models import StreamEventType


# Inline cap on the preview slice. Independent of ``max_sse_frame_bytes``
# so a tighter overall cap does not shrink the preview to uselessness.
# 4 KiB matches the typical browser tooltip / dev-tools display budget.
_TRUNCATION_PREVIEW_BYTES = 4096


# ── Event-name vocabulary (the table the consumer extends) ───────────────────

# Generic, domain-blind event set. Derived from the StreamEventType enum so
# there is a single source of truth: the enum members ARE the generic
# vocabulary. A consumer never edits this set; it registers domain names on
# top via ``register_domain_events``.
GENERIC_EVENT_NAMES: frozenset[str] = frozenset(e.value for e in StreamEventType)

# The terminal frames that legally end a stream. After one of these, no
# further frame may appear on the wire (asserted by the contract probe).
GENERIC_TERMINALS: frozenset[str] = frozenset(
    {
        StreamEventType.DONE.value,
        StreamEventType.ERROR.value,
        StreamEventType.ABORTED.value,
    }
)

# Domain event names registered by the consumer at composition time. Kept
# mutable + module-scoped so registration is a single declarative call; the
# generic core never names a domain event.
_domain_event_names: set[str] = set()


def register_domain_events(*names: str) -> None:
    """Register consumer-domain SSE event names on top of the generic table.

    Idempotent. The consumer (e.g. GridIQ) calls this once at composition
    time with the event names its routers emit that are not part of the
    generic core (``audit_report``, ``situation``, …). Those names then
    count as ``known`` for the contract probe without ever being baked
    into agentkit.

    Args:
        *names: One or more SSE ``event:`` field values to register.
    """
    for name in names:
        if name:
            _domain_event_names.add(name)


def known_event_names() -> frozenset[str]:
    """Return the generic vocabulary unioned with all registered domain names."""
    return GENERIC_EVENT_NAMES | frozenset(_domain_event_names)


def is_known_event(name: str) -> bool:
    """True if ``name`` is a generic core event or a registered domain event."""
    return name in GENERIC_EVENT_NAMES or name in _domain_event_names


# ── Frame formatters ─────────────────────────────────────────────────────────


def _truncate_to_utf8(raw: str, limit: int) -> str:
    """Return ``raw`` truncated to ``limit`` bytes on a valid UTF-8 boundary.

    ``str.encode("utf-8")[:limit]`` can split a multi-byte codepoint and
    produce a string that fails to decode. ``errors="ignore"`` on the
    inverse decode drops the partial bytes cleanly without raising.
    """
    encoded = raw.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return raw
    return encoded[:limit].decode("utf-8", errors="ignore")


def _maybe_truncate(event_name: str, data: dict[str, Any]) -> str:
    """Serialise ``data`` to JSON, falling back to a truncation envelope.

    The truncation envelope is itself JSON-serialised and guaranteed to be
    smaller than ``get_settings().max_sse_frame_bytes`` because (a) the
    preview is hard-capped at ``_TRUNCATION_PREVIEW_BYTES`` and (b) the
    envelope fields are small fixed-size strings/ints. The check uses the
    encoded UTF-8 byte length so multi-byte payloads (non-ASCII tool
    results) are measured correctly.
    """
    encoded = json.dumps(data)
    limit = max(int(get_settings().max_sse_frame_bytes), 0)
    if limit <= 0 or len(encoded.encode("utf-8")) <= limit:
        return encoded
    preview = _truncate_to_utf8(encoded, _TRUNCATION_PREVIEW_BYTES)
    envelope = {
        "truncated": True,
        "preview": preview,
        "original_event": event_name,
        "original_bytes": len(encoded.encode("utf-8")),
    }
    return json.dumps(envelope)


def format_sse(event_name: str, data: dict[str, Any]) -> dict[str, str]:
    """Format an sse-starlette frame.

    Returns ``{"event": event_name, "data": json.dumps(data)}``. Pass
    the result to ``yield`` inside an ``EventSourceResponse`` generator.
    Oversized payloads are replaced with a categorical truncation
    envelope; see module docstring.
    """
    return {"event": event_name, "data": _maybe_truncate(event_name, data)}


def format_sse_wire(event_name: str, data: dict[str, Any]) -> str:
    """Format a raw SSE wire frame for ``StreamingResponse`` generators.

    Oversized payloads are replaced with a categorical truncation
    envelope; see module docstring.
    """
    return f"event: {event_name}\ndata: {_maybe_truncate(event_name, data)}\n\n"
