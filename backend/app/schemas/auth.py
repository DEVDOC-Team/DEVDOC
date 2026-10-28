"""Authentication schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.schemas.user import UserResponse


class TokenPayload(BaseModel):
    sub: uuid.UUID
    email: str | None = None
    exp: int
    aud: str | None = None
    iss: str | None = None
    role: str | None = None


class AuthSyncResponse(BaseModel):
    success: bool = True
    message: str
    user: UserResponse


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    user: dict | None = None


class OAuthAuthorizeUrlResponse(BaseModel):
    provider: str
    authorization_url: str
    redirect_to: str


class OAuthExchangeRequest(BaseModel):
    auth_code: str
    code_verifier: str | None = None
    redirect_to: str | None = None


class OAuthProviderInfo(BaseModel):
    id: str
    name: str
    enabled: bool
