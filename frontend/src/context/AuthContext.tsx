import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { clearStoredToken, getStoredToken, setStoredToken, setOnUnauthorized, ApiError } from '../api/client';
import { getMyProfile, loginWithPassword, syncProfile, getOAuthAuthorizeUrl, exchangeOAuthCode } from '../api/auth';
import type { User, OAuthProvider } from '../api/types';

export type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated';

export interface AuthContextValue {
  user: User | null;
  token: string | null;
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
  const [status, setStatus] = useState<AuthStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [isAuthResolving, setIsAuthResolving] = useState<boolean>(true);

  const clearError = useCallback(() => setError(null), []);

  const signOut = useCallback((reason?: string) => {
    clearStoredToken();
    if (typeof window !== 'undefined' && window.sessionStorage) {
      sessionStorage.removeItem('devdoc_persist_session');
    }
    setToken(null);
    setUser(null);
    setStatus('unauthenticated');
    if (reason) {
      setError(reason);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    const activeToken = getStoredToken();
    if (!activeToken) {
      setUser(null);
      setStatus('unauthenticated');
      setIsAuthResolving(false);
      return;
    }

    try {
      setStatus('loading');
      const profile = await getMyProfile({ token: activeToken });
      setUser(profile);
      setToken(activeToken);
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
          const safeMessage = sanitizeOAuthError(callback.error, callback.errorDescription);
          setError(safeMessage);
          setStatus('unauthenticated');
          setIsAuthResolving(false);
          return;
        }

        if (callback.accessToken) {
          setStatus('loading');
          try {
            const shouldPersist =
              typeof window !== 'undefined' &&
              window.sessionStorage &&
              sessionStorage.getItem('devdoc_persist_session') !== 'false';
            if (typeof window !== 'undefined' && window.sessionStorage) {
              sessionStorage.removeItem('devdoc_persist_session');
            }

            const rawToken = callback.accessToken;
            setStoredToken(rawToken, shouldPersist);
            setToken(rawToken);

            const profile = await getMyProfile({ token: rawToken });
            try {
              await syncProfile({ token: rawToken });
            } catch {
              // Non-fatal
            }

            setUser(profile);
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

            const exchangeResp = await exchangeOAuthCode({ auth_code: callback.code });
            const exchangedToken = exchangeResp.access_token;
            setStoredToken(exchangedToken, shouldPersist);
            setToken(exchangedToken);

            const profile = await getMyProfile({ token: exchangedToken });
            try {
              await syncProfile({ token: exchangedToken });
            } catch {
              // Non-fatal
            }

            setUser(profile);
            setStatus('authenticated');
            setError(null);
            setIsAuthResolving(false);
            return;
          } catch (err: any) {
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
        if (typeof window !== 'undefined' && window.sessionStorage) {
          sessionStorage.setItem('devdoc_persist_session', persist ? 'true' : 'false');
        }

        const redirectUri = typeof window !== 'undefined' ? `${window.location.origin}/` : 'http://localhost:5173/';
        const res = await getOAuthAuthorizeUrl(provider, redirectUri);
        if (!res.authorization_url) {
          throw new Error(`Failed to obtain authorization URL for ${provider}`);
        }

        if (typeof window !== 'undefined') {
          window.location.assign(res.authorization_url);
        }
        return { success: true };
      } catch (err: any) {
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
