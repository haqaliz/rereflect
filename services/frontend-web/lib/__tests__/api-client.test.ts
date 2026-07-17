import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { apiClient } from '../api-client';

// Mock localStorage (same pattern as ThemeContext.test.tsx / AuthContext.test.tsx)
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

// Grab the interceptor functions directly rather than firing real requests —
// axios exposes registered handlers via `interceptors.<type>.handlers`.
const requestInterceptor = (apiClient.interceptors.request as any).handlers[0];
const responseInterceptor = (apiClient.interceptors.response as any).handlers[0];

describe('api-client request interceptor', () => {
  beforeEach(() => {
    localStorageMock.clear();
  });

  it('attaches Authorization: Bearer <token> when access_token is present in localStorage', () => {
    localStorageMock.setItem('access_token', 'abc123');
    const config = { headers: {} } as any;

    const result = requestInterceptor.fulfilled(config);

    expect(result.headers.Authorization).toBe('Bearer abc123');
  });

  it('omits the Authorization header when access_token is absent', () => {
    const config = { headers: {} } as any;

    const result = requestInterceptor.fulfilled(config);

    expect(result.headers.Authorization).toBeUndefined();
  });
});

describe('api-client response interceptor (401 skip-list)', () => {
  let originalLocation: Location;

  beforeEach(() => {
    localStorageMock.clear();
    originalLocation = window.location;
    // jsdom's window.location isn't a plain writable object, so it can't be
    // mutated in place for pathname/href assertions. Replacing it wholesale
    // is the standard workaround for pinning navigation decisions in jsdom.
    delete (window as any).location;
    window.location = { ...originalLocation, pathname: '/', href: '' } as any;
  });

  afterEach(() => {
    window.location = originalLocation;
  });

  function make401() {
    return { response: { status: 401 } };
  }

  it.each(['/login', '/login/callback', '/signup', '/invite/abc123', '/shared/report-1'])(
    'does not redirect on a 401 when pathname is %s (skip-list)',
    async (pathname) => {
      window.location.pathname = pathname;
      localStorageMock.setItem('access_token', 'stale-token');

      await expect(responseInterceptor.rejected(make401())).rejects.toBeDefined();

      expect(window.location.href).toBe('');
      // Token clearing happens regardless of which branch is taken.
      expect(localStorageMock.getItem('access_token')).toBeNull();
    }
  );

  it('redirects to /login on a 401 when pathname is not in the skip-list', async () => {
    window.location.pathname = '/dashboard';
    localStorageMock.setItem('access_token', 'stale-token');

    await expect(responseInterceptor.rejected(make401())).rejects.toBeDefined();

    expect(window.location.href).toBe('/login');
    expect(localStorageMock.getItem('access_token')).toBeNull();
  });

  it('leaves localStorage and navigation untouched for non-401 errors', async () => {
    window.location.pathname = '/dashboard';
    localStorageMock.setItem('access_token', 'still-valid');

    await expect(
      responseInterceptor.rejected({ response: { status: 500 } })
    ).rejects.toBeDefined();

    expect(window.location.href).toBe('');
    expect(localStorageMock.getItem('access_token')).toBe('still-valid');
  });
});
