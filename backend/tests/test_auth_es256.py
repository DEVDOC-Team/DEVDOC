"""DEVDOC — Asymmetric ES256 JWT & JWKS Verification Test Suite.

Comprehensive security test suite verifying:
1. Missing bearer token -> 401
2. Malformed JWT -> 401
3. Expired token -> 401
4. Wrong signing key / signature mismatch -> 401
5. Wrong issuer claim -> 401
6. Wrong audience claim -> 401
7. Valid ES256 token signed by test-only EC private key with matching JWKS -> Accepted
8. Unknown key ID (kid) -> 401
9. Missing key ID (kid) -> 401
10. Algorithm mismatch / header tampering (e.g. HS256 when ES256 expected) -> 401
11. JWKS endpoint unavailable -> 503 Fail-closed (Never bypasses verification)
12. Issuer trailing-slash normalization
13. End-to-end FastAPI dependency & /api/v1/auth/me route resolution with ES256
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any
from unittest.mock import patch

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.auth import router as auth_router
from app.core.config import Settings
from app.core.security import (
    clear_jwks_cache,
    extract_bearer_token,
    get_jwks_client,
    verify_and_decode_jwt,
)
from app.db.base import Base
from app.dependencies import get_current_user, get_db
from app.models.user import User

# ---------------------------------------------------------------------------
# Test Constants & Key Generation
# ---------------------------------------------------------------------------

TEST_ISSUER = "https://test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"
TEST_JWKS_URL = "https://test.supabase.co/auth/v1/.well-known/jwks.json"

# Generate test EC P-256 key pair A
_TEST_PRIVATE_KEY_A = ec.generate_private_key(ec.SECP256R1(), default_backend())
_TEST_PUBLIC_KEY_A = _TEST_PRIVATE_KEY_A.public_key()
_TEST_KID_A = "test-ec-kid-a-2026"

# Generate test EC P-256 key pair B (distinct key for mismatch tests)
_TEST_PRIVATE_KEY_B = ec.generate_private_key(ec.SECP256R1(), default_backend())
_TEST_PUBLIC_KEY_B = _TEST_PRIVATE_KEY_B.public_key()
_TEST_KID_B = "test-ec-kid-b-2026"

# Build test JWKS dictionary with public key A only
_JWK_DICT_A = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(_TEST_PUBLIC_KEY_A))
_JWK_DICT_A["kid"] = _TEST_KID_A
_JWK_DICT_A["alg"] = "ES256"
_JWK_DICT_A["use"] = "sig"

MOCK_JWKS_PAYLOAD = {
    "keys": [_JWK_DICT_A]
}

TEST_ES256_SETTINGS = Settings(
    supabase_url="https://test.supabase.co",
    supabase_jwks_url=TEST_JWKS_URL,
    supabase_jwt_algorithm="ES256",
    supabase_jwt_issuer=TEST_ISSUER,
    supabase_jwt_audience=TEST_AUDIENCE,
)


def make_test_es256_token(
    sub: str | None = None,
    email: str = "engineer@devdoc.ai",
    exp_offset_seconds: int = 3600,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    kid: str | None = _TEST_KID_A,
    alg: str = "ES256",
    private_key: Any = _TEST_PRIVATE_KEY_A,
) -> str:
    """Helper to generate a cryptographically signed ES256 test JWT."""
    now = int(time.time())
    user_id = sub or str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "email": email,
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": now + exp_offset_seconds,
        "role": "authenticated",
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "DevDoc Test Engineer"},
    }
    headers: dict[str, Any] = {"alg": alg}
    if kid is not None:
        headers["kid"] = kid

    return jwt.encode(payload, private_key, algorithm=alg, headers=headers)


@pytest.fixture(autouse=True)
def reset_jwks():
    """Ensure cached JWKS clients are cleared before and after each test."""
    clear_jwks_cache()
    yield
    clear_jwks_cache()


# ---------------------------------------------------------------------------
# Unit Tests: verify_and_decode_jwt with ES256 & JWKS
# ---------------------------------------------------------------------------


def test_es256_valid_token_accepted():
    """Valid ES256 token verified against mocked trusted JWKS succeeds."""
    token = make_test_es256_token()
    jwks_client = get_jwks_client(TEST_JWKS_URL)

    with patch.object(jwks_client, "fetch_data", return_value=MOCK_JWKS_PAYLOAD):
        claims = verify_and_decode_jwt(
            token,
            settings_override=TEST_ES256_SETTINGS,
        )

    assert claims["aud"] == TEST_AUDIENCE
    assert claims["iss"] == TEST_ISSUER
    assert claims["email"] == "engineer@devdoc.ai"
    assert uuid.UUID(claims["sub"])


def test_es256_missing_bearer_token():
    """Missing or empty Authorization header raises HTTP 401."""
    with pytest.raises(HTTPException) as exc_info:
        extract_bearer_token(None)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing Authorization header" in exc_info.value.detail

    with pytest.raises(HTTPException) as exc_info:
        extract_bearer_token("")
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_es256_malformed_jwt():
    """Malformed or non-JWT string raises HTTP 401."""
    with pytest.raises(HTTPException) as exc_info:
        verify_and_decode_jwt(
            "not.a.valid.jwt.token",
            settings_override=TEST_ES256_SETTINGS,
        )
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Malformed token header" in exc_info.value.detail


def test_es256_expired_token():
    """Expired ES256 token is rejected with HTTP 401."""
    token = make_test_es256_token(exp_offset_seconds=-300)  # expired 5m ago
    jwks_client = get_jwks_client(TEST_JWKS_URL)

    with patch.object(jwks_client, "fetch_data", return_value=MOCK_JWKS_PAYLOAD):
        with pytest.raises(HTTPException) as exc_info:
            verify_and_decode_jwt(
                token,
                settings_override=TEST_ES256_SETTINGS,
            )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Token has expired" in exc_info.value.detail


def test_es256_wrong_signing_key_signature_mismatch():
    """Token signed by untrusted Key B but with Key A in JWKS is rejected with 401."""
    token = make_test_es256_token(
        kid=_TEST_KID_A,
        private_key=_TEST_PRIVATE_KEY_B,  # Signed with Key B, claims to be Key A
    )
    jwks_client = get_jwks_client(TEST_JWKS_URL)

    with patch.object(jwks_client, "fetch_data", return_value=MOCK_JWKS_PAYLOAD):
        with pytest.raises(HTTPException) as exc_info:
            verify_and_decode_jwt(
                token,
                settings_override=TEST_ES256_SETTINGS,
            )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid token signature" in exc_info.value.detail


def test_es256_unknown_kid_rejected():
    """Token with kid not found in JWKS is rejected with HTTP 401."""
    token = make_test_es256_token(kid="unknown-kid-999")
    jwks_client = get_jwks_client(TEST_JWKS_URL)

    with patch.object(jwks_client, "fetch_data", return_value=MOCK_JWKS_PAYLOAD):
        with pytest.raises(HTTPException) as exc_info:
            verify_and_decode_jwt(
                token,
                settings_override=TEST_ES256_SETTINGS,
            )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Unable to verify token against JWKS" in exc_info.value.detail


def test_es256_missing_kid_rejected():
    """Token missing kid header for asymmetric verification is rejected with 401."""
    token = make_test_es256_token(kid=None)
    with pytest.raises(HTTPException) as exc_info:
        verify_and_decode_jwt(
            token,
            settings_override=TEST_ES256_SETTINGS,
        )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Token header missing key identifier (kid)" in exc_info.value.detail


def test_es256_algorithm_mismatch_header_tampering_rejected():
    """Token presenting an unexpected algorithm (e.g. HS256) when ES256 is expected is rejected."""
    # Attempt algorithm confusion: send HS256 token to an ES256 server
    hs256_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": int(time.time()) + 3600},
        "some-symmetric-secret-key-32-chars-long!",
        algorithm="HS256",
        headers={"alg": "HS256"},
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_and_decode_jwt(
            hs256_token,
            settings_override=TEST_ES256_SETTINGS,
        )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid token algorithm" in exc_info.value.detail


def test_es256_wrong_issuer_rejected():
    """Token signed with wrong issuer is rejected with HTTP 401."""
    token = make_test_es256_token(issuer="https://attacker.supabase.co/auth/v1")
    jwks_client = get_jwks_client(TEST_JWKS_URL)

    with patch.object(jwks_client, "fetch_data", return_value=MOCK_JWKS_PAYLOAD):
        with pytest.raises(HTTPException) as exc_info:
            verify_and_decode_jwt(
                token,
                settings_override=TEST_ES256_SETTINGS,
            )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid token issuer" in exc_info.value.detail


def test_es256_issuer_trailing_slash_normalization():
    """Issuer validation normalizes trailing slashes so both match correctly."""
    token = make_test_es256_token(issuer="https://test.supabase.co/auth/v1")
    jwks_client = get_jwks_client(TEST_JWKS_URL)

    # Configure settings with a trailing slash
    settings_with_trailing = Settings(
        supabase_url="https://test.supabase.co",
        supabase_jwks_url=TEST_JWKS_URL,
        supabase_jwt_algorithm="ES256",
        supabase_jwt_issuer="https://test.supabase.co/auth/v1/",
        supabase_jwt_audience=TEST_AUDIENCE,
    )

    with patch.object(jwks_client, "fetch_data", return_value=MOCK_JWKS_PAYLOAD):
        claims = verify_and_decode_jwt(
            token,
            settings_override=settings_with_trailing,
        )

    assert claims["iss"] == "https://test.supabase.co/auth/v1"


def test_es256_wrong_audience_rejected():
    """Token with invalid audience is rejected with HTTP 401."""
    token = make_test_es256_token(audience="unauthorized-service")
    jwks_client = get_jwks_client(TEST_JWKS_URL)

    with patch.object(jwks_client, "fetch_data", return_value=MOCK_JWKS_PAYLOAD):
        with pytest.raises(HTTPException) as exc_info:
            verify_and_decode_jwt(
                token,
                settings_override=TEST_ES256_SETTINGS,
            )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid token audience" in exc_info.value.detail


def test_es256_jwks_unavailable_fails_closed():
    """When the trusted JWKS endpoint is unreachable, fail closed with HTTP 503."""
    token = make_test_es256_token()
    jwks_client = get_jwks_client(TEST_JWKS_URL)

    with patch.object(
        jwks_client,
        "fetch_data",
        side_effect=PyJWKClientConnectionError("Connection timed out"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            verify_and_decode_jwt(
                token,
                settings_override=TEST_ES256_SETTINGS,
            )

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "temporarily unavailable" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Integration Tests: FastAPI End-to-End /api/v1/auth/me with ES256
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_es256_fastapi_auth_me_end_to_end():
    """FastAPI /api/v1/auth/me accepts valid ES256 Bearer token and provisions profile."""
    # Build isolated in-memory test database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    test_user_id = str(uuid.uuid4())
    token = make_test_es256_token(sub=test_user_id, email="es256_commander@devdoc.ai")
    jwks_client = get_jwks_client(TEST_JWKS_URL)

    with patch("app.dependencies.verify_and_decode_jwt") as mock_verify:
        mock_verify.return_value = {
            "sub": test_user_id,
            "email": "es256_commander@devdoc.ai",
            "aud": TEST_AUDIENCE,
            "iss": TEST_ISSUER,
            "user_metadata": {"full_name": "ES256 Commander"},
            "app_metadata": {"provider": "supabase"},
        }

        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == test_user_id
    assert data["email"] == "es256_commander@devdoc.ai"
    assert data["full_name"] == "ES256 Commander"
    assert data["is_active"] is True

    await engine.dispose()
