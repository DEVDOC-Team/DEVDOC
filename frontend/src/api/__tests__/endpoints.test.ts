import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getMyProfile, syncProfile, checkHealth, checkReadiness, verifyProjectAccess } from '../auth';
import {
  listProjects,
  getProject,
  createProject,
  updateProject,
  deleteProject,
  getProjectGitHubRepo,
  attachProjectGitHubRepo,
  disconnectProjectGitHubRepo,
} from '../projects';

describe('Auth & Projects API Service Functions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('Auth Service', () => {
    it('calls getMyProfile on /api/v1/auth/me', async () => {
      const mockUser = { id: 'u-1', email: 'dev@devdoc.ai', is_active: true };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockUser,
      } as Response);

      const res = await getMyProfile({ token: 'jwt-123' });
      expect(res).toEqual(mockUser);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/auth/me'),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('calls syncProfile on /api/v1/auth/sync', async () => {
      const syncData = { success: true, message: 'Synced', user: { id: 'u-1', email: 'dev@devdoc.ai' } };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => syncData,
      } as Response);

      const res = await syncProfile();
      expect(res.success).toBe(true);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/auth/sync'),
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('calls checkHealth on /api/v1/health', async () => {
      const healthData = { success: true, service: 'DEVDOC', status: 'healthy' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => healthData,
      } as Response);

      const res = await checkHealth();
      expect(res.status).toBe('healthy');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/health'),
        expect.anything()
      );
    });

    it('calls checkReadiness on /api/v1/ready', async () => {
      const readyData = { success: true, service: 'DEVDOC', status: 'ready', checks: { database: 'ok' } };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => readyData,
      } as Response);

      const res = await checkReadiness();
      expect(res.checks.database).toBe('ok');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/ready'),
        expect.anything()
      );
    });

    it('calls verifyProjectAccess on /api/v1/auth/projects/{id}/verify-access', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true, project_id: 'p-123' }),
      } as Response);

      const res = await verifyProjectAccess('p-123');
      expect(res.success).toBe(true);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/auth/projects/p-123/verify-access'),
        expect.anything()
      );
    });
  });

  describe('Projects Service', () => {
    it('constructs correct query parameters for listProjects', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ items: [], total: 0, limit: 10, offset: 5 }),
      } as Response);

      await listProjects({ limit: 10, offset: 5, include_inactive: true });
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/v1\/projects\?limit=10&offset=5&include_inactive=true/),
        expect.anything()
      );
    });

    it('calls getProject on /api/v1/projects/{id}', async () => {
      const proj = { id: 'p-123', name: 'Auth Service' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => proj,
      } as Response);

      const res = await getProject('p-123');
      expect(res.id).toBe('p-123');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/projects/p-123'),
        expect.anything()
      );
    });

    it('sends POST to /api/v1/projects with JSON body on createProject', async () => {
      const newProj = { id: 'p-new', name: 'New Service', slug: 'new-service' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => newProj,
      } as Response);

      const res = await createProject({ name: 'New Service' });
      expect(res).toEqual(newProj);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/projects'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'New Service' }),
        })
      );
    });

    it('sends PATCH to /api/v1/projects/{id} on updateProject', async () => {
      const updated = { id: 'p-123', name: 'Updated Name' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => updated,
      } as Response);

      const res = await updateProject('p-123', { name: 'Updated Name' });
      expect(res.name).toBe('Updated Name');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/projects/p-123'),
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ name: 'Updated Name' }),
        })
      );
    });

    it('sends DELETE to /api/v1/projects/{id} on deleteProject', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true, message: 'Deleted', project_id: 'p-123' }),
      } as Response);

      const res = await deleteProject('p-123');
      expect(res.success).toBe(true);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/projects/p-123'),
        expect.objectContaining({ method: 'DELETE' })
      );
    });

    it('calls getProjectGitHubRepo on /api/v1/projects/{id}/github/repository', async () => {
      const repo = { id: 'r-1', full_name: 'org/repo' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => repo,
      } as Response);

      const res = await getProjectGitHubRepo('p-123');
      expect(res.full_name).toBe('org/repo');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/projects/p-123/github/repository'),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('handles GitHub repository attachment on project', async () => {
      const repoData = { id: 'r-1', full_name: 'DEVDOC-Team/DEVDOC', default_branch: 'main' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => repoData,
      } as Response);

      const res = await attachProjectGitHubRepo('p-123', { full_name: 'DEVDOC-Team/DEVDOC' });
      expect(res.full_name).toBe('DEVDOC-Team/DEVDOC');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/projects/p-123/github/repository'),
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('sends DELETE to disconnect GitHub repository from project', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true, message: 'Disconnected', repository_id: 'r-1' }),
      } as Response);

      const res = await disconnectProjectGitHubRepo('p-123');
      expect(res.success).toBe(true);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/projects/p-123/github/repository'),
        expect.objectContaining({ method: 'DELETE' })
      );
    });
  });
});
