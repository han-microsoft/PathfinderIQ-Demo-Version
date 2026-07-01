"""agentkit.hosting.devauth — generic Ed25519 signed-request dev auth.

Domain-blind transport-layer dev-auth middleware. Verifies Ed25519-
signed requests (canonical-string reconstruction + replay protection)
and attaches a consumer-built principal to the ASGI scope. The consumer
injects an ``identity_factory`` so this package never imports a domain
identity type.

Public surface:
    - ``install_signed_request_auth(app, *, public_key_b64,
      identity_factory, replay_cache=None, scope_key="devauth_user")``
      — idempotent mount; no-op when ``public_key_b64`` is empty.
    - ``SignedRequestASGIMiddleware`` — the ASGI middleware class.
    - ``ReplayCache`` — per-process single-flight replay cache
      (TODO(B-CHAOS-025): distributed-lease seam for autoscale).
    - ``verify`` / ``VerifyResult`` — the pure verifier primitive.

See ``README.md`` for the threat model and wire format.
"""

from agentkit.hosting.devauth._middleware import (
    ReplayCache,
    SignedRequestASGIMiddleware,
    install_signed_request_auth,
)
from agentkit.hosting.devauth._verifier import VerifyResult, verify

__all__ = [
    "install_signed_request_auth",
    "SignedRequestASGIMiddleware",
    "ReplayCache",
    "verify",
    "VerifyResult",
]
