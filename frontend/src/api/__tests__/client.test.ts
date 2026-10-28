import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  apiClient,
  ApiError,
  AUTH_TOKEN_KEY,
  clearStoredToken,
  getStoredToken,
  setStoredToken,
} from '../client';

class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  clear(): void {
    this.store.clear();
  }
}

const mockLocal = new MemoryStorage();
const mockSession = new MemoryStorage();

Object.defineProperty(globalThis, 'localStorage', { value: mockLocal, writable: true });
Object.defineProperty(globalThis, 'sessionStorage', { value: mockSession, writable: true });

describe('API Client & Token Storage', () => {
  beforeEach(() => {
    mockLocal.clear();
    mockSession.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Token Management', () => {
    it('stores and retrieves token from localStorage', () => {
      expect(getStoredToken()).toBeNull();
      setStoredToken('test-token-123', true);
      expect(getStoredToken()).toBe('test-token-123');
      expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBe('test-token-123');
    });

    it('stores and retrieves token from sessionStorage when persist=false', () => {
      setStoredToken('session-token-456', false);
      expect(getStoredToken()).toBe('session-token-456');
      expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe('session-token-456');
      expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
    });

    it('clears stored token completely', () => {
      setStoredToken('token-to-clear', true);
      clearStoredToken();
      expect(getStoredToken()).toBeNull();
    });
  });

  describe('apiClient HTTP requests', () => {
    it('handles successful JSON response', async () => {
      const mockData = { id: 'proj-1', name: 'Test Project' };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockData,
      } as Response);

      const result = await apiClient<typeof mockData>('/api/v1/projects');
      expect(result).toEqual(mockData);
      expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    });

    it('handles 204 No Content response cleanly without JSON parse error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        headers: new Headers(),
      } as Response);

      const result = await apiClient('/api/v1/projects/123', { method: 'DELETE' });
      expect(result).toBeNull();
    });

    it('injects Bearer token in Authorization header when available', async () => {
      setStoredToken('jwt-bearer-xyz', true);

      globalThis.fetch = vi.fn().mockImplementation((_url, init) => {
        const headers = init.headers as Headers;
        expect(headers.get('Authorization')).toBe('Bearer jwt-bearer-xyz');
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ success: true }),
        } as Response);
      });

      await apiClient('/api/v1/auth/me');
      expect(globalThis.fetch).toHaveBeenCalled();
    });

    it('handles structured 401 Unauthorized error with detail message', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Invalid authentication credentials' }),
      } as Response);

      await expect(apiClient('/api/v1/auth/me')).rejects.toThrow('Invalid authentication credentials');
      try {
        await apiClient('/api/v1/auth/me');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.status).toBe(401);
        expect(err.isUnauthorized).toBe(true);
        expect(err.isForbidden).toBe(false);
      }
    });

    it('handles structured 403 Forbidden error with distinction', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'User account is inactive' }),
      } as Response);

      try {
        await apiClient('/api/v1/projects');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.status).toBe(403);
        expect(err.isForbidden).toBe(true);
        expect(err.isUnauthorized).toBe(false);
      }
    });

    it('handles 422 Validation error array from FastAPI', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          detail: [
            { loc: ['body', 'name'], msg: 'Field required', type: 'value_error.missing' },
          ],
        }),
      } as Response);

      try {
        await apiClient('/api/v1/projects', { method: 'POST', body: '{}' });
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.status).toBe(422);
        expect(err.isValidationError).toBe(true);
        expect(err.message).toContain('Field required');
      }
    });

    it('handles non-JSON error (e.g. 502 Bad Gateway text/html)', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        headers: new Headers({ 'content-type': 'text/plain' }),
        text: async () => '502 Bad Gateway from reverse proxy',
      } as Response);

      try {
        await apiClient('/api/v1/health');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.status).toBe(502);
        expect(err.message).toContain('502 Bad Gateway');
      }
    });

    it('handles network failure (fetch throws)', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch (connection refused)'));

      try {
        await apiClient('/api/v1/health');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.status).toBe(0);
        expect(err.message).toContain('Failed to fetch');
      }
    });

    it('invokes unauthorizedListener on standard 401 endpoints', async () => {
      const { setOnUnauthorized } = await import('../client');
      const listener = vi.fn();
      setOnUnauthorized(listener);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Session expired' }),
      } as Response);

      await expect(apiClient('/api/v1/projects')).rejects.toThrow();
      expect(listener).toHaveBeenCalledTimes(1);
      setOnUnauthorized(null);
    });

    it('does NOT invoke unauthorizedListener when /auth/login returns 401', async () => {
      const { setOnUnauthorized } = await import('../client');
      const listener = vi.fn();
      setOnUnauthorized(listener);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Invalid email or password' }),
      } as Response);

      await expect(
        apiClient('/api/v1/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email: 'test@example.com', password: 'wrong' }),
        })
      ).rejects.toThrow('Invalid email or password');
      expect(listener).not.toHaveBeenCalled();
      setOnUnauthorized(null);
    });
  });
});
