"""Request-scoped correlation ID via contextvars + ASGI middleware.

Module role:
    Provides a pure ASGI middleware that generates a unique ``request_id`` for
    every incoming HTTP request, stores it in a ``ContextVar``, and attaches it
    as a response header (``X-Request-ID``).  The ``_logging`` module's filter
    reads this ContextVar so every log record emitted during the request
    carries the same ``request_id``.

    Uses a raw ASGI middleware class instead of Starlette's BaseHTTPMiddleware
    to avoid buffering streaming responses (SSE, chunked) in memory.

    Callers may also pass ``X-Request-ID`` on the inbound request to propagate
    an externally-assigned correlation ID (e.g., from a load balancer).

Key collaborators:
    - ``_logging.py`` — ``_CorrelationFilter`` reads ``request_id_var``
    - ``_bootstrap.py`` — registers this middleware on the FastAPI app

Dependents:
    Called by: ``_bootstrap.configure()`` (middleware registration)
"""

from __future__ import annotations

import contextvars
import uuid

# ── Context variable ─────────────────────────────────────────────────────────
# Accessible from any async task spawned during a request's lifetime.
# Default is empty string — log records emitted outside a request context
# (e.g., at startup) get ``request_id=""`` which is harmless.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)


class CorrelationIdMiddleware:
    """Pure ASGI middleware — injects correlation ID without buffering.

    Unlike Starlette's ``BaseHTTPMiddleware``, this does not read the
    response body into memory. This is essential for SSE streaming
    endpoints (chat, observability logs) which must stream without
    buffering.
    """

    def __init__(self, app):
        """Store the next ASGI app in the chain."""
        self.app = app

    async def __call__(self, scope, receive, send):
        """ASGI interface — inject correlation ID for HTTP requests."""
        if scope["type"] != "http":
            # Non-HTTP (lifespan, websocket) — pass through unchanged
            await self.app(scope, receive, send)
            return

        # Extract caller-supplied ID or generate one
        headers = dict(scope.get("headers", []))
        x_request_id = headers.get(b"x-request-id", b"").decode("utf-8", errors="ignore")
        rid = x_request_id or uuid.uuid4().hex

        # Set the context variable for the duration of the request
        token = request_id_var.set(rid)

        async def send_with_header(message):
            """Inject X-Request-ID header into the HTTP response start."""
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", rid.encode()))
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(token)
