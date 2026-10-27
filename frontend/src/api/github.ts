import { apiClient, type RequestOptions } from './client';
import type {
  GitHubConnectionResponse,
  GitHubConnectResponse,
  GitHubDisconnectResponse,
  GitHubRepositoriesListResponse,
} from './types';

/**
 * Return safe GitHub connection status for the authenticated user.
 * Endpoint: GET /api/v1/github/connection
 */
export async function getGitHubConnection(
  options?: RequestOptions
): Promise<GitHubConnectionResponse> {
  return apiClient<GitHubConnectionResponse>('/api/v1/github/connection', {
    method: 'GET',
    ...options,
  });
}

/**
 * Initiate GitHub OAuth connection flow.
 * Endpoint: GET /api/v1/github/connect
 */
export async function initiateGitHubConnect(
  options?: RequestOptions
): Promise<GitHubConnectResponse> {
  return apiClient<GitHubConnectResponse>('/api/v1/github/connect', {
    method: 'GET',
    ...options,
  });
}

/**
 * Disconnect and revoke stored GitHub credentials for current user.
 * Endpoint: DELETE /api/v1/github/connection
 */
export async function disconnectGitHub(
  options?: RequestOptions
): Promise<GitHubDisconnectResponse> {
  return apiClient<GitHubDisconnectResponse>('/api/v1/github/connection', {
    method: 'DELETE',
    ...options,
  });
}

/**
 * List repositories accessible to the user's connected GitHub account.
 * Endpoint: GET /api/v1/github/repositories
 */
export async function listGitHubRepositories(
  params?: { page?: number; per_page?: number },
  options?: RequestOptions
): Promise<GitHubRepositoriesListResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set('page', String(params.page));
  if (params?.per_page) query.set('per_page', String(params.per_page));

  const qs = query.toString();
  return apiClient<GitHubRepositoriesListResponse>(`/api/v1/github/repositories${qs ? `?${qs}` : ''}`, {
    method: 'GET',
    ...options,
  });
}
