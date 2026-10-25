import { apiClient, type RequestOptions } from './client';
import type {
  Project,
  ProjectCreate,
  ProjectDeleteResponse,
  ProjectListResponse,
  ProjectRepositoryAttach,
  ProjectRepositoryDeleteResponse,
  ProjectUpdate,
  RepositoryResponse,
} from './types';

export interface ListProjectsParams {
  limit?: number;
  offset?: number;
  include_inactive?: boolean;
}

/**
 * List all projects belonging to the authenticated user.
 * Endpoint: GET /api/v1/projects
 */
export async function listProjects(
  params?: ListProjectsParams,
  options?: RequestOptions
): Promise<ProjectListResponse> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));
  if (params?.include_inactive !== undefined) query.set('include_inactive', String(params.include_inactive));

  const qs = query.toString();
  const endpoint = `/api/v1/projects${qs ? `?${qs}` : ''}`;

  return apiClient<ProjectListResponse>(endpoint, {
    method: 'GET',
    ...options,
  });
}

/**
 * Retrieve an authorized project by its ID.
 * Endpoint: GET /api/v1/projects/{project_id}
 */
export async function getProject(
  projectId: string,
  options?: RequestOptions
): Promise<Project> {
  return apiClient<Project>(`/api/v1/projects/${projectId}`, {
    method: 'GET',
    ...options,
  });
}

/**
 * Create a new project owned by the authenticated user.
 * Endpoint: POST /api/v1/projects
 */
export async function createProject(
  data: ProjectCreate,
  options?: RequestOptions
): Promise<Project> {
  return apiClient<Project>('/api/v1/projects', {
    method: 'POST',
    body: JSON.stringify(data),
    ...options,
  });
}

/**
 * Update project metadata.
 * Endpoint: PATCH /api/v1/projects/{project_id}
 */
export async function updateProject(
  projectId: string,
  data: ProjectUpdate,
  options?: RequestOptions
): Promise<Project> {
  return apiClient<Project>(`/api/v1/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
    ...options,
  });
}

/**
 * Delete an authorized project.
 * Endpoint: DELETE /api/v1/projects/{project_id}
 */
export async function deleteProject(
  projectId: string,
  options?: RequestOptions
): Promise<ProjectDeleteResponse> {
  return apiClient<ProjectDeleteResponse>(`/api/v1/projects/${projectId}`, {
    method: 'DELETE',
    ...options,
  });
}

/**
 * Retrieve connected GitHub repository for the project.
 * Endpoint: GET /api/v1/projects/{project_id}/github/repository
 */
export async function getProjectGitHubRepo(
  projectId: string,
  options?: RequestOptions
): Promise<RepositoryResponse> {
  return apiClient<RepositoryResponse>(`/api/v1/projects/${projectId}/github/repository`, {
    method: 'GET',
    ...options,
  });
}

/**
 * Attach a GitHub repository to the project.
 * Endpoint: POST /api/v1/projects/{project_id}/github/repository
 */
export async function attachProjectGitHubRepo(
  projectId: string,
  data: ProjectRepositoryAttach,
  options?: RequestOptions
): Promise<RepositoryResponse> {
  return apiClient<RepositoryResponse>(`/api/v1/projects/${projectId}/github/repository`, {
    method: 'POST',
    body: JSON.stringify(data),
    ...options,
  });
}

/**
 * Disconnect the GitHub repository from the project.
 * Endpoint: DELETE /api/v1/projects/{project_id}/github/repository
 */
export async function disconnectProjectGitHubRepo(
  projectId: string,
  options?: RequestOptions
): Promise<ProjectRepositoryDeleteResponse> {
  return apiClient<ProjectRepositoryDeleteResponse>(`/api/v1/projects/${projectId}/github/repository`, {
    method: 'DELETE',
    ...options,
  });
}

/**
 * List branches for the connected GitHub repository.
 * Endpoint: GET /api/v1/projects/{project_id}/github/branches
 */
export async function listProjectBranches(
  projectId: string,
  params?: { page?: number; per_page?: number },
  options?: RequestOptions
): Promise<any[]> {
  const query = new URLSearchParams();
  if (params?.page) query.set('page', String(params.page));
  if (params?.per_page) query.set('per_page', String(params.per_page));

  const qs = query.toString();
  return apiClient<any[]>(`/api/v1/projects/${projectId}/github/branches${qs ? `?${qs}` : ''}`, {
    method: 'GET',
    ...options,
  });
}

/**
 * List commits for the connected GitHub repository.
 * Endpoint: GET /api/v1/projects/{project_id}/github/commits
 */
export async function listProjectCommits(
  projectId: string,
  params?: { sha?: string; page?: number; per_page?: number },
  options?: RequestOptions
): Promise<any[]> {
  const query = new URLSearchParams();
  if (params?.sha) query.set('sha', params.sha);
  if (params?.page) query.set('page', String(params.page));
  if (params?.per_page) query.set('per_page', String(params.per_page));

  const qs = query.toString();
  return apiClient<any[]>(`/api/v1/projects/${projectId}/github/commits${qs ? `?${qs}` : ''}`, {
    method: 'GET',
    ...options,
  });
}
