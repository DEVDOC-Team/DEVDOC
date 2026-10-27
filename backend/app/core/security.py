"""Authentication and cryptographic security utilities.

Provides secure Supabase JWT verification, Bearer token extraction,
and claims validation.
"""

from __future__ import annotations

import uuid
from typing import Any

import jwt
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import logger


def extract_bearer_token(authorization_header: str | None) -> str:
    """Extract and validate the Bearer token from the Authorization header.

    Raises:
        HTTPException(401): If header is missing, malformed, or token is empty.
    """
    if not authorization_header or not authorization_header.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token

# Module-level cache for PyJWKClient instances keyed by JWKS URL
_JWKS_CLIENTS: dict[str, jwt.PyJWKClient] = {}


def get_jwks_client(jwks_url: str, timeout: int = 10, lifespan: int = 300) -> jwt.PyJWKClient:
    """Retrieve or initialize a cached PyJWKClient instance for the given JWKS URL."""
    if jwks_url not in _JWKS_CLIENTS:
        _JWKS_CLIENTS[jwks_url] = jwt.PyJWKClient(
            jwks_url,
            cache_keys=True,
            max_cached_keys=16,
            lifespan=lifespan,
            timeout=timeout,
        )
    return _JWKS_CLIENTS[jwks_url]


def clear_jwks_cache() -> None:
    """Clear cached JWKS clients (primarily for testing and key rotations)."""
    _JWKS_CLIENTS.clear()


def verify_and_decode_jwt(
    token: str,
    secret: str | None = None,
    algorithm: str | None = None,
    audience: str | None = None,
    issuer: str | None = None,
    settings_override: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Cryptographically verify and decode a Supabase JWT access token.

    Validates:
    - Cryptographic signature (never skipped or bypassed)
    - Algorithm strictly matches the explicitly configured expected algorithm (ES256 or HS256)
    - Expiration time (exp)
    - Subject claim (sub) as valid UUID
    - Audience (aud) when configured
    - Issuer (iss) when configured (normalized without trailing slashes)

    Args:
        token: Raw JWT string
        secret: Optional secret override for HS256
        algorithm: Optional algorithm override (defaults to settings.supabase_jwt_algorithm)
        audience: Optional audience override (defaults to settings.supabase_jwt_audience)
        issuer: Optional issuer override (defaults to settings.supabase_jwt_issuer)
        settings_override: Optional configuration settings object for tests

    Returns:
        dict containing verified claims.

    Raises:
        HTTPException(401): On expired, malformed, invalid tokens, untrusted kid, or signature failures.
        HTTPException(500): If signing keys/JWKS endpoints are misconfigured.
        HTTPException(503): If the trusted JWKS endpoint is unreachable/unavailable.
    """
    if not token or not isinstance(token, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token parameter",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Determine key and expected algorithm
    cfg = settings_override or kwargs.get("settings") or settings
    expected_alg = (
        algorithm
        or getattr(cfg, "supabase_jwt_algorithm", "ES256")
        or "ES256"
    ).upper()

    if expected_alg not in ("ES256", "HS256"):
        logger.error("Configured JWT algorithm %s is not supported", expected_alg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service misconfigured: unsupported algorithm",
        )

    jwt_audience = audience if audience is not None else getattr(cfg, "supabase_jwt_audience", None)
    raw_issuer = issuer if issuer is not None else getattr(cfg, "supabase_jwt_issuer", None)
    if not raw_issuer:
        supabase_url = getattr(cfg, "supabase_url", None)
        if supabase_url:
            raw_issuer = f"{supabase_url.rstrip('/')}/auth/v1"
    jwt_issuer = raw_issuer.rstrip("/") if raw_issuer else None

    # Inspect token header without verifying signature to check alg and kid
    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:
        logger.warning("Failed to parse JWT header: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token header",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    token_alg = header.get("alg")
    if not token_alg or token_alg.upper() != expected_alg:
        logger.warning(
            "Token algorithm %s does not match expected algorithm %s",
            token_alg,
            expected_alg,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token algorithm",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Resolve signing key strictly based on the configured expected algorithm
    key: Any = None
    if expected_alg == "ES256":
        kid = header.get("kid")
        if not kid:
            logger.warning("Token missing kid header for asymmetric verification")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token header missing key identifier (kid)",
                headers={"WWW-Authenticate": "Bearer"},
            )

        jwks_url = getattr(cfg, "supabase_jwks_url", None)
        if not jwks_url:
            supabase_url = getattr(cfg, "supabase_url", None)
            if supabase_url:
                jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

        if not jwks_url:
            logger.error("No JWKS endpoint or Supabase URL configured for ES256 verification")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service misconfigured: missing JWKS configuration",
            )

        try:
            jwks_client = get_jwks_client(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            key = signing_key.key
        except jwt.exceptions.PyJWKClientConnectionError as exc:
            logger.error("Failed to connect to JWKS endpoint: %s", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except jwt.exceptions.PyJWKClientError as exc:
            logger.warning("JWKS key lookup failed for token kid %s: %s", kid, type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to verify token against JWKS",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except Exception as exc:
            logger.warning("Unexpected error retrieving JWKS key: %s", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to verify token signature",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    elif expected_alg == "HS256":
        jwt_secret = secret or (
            cfg.supabase_jwt_secret.get_secret_value()
            if getattr(cfg, "supabase_jwt_secret", None)
            else None
        )
        if not jwt_secret:
            logger.error("SUPABASE_JWT_SECRET is not configured for HMAC verification")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service misconfigured: missing verification secret",
            )
        key = jwt_secret

    # 2. Cryptographic signature and claim verification
    decode_options = {
        "verify_signature": True,
        "require": ["sub", "exp"],
        "verify_exp": True,
        "verify_aud": bool(jwt_audience),
        "verify_iss": bool(jwt_issuer),
    }

    try:
        payload = jwt.decode(
            token,
            key=key,
            algorithms=[expected_alg],
            audience=jwt_audience if jwt_audience else None,
            issuer=jwt_issuer if jwt_issuer else None,
            options=decode_options,
        )
    except jwt.ExpiredSignatureError as exc:
        logger.info("Authentication failed: token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.MissingRequiredClaimError as exc:
        logger.warning("Authentication failed: missing required claim (%s)", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token missing required claim: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidAudienceError as exc:
        logger.warning("Authentication failed: invalid audience claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token audience",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidIssuerError as exc:
        logger.warning("Authentication failed: invalid issuer claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidSignatureError as exc:
        logger.warning("Authentication failed: invalid token signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (jwt.DecodeError, jwt.InvalidTokenError) as exc:
        logger.warning("Authentication failed: decode error (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # 3. Validate subject claim as a valid UUID
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        uuid.UUID(str(sub))
    except ValueError as exc:
        logger.warning("Authentication failed: subject is not a valid UUID")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier in token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return payload
