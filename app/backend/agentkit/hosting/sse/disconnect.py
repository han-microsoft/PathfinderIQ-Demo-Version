"""ASGI client-disconnect-aware producer wrapper (B2).

Module role:
    Single home for the "iterate a producer generator while polling the
    client connection and cancel the producer task on disconnect" pattern.
    Without this, long-running SSE producers (multi-minute audits,
    summaries) keep burning compute long after the operator closes the
    tab, because the underlying generator is never cancelled.

Behaviour:
    * Runs the producer in a background task so the iteration itself does
      not block the disconnect-polling loop.
    * Polls ``request.is_disconnected()`` on the configured cadence
      (``get_settings().disconnect_poll_seconds``).
    * On disconnect: cancels the producer task, awaits its teardown, runs
      the optional ``on_disconnect`` callback, exits the generator cleanly.
      The caller (the ASGI framework) sees a normal generator close.
    * On producer exception: re-raises so the outer route's error envelope
      still applies.

Layer note:
    Imports ``agentkit.config`` and stdlib only. The request object is
    consumed structurally via ``DisconnectAware`` so agentkit never imports
    the consumer's web framework (FastAPI/Starlette).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, TypeVar

from agentkit.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DisconnectAware(Protocol):
    """Structural contract for the request object polled for disconnect.

    Any object exposing an async ``is_disconnected()`` satisfies this — e.g.
    a Starlette/FastAPI ``Request``. Typed structurally so agentkit stays
    framework-agnostic.
    """

    async def is_disconnected(self) -> bool: ...


async def sse_with_disconnect(
    request: DisconnectAware,
    producer: AsyncIterable[T],
    *,
    on_disconnect: Callable[[], Awaitable[None] | None] | None = None,
    poll_seconds: float | None = None,
    log_event: str = "sse.client_disconnect",
    log_extra: dict[str, Any] | None = None,
) -> AsyncIterator[T]:
    """Yield items from ``producer`` until the client disconnects.

    Args:
        request: Request-like object polled via ``is_disconnected()``.
        producer: Async iterable producing SSE frames (dict or wire-string).
        on_disconnect: Optional async-or-sync callback invoked exactly
            once after the producer task is cancelled and before this
            generator exits. Used by callers to release in-flight
            resources (e.g. an audit-runner release).
        poll_seconds: Override for the ``is_disconnected()`` poll interval.
            Defaults to ``get_settings().disconnect_poll_seconds``.
        log_event: Logger event name emitted on disconnect.
        log_extra: Optional structured-log dict merged into the
            disconnect log line.

    Yields:
        Items pulled from ``producer`` in their original shape.
    """
    poll = poll_seconds if poll_seconds is not None else max(float(get_settings().disconnect_poll_seconds), 0.1)
    iterator = producer.__aiter__()

    # Pull each item via a wrapped task so the poll loop can race the
    # producer's ``__anext__`` against ``is_disconnected``. ``__anext__``
    # is wrapped fresh each round so cancellation cleanly stops the
    # producer mid-step.
    async def _next() -> tuple[bool, T | None]:
        try:
            return False, await iterator.__anext__()
        except StopAsyncIteration:
            return True, None

    next_task: asyncio.Task[tuple[bool, T | None]] | None = None
    disconnected = False
    try:
        while True:
            if next_task is None:
                next_task = asyncio.create_task(_next())

            done, _pending = await asyncio.wait(
                {next_task}, timeout=poll, return_when=asyncio.FIRST_COMPLETED
            )

            # Disconnect check fires on every poll tick, including when
            # the producer yielded — operators expect cancellation latency
            # of at most ``poll`` seconds after the socket closes.
            try:
                if await request.is_disconnected():
                    disconnected = True
                    break
            except Exception:
                # Broken ASGI receive — treat as disconnect.
                disconnected = True
                break

            if next_task in done:
                stop, value = next_task.result()
                next_task = None
                if stop:
                    return
                # ``None`` is a legitimate sentinel only when the producer
                # explicitly yields it; pass through verbatim.
                yield value  # type: ignore[misc]
    finally:
        if next_task is not None and not next_task.done():
            next_task.cancel()
            try:
                await next_task
            except (asyncio.CancelledError, Exception):
                pass

        # Cancel the underlying generator so background driver tasks
        # observe the cancel and exit. ``aclose`` is the documented async
        # generator teardown; non-generator iterables ignore the call.
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                pass

        if disconnected:
            logger.info(log_event, extra=log_extra or {})
            if on_disconnect is not None:
                try:
                    result = on_disconnect()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("sse.on_disconnect_failed")


__all__ = ["DisconnectAware", "sse_with_disconnect"]
