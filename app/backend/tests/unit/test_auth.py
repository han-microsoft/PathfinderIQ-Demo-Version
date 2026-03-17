"""Unit tests for app.auth — JWT validation, User model, get_current_user.

Test layer: unit (no I/O, no network, mocked JWKS).
All tests use a locally-generated RSA key pair and sign real JWTs with PyJWT.
The JWKS endpoint is mocked via monkeypatch — no HTTP calls leave the process.

Follows the project's test convention:
    - asyncio_mode = "auto" (no @pytest.mark.asyncio needed)
    - Markers: @pytest.mark.unit
    - Fixtures in this file (auth-specific) + conftest.py (shared)
"""

import base64
import time
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.testclient import TestClient

pytestmark = pytest.mark.unit

# ── Test Constants ───────────────────────────────────────────────────────────

TEST_CLIENT_ID = "test-client-id-00000000"
TEST_TENANT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_TENANT_ID = "11111111-2222-3333-4444-555555555555"
TEST_OID = "user-oid-12345678"
TEST_EMAIL = "testuser@contoso.com"
TEST_NAME = "Test User"
TEST_KID = "test-signing-key-1"


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_jwks_cache():
    """Clear the JWKS cache before each test to prevent cross-contamination."""
    from app.auth import _jwks_cache

    _jwks_cache.clear()
    yield
    _jwks_cache.clear()


@pytest.fixture
def rsa_private_key():
    """Generate a fresh RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def rsa_public_numbers(rsa_private_key):
    """Extract RSA public key numbers (n, e) for JWKS mock response."""
    pub = rsa_private_key.public_key().public_numbers()
    return pub


@pytest.fixture
def jwks_response(rsa_public_numbers):
    """Build a JWKS JSON response matching the test key pair.

    Returns a dict shaped like Microsoft's OIDC discovery endpoint response.
    The 'n' and 'e' values are base64url-encoded per RFC 7517.
    """
    n_bytes = rsa_public_numbers.n.to_bytes(
        (rsa_public_numbers.n.bit_length() + 7) // 8, byteorder="big"
    )
    e_bytes = rsa_public_numbers.e.to_bytes(
        (rsa_public_numbers.e.bit_length() + 7) // 8, byteorder="big"
    )
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": TEST_KID,
                "n": base64.urlsafe_b64encode(n_bytes).rstrip(b"=").decode(),
                "e": base64.urlsafe_b64encode(e_bytes).rstrip(b"=").decode(),
                "alg": "RS256",
            }
        ]
    }


@pytest.fixture
def make_token(rsa_private_key):
    """Factory fixture — creates RS256-signed JWTs with customisable claims.

    Default claims produce a valid multi-tenant Entra ID access token
    targeting TEST_CLIENT_ID. Override any claim via claims_override.
    """
    # Serialise private key to PEM for PyJWT
    pem = rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    def _make(claims_override: dict | None = None, kid: str = TEST_KID):
        now = int(time.time())
        base_claims = {
            "aud": TEST_CLIENT_ID,
            "iss": f"https://login.microsoftonline.com/{TEST_TENANT_ID}/v2.0",
            "iat": now,
            "nbf": now,
            "exp": now + 3600,  # 1 hour from now
            "oid": TEST_OID,
            "preferred_username": TEST_EMAIL,
            "name": TEST_NAME,
            "tid": TEST_TENANT_ID,
            "sub": str(uuid.uuid4()),
            "ver": "2.0",
        }
        if claims_override:
            base_claims.update(claims_override)
        return pyjwt.encode(
            base_claims, pem, algorithm="RS256", headers={"kid": kid}
        )

    return _make


@pytest.fixture
def mock_jwks_fetch(jwks_response):
    """Patch the JWKS fetch in auth.py to return the test JWKS without HTTP.

    Returns a context-manager-style mock. The mock is applied by patching
    the internal _fetch_jwks_keys function in the auth module.
    """
    return jwks_response


@pytest.fixture
def auth_settings_enabled(monkeypatch):
    """Configure settings for auth-enabled mode.

    Patches the settings singleton in app.config to enable auth with
    test client ID and multi-tenant (common).
    """
    monkeypatch.setenv("LLM_PROVIDER", "echo")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("AUTH_TENANT_ID", "common")


@pytest.fixture
def auth_settings_disabled(monkeypatch):
    """Configure settings for auth-disabled mode (default dev experience)."""
    monkeypatch.setenv("LLM_PROVIDER", "echo")
    monkeypatch.setenv("AUTH_ENABLED", "false")


@pytest.fixture
def auth_settings_single_tenant(monkeypatch):
    """Configure settings for single-tenant auth mode."""
    monkeypatch.setenv("LLM_PROVIDER", "echo")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("AUTH_TENANT_ID", TEST_TENANT_ID)


# ── Helper ───────────────────────────────────────────────────────────────────


def _make_request(headers: dict | None = None):
    """Build a minimal mock Starlette Request with given headers."""
    mock_request = MagicMock()
    mock_request.headers = headers or {}
    return mock_request


# ── Tests: User model ───────────────────────────────────────────────────────


class TestUserModel:
    """Tests for the User dataclass."""

    def test_user_fields(self):
        """User stores oid, email, name as string fields."""
        from app.auth import User

        user = User(oid="abc", email="x@y.com", name="X Y")
        assert user.oid == "abc"
        assert user.email == "x@y.com"
        assert user.name == "X Y"


# ── Tests: Config validator ─────────────────────────────────────────────────


class TestConfigValidator:
    """Tests for the auth config model_validator on Settings."""

    def test_config_validator_rejects_enabled_without_client_id(self, monkeypatch):
        """AUTH_ENABLED=true + AUTH_CLIENT_ID='' → ValueError at startup."""
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("AUTH_CLIENT_ID", "")
        monkeypatch.setenv("LLM_PROVIDER", "echo")
        # Must re-instantiate Settings to trigger the validator
        from app.foundation.config import Settings

        with pytest.raises(ValueError, match="AUTH_ENABLED=true requires AUTH_CLIENT_ID"):
            Settings()

    def test_config_validator_accepts_enabled_with_client_id(self, monkeypatch):
        """AUTH_ENABLED=true + AUTH_CLIENT_ID=<value> → no error."""
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("AUTH_CLIENT_ID", TEST_CLIENT_ID)
        monkeypatch.setenv("LLM_PROVIDER", "echo")
        from app.foundation.config import Settings

        s = Settings()
        assert s.auth_enabled is True
        assert s.auth_client_id == TEST_CLIENT_ID

    def test_config_validator_accepts_disabled_without_client_id(self, monkeypatch):
        """AUTH_ENABLED=false + AUTH_CLIENT_ID='' → no error (default dev)."""
        monkeypatch.setenv("AUTH_ENABLED", "false")
        monkeypatch.setenv("AUTH_CLIENT_ID", "")
        monkeypatch.setenv("LLM_PROVIDER", "echo")
        from app.foundation.config import Settings

        s = Settings()
        assert s.auth_enabled is False

    def test_config_rejects_default_empty_client_id_when_enabled(self, monkeypatch):
        """AUTH_ENABLED=true without explicit AUTH_CLIENT_ID → ValueError.

        Verifies that the default auth_client_id is empty string, so
        deployers must explicitly set AUTH_CLIENT_ID when auth is enabled.
        """
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("LLM_PROVIDER", "echo")
        # Do NOT set AUTH_CLIENT_ID — relies on default being ""
        monkeypatch.delenv("AUTH_CLIENT_ID", raising=False)
        from app.foundation.config import Settings

        with pytest.raises(ValueError, match="AUTH_ENABLED=true requires AUTH_CLIENT_ID"):
            Settings()

    def test_config_accepts_disabled_without_client_id_default(self, monkeypatch):
        """AUTH_ENABLED=false with default empty AUTH_CLIENT_ID → OK."""
        monkeypatch.setenv("AUTH_ENABLED", "false")
        monkeypatch.setenv("LLM_PROVIDER", "echo")
        monkeypatch.delenv("AUTH_CLIENT_ID", raising=False)
        from app.foundation.config import Settings

        s = Settings()
        assert s.auth_client_id == ""


# ── Tests: get_current_user — auth disabled ─────────────────────────────────


class TestGetCurrentUserDisabled:
    """Tests for get_current_user when AUTH_ENABLED=false."""

    async def test_anonymous_user_when_disabled(self):
        """AUTH_ENABLED=false → returns anonymous User regardless of headers."""
        from app.auth import User, get_current_user

        # Patch settings at the module level inside auth
        with patch("app.auth.settings") as mock_settings:
            mock_settings.auth_enabled = False
            request = _make_request()
            user = await get_current_user(request)
            assert isinstance(user, User)
            assert user.oid == "anonymous"
            assert user.email == "dev@local"
            assert user.name == "Developer"

    async def test_anonymous_ignores_auth_header(self):
        """AUTH_ENABLED=false → ignores any Authorization header present."""
        from app.auth import User, get_current_user

        with patch("app.auth.settings") as mock_settings:
            mock_settings.auth_enabled = False
            request = _make_request({"Authorization": "Bearer some-token"})
            user = await get_current_user(request)
            assert user.oid == "anonymous"


# ── Tests: get_current_user — auth enabled, header parsing ──────────────────


class TestGetCurrentUserHeaderParsing:
    """Tests for header extraction when AUTH_ENABLED=true."""

    async def test_missing_auth_header_raises_401(self):
        """No Authorization header → HTTPException 401."""
        from app.auth import get_current_user

        with patch("app.auth.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.auth_client_id = TEST_CLIENT_ID
            mock_settings.auth_tenant_id = "common"
            request = _make_request({})
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request)
            assert exc_info.value.status_code == 401

    async def test_malformed_bearer_raises_401(self):
        """Authorization: Basic xxx → HTTPException 401."""
        from app.auth import get_current_user

        with patch("app.auth.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.auth_client_id = TEST_CLIENT_ID
            mock_settings.auth_tenant_id = "common"
            request = _make_request({"Authorization": "Basic abc123"})
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request)
            assert exc_info.value.status_code == 401

    async def test_empty_bearer_raises_401(self):
        """Authorization: Bearer (no token) → HTTPException 401."""
        from app.auth import get_current_user

        with patch("app.auth.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.auth_client_id = TEST_CLIENT_ID
            mock_settings.auth_tenant_id = "common"
            request = _make_request({"Authorization": "Bearer "})
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request)
            assert exc_info.value.status_code == 401


# ── Tests: JWT validation ───────────────────────────────────────────────────


class TestJWTValidation:
    """Tests for _validate_token — JWT signature, audience, issuer, expiry."""

    async def test_valid_token_extracts_claims(self, make_token, jwks_response):
        """Valid RS256 JWT → returns claims dict with oid, email, name."""
        from app.auth import _validate_token

        token = make_token()
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                claims = await _validate_token(token)
                assert claims["oid"] == TEST_OID
                assert claims["preferred_username"] == TEST_EMAIL
                assert claims["name"] == TEST_NAME

    async def test_expired_token_raises_401(self, make_token, jwks_response):
        """JWT with past exp claim → HTTPException 401."""
        from app.auth import _validate_token

        token = make_token({"exp": int(time.time()) - 3600})
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                with pytest.raises(HTTPException) as exc_info:
                    await _validate_token(token)
                assert exc_info.value.status_code == 401

    async def test_bad_audience_raises_401(self, make_token, jwks_response):
        """JWT with wrong audience → HTTPException 401."""
        from app.auth import _validate_token

        token = make_token({"aud": "wrong-client-id"})
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                with pytest.raises(HTTPException) as exc_info:
                    await _validate_token(token)
                assert exc_info.value.status_code == 401

    async def test_api_prefixed_audience_accepted(self, make_token, jwks_response):
        """JWT with aud=api://<client_id> → accepted."""
        from app.auth import _validate_token

        token = make_token({"aud": f"api://{TEST_CLIENT_ID}"})
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                claims = await _validate_token(token)
                assert claims["oid"] == TEST_OID

    async def test_bad_issuer_raises_401(self, make_token, jwks_response):
        """JWT with non-Entra issuer → HTTPException 401."""
        from app.auth import _validate_token

        token = make_token({"iss": "https://evil.example.com/v2.0"})
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                with pytest.raises(HTTPException) as exc_info:
                    await _validate_token(token)
                assert exc_info.value.status_code == 401

    async def test_multi_tenant_accepts_any_tenant_issuer(
        self, make_token, jwks_response
    ):
        """AUTH_TENANT_ID=common → accepts token from any tenant."""
        from app.auth import _validate_token

        # Token from OTHER_TENANT_ID, but we're in multi-tenant mode
        token = make_token({
            "iss": f"https://login.microsoftonline.com/{OTHER_TENANT_ID}/v2.0",
            "tid": OTHER_TENANT_ID,
        })
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                claims = await _validate_token(token)
                assert claims["tid"] == OTHER_TENANT_ID

    async def test_single_tenant_rejects_other_tenant(
        self, make_token, jwks_response
    ):
        """AUTH_TENANT_ID=<guid> → rejects token from a different tenant."""
        from app.auth import _validate_token

        # Token from OTHER_TENANT_ID, but we configured TEST_TENANT_ID
        token = make_token({
            "iss": f"https://login.microsoftonline.com/{OTHER_TENANT_ID}/v2.0",
            "tid": OTHER_TENANT_ID,
        })
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = TEST_TENANT_ID
                with pytest.raises(HTTPException) as exc_info:
                    await _validate_token(token)
                assert exc_info.value.status_code == 401

    async def test_single_tenant_accepts_own_tenant(
        self, make_token, jwks_response
    ):
        """AUTH_TENANT_ID=<guid> → accepts token from the configured tenant."""
        from app.auth import _validate_token

        token = make_token({
            "iss": f"https://login.microsoftonline.com/{TEST_TENANT_ID}/v2.0",
            "tid": TEST_TENANT_ID,
        })
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = TEST_TENANT_ID
                claims = await _validate_token(token)
                assert claims["oid"] == TEST_OID

    async def test_unknown_kid_raises_401(self, make_token, jwks_response):
        """JWT signed with unknown kid → HTTPException 401."""
        from app.auth import _validate_token

        token = make_token(kid="unknown-kid-999")
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                with pytest.raises(HTTPException) as exc_info:
                    await _validate_token(token)
                assert exc_info.value.status_code == 401


# ── Tests: JWKS cache ───────────────────────────────────────────────────────


class TestJWKSCache:
    """Tests for the JWKS key caching mechanism."""

    async def test_jwks_cache_skips_refetch(self, jwks_response):
        """Second call within 24h uses cached keys — no HTTP call."""
        from app.auth import _jwks_cache

        # Reset cache state
        _jwks_cache.clear()

        mock_fetch = AsyncMock(return_value=jwks_response)
        with patch("app.auth._fetch_jwks_keys", mock_fetch):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_tenant_id = "common"
                # First call — should fetch
                keys1 = await _jwks_cache.get_keys()
                assert mock_fetch.call_count == 1
                # Second call — should use cache
                keys2 = await _jwks_cache.get_keys()
                assert mock_fetch.call_count == 1  # No additional call
                assert keys1 == keys2

    async def test_jwks_cache_refreshes_after_ttl(self, jwks_response):
        """Cache older than 24h triggers a fresh fetch."""
        from app.auth import _jwks_cache

        _jwks_cache.clear()

        mock_fetch = AsyncMock(return_value=jwks_response)
        with patch("app.auth._fetch_jwks_keys", mock_fetch):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_tenant_id = "common"
                await _jwks_cache.get_keys()
                assert mock_fetch.call_count == 1
                # Simulate TTL expiry by backdating the timestamp
                _jwks_cache._fetched_at = time.monotonic() - 90000  # 25 hours ago
                await _jwks_cache.get_keys()
                assert mock_fetch.call_count == 2


# ── Tests: get_current_user end-to-end (auth enabled) ───────────────────────


class TestGetCurrentUserE2E:
    """End-to-end tests: header → JWT validation → User object."""

    async def test_valid_token_returns_user(self, make_token, jwks_response):
        """Full flow: valid Bearer token → User with correct fields."""
        from app.auth import User, get_current_user

        token = make_token()
        request = _make_request({"Authorization": f"Bearer {token}"})

        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_enabled = True
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                user = await get_current_user(request)
                assert isinstance(user, User)
                assert user.oid == TEST_OID
                assert user.email == TEST_EMAIL
                assert user.name == TEST_NAME

    async def test_garbage_token_raises_401(self):
        """Bearer with garbage string → HTTPException 401."""
        from app.auth import get_current_user

        request = _make_request({"Authorization": "Bearer not-a-jwt"})

        with patch("app.auth.settings") as mock_settings:
            mock_settings.auth_enabled = True
            mock_settings.auth_client_id = TEST_CLIENT_ID
            mock_settings.auth_tenant_id = "common"
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request)
            assert exc_info.value.status_code == 401


# ── Tests: JWKS key issuer validation (multi-tenant hardening) ───────────────


class TestJWKSKeyIssuerValidation:
    """Tests for signing key issuer validation per Microsoft multi-tenant docs."""

    def _build_jwks_with_issuer(self, rsa_public_numbers, issuer_value):
        """Helper: build a JWKS response with an issuer field on the key."""
        n_bytes = rsa_public_numbers.n.to_bytes(
            (rsa_public_numbers.n.bit_length() + 7) // 8, byteorder="big"
        )
        e_bytes = rsa_public_numbers.e.to_bytes(
            (rsa_public_numbers.e.bit_length() + 7) // 8, byteorder="big"
        )
        return {
            "keys": [{
                "kty": "RSA", "use": "sig", "kid": TEST_KID,
                "n": base64.urlsafe_b64encode(n_bytes).rstrip(b"=").decode(),
                "e": base64.urlsafe_b64encode(e_bytes).rstrip(b"=").decode(),
                "alg": "RS256",
                "issuer": issuer_value,
            }]
        }

    async def test_multi_tenant_accepts_matching_key_issuer(
        self, make_token, rsa_public_numbers
    ):
        """JWKS key issuer with {tenantid} template matches token tid."""
        from app.auth import _validate_token

        jwks = self._build_jwks_with_issuer(
            rsa_public_numbers,
            "https://login.microsoftonline.com/{tenantid}/v2.0",
        )
        token = make_token()
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                claims = await _validate_token(token)
                assert claims["oid"] == TEST_OID

    async def test_multi_tenant_rejects_mismatched_key_issuer(
        self, make_token, rsa_public_numbers
    ):
        """JWKS key scoped to OTHER_TENANT_ID rejects token from TEST_TENANT_ID."""
        from app.auth import _validate_token

        jwks = self._build_jwks_with_issuer(
            rsa_public_numbers,
            f"https://login.microsoftonline.com/{OTHER_TENANT_ID}/v2.0",
        )
        token = make_token()
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                with pytest.raises(HTTPException):
                    await _validate_token(token)

    async def test_key_without_issuer_field_still_accepted(
        self, make_token, jwks_response
    ):
        """JWKS key without 'issuer' field (old format) → accepted (backward compat)."""
        from app.auth import _validate_token

        token = make_token()
        with patch("app.auth._fetch_jwks_keys", new_callable=AsyncMock, return_value=jwks_response):
            with patch("app.auth.settings") as mock_settings:
                mock_settings.auth_client_id = TEST_CLIENT_ID
                mock_settings.auth_tenant_id = "common"
                claims = await _validate_token(token)
                assert claims["oid"] == TEST_OID


# ── Tests: Middleware OID extraction ─────────────────────────────────────────


class TestMiddlewareOIDExtraction:
    """Tests for _middleware._extract_user_oid — lightweight JWT peek."""

    def test_no_token_auth_enabled_returns_none(self):
        """Auth enabled, no Bearer header → None."""
        from app._middleware import _extract_user_oid

        with patch("app._middleware.settings") as mock:
            mock.auth_enabled = True
            request = _make_request({})
            assert _extract_user_oid(request) is None

    def test_no_token_auth_disabled_returns_anonymous(self):
        """Auth disabled, no Bearer header → 'anonymous'."""
        from app._middleware import _extract_user_oid

        with patch("app._middleware.settings") as mock:
            mock.auth_enabled = False
            request = _make_request({})
            assert _extract_user_oid(request) == "anonymous"

    def test_malformed_jwt_returns_none(self):
        """Bearer with garbage → None, no crash."""
        from app._middleware import _extract_user_oid

        with patch("app._middleware.settings") as mock:
            mock.auth_enabled = True
            request = _make_request({"authorization": "Bearer not.a.valid.jwt"})
            result = _extract_user_oid(request)
            assert result is None or isinstance(result, str)

    def test_valid_jwt_extracts_oid(self, make_token):
        """Bearer with valid JWT → extracts oid claim."""
        from app._middleware import _extract_user_oid

        with patch("app._middleware.settings") as mock:
            mock.auth_enabled = True
            token = make_token()
            request = _make_request({"authorization": f"Bearer {token}"})
            oid = _extract_user_oid(request)
            assert oid == TEST_OID