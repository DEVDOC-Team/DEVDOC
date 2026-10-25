import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { clearStoredToken, getStoredToken, setStoredToken, ApiError } from '../api/client';
import { getMyProfile } from '../api/auth';
import type { User } from '../api/types';

export type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated';

export interface AuthContextValue {
  user: User | null;
  token: string | null;
  status: AuthStatus;
  error: string | null;
  isAuthResolving: boolean;
  signInWithToken: (token: string, persist?: boolean) => Promise<{ success: boolean; error?: string }>;
  signOut: () => void;
  refreshUser: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(getStoredToken());
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [isAuthResolving, setIsAuthResolving] = useState<boolean>(true);

  const clearError = useCallback(() => setError(null), []);

  const signOut = useCallback(() => {
    clearStoredToken();
    setToken(null);
    setUser(null);
    setStatus('unauthenticated');
    setError(null);
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

  // Initial session restoration on mount
  useEffect(() => {
    const existing = getStoredToken();
    if (existing) {
      refreshUser();
    } else {
      setIsAuthResolving(false);
      setStatus('unauthenticated');
    }
  }, [refreshUser]);

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

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        status,
        error,
        isAuthResolving,
        signInWithToken,
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
