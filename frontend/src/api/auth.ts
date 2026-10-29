import { apiClient, type RequestOptions } from './client';
import type {
  AuthSyncResponse,
  HealthResponse,
  LoginRequest,
  LoginResponse,
  OAuthAuthorizeUrlResponse,
  OAuthExchangeRequest,
  OAuthProvider,
  OAuthProviderInfo,
  ReadinessResponse,
  User,
} from './types';

/**
 * Sign in using email and password against the backend Supabase Auth endpoint.
 * Endpoint: POST /api/v1/auth/login
 */
export async function loginWithPassword(
  credentials: LoginRequest,
  options?: RequestOptions
): Promise<LoginResponse> {
  return apiClient<LoginResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
    ...options,
  });
}

/**
 * Request an authorization URL for Google or GitHub OAuth from backend.
 * Endpoint: GET /api/v1/auth/oauth/{provider}/url
 */
export async function getOAuthAuthorizeUrl(
  provider: OAuthProvider,
  redirectTo?: string,
  codeChallenge?: string,
  options?: RequestOptions
): Promise<OAuthAuthorizeUrlResponse> {
  const query = new URLSearchParams();
  if (redirectTo) {
    query.set('redirect_to', redirectTo);
  }
  if (codeChallenge) {
    query.set('code_challenge', codeChallenge);
  }
  const qs = query.toString();
  return apiClient<OAuthAuthorizeUrlResponse>(
    `/api/v1/auth/oauth/${provider}/url${qs ? `?${qs}` : ''}`,
    {
      method: 'GET',
      ...options,
    }
  );
}

/**
 * Exchange an OAuth authorization code or PKCE token with Supabase Auth via the backend.
 * Endpoint: POST /api/v1/auth/oauth/exchange
 */
export async function exchangeOAuthCode(
  payload: OAuthExchangeRequest,
  options?: RequestOptions
): Promise<LoginResponse> {
  return apiClient<LoginResponse>('/api/v1/auth/oauth/exchange', {
    method: 'POST',
    body: JSON.stringify(payload),
    ...options,
  });
}

/**
 * Fetch supported OAuth providers and configuration readiness.
 * Endpoint: GET /api/v1/auth/oauth/providers
 */
export async function listOAuthProviders(
  options?: RequestOptions
): Promise<OAuthProviderInfo[]> {
  return apiClient<OAuthProviderInfo[]>('/api/v1/auth/oauth/providers', {
    method: 'GET',
    ...options,
  });
}

/**
 * Retrieve the current authenticated user's profile.
 * Endpoint: GET /api/v1/auth/me (or /api/v1/users/me)
 */
export async function getMyProfile(options?: RequestOptions): Promise<User> {
  return apiClient<User>('/api/v1/auth/me', {
    method: 'GET',
    ...options,
  });
}

/**
 * Synchronize current Supabase JWT session with public.users.
 * Endpoint: POST /api/v1/auth/sync
 */
export async function syncProfile(options?: RequestOptions): Promise<AuthSyncResponse> {
  return apiClient<AuthSyncResponse>('/api/v1/auth/sync', {
    method: 'POST',
    ...options,
  });
}

/**
 * Check backend liveness.
 * Endpoint: GET /api/v1/health
 */
export async function checkHealth(options?: RequestOptions): Promise<HealthResponse> {
  return apiClient<HealthResponse>('/api/v1/health', {
    method: 'GET',
    ...options,
  });
}

/**
 * Check backend readiness (database connectivity).
 * Endpoint: GET /api/v1/ready
 */
export async function checkReadiness(options?: RequestOptions): Promise<ReadinessResponse> {
  return apiClient<ReadinessResponse>('/api/v1/ready', {
    method: 'GET',
    ...options,
  });
}

/**
 * Verify project access authorization for the current user.
 * Endpoint: GET /api/v1/auth/projects/{project_id}/verify-access
 */
export async function verifyProjectAccess(
  projectId: string,
  options?: RequestOptions
): Promise<{ success: boolean; project_id: string; project_name: string; owner_id: string; caller_id: string }> {
  return apiClient(`/api/v1/auth/projects/${projectId}/verify-access`, {
    method: 'GET',
    ...options,
  });
}
