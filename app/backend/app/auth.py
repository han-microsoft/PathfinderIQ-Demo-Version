"""JWT authentication — User model + get_current_user dependency.

Module role:
    Validates Entra ID JWT Bearer tokens from the Authorization header.
    Extracts user identity (oid, email, name) into a User dataclass.
    Provides get_current_user() as a FastAPI Depends() callable.

    When AUTH_ENABLED=false (local dev), returns an anonymous User
    without any token validation — zero-friction dev experience.

Key collaborators:
    - config.py          — reads auth_enabled, auth_client_id, auth_tenant_id
    - deps.py            — re-exports get_current_user for router imports
    - main.py            — mounts /api/auth_setup endpoint using settings

Dependents:
    Called by: routers/sessions.py, routers/chat.py via Depends(get_current_user)

Design rationale:
    All auth logic in one file. Routers never parse headers or validate
    tokens directly — they receive a User object. To change auth behavior
    (add domain restrictions, roles, API keys), modify only this file.

    JWKS keys are cached in-memory with a 24h TTL. The azure-search-openai-demo
    reference fetches JWKS on every call (no cache) — we diverge intentionally
    to avoid a latency and reliability problem under load.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass

import httpx
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from fastapi import HTTPException, Request

try:
    from opentelemetry.trace import StatusCode
except ModuleNotFoundError:
    class StatusCode:
        """Fallback status code shim used when OTel is not installed."""

        ERROR = "ERROR"

from app.foundation.config import settings
from app.observability import get_tracer

# ── Logger + tracer ──────────────────────────────────────────────────────────
# Logger follows the project's dot-separated structured logging convention.
# Tracer wraps validation in an OTel span (noop when OTEL_EXPORT_TARGET="").

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# ── Multi-tenant issuer pattern ──────────────────────────────────────────────
# Entra ID v2.0 issuers follow this format. For multi-tenant (AUTH_TENANT_ID=common),
# we validate the format rather than the exact tenant GUID. For single-tenant, we
# exact-match the configured tenant.

_ISSUER_RE = re.compile(
    r"^https://login\.microsoftonline\.com/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/v2\.0$"
)


# ── User dataclass ───────────────────────────────────────────────────────────


@dataclass
class User:
    """Authenticated user identity extracted from JWT claims.

    Attributes:
        oid:   Entra object ID — globally unique per user. Used as session user_id.
        email: preferred_username claim — the user's email address.
        name:  Display name from token claims.

    Created by:
        get_current_user() — either from JWT claims or as anonymous fallback.

    Consumed by:
        routers/sessions.py — sets session.user_id = user.oid
        routers/chat.py — verifies session ownership
    """

    oid: str
    email: str
    name: str


# ── AuthError ────────────────────────────────────────────────────────────────


class AuthError(Exception):
    """Internal auth failure — converted to HTTPException(401) at the boundary.

    Attributes:
        message: Human-readable error description for logging.
        reason:  Machine-parseable reason code for structured logs.
    """

    def __init__(self, message: str, reason: str = "unknown"):
        super().__init__(message)
        self.reason = reason


# ── JWKS Cache ───────────────────────────────────────────────────────────────

# Cache TTL in seconds — 24 hours. OIDC spec recommends caching JWKS keys and
# refreshing on cache miss (key rotation) or periodic schedule.
_JWKS_TTL_SECONDS = 86400


async def _fetch_jwks_keys(tenant_id: str) -> dict:
    """Fetch JWKS keys from the Entra ID discovery endpoint.

    Args:
        tenant_id: Entra tenant ID or "common" for multi-tenant.

    Returns:
        JWKS JSON dict with "keys" array.

    Side effects:
        One outbound HTTPS request to login.microsoftonline.com.
    """
    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    t0 = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
    elapsed = round((time.monotonic() - t0) * 1000, 1)
    jwks = resp.json()
    logger.info(
        "auth.jwks.fetched",
        extra={
            "url": url,
            "key_count": len(jwks.get("keys", [])),
            "duration_ms": elapsed,
        },
    )
    return jwks


class _JWKSCache:
    """In-memory JWKS key cache with TTL-based refresh.

    Caches the full JWKS response (all keys) from the Entra ID discovery
    endpoint. Refreshes when the cache is older than _JWKS_TTL_SECONDS
    or when a requested kid is not found (handles key rotation).

    Lifecycle:
        Module-level singleton (_jwks_cache). Lives for the process lifetime.
        Thread-safe for asyncio (single event loop, no concurrent mutation).

    Design rationale:
        The azure-search-openai-demo reference fetches JWKS on every token
        validation call (no cache). This is a perf bug under load — every
        request triggers an HTTP call. We cache with 24h TTL instead.
    """

    def __init__(self) -> None:
        """Initialise empty cache."""
        self._keys: dict | None = None
        self._fetched_at: float = 0.0

    def clear(self) -> None:
        """Reset cache state. Used in tests."""
        self._keys = None
        self._fetched_at = 0.0

    def _is_expired(self) -> bool:
        """Check if cached keys are older than TTL."""
        return (time.monotonic() - self._fetched_at) > _JWKS_TTL_SECONDS

    async def get_keys(self, force_refresh: bool = False) -> dict:
        """Return cached JWKS keys, fetching if expired or forced.

        Args:
            force_refresh: Bypass cache (used on kid-miss for key rotation).

        Returns:
            JWKS dict with "keys" array.
        """
        if self._keys is not None and not self._is_expired() and not force_refresh:
            age = time.monotonic() - self._fetched_at
            logger.debug(
                "auth.jwks.cache_hit",
                extra={"age_hours": round(age / 3600, 1)},
            )
            return self._keys

        self._keys = await _fetch_jwks_keys(settings.auth_tenant_id)
        self._fetched_at = time.monotonic()
        return self._keys


# Module-level singleton — lives for the process lifetime.
_jwks_cache = _JWKSCache()


# ── Token Validation ─────────────────────────────────────────────────────────


def _build_rsa_pem(jwk: dict) -> bytes:
    """Construct an RSA PEM public key from a JWKS key entry.

    Args:
        jwk: A single key dict from the JWKS "keys" array with "n" and "e"
             base64url-encoded values per RFC 7517.

    Returns:
        PEM-encoded RSA public key bytes suitable for PyJWT verification.
    """
    # Pad base64url values — Python's b64decode requires padding
    n_b64 = jwk["n"] + "=="
    e_b64 = jwk["e"] + "=="
    n_int = int.from_bytes(base64.urlsafe_b64decode(n_b64), byteorder="big")
    e_int = int.from_bytes(base64.urlsafe_b64decode(e_b64), byteorder="big")
    pub_numbers = RSAPublicNumbers(e=e_int, n=n_int)
    pub_key = pub_numbers.public_key()
    return pub_key.public_bytes(
        encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
    )


def _validate_issuer(issuer: str, tid: str) -> None:
    """Validate the token's issuer claim against configured tenant.

    For multi-tenant (AUTH_TENANT_ID="common"): accepts any issuer matching
    the Entra ID v2.0 format (https://login.microsoftonline.com/{guid}/v2.0).

    For single-tenant (AUTH_TENANT_ID=<guid>): exact-matches the issuer
    against the configured tenant GUID.

    Args:
        issuer: The "iss" claim from the decoded JWT.
        tid: The "tid" claim from the decoded JWT (user's home tenant).

    Raises:
        AuthError: If the issuer doesn't match expectations.
    """
    if settings.auth_tenant_id == "common":
        # Multi-tenant: validate format only — accept any tenant GUID
        if not _ISSUER_RE.match(issuer):
            raise AuthError(
                f"Issuer {issuer} does not match Entra ID format",
                reason="bad_issuer",
            )
    else:
        # Single-tenant: exact match the configured tenant
        expected = f"https://login.microsoftonline.com/{settings.auth_tenant_id}/v2.0"
        if issuer != expected:
            raise AuthError(
                f"Issuer {issuer} does not match configured tenant {settings.auth_tenant_id}",
                reason="bad_issuer",
            )


async def _validate_token(token: str) -> dict:
    """Validate a JWT Bearer token against Entra ID JWKS and return claims.

    Validation steps:
        1. Fetch JWKS keys (from cache, refreshed every 24h)
        2. Find the signing key by kid from the JWT header
        3. Construct RSA public key from the JWKS n/e values
        4. Verify RS256 signature, audience, and expiry via PyJWT
        5. Validate issuer (multi-tenant format or single-tenant exact match)

    Args:
        token: Raw JWT string (without "Bearer " prefix).

    Returns:
        Decoded claims dict containing oid, preferred_username, name, tid, etc.

    Raises:
        HTTPException(401): On any validation failure (expired, bad signature,
        wrong audience, wrong issuer, unknown kid, malformed token).

    Side effects:
        - OTel span "auth.validate_token" with tenant_id and user_oid attributes
        - Structured log: auth.token.rejected on failure
    """
    with tracer.start_as_current_span("auth.validate_token") as span:
        t0 = time.monotonic()
        try:
            # Step 1: Decode header without verification to extract kid
            try:
                unverified_header = pyjwt.get_unverified_header(token)
            except pyjwt.exceptions.DecodeError as exc:
                raise AuthError("Malformed JWT — cannot decode header", reason="malformed") from exc

            kid = unverified_header.get("kid", "")

            # Step 2: Find matching key in JWKS
            jwks = await _jwks_cache.get_keys()
            matching_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    matching_key = key
                    break

            # If kid not found, force a refresh (key rotation scenario)
            if matching_key is None:
                jwks = await _jwks_cache.get_keys(force_refresh=True)
                for key in jwks.get("keys", []):
                    if key.get("kid") == kid:
                        matching_key = key
                        break

            if matching_key is None:
                raise AuthError(f"No JWKS key found for kid={kid}", reason="unknown_kid")

            # Step 3: Build PEM key from JWKS entry
            pem_key = _build_rsa_pem(matching_key)

            # Step 3b: Prepare signing key issuer check (multi-tenant hardening)
            # Microsoft JWKS keys include an "issuer" field. When it contains
            # {tenantid}, replace with the token's tid claim and exact-match.
            # When it's a specific tenant GUID, only accept tokens from that tenant.
            # Keys without an "issuer" field (legacy) skip this check.
            key_issuer = matching_key.get("issuer", "")
            if key_issuer:
                _unverified = pyjwt.decode(token, options={"verify_signature": False})
                _token_tid = _unverified.get("tid", "")
                _expected_key_issuer = key_issuer.replace("{tenantid}", _token_tid)
            else:
                _expected_key_issuer = None

            # Step 4: Verify signature, audience, expiry
            # Accept both bare client_id and api://<client_id> as audience
            valid_audiences = [
                settings.auth_client_id,
                f"api://{settings.auth_client_id}",
            ]
            claims = pyjwt.decode(
                token,
                pem_key,
                algorithms=["RS256"],
                audience=valid_audiences,
                options={"verify_iss": False},  # We validate issuer manually below
                leeway=10,  # 10-second leeway for clock skew (iat, nbf, exp)
            )

            # Step 5: Validate issuer (multi-tenant vs single-tenant)
            issuer = claims.get("iss", "")
            tid = claims.get("tid", "")
            _validate_issuer(issuer, tid)

            # Step 5b: Validate signing key issuer matches token issuer
            # Per Microsoft docs: keys with a specific tenant GUID issuer must
            # only be used for tokens from that exact tenant.
            if _expected_key_issuer and issuer != _expected_key_issuer:
                raise AuthError(
                    f"Token issuer {issuer} does not match signing key issuer {_expected_key_issuer}",
                    reason="key_issuer_mismatch",
                )

            # Set OTel span attributes on success
            span.set_attribute("auth.tenant_id", tid)
            span.set_attribute("auth.user_oid", claims.get("oid", ""))

            elapsed = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "auth.token.validated",
                extra={
                    "user_oid": claims.get("oid", ""),
                    "user_email": claims.get("preferred_username", ""),
                    "tenant_id": tid,
                    "duration_ms": elapsed,
                },
            )
            return claims

        except AuthError as exc:
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            logger.warning(
                "auth.token.rejected",
                extra={"reason": exc.reason, "duration_ms": elapsed},
            )
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        except pyjwt.ExpiredSignatureError as exc:
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            logger.warning(
                "auth.token.rejected",
                extra={"reason": "expired", "duration_ms": elapsed},
            )
            span.set_status(StatusCode.ERROR, "Token expired")
            raise HTTPException(status_code=401, detail="Token expired") from exc

        except pyjwt.InvalidAudienceError as exc:
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            logger.warning(
                "auth.token.rejected",
                extra={"reason": "bad_audience", "duration_ms": elapsed},
            )
            span.set_status(StatusCode.ERROR, "Invalid audience")
            raise HTTPException(status_code=401, detail="Invalid audience") from exc

        except pyjwt.PyJWTError as exc:
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            logger.warning(
                "auth.token.rejected",
                extra={"reason": "jwt_error", "duration_ms": elapsed},
            )
            span.set_status(StatusCode.ERROR, str(exc))
            raise HTTPException(status_code=401, detail=f"Token validation failed: {exc}") from exc

        except HTTPException:
            raise  # Re-raise HTTPExceptions without wrapping

        except Exception as exc:
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            logger.warning(
                "auth.token.rejected",
                extra={"reason": "unexpected", "duration_ms": elapsed},
            )
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise HTTPException(status_code=401, detail="Authentication failed") from exc


# ── FastAPI Dependency ───────────────────────────────────────────────────────


async def get_current_user(request: Request) -> User:
    """Extract authenticated user from the request.

    FastAPI ``Depends()`` callable — inject into route signatures as:
        ``user: User = Depends(get_current_user)``

    When AUTH_ENABLED=false:
        Returns User(oid="anonymous", email="dev@local", name="Developer")
        without inspecting headers. Zero-friction dev experience.

    When AUTH_ENABLED=true:
        Extracts "Authorization: Bearer <token>" → validates JWT via
        _validate_token() → returns User with real identity claims.

    Args:
        request: Starlette/FastAPI Request (injected by framework).

    Returns:
        User: Authenticated user identity.

    Raises:
        HTTPException(401): When auth is enabled and token is missing,
        malformed, expired, or fails validation.

    Side effects:
        Structured log: auth.anonymous (debug) or auth.token.validated (info)
                        or auth.token.rejected (warning).
    """
    # Ed25519 dev-sign side-channel: if the signed-request middleware verified
    # this request it attached a principal to the ASGI scope. Honour it before
    # the JWT path so headless probes work against an auth-gated deployment.
    devsign_principal = request.scope.get("devauth_user")
    if isinstance(devsign_principal, User):
        logger.info("auth.devsign.accepted", extra={"oid": devsign_principal.oid})
        return devsign_principal

    # Dev mode bypass — no token validation, no header inspection
    if not settings.auth_enabled:
        logger.debug("auth.anonymous", extra={"reason": "auth_disabled"})
        return User(oid="anonymous", email="dev@local", name="Developer")

    # Extract Bearer token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning(
            "auth.token.rejected",
            extra={"reason": "missing_header", "duration_ms": 0},
        )
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )

    token = auth_header[7:]  # Strip "Bearer " prefix
    if not token.strip():
        logger.warning(
            "auth.token.rejected",
            extra={"reason": "empty_token", "duration_ms": 0},
        )
        raise HTTPException(
            status_code=401,
            detail="Empty Bearer token",
        )

    # Validate JWT and extract claims
    claims = await _validate_token(token)

    return User(
        oid=claims.get("oid", ""),
        email=claims.get("preferred_username", ""),
        name=claims.get("name", ""),
    )
