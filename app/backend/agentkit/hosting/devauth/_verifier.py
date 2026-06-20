"""Ed25519 signature verification — pure function, no logging.

Module role:
    Verifies a request signature against a configured public key. Pure,
    side-effect-free, no I/O, no logging. The middleware in
    ``_middleware.py`` is the only caller.

Why a separate module:
    The verifier is the security-critical primitive. Keeping it in
    isolation makes it trivial to unit-test against tampered inputs and
    makes a code review of the security boundary fit on one screen.

Why no logging anywhere in this module:
    A goal of signed-request dev auth is that a failed verification
    looks identical to "no auth attempted" from any log vantage. The
    verifier therefore never logs the headers, the timestamp, the
    public key, the slug, the verification outcome, or any exception
    text — even at debug. Failures collapse to a single bool.

Domain-blind:
    This module is pure transport cryptography. It knows nothing about
    any consuming application's identity type. The verified context
    slug is returned as an opaque string; the consumer's injected
    identity factory turns it into a principal.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

# ``cryptography`` is transitively present via ``azure-identity``; no new
# dependency required. ``InvalidSignature`` is the only exception we
# want to distinguish from arbitrary verifier errors, but we still
# collapse both to ``ok=False`` — the caller cannot learn anything from
# the distinction.
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Allowed shape for the normalised context slug. Lowercase ASCII
# letters, digits, underscore and hyphen, up to 64 characters. Empty
# matches — the middleware maps an empty slug to the consumer's default
# identity.
_SLUG_RE = re.compile(r"^[a-z0-9_-]{0,64}$")

# Maximum allowed skew between client-supplied timestamp and server
# wall-clock, in seconds. Five minutes is large enough to tolerate
# operator-laptop clock drift without NTP, small enough that a captured
# request is unusable after a coffee break. The constant is module-
# private (no env override) so an attacker cannot widen the window via
# config injection.
_MAX_SKEW_SECONDS = 300


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Outcome of a verification attempt.

    Only two bits of information cross the boundary back to the caller:
    whether the signature was valid, and (when valid) the
    caller-supplied context slug. No diagnostic strings, no failure
    reason codes — every "no" looks the same.
    """

    ok: bool
    user_slug: str = ""


def _decode_public_key(b64: str) -> Ed25519PublicKey | None:
    """Decode a base64 32-byte Ed25519 public key. ``None`` on any failure.

    Public keys are never sensitive, but we still avoid raising — the
    middleware uses ``None`` to short-circuit to ``ok=False`` without
    leaking decoder errors into a stack trace or log.
    """
    try:
        raw = base64.b64decode(b64.strip(), validate=True)
    except Exception:
        return None
    if len(raw) != 32:
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception:
        return None


def _canonical(
    *,
    method: str,
    path_and_query: str,
    ts: str,
    context_slug: str,
    body_sha256_hex: str,
) -> bytes:
    """Build the canonical string that gets signed.

    Field order is fixed forever. Adding a field is a wire-incompatible
    change (rotate keys). The ``\\n`` delimiter is unambiguous because
    none of the encoded fields can contain a newline:

      - ``method``     — uppercase ASCII verb
      - ``path_and_query`` — URL-encoded; newlines are %0A
      - ``ts``         — RFC 3339 UTC, no newlines
      - ``context_slug`` — single-token slug, normalised before signing
      - ``body_sha256_hex`` — 64 lowercase hex chars

    Both sides MUST normalise the slug the same way (lowercase, strip).
    """
    return (
        f"{method.upper()}\n"
        f"{path_and_query}\n"
        f"{ts}\n"
        f"{context_slug}\n"
        f"{body_sha256_hex}"
    ).encode("ascii")


def verify(
    *,
    public_key_b64: str,
    method: str,
    path_and_query: str,
    ts: str,
    sig_b64: str,
    body: bytes,
    user_slug: str = "",
) -> VerifyResult:
    """Verify an Ed25519-signed request.

    Returns ``VerifyResult(ok=True, user_slug=...)`` iff every check
    passes. Returns ``VerifyResult(ok=False)`` for every failure mode
    — bad public key, bad timestamp, bad base64, bad signature, replay
    outside the skew window, anything. No partial information is
    returned to the caller.

    Args:
        public_key_b64: Server-configured Ed25519 public key, base64 of
            32 raw bytes.
        method: HTTP method, case-insensitive (uppercased internally).
        path_and_query: Path with query string included verbatim, e.g.
            ``"/api/sessions?limit=10"``. Must match exactly what the
            client signed.
        ts: Client-supplied timestamp, RFC 3339 UTC (``...Z``).
        sig_b64: Client-supplied base64-encoded Ed25519 signature.
        body: Raw request body bytes (empty for GET).
        user_slug: Optional caller context, lowercased/stripped before
            it enters the canonical string.

    Returns:
        VerifyResult.
    """
    if not public_key_b64 or not ts or not sig_b64:
        return VerifyResult(False)

    pk = _decode_public_key(public_key_b64)
    if pk is None:
        return VerifyResult(False)

    # Timestamp window. ``fromisoformat`` accepts ``+00:00``; we accept
    # the more compact ``Z`` suffix by translating it. Anything else
    # that fails parsing collapses to ``ok=False``.
    try:
        request_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if request_ts.tzinfo is None:
            return VerifyResult(False)
        skew = abs((datetime.now(timezone.utc) - request_ts).total_seconds())
        if skew > _MAX_SKEW_SECONDS:
            return VerifyResult(False)
    except Exception:
        return VerifyResult(False)

    try:
        sig = base64.b64decode(sig_b64.strip(), validate=True)
    except Exception:
        return VerifyResult(False)
    # Ed25519 signatures are exactly 64 bytes. Reject other lengths
    # before the cryptographic check so we never spend cycles on
    # obviously-malformed inputs.
    if len(sig) != 64:
        return VerifyResult(False)

    # Slug normalisation. The middleware and the CLI MUST agree.
    slug_norm = (user_slug or "").strip().lower()

    # Chaos hardening 2026-05-22 (CHAOS-032): allowlist the normalised
    # slug to ASCII ``[a-z0-9_-]`` up to 64 chars. The unconstrained
    # ``strip().lower()`` previously accepted latin-1-encodable
    # non-ASCII, path-traversal shapes ("probe/../admin"), and
    # arbitrarily long values. Non-ASCII slugs crashed downstream
    # consumers (e.g. partition keys, request-scope construction) with
    # an unhandled HTTP 500. Validating at the trust boundary closes
    # the crash class. Empty slug stays valid (maps to the consumer's
    # default identity upstream).
    if not _SLUG_RE.match(slug_norm):
        return VerifyResult(False)

    body_sha = hashlib.sha256(body).hexdigest()
    msg = _canonical(
        method=method,
        path_and_query=path_and_query,
        ts=ts,
        context_slug=slug_norm,
        body_sha256_hex=body_sha,
    )

    try:
        pk.verify(sig, msg)
    except InvalidSignature:
        return VerifyResult(False)
    except Exception:
        # Defence in depth: any other crypto-layer exception (encoding,
        # algorithm mismatch) collapses to the same outcome as a bad
        # signature.
        return VerifyResult(False)

    return VerifyResult(True, user_slug=slug_norm)
