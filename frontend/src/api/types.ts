/**
 * DEVDOC Frontend API Types
 * Strictly aligned with verified backend schemas in backend/app/schemas/
 */

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_active: boolean;
  is_superuser: boolean;
  provider?: string | null;
  provider_user_id?: string | null;
  last_sign_in_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserUpdate {
  full_name?: string | null;
  avatar_url?: string | null;
}

export interface AuthSyncResponse {
  success: boolean;
  message: string;
  user: User;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  settings_json: string | null;
  owner_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  slug?: string | null;
  settings_json?: string | null;
}

export interface ProjectUpdate {
  name?: string;
  description?: string | null;
  settings_json?: string | null;
  is_active?: boolean;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProjectDeleteResponse {
  success: boolean;
  message: string;
  project_id: string;
}

export interface GitHubConnectionResponse {
  connected: boolean;
  github_user_id: string | null;
  github_username: string | null;
  avatar_url: string | null;
  scope: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface GitHubConnectResponse {
  authorization_url: string;
  state: string;
}

export interface GitHubDisconnectResponse {
  success: boolean;
  message: string;
}

export interface GitHubRepositoryInfo {
  id: number;
  name: string;
  full_name: string;
  owner: string;
  is_private: boolean;
  html_url: string;
  description: string | null;
  default_branch: string;
  language: string | null;
}

export interface GitHubRepositoriesListResponse {
  items: GitHubRepositoryInfo[];
  page: number;
  per_page: number;
  total: number;
}

export interface RepositoryResponse {
  id: string;
  project_id: string;
  github_repo_id: number;
  full_name: string;
  owner: string;
  name: string;
  default_branch: string;
  is_private: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectRepositoryAttach {
  full_name: string;
}

export interface ProjectRepositoryDeleteResponse {
  success: boolean;
  message: string;
  repository_id: string;
}

export interface HealthResponse {
  success: boolean;
  service: string;
  status: string;
}

export interface ReadinessResponse {
  success: boolean;
  service: string;
  status: string;
  checks: Record<string, string>;
}
