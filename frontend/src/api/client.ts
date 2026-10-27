/**
 * DEVDOC API Client
 * Centralized, typed, resilient HTTP client for FastAPI backend.
 */

export class ApiError extends Error {
  public status: number;
  public data?: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isValidationError(): boolean {
    return this.status === 422;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
  token?: string | null;
}

// Token storage key
export const AUTH_TOKEN_KEY = 'devdoc_auth_token';

export const getStoredToken = (): string | null => {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY) || sessionStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
};

export const setStoredToken = (token: string, persist = true): void => {
  try {
    if (persist) {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
      sessionStorage.removeItem(AUTH_TOKEN_KEY);
    } else {
      sessionStorage.setItem(AUTH_TOKEN_KEY, token);
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  } catch {
    // Non-fatal if localStorage is restricted
  }
};

export const clearStoredToken = (): void => {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // Non-fatal
  }
};

export type UnauthorizedListener = () => void;
let unauthorizedListener: UnauthorizedListener | null = null;

export const setOnUnauthorized = (listener: UnauthorizedListener | null): void => {
  unauthorizedListener = listener;
};

export const getApiBaseUrl = (): string => {
  return (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000';
};

export async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const baseUrl = getApiBaseUrl().replace(/\/$/, '');
  const url = endpoint.startsWith('http') ? endpoint : `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const {
    timeoutMs = 15000,
    token = getStoredToken(),
    headers: customHeaders = {},
    signal: userSignal,
    ...fetchOptions
  } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // Link user-provided AbortSignal if present
  if (userSignal) {
    if (userSignal.aborted) {
      controller.abort();
    } else {
      userSignal.addEventListener('abort', () => controller.abort());
    }
  }

  const headers = new Headers(customHeaders);
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  // Attach Content-Type for mutations with body
  if (fetchOptions.body && typeof fetchOptions.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  // Inject Bearer token
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    // Handle 204 No Content
    if (response.status === 204) {
      return null as T;
    }

    const contentType = response.headers.get('content-type') || '';
    const isJson = contentType.includes('application/json');

    let bodyData: any = null;
    if (isJson) {
      try {
        bodyData = await response.json();
      } catch {
        bodyData = null;
      }
    } else {
      try {
        bodyData = await response.text();
      } catch {
        bodyData = null;
      }
    }

    if (!response.ok) {
      let errorMessage = `Request failed with status ${response.status}`;
      if (bodyData && typeof bodyData === 'object') {
        if (typeof bodyData.detail === 'string') {
          errorMessage = bodyData.detail;
        } else if (Array.isArray(bodyData.detail)) {
          errorMessage = bodyData.detail.map((err: any) => err.msg || JSON.stringify(err)).join(', ');
        } else if (bodyData.error && typeof bodyData.error === 'object' && typeof bodyData.error.message === 'string') {
          errorMessage = bodyData.error.message;
        } else if (typeof bodyData.error === 'string') {
          errorMessage = bodyData.error;
        } else if (typeof bodyData.message === 'string') {
          errorMessage = bodyData.message;
        }
      } else if (typeof bodyData === 'string' && bodyData.trim()) {
        errorMessage = bodyData.slice(0, 200);
      }

      if (response.status === 401) {
        clearStoredToken();
        if (unauthorizedListener) {
          try {
            unauthorizedListener();
          } catch {
            // Non-fatal
          }
        }
      }

      throw new ApiError(response.status, errorMessage, bodyData);
    }

    return bodyData as T;
  } catch (error: any) {
    clearTimeout(timeoutId);

    if (error instanceof ApiError) {
      throw error;
    }

    if (error.name === 'AbortError') {
      throw new ApiError(0, 'Request timed out or was cancelled');
    }

    throw new ApiError(0, error.message || 'Network connection failed');
  }
}
