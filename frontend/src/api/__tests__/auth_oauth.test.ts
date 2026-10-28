import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  AUTH_TOKEN_KEY,
  clearStoredToken,
  getStoredToken,
  setStoredToken,
} from '../client';
import {
  getOAuthAuthorizeUrl,
  exchangeOAuthCode,
  listOAuthProviders,
  loginWithPassword,
} from '../auth';

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

describe('OAuth Authentication & Session Lifecycle', () => {
  beforeEach(() => {
    mockLocal.clear();
    mockSession.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('1. OAuth URL Generation & Allowlist Protection', () => {
    it('requests Google OAuth authorize URL with redirect target', async () => {
      const mockResp = {
        provider: 'google',
        authorization_url: 'https://test.supabase.co/auth/v1/authorize?provider=google&redirect_to=http%3A%2F%2Flocalhost%3A5173%2F',
        redirect_to: 'http://localhost:5173/',
      };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockResp,
      } as Response);

      const res = await getOAuthAuthorizeUrl('google', 'http://localhost:5173/');
      expect(res.provider).toBe('google');
      expect(res.authorization_url).toContain('provider=google');
      expect(res.redirect_to).toBe('http://localhost:5173/');
    });

    it('requests GitHub OAuth authorize URL with redirect target', async () => {
      const mockResp = {
        provider: 'github',
        authorization_url: 'https://test.supabase.co/auth/v1/authorize?provider=github&redirect_to=http%3A%2F%2Flocalhost%3A5173%2F',
        redirect_to: 'http://localhost:5173/',
      };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockResp,
      } as Response);

      const res = await getOAuthAuthorizeUrl('github', 'http://localhost:5173/');
      expect(res.provider).toBe('github');
      expect(res.authorization_url).toContain('provider=github');
    });

    it('exchanges PKCE authorization code via backend endpoint', async () => {
      const mockTokenResp = {
        access_token: 'supabase-jwt-es256-bearer',
        token_type: 'bearer',
        expires_in: 3600,
        user: { id: 'u-123', email: 'oauth@example.com' },
      };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockTokenResp,
      } as Response);

      const res = await exchangeOAuthCode({ auth_code: 'code-xyz' });
      expect(res.access_token).toBe('supabase-jwt-es256-bearer');
    });

    it('lists available OAuth providers', async () => {
      const mockList = [
        { id: 'google', name: 'Google', enabled: true },
        { id: 'github', name: 'GitHub', enabled: true },
      ];
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockList,
      } as Response);

      const res = await listOAuthProviders();
      expect(res.some((p) => p.id === 'google')).toBe(true);
      expect(res.some((p) => p.id === 'github')).toBe(true);
    });
  });

  describe('2. Unified Session Lifecycle', () => {
    it('persists OAuth token across simulated browser refresh', () => {
      expect(getStoredToken()).toBeNull();

      // OAuth token landed and stored
      setStoredToken('oauth-access-token-999', true);
      expect(getStoredToken()).toBe('oauth-access-token-999');
      expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBe('oauth-access-token-999');

      // Logout clears tokens completely
      clearStoredToken();
      expect(getStoredToken()).toBeNull();
      expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
      expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
    });

    it('supports session-only storage when remember=false', () => {
      setStoredToken('transient-oauth-token', false);
      expect(getStoredToken()).toBe('transient-oauth-token');
      expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe('transient-oauth-token');
      expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
    });
  });

  describe('3. Email/Password Coexistence', () => {
    it('email/password login remains functional alongside OAuth', async () => {
      const mockLogin = {
        access_token: 'email-password-jwt',
        token_type: 'bearer',
        expires_in: 3600,
        user: { id: 'u-password-1', email: 'registered@devdoc.ai' },
      };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockLogin,
      } as Response);

      const res = await loginWithPassword({
        email: 'registered@devdoc.ai',
        password: 'securePassword123!',
      });
      expect(res.access_token).toBe('email-password-jwt');
      expect(res.user?.email).toBe('registered@devdoc.ai');
    });
  });

  describe('4. Unauthenticated Startup & Public Endpoint Regression Suite', () => {
    it('returns null for empty, whitespace, null, or undefined sentinel storage values', () => {
      mockLocal.setItem(AUTH_TOKEN_KEY, 'undefined');
      expect(getStoredToken()).toBeNull();

      mockLocal.setItem(AUTH_TOKEN_KEY, 'null');
      expect(getStoredToken()).toBeNull();

      mockLocal.setItem(AUTH_TOKEN_KEY, '   ');
      expect(getStoredToken()).toBeNull();

      mockLocal.setItem(AUTH_TOKEN_KEY, '');
      expect(getStoredToken()).toBeNull();
    });

    it('fresh unauthenticated page load does not send Authorization header for OAuth provider discovery', async () => {
      clearStoredToken();
      expect(getStoredToken()).toBeNull();

      let capturedHeaders: Headers | undefined;
      globalThis.fetch = vi.fn().mockImplementation((_url, init) => {
        capturedHeaders = init?.headers as Headers;
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => [
            { id: 'google', name: 'Google', enabled: true },
            { id: 'github', name: 'GitHub', enabled: true },
          ],
        } as Response);
      });

      const providers = await listOAuthProviders();
      expect(providers).toHaveLength(2);
      expect(capturedHeaders?.has('Authorization')).toBe(false);
    });

    it('OAuth authorization URL initiation does not require an Authorization header', async () => {
      clearStoredToken();

      let capturedHeaders: Headers | undefined;
      globalThis.fetch = vi.fn().mockImplementation((_url, init) => {
        capturedHeaders = init?.headers as Headers;
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({
            provider: 'google',
            authorization_url: 'https://test.supabase.co/auth/v1/authorize?provider=google',
            redirect_to: 'http://localhost:5173/',
          }),
        } as Response);
      });

      const res = await getOAuthAuthorizeUrl('google');
      expect(res.provider).toBe('google');
      expect(capturedHeaders?.has('Authorization')).toBe(false);
    });

    it('valid-session restoration attaches Bearer token to protected endpoints', async () => {
      const validJwt = 'valid.supabase.bearer.token';
      setStoredToken(validJwt, true);

      let capturedAuth: string | null = null;
      globalThis.fetch = vi.fn().mockImplementation((_url, init) => {
        const headers = init?.headers as Headers;
        capturedAuth = headers?.get('Authorization') ?? null;
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ id: 'u-valid', email: 'verified@devdoc.ai' }),
        } as Response);
      });

      const { getMyProfile } = await import('../auth');
      const profile = await getMyProfile({ token: validJwt });
      expect(profile.id).toBe('u-valid');
      expect(capturedAuth).toBe(`Bearer ${validJwt}`);
    });

    it('does not invoke unauthorizedListener on public OAuth endpoints when 401 is received', async () => {
      const { setOnUnauthorized } = await import('../client');
      const listener = vi.fn();
      setOnUnauthorized(listener);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Unauthorized' }),
      } as Response);

      await expect(listOAuthProviders()).rejects.toThrow();
      expect(listener).not.toHaveBeenCalled();
      setOnUnauthorized(null);
    });
  });
});
