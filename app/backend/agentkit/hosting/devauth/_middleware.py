"""ASGI middleware that verifies Ed25519-signed requests — domain-blind.

Module role:
    Generic signed-request dev-auth transport. A consuming application
    mounts it via ``install_signed_request_auth(app, public_key_b64=...,
    identity_factory=...)``. Activates per-request only when the public
    key is configured AND the two signing headers are present.
    Otherwise pass-through — the application's primary auth path is
    untouched.

The seam (why this module is domain-blind):
    This middleware owns the crypto/transport: canonical-string
    reconstruction, Ed25519 verification (delegated to ``_verifier``),
    single-flight replay protection, and the bare-401 failure shape. It
    does NOT know the consumer's identity type. On success it calls the
    INJECTED ``identity_factory(slug)`` to materialise an opaque
    principal and attaches it to ``scope[scope_key]`` (default
    ``"devauth_user"``). The consumer's primary auth dependency reads
    that scope key. agentkit never imports a domain identity class.

Why ASGI, not BaseHTTPMiddleware:
    BaseHTTPMiddleware buffers responses, which would break SSE
    streaming endpoints. The ASGI form keeps the response stream
    pristine: we only inspect the request headers and (when activated)
    read the request body once, then re-emit it through a fresh
    ``receive`` callable.

No logging:
    This module does not import a logger. There is no info/warn/debug
    line anywhere on success or failure. The only externally observable
    signal of activity is the HTTP response code; failed verification
    returns ``401`` with an empty body — identical in shape to a
    request that omitted authentication entirely.
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from agentkit.hosting.devauth._verifier import verify

# Header names look like generic API request-signing (cf. AWS SigV4,
# Stripe). No "dev"/"key"/"bypass" hint to a casual inspector of
# captured traffic.
_TS_HEADER = b"x-request-timestamp"
_SIG_HEADER = b"x-request-signature"
_CTX_HEADER = b"x-request-context"

# Default scope key under which the synthetic principal is attached for
# downstream consumption by the consumer's primary auth dependency.
# Living on ``scope`` (not ``request.state``) sidesteps Starlette's
# ``State`` class wiring and makes the contract independent of Starlette
# internals.
_DEFAULT_SCOPE_USER_KEY = "devauth_user"


class ReplayCache:
    """Single-flight replay-protection cache.

    Signing material is ``(method, raw_path, timestamp, body_sha256)``
    only — no nonce, no jti. A captured signature is therefore
    replayable for the full skew window. This cache tracks every
    accepted signature until its TTL elapses and rejects any second
    occurrence.

    TODO(B-CHAOS-025): this cache is PER-PROCESS. Under horizontal
    autoscale (e.g. Azure Container Apps multiple replicas), a signed
    request captured and replayed against a DIFFERENT replica is NOT
    caught — each replica has its own ``_seen`` dict. Solving
    distributed replay needs a shared lease (Redis SETNX / Cosmos
    optimistic-etag / a signed-nonce ledger keyed on the signature)
    with the same TTL. Deliberately NOT solved here — the single-
    replica behaviour below is preserved exactly. This is the
    distributed-lease seam (mirrors the abort_registry seam).
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        # TTL window must match the verifier's ``_MAX_SKEW_SECONDS`` so
        # a signature can never be replayable after it has been evicted.
        self._ttl = ttl_seconds
        self._seen: dict[str, float] = {}

    def check_and_record(self, sig: str) -> bool:
        """Return True if this signature is fresh, False if replay.

        Side effect: records ``sig`` with an expiry of ``now + ttl``
        when fresh; opportunistically evicts expired entries on every
        call so the dict stays bounded by the number of legitimate
        signatures in flight within the TTL window.
        """
        now = time.monotonic()
        if self._seen:
            expired = [k for k, exp in self._seen.items() if exp <= now]
            for k in expired:
                self._seen.pop(k, None)
        if sig in self._seen:
            return False
        self._seen[sig] = now + self._ttl
        return True


# Module-level default replay cache. The middleware uses this when the
# consumer does not inject its own — preserving the original GridIQ
# per-process behaviour byte-for-byte.
_DEFAULT_REPLAY_CACHE = ReplayCache()


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> str:
    """Single-value, case-insensitive header lookup over the raw ASGI
    headers list. Returns ``""`` when absent.

    We work at the ASGI level rather than constructing a ``Request``
    object because building a ``Request`` here would force us to
    eagerly resolve ``scope["state"]`` and risk capturing a stale
    reference in long-running endpoints.
    """
    name_lower = name.lower()
    for k, v in headers:
        if k.lower() == name_lower:
            try:
                return v.decode("latin-1")
            except Exception:
                return ""
    return ""


class SignedRequestASGIMiddleware:
    """Pure ASGI middleware. Verifies signed requests, stays out of the
    way for everything else.

    Args:
        app: The next ASGI callable in the chain.
        public_key_b64: Server-configured Ed25519 public key (base64 of
            32 raw bytes). Captured at construction; rotation requires a
            redeploy.
        identity_factory: ``Callable[[str], object]`` mapping the
            verified, normalised context slug to an opaque principal
            object. Called only after a signature passes verification
            AND replay checks. The returned object is attached to
            ``scope[scope_key]``. This is the domain seam: agentkit
            never constructs the consumer's identity type.
        replay_cache: Optional injected replay cache. Defaults to the
            module-level per-process singleton.
        scope_key: Scope key the principal is attached under. Defaults
            to ``"devauth_user"``.

    Activation gate:
        - ``public_key_b64`` must be non-empty.
        - Both ``X-Request-Timestamp`` and ``X-Request-Signature``
          headers must be present on the request.

    Inactive path:
        Direct passthrough to the inner app. No body read, no header
        rewriting, no state mutation.

    Active path:
        Read the body (so we can hash it), build the canonical string,
        verify. On success, build the principal via ``identity_factory``,
        attach it to ``scope[scope_key]`` and call the inner app with a
        fresh ``receive`` that replays the buffered body. On failure,
        send a bare 401 directly without invoking the inner app.
    """

    def __init__(
        self,
        app: Callable,
        *,
        public_key_b64: str,
        identity_factory: Callable[[str], object],
        replay_cache: ReplayCache | None = None,
        scope_key: str = _DEFAULT_SCOPE_USER_KEY,
    ) -> None:
        self._app = app
        self._pk = public_key_b64
        self._identity_factory = identity_factory
        self._replay = replay_cache or _DEFAULT_REPLAY_CACHE
        self._scope_key = scope_key

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        # Lifespan, websocket, and any non-HTTP scope types are not in
        # scope for this feature. Pass them through unmodified.
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])

        # Cheap pre-check: if the operator did not attach signing
        # headers we have nothing to do.
        ts = _header(headers, _TS_HEADER)
        sig = _header(headers, _SIG_HEADER)
        if not ts or not sig:
            await self._app(scope, receive, send)
            return

        # Buffer the entire request body. FastAPI route handlers expect
        # the full body to be replayed; collecting it here is safe
        # because every signed endpoint uses small JSON payloads (no
        # streaming uploads).
        body_chunks: list[bytes] = []
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                # Disconnect or other non-body messages → reject.
                await _send_401(send)
                return
            body_chunks.append(message.get("body") or b"")
            more = bool(message.get("more_body", False))
        body = b"".join(body_chunks)

        # Reconstruct path+query exactly as the operator would have
        # signed it. ASGI guarantees ``raw_path`` as the original byte
        # sequence of the URI path (still percent-encoded); ``path`` is
        # the *decoded* form. Clients sign the encoded path they sent
        # over the wire, so reconstruct from ``raw_path`` when present.
        # Without this, any signed path containing percent-encoded
        # special characters (apostrophe, newline, semicolon, etc.)
        # fails verification — observed in chaos hardening 2026-05-22
        # (CHAOS-012 / 017 / 018) where ``/api/topology/A%0AB`` returned
        # 401 because the server reconstructed ``A\nB`` and re-encoded
        # mismatched the client's signed string.
        raw_path = scope.get("raw_path")
        if isinstance(raw_path, (bytes, bytearray)):
            path_q = raw_path.decode("latin-1")
        else:
            path_q = scope.get("path", "")
        qs = scope.get("query_string") or b""
        if qs:
            path_q = f"{path_q}?{qs.decode('latin-1')}"

        ctx = _header(headers, _CTX_HEADER)

        result = verify(
            public_key_b64=self._pk,
            method=scope.get("method", ""),
            path_and_query=path_q,
            ts=ts,
            sig_b64=sig,
            body=body,
            user_slug=ctx,
        )

        if not result.ok:
            # Bare 401, no body, no WWW-Authenticate hint — looks like
            # any other unauthenticated request.
            await _send_401(send)
            return

        # Chaos hardening 2026-05-22 (CHAOS-026): single-flight replay
        # rejection. Signature passed verify(), but if we have seen it
        # before within the TTL window, treat it as a replay attack and
        # 401 with the same shape as any other auth failure.
        if not self._replay.check_and_record(sig):
            await _send_401(send)
            return

        # Materialise the principal via the injected factory. agentkit
        # passes the verified, normalised slug; the consumer owns the
        # identity shape (oid namespace, default-user mapping, etc.).
        scope[self._scope_key] = self._identity_factory(result.user_slug)

        # Replay the buffered body for downstream consumers. The first
        # ``receive`` call returns the captured body in a single
        # message; subsequent calls delegate to the original transport
        # ``receive`` so that genuine ``http.disconnect`` signals reach
        # the framework. Fabricating a synthetic disconnect here would
        # cancel any streaming response (e.g. SSE) the moment the
        # endpoint starts streaming.
        already_sent = False

        async def replay_receive() -> dict:
            nonlocal already_sent
            if not already_sent:
                already_sent = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            return await receive()

        await self._app(scope, replay_receive, send)


async def _send_401(send: Callable) -> None:
    """Emit a stock 401 with no body and no diagnostic headers."""
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-length", b"0")],
        }
    )
    await send({"type": "http.response.body", "body": b"", "more_body": False})


def install_signed_request_auth(
    app,
    *,
    public_key_b64: str,
    identity_factory: Callable[[str], object],
    replay_cache: ReplayCache | None = None,
    scope_key: str = _DEFAULT_SCOPE_USER_KEY,
) -> bool:
    """Idempotent mount of the signed-request middleware.

    When ``public_key_b64`` is empty the middleware is **not** mounted
    at all — the application's ASGI stack is byte-identical to a build
    without this feature. Returns True if mounted, False if skipped.

    The middleware is added with ``app.add_middleware`` so it runs early
    in the request pipeline (before CORS short-circuits a preflight;
    CORS-preflight has no signing headers and falls through to the
    pass-through branch above).
    """
    pk = (public_key_b64 or "").strip()
    if not pk:
        return False
    app.add_middleware(
        SignedRequestASGIMiddleware,
        public_key_b64=pk,
        identity_factory=identity_factory,
        replay_cache=replay_cache,
        scope_key=scope_key,
    )
    return True
