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

const SERVER_OUTAGE_MESSAGE = "Oops! Something went wrong on our end. We're working to fix it.";
const SECTION_ERROR_MESSAGE = 'Unable to load this section right now.';
const ACTION_ERROR_MESSAGE = "We couldn't save your changes. Please check your connection and try again.";

const getPublicErrorMessage = (method: string, status?: number, connectionUnavailable = false): string => {
  const isReadRequest = ['GET', 'HEAD', 'OPTIONS'].includes(method);
  if (status === 500 || status === 503 || status === 504 || (connectionUnavailable && isReadRequest)) {
    return SERVER_OUTAGE_MESSAGE;
  }

  return ['GET', 'HEAD', 'OPTIONS'].includes(method) ? SECTION_ERROR_MESSAGE : ACTION_ERROR_MESSAGE;
};

// Token storage key
export const AUTH_TOKEN_KEY = 'devdoc_auth_token';

export const getStoredToken = (): string | null => {
  try {
    const raw = localStorage.getItem(AUTH_TOKEN_KEY) || sessionStorage.getItem(AUTH_TOKEN_KEY);
    if (!raw || !raw.trim() || raw === 'undefined' || raw === 'null') {
      return null;
    }
    return raw.trim();
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

const isLoopbackHost = (hostname: string): boolean =>
  ['localhost', '127.0.0.1', '::1', '[::1]'].includes(hostname.toLowerCase());

export const getApiBaseUrl = (): string => {
  const configuredUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
  const pageLocation = typeof window !== 'undefined' ? window.location : null;
  const fallbackUrl = import.meta.env.DEV ? 'http://127.0.0.1:8000' : pageLocation?.origin;
  let apiBaseUrl = configuredUrl || fallbackUrl;

  if (!apiBaseUrl) {
    throw new Error('Set VITE_API_BASE_URL to the FastAPI backend URL for this deployment.');
  }

  if (pageLocation) {
    let apiUrl: URL;
    try {
      apiUrl = new URL(apiBaseUrl, pageLocation.origin);
    } catch {
      throw new Error('VITE_API_BASE_URL must be a valid backend URL.');
    }

    if (apiUrl.protocol !== 'http:' && apiUrl.protocol !== 'https:') {
      throw new Error('VITE_API_BASE_URL must use HTTP or HTTPS.');
    }

    if (isLoopbackHost(apiUrl.hostname) && !isLoopbackHost(pageLocation.hostname)) {
      if (import.meta.env.PROD) {
        // A local URL copied into Vercel settings cannot be reached from a
        // visitor's browser. Use the same-origin API rewrite configured for
        // the Vercel deployment instead.
        apiBaseUrl = pageLocation.origin;
      } else {
        throw new Error(
          'VITE_API_BASE_URL points to localhost, which is only reachable from the computer running this browser. Set it to the FastAPI URL reachable by this device and allow this frontend origin in backend CORS.'
        );
      }
    }

    // Validate the URL after production loopback fallback so a stale local
    // VITE_API_BASE_URL in Vercel can use the same-origin HTTPS API rewrite.
    apiUrl = new URL(apiBaseUrl, pageLocation.origin);
    if (pageLocation.protocol === 'https:' && apiUrl.protocol !== 'https:') {
      throw new Error('An HTTPS frontend requires an HTTPS backend URL.');
    }
  }

  return apiBaseUrl.replace(/\/+$/, '');
};

export async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const requestMethod = (options.method || 'GET').toUpperCase();
  let baseUrl: string;
  let url: string;
  try {
    baseUrl = getApiBaseUrl().replace(/\/$/, '');
    url = endpoint.startsWith('http') ? endpoint : `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
  } catch {
    throw new ApiError(0, getPublicErrorMessage(requestMethod, undefined, true));
  }

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
      // Keep backend diagnostics out of user-visible messages. Developers can
      // inspect the server logs for the underlying response details.
      const errorMessage = getPublicErrorMessage(requestMethod, response.status);

      const isPublicEndpoint =
        endpoint.includes('/auth/login') ||
        endpoint.includes('/auth/oauth') ||
        endpoint.includes('/health') ||
        endpoint.includes('/ready');

      if (response.status === 401 && !isPublicEndpoint) {
        clearStoredToken();
        if (unauthorizedListener) {
          try {
            unauthorizedListener();
          } catch {
            // Non-fatal
          }
        }
      }

      throw new ApiError(response.status, errorMessage);
    }

    return bodyData as T;
  } catch (error: any) {
    clearTimeout(timeoutId);

    if (error instanceof ApiError) {
      throw error;
    }

    if (error.name === 'AbortError') {
      throw new ApiError(0, getPublicErrorMessage(requestMethod, undefined, true));
    }

    if (error instanceof TypeError && /failed to fetch|networkerror|load failed/i.test(error.message)) {
      throw new ApiError(0, getPublicErrorMessage(requestMethod, undefined, true));
    }

    throw new ApiError(0, getPublicErrorMessage(requestMethod));
  }
}
