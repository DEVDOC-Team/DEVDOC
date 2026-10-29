import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { clearStoredToken, getStoredToken, setStoredToken, setOnUnauthorized, ApiError } from '../api/client';
import { getMyProfile, loginWithPassword, syncProfile, getOAuthAuthorizeUrl, exchangeOAuthCode } from '../api/auth';
import type { User, OAuthProvider } from '../api/types';

export type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated';
export type SignInProvider = OAuthProvider | 'email';

export interface AuthContextValue {
  user: User | null;
  token: string | null;
  authProvider: SignInProvider | null;
  status: AuthStatus;
  error: string | null;
  isAuthResolving: boolean;
  signInWithCredentials: (email: string, password: string, persist?: boolean) => Promise<{ success: boolean; error?: string }>;
  signInWithToken: (token: string, persist?: boolean) => Promise<{ success: boolean; error?: string }>;
  signInWithOAuth: (provider: OAuthProvider, persist?: boolean) => Promise<{ success: boolean; error?: string }>;
  signOut: () => void;
  refreshUser: () => Promise<void>;
  clearError: () => void;
}

interface OAuthCallbackData {
  accessToken?: string;
  code?: string;
  error?: string;
  errorDescription?: string;
  errorCode?: string;
}

const OAUTH_CODE_VERIFIER_KEY = 'devdoc_oauth_code_verifier';
const AUTH_PROVIDER_KEY = 'devdoc_auth_provider';

const normalizeAuthProvider = (provider: unknown): SignInProvider | null => {
  if (typeof provider !== 'string') return null;
  const normalized = provider.trim().toLowerCase();
  return normalized === 'google' || normalized === 'github' || normalized === 'email'
    ? normalized
    : null;
};

const getAuthProviderFromToken = (accessToken: string | null): SignInProvider | null => {
  if (!accessToken || typeof window === 'undefined') return null;

  try {
    const payloadPart = accessToken.split('.')[1];
    if (!payloadPart) return null;
    const base64 = payloadPart.replace(/-/g, '+').replace(/_/g, '/');
    const binary = window.atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='));
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const payload = JSON.parse(new TextDecoder().decode(bytes));
    return normalizeAuthProvider(payload?.app_metadata?.provider ?? payload?.provider);
  } catch {
    return null;
  }
};

const getStoredAuthProvider = (): SignInProvider | null => {
  if (typeof window === 'undefined') return null;
  try {
    return normalizeAuthProvider(window.sessionStorage.getItem(AUTH_PROVIDER_KEY));
  } catch {
    return null;
  }
};

const storeAuthProvider = (provider: SignInProvider | null): void => {
  if (typeof window === 'undefined') return;
  try {
    if (provider) window.sessionStorage.setItem(AUTH_PROVIDER_KEY, provider);
    else window.sessionStorage.removeItem(AUTH_PROVIDER_KEY);
  } catch {
    // Provider display is best-effort when browser storage is unavailable.
  }
};

const encodeBase64Url = (bytes: Uint8Array): string => {
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return window
    .btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
};

const createOAuthPkcePair = async (): Promise<{ verifier: string; challenge: string }> => {
  if (!window.crypto?.subtle || !window.crypto?.getRandomValues) {
    throw new Error('Secure browser cryptography is required for sign-in.');
  }

  const randomBytes = window.crypto.getRandomValues(new Uint8Array(32));
  const verifier = encodeBase64Url(randomBytes);
  const digest = await window.crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(verifier)
  );

  return {
    verifier,
    challenge: encodeBase64Url(new Uint8Array(digest)),
  };
};

const parseOAuthCallback = (): OAuthCallbackData | null => {
  if (typeof window === 'undefined') return null;

  try {
    // 1. Check hash fragment (Supabase implicit grant)
    const rawHash = window.location.hash;
    if (rawHash && rawHash.length > 1) {
      const hashContent = rawHash.startsWith('#') ? rawHash.slice(1) : rawHash;
      const hashParams = new URLSearchParams(hashContent);
      const accessToken = hashParams.get('access_token');
      const error = hashParams.get('error');
      if (accessToken || error) {
        return {
          accessToken: accessToken || undefined,
          error: error || undefined,
          errorDescription: hashParams.get('error_description') || undefined,
          errorCode: hashParams.get('error_code') || undefined,
        };
      }
    }

    // 2. Check query search params (PKCE / authorization code flow)
    const rawSearch = window.location.search;
    if (rawSearch && rawSearch.length > 1) {
      const searchParams = new URLSearchParams(rawSearch);
      const code = searchParams.get('code');
      const error = searchParams.get('error');
      if (code || error) {
        return {
          code: code || undefined,
          error: error || undefined,
          errorDescription: searchParams.get('error_description') || undefined,
          errorCode: searchParams.get('error_code') || undefined,
        };
      }
    }
  } catch {
    return null;
  }
  return null;
};

const sanitizeOAuthError = (error?: string, desc?: string): string => {
  const errType = (error || '').toLowerCase();
  const errDesc = (desc || '').toLowerCase();

  if (errType === 'access_denied' || errDesc.includes('cancel') || errDesc.includes('denied')) {
    return 'Sign in was cancelled or access was denied by the authentication provider.';
  }
  if (errType === 'unsupported_provider' || errDesc.includes('provider not found') || errDesc.includes('disabled')) {
    return 'This OAuth provider is not yet configured or enabled in the Supabase project.';
  }
  if (errDesc.includes('rate limit') || errType === 'over_request_rate_limit') {
    return 'Too many authentication attempts. Please wait a moment and try again.';
  }
  if (desc && desc.trim()) {
    // Strip sensitive provider payload details
    return desc.replace(/[<>{}]/g, '').slice(0, 150);
  }
  return 'OAuth authentication failed. Please try again.';
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(getStoredToken());
  const [user, setUser] = useState<User | null>(null);
  const [authProvider, setAuthProvider] = useState<SignInProvider | null>(
    () => getStoredAuthProvider() ?? getAuthProviderFromToken(getStoredToken()),
  );
  const [status, setStatus] = useState<AuthStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [isAuthResolving, setIsAuthResolving] = useState<boolean>(true);

  const clearError = useCallback(() => setError(null), []);

  const signOut = useCallback((reason?: string) => {
    clearStoredToken();
    if (typeof window !== 'undefined' && window.sessionStorage) {
      sessionStorage.removeItem('devdoc_persist_session');
    }
    storeAuthProvider(null);
    setToken(null);
    setUser(null);
    setAuthProvider(null);
    setStatus('unauthenticated');
    if (reason) {
      setError(reason);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    const activeToken = getStoredToken();
    if (!activeToken) {
      setUser(null);
      setAuthProvider(null);
      setStatus('unauthenticated');
      setIsAuthResolving(false);
      return;
    }

    try {
      setStatus('loading');
      const profile = await getMyProfile({ token: activeToken });
      setUser(profile);
      setToken(activeToken);
      setAuthProvider(
        getStoredAuthProvider() ??
          getAuthProviderFromToken(activeToken) ??
          normalizeAuthProvider(profile.provider),
      );
      setStatus('authenticated');
      setError(null);
    } catch (err: any) {
      if (err instanceof ApiError) {
        if (err.isUnauthorized) {
          setError('Session expired or token invalid. Please sign in again.');
          signOut();
        } else if (err.isForbidden) {
          setError('Account access is inactive or restricted.');
          signOut();
        } else {
          setError(err.message);
        }
      } else {
        setError(err.message || 'Unable to connect to authentication service');
      }
      setStatus('unauthenticated');
    } finally {
      setIsAuthResolving(false);
    }
  }, [signOut]);

  // Initial session restoration on mount, OAuth callback handling, and global 401 subscription
  useEffect(() => {
    setOnUnauthorized(() => {
      const hadToken = Boolean(getStoredToken());
      signOut(hadToken ? 'Session expired or authentication required (401). Please sign in.' : undefined);
    });

    const initializeAuth = async () => {
      // 1. Process OAuth callback if present in URL
      const callback = parseOAuthCallback();
      if (callback) {
        // Immediately sanitize URL in browser history and address bar
        if (typeof window !== 'undefined') {
          const cleanPath = window.location.pathname || '/';
          window.history.replaceState(null, '', cleanPath);
        }

        if (callback.error) {
          if (typeof window !== 'undefined' && window.sessionStorage) {
            sessionStorage.removeItem(OAUTH_CODE_VERIFIER_KEY);
          }
          storeAuthProvider(null);
          setAuthProvider(null);
          const safeMessage = sanitizeOAuthError(callback.error, callback.errorDescription);
          setError(safeMessage);
          setStatus('unauthenticated');
          setIsAuthResolving(false);
          return;
        }

        if (callback.accessToken) {
          setStatus('loading');
          try {
            if (typeof window !== 'undefined' && window.sessionStorage) {
              sessionStorage.removeItem(OAUTH_CODE_VERIFIER_KEY);
            }
            const shouldPersist =
              typeof window !== 'undefined' &&
              window.sessionStorage &&
              sessionStorage.getItem('devdoc_persist_session') !== 'false';
            if (typeof window !== 'undefined' && window.sessionStorage) {
              sessionStorage.removeItem('devdoc_persist_session');
            }

            const rawToken = callback.accessToken;
            const requestedProvider = getStoredAuthProvider();
            setStoredToken(rawToken, shouldPersist);
            setToken(rawToken);

            const profile = await getMyProfile({ token: rawToken });
            try {
              await syncProfile({ token: rawToken });
            } catch {
              // Non-fatal
            }

            setUser(profile);
            const resolvedProvider =
              requestedProvider ??
              getAuthProviderFromToken(rawToken) ??
              normalizeAuthProvider(profile.provider);
            storeAuthProvider(resolvedProvider);
            setAuthProvider(resolvedProvider);
            setStatus('authenticated');
            setError(null);
            setIsAuthResolving(false);
            return;
          } catch (err: any) {
            setError(err.message || 'Failed to initialize session from OAuth token');
            setStatus('unauthenticated');
            setIsAuthResolving(false);
            return;
          }
        }

        if (callback.code) {
          setStatus('loading');
          try {
            const shouldPersist =
              typeof window !== 'undefined' &&
              window.sessionStorage &&
              sessionStorage.getItem('devdoc_persist_session') !== 'false';
            if (typeof window !== 'undefined' && window.sessionStorage) {
              sessionStorage.removeItem('devdoc_persist_session');
            }

            const codeVerifier =
              typeof window !== 'undefined' && window.sessionStorage
                ? sessionStorage.getItem(OAUTH_CODE_VERIFIER_KEY)
                : null;
            if (!codeVerifier) {
              throw new Error('OAuth verification data is missing. Please restart sign-in.');
            }

            const exchangeResp = await exchangeOAuthCode({
              auth_code: callback.code,
              code_verifier: codeVerifier,
            });
            sessionStorage.removeItem(OAUTH_CODE_VERIFIER_KEY);
            const exchangedToken = exchangeResp.access_token;
            const requestedProvider = getStoredAuthProvider();
            setStoredToken(exchangedToken, shouldPersist);
            setToken(exchangedToken);

            const profile = await getMyProfile({ token: exchangedToken });
            try {
              await syncProfile({ token: exchangedToken });
            } catch {
              // Non-fatal
            }

            setUser(profile);
            const resolvedProvider =
              requestedProvider ??
              getAuthProviderFromToken(exchangedToken) ??
              normalizeAuthProvider(profile.provider);
            storeAuthProvider(resolvedProvider);
            setAuthProvider(resolvedProvider);
            setStatus('authenticated');
            setError(null);
            setIsAuthResolving(false);
            return;
          } catch (err: any) {
            if (typeof window !== 'undefined' && window.sessionStorage) {
              sessionStorage.removeItem(OAUTH_CODE_VERIFIER_KEY);
            }
            setError(err.message || 'Failed to exchange OAuth authorization code');
            setStatus('unauthenticated');
            setIsAuthResolving(false);
            return;
          }
        }
      }

      // 2. Standard session restoration from local/session storage
      const existing = getStoredToken();
      if (existing) {
        try {
          await refreshUser();
        } catch {
          // Handled within refreshUser
        }
      } else {
        setIsAuthResolving(false);
        setStatus('unauthenticated');
        setError(null);
      }
    };

    initializeAuth();

    return () => {
      setOnUnauthorized(null);
    };
  }, [refreshUser, signOut]);

  const signInWithCredentials = useCallback(
    async (email: string, password: string, persist = true): Promise<{ success: boolean; error?: string }> => {
      const cleanEmail = email.trim();
      if (!cleanEmail || !password) {
        const msg = 'Email and password are required';
        setError(msg);
        return { success: false, error: msg };
      }

      setStatus('loading');
      setError(null);

      try {
        const loginResp = await loginWithPassword({ email: cleanEmail, password });
        const accessToken = loginResp.access_token;
        if (!accessToken) {
          throw new Error('No access token returned by authentication provider');
        }

        setStoredToken(accessToken, persist);
        setToken(accessToken);
        storeAuthProvider('email');
        setAuthProvider('email');

        // Fetch verified user profile using the new Bearer token
        const profile = await getMyProfile({ token: accessToken });
        setUser(profile);
        setStatus('authenticated');
        setError(null);
        return { success: true };
      } catch (err: any) {
        let msg = 'Authentication failed';
        if (err instanceof ApiError) {
          if (err.isUnauthorized) {
            msg = err.message || 'Invalid email or password';
          } else if (err.isForbidden) {
            msg = err.message || 'User account is inactive or restricted';
          } else {
            msg = err.message;
          }
        } else if (err.message) {
          msg = err.message;
        }

        setError(msg);
        storeAuthProvider(null);
        setAuthProvider(null);
        setStatus('unauthenticated');
        return { success: false, error: msg };
      }
    },
    []
  );

  const signInWithToken = useCallback(
    async (rawToken: string, persist = true): Promise<{ success: boolean; error?: string }> => {
      const cleanToken = rawToken.trim();
      if (!cleanToken) {
        const msg = 'Bearer access token cannot be empty';
        setError(msg);
        return { success: false, error: msg };
      }

      setStatus('loading');
      setError(null);

      try {
        const profile = await getMyProfile({ token: cleanToken });
        setStoredToken(cleanToken, persist);
        setToken(cleanToken);
        setUser(profile);
        const resolvedProvider =
          getAuthProviderFromToken(cleanToken) ?? normalizeAuthProvider(profile.provider);
        storeAuthProvider(resolvedProvider);
        setAuthProvider(resolvedProvider);
        setStatus('authenticated');
        setError(null);
        return { success: true };
      } catch (err: any) {
        let msg = 'Authentication failed';
        if (err instanceof ApiError) {
          if (err.isUnauthorized) {
            msg = 'Invalid or expired Bearer token (401 Unauthorized)';
          } else if (err.isForbidden) {
            msg = 'User account is inactive or forbidden (403 Forbidden)';
          } else {
            msg = err.message;
          }
        } else if (err.message) {
          msg = err.message;
        }

        setError(msg);
        setStatus('unauthenticated');
        return { success: false, error: msg };
      }
    },
    []
  );

  const signInWithOAuth = useCallback(
    async (provider: OAuthProvider, persist = true): Promise<{ success: boolean; error?: string }> => {
      setStatus('loading');
      setError(null);

      try {
        storeAuthProvider(provider);
        setAuthProvider(provider);
        if (typeof window !== 'undefined' && window.sessionStorage) {
          sessionStorage.setItem('devdoc_persist_session', persist ? 'true' : 'false');
        }

        const redirectUri = typeof window !== 'undefined' ? `${window.location.origin}/` : 'http://localhost:5173/';
        const pkce = await createOAuthPkcePair();
        sessionStorage.setItem(OAUTH_CODE_VERIFIER_KEY, pkce.verifier);

        const res = await getOAuthAuthorizeUrl(provider, redirectUri, pkce.challenge);
        if (!res.authorization_url) {
          throw new Error(`Failed to obtain authorization URL for ${provider}`);
        }

        if (typeof window !== 'undefined') {
          window.location.assign(res.authorization_url);
        }
        return { success: true };
      } catch (err: any) {
        if (typeof window !== 'undefined' && window.sessionStorage) {
          sessionStorage.removeItem(OAUTH_CODE_VERIFIER_KEY);
          sessionStorage.removeItem('devdoc_persist_session');
        }
        storeAuthProvider(null);
        setAuthProvider(null);
        let msg = `Unable to connect to ${provider} authentication`;
        if (err instanceof ApiError) {
          msg = err.message;
        } else if (err.message) {
          msg = err.message;
        }
        setError(msg);
        setStatus('unauthenticated');
        return { success: false, error: msg };
      }
    },
    []
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        authProvider,
        status,
        error,
        isAuthResolving,
        signInWithCredentials,
        signInWithToken,
        signInWithOAuth,
        signOut,
        refreshUser,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
