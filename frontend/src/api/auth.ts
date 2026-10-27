import { apiClient, type RequestOptions } from './client';
import type { AuthSyncResponse, HealthResponse, ReadinessResponse, User } from './types';

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
