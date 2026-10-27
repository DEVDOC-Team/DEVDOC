import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useAuth } from './AuthContext';
import {
  createProject as apiCreateProject,
  deleteProject as apiDeleteProject,
  getProjectGitHubRepo,
  attachProjectGitHubRepo as apiAttachProjectGitHubRepo,
  disconnectProjectGitHubRepo as apiDisconnectProjectGitHubRepo,
  listProjects as apiListProjects,
  updateProject as apiUpdateProject,
} from '../api/projects';
import {
  getGitHubConnection as apiGetGitHubConnection,
  disconnectGitHub as apiDisconnectGitHub,
} from '../api/github';
import type {
  Project,
  ProjectCreate,
  ProjectUpdate,
  RepositoryResponse,
  GitHubConnectionResponse,
} from '../api/types';
import { ApiError } from '../api/client';

export const SELECTED_PROJECT_KEY = 'devdoc_selected_project_id';

export interface ProjectContextValue {
  projects: Project[];
  selectedProject: Project | null;
  selectedProjectId: string | null;
  connectedRepo: RepositoryResponse | null;
  githubConnection: GitHubConnectionResponse | null;
  loading: boolean;
  repoLoading: boolean;
  githubConnectionLoading: boolean;
  error: string | null;
  refreshProjects: () => Promise<void>;
  refreshGitHubConnection: () => Promise<void>;
  disconnectUserGitHub: () => Promise<void>;
  attachRepoToProject: (fullName: string) => Promise<RepositoryResponse>;
  disconnectRepoFromProject: () => Promise<void>;
  selectProject: (id: string) => void;
  createProject: (data: ProjectCreate) => Promise<Project>;
  updateProject: (id: string, data: ProjectUpdate) => Promise<Project>;
  deleteProject: (id: string) => Promise<void>;
  clearError: () => void;
}

const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { status, user } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(SELECTED_PROJECT_KEY);
    } catch {
      return null;
    }
  });
  const [connectedRepo, setConnectedRepo] = useState<RepositoryResponse | null>(null);
  const [githubConnection, setGitHubConnection] = useState<GitHubConnectionResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [repoLoading, setRepoLoading] = useState<boolean>(false);
  const [githubConnectionLoading, setGithubConnectionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => setError(null), []);

  const refreshGitHubConnection = useCallback(async () => {
    if (status !== 'authenticated') {
      setGitHubConnection(null);
      return;
    }

    setGithubConnectionLoading(true);
    try {
      const conn = await apiGetGitHubConnection();
      setGitHubConnection(conn);
    } catch {
      setGitHubConnection({
        connected: false,
        github_user_id: null,
        github_username: null,
        avatar_url: null,
        scope: null,
        created_at: null,
        updated_at: null,
      });
    } finally {
      setGithubConnectionLoading(false);
    }
  }, [status]);

  const disconnectUserGitHub = useCallback(async (): Promise<void> => {
    setGithubConnectionLoading(true);
    try {
      await apiDisconnectGitHub();
      setGitHubConnection({
        connected: false,
        github_user_id: null,
        github_username: null,
        avatar_url: null,
        scope: null,
        created_at: null,
        updated_at: null,
      });
      setConnectedRepo(null);
    } catch (err: any) {
      const msg = err instanceof ApiError ? err.message : err.message || 'Failed to disconnect GitHub';
      setError(msg);
      throw err;
    } finally {
      setGithubConnectionLoading(false);
    }
  }, []);

  // Listen for popup OAuth postMessage completion
  useEffect(() => {
    const handleOAuthMessage = (event: MessageEvent) => {
      if (event.data?.type === 'DEVDOC_GITHUB_CONNECTED') {
        refreshGitHubConnection();
      }
    };
    window.addEventListener('message', handleOAuthMessage);
    return () => {
      window.removeEventListener('message', handleOAuthMessage);
    };
  }, [refreshGitHubConnection]);

  // Check GitHub connection when auth status changes
  useEffect(() => {
    if (status === 'authenticated') {
      refreshGitHubConnection();
    } else {
      setGitHubConnection(null);
    }
  }, [status, refreshGitHubConnection]);

  const selectProject = useCallback((id: string) => {
    setSelectedProjectId(id);
    try {
      localStorage.setItem(SELECTED_PROJECT_KEY, id);
    } catch {
      // Non-fatal
    }
  }, []);

  const refreshProjects = useCallback(async () => {
    if (status !== 'authenticated') {
      setProjects([]);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await apiListProjects({ limit: 50, offset: 0, include_inactive: false });
      const items = response.items || [];
      setProjects(items);

      // Verify or auto-select project
      setSelectedProjectId((currentId) => {
        if (currentId && items.some((p) => p.id === currentId)) {
          return currentId;
        }
        const defaultProj = items[0];
        const newId = defaultProj ? defaultProj.id : null;
        if (newId) {
          try {
            localStorage.setItem(SELECTED_PROJECT_KEY, newId);
          } catch {
            // Non-fatal
          }
        } else {
          try {
            localStorage.removeItem(SELECTED_PROJECT_KEY);
          } catch {
            // Non-fatal
          }
        }
        return newId;
      });
    } catch (err: any) {
      if (err instanceof ApiError) {
        if (err.isUnauthorized) {
          setError('Session expired or authentication required. Please sign in to view projects.');
          setProjects([]);
        } else if (err.isForbidden) {
          setError('Account access forbidden (403). You do not have permission to view projects.');
        } else {
          setError(err.message);
        }
      } else {
        setError(err.message || 'Failed to load projects');
      }
    } finally {
      setLoading(false);
    }
  }, [status]);

  // Load projects whenever authenticated user changes
  useEffect(() => {
    if (status === 'authenticated' && user) {
      refreshProjects();
    } else if (status === 'unauthenticated') {
      setProjects([]);
      setSelectedProjectId(null);
      setConnectedRepo(null);
      setError(null);
    }
  }, [status, user, refreshProjects]);

  // Fetch connected GitHub repo for selected project
  useEffect(() => {
    let active = true;
    if (!selectedProjectId || status !== 'authenticated') {
      setConnectedRepo(null);
      return;
    }

    setRepoLoading(true);
    getProjectGitHubRepo(selectedProjectId)
      .then((repo) => {
        if (active) {
          setConnectedRepo(repo);
        }
      })
      .catch((err) => {
        if (active) {
          // If 404, simply no repo attached yet
          if (err instanceof ApiError && err.status === 404) {
            setConnectedRepo(null);
          } else {
            setConnectedRepo(null);
          }
        }
      })
      .finally(() => {
        if (active) {
          setRepoLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [selectedProjectId, status]);

  const createProject = useCallback(
    async (data: ProjectCreate): Promise<Project> => {
      setLoading(true);
      setError(null);
      try {
        const newProject = await apiCreateProject(data);
        setProjects((prev) => [newProject, ...prev]);
        selectProject(newProject.id);
        return newProject;
      } catch (err: any) {
        const msg = err instanceof ApiError ? err.message : err.message || 'Failed to create project';
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [selectProject]
  );

  const updateProject = useCallback(
    async (id: string, data: ProjectUpdate): Promise<Project> => {
      setLoading(true);
      setError(null);
      try {
        const updated = await apiUpdateProject(id, data);
        setProjects((prev) => prev.map((p) => (p.id === id ? updated : p)));
        return updated;
      } catch (err: any) {
        const msg = err instanceof ApiError ? err.message : err.message || 'Failed to update project';
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const deleteProject = useCallback(
    async (id: string): Promise<void> => {
      setLoading(true);
      setError(null);
      try {
        await apiDeleteProject(id);
        setProjects((prev) => prev.filter((p) => p.id !== id));
        setSelectedProjectId((currentId) => {
          if (currentId === id) {
            try {
              localStorage.removeItem(SELECTED_PROJECT_KEY);
            } catch {
              // Non-fatal
            }
            return null;
          }
          return currentId;
        });
      } catch (err: any) {
        const msg = err instanceof ApiError ? err.message : err.message || 'Failed to delete project';
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const attachRepoToProject = useCallback(
    async (fullName: string): Promise<RepositoryResponse> => {
      if (!selectedProjectId) {
        throw new Error('No project selected to attach repository');
      }
      setRepoLoading(true);
      setError(null);
      try {
        const repo = await apiAttachProjectGitHubRepo(selectedProjectId, { full_name: fullName });
        setConnectedRepo(repo);
        return repo;
      } catch (err: any) {
        const msg = err instanceof ApiError ? err.message : err.message || 'Failed to attach repository';
        setError(msg);
        throw err;
      } finally {
        setRepoLoading(false);
      }
    },
    [selectedProjectId]
  );

  const disconnectRepoFromProject = useCallback(async (): Promise<void> => {
    if (!selectedProjectId) return;
    setRepoLoading(true);
    setError(null);
    try {
      await apiDisconnectProjectGitHubRepo(selectedProjectId);
      setConnectedRepo(null);
    } catch (err: any) {
      const msg = err instanceof ApiError ? err.message : err.message || 'Failed to disconnect repository';
      setError(msg);
      throw err;
    } finally {
      setRepoLoading(false);
    }
  }, [selectedProjectId]);

  const selectedProject = projects.find((p) => p.id === selectedProjectId) || null;

  return (
    <ProjectContext.Provider
      value={{
        projects,
        selectedProject,
        selectedProjectId,
        connectedRepo,
        githubConnection,
        loading,
        repoLoading,
        githubConnectionLoading,
        error,
        refreshProjects,
        refreshGitHubConnection,
        disconnectUserGitHub,
        attachRepoToProject,
        disconnectRepoFromProject,
        selectProject,
        createProject,
        updateProject,
        deleteProject,
        clearError,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
};

export const useProjects = (): ProjectContextValue => {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error('useProjects must be used within a ProjectProvider');
  }
  return context;
};
