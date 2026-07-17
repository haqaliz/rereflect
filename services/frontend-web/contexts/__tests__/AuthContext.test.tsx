import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRouter, usePathname } from 'next/navigation';
import { AuthProvider, useAuth } from '../AuthContext';
import { authAPI } from '@/lib/api/auth';

// Mock next/navigation — AuthContext reads pathname to decide on redirects
// and calls router.push() directly, so both hooks need mocking.
vi.mock('next/navigation', () => ({
  useRouter: vi.fn(),
  usePathname: vi.fn(),
}));

// Mock the auth API module boundary — no real network calls.
vi.mock('@/lib/api/auth', () => ({
  authAPI: {
    getMe: vi.fn(),
  },
}));

// Mock localStorage (same pattern as ThemeContext.test.tsx)
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

const fakeUser = {
  id: 1,
  email: 'user@example.com',
  organization_id: 10,
  role: 'owner',
  plan: 'pro',
  is_system_admin: false,
};

const mockPush = vi.fn();

function TestConsumer() {
  const { user, isAuthenticated, login, logout } = useAuth();
  return (
    <div>
      <div data-testid="user-email">{user?.email ?? 'no-user'}</div>
      <div data-testid="is-authenticated">{String(isAuthenticated)}</div>
      <button onClick={() => login('new-token')}>Login</button>
      <button onClick={() => logout()}>Logout</button>
    </div>
  );
}

describe('AuthContext', () => {
  beforeEach(() => {
    localStorageMock.clear();
    mockPush.mockClear();
    vi.mocked(useRouter).mockReturnValue({ push: mockPush } as any);
    vi.mocked(authAPI.getMe).mockReset();
  });

  it('fetches and exposes the user when a token is present on mount', async () => {
    localStorageMock.setItem('access_token', 'valid-token');
    // '/' is public and not an auth route, so no redirect fires either way.
    vi.mocked(usePathname).mockReturnValue('/');
    vi.mocked(authAPI.getMe).mockResolvedValue(fakeUser);

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('user-email')).toHaveTextContent('user@example.com');
    });
    expect(screen.getByTestId('is-authenticated')).toHaveTextContent('true');
    expect(authAPI.getMe).toHaveBeenCalledTimes(1);
  });

  it('redirects to /login when no token is present on a protected route', async () => {
    vi.mocked(usePathname).mockReturnValue('/dashboard'); // not in publicRoutes

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/login');
    });
    expect(authAPI.getMe).not.toHaveBeenCalled();
  });

  it('login() persists the token to localStorage', async () => {
    // Public, tokenless mount — avoids the loading screen and any redirect,
    // so the consumer is available for interaction immediately.
    vi.mocked(usePathname).mockReturnValue('/');
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await user.click(screen.getByText('Login'));

    // NOTE: login() only persists the token; per current AuthContext code it
    // relies on the mount effect (keyed on [pathname, router]) to re-run and
    // fetch the user, so isAuthenticated does not flip synchronously from
    // this call alone. That's the real behavior being pinned here, not a
    // limitation of the test.
    expect(localStorageMock.getItem('access_token')).toBe('new-token');
  });

  it('logout() clears the token and redirects to /login', async () => {
    vi.mocked(usePathname).mockReturnValue('/'); // public, tokenless mount
    localStorageMock.setItem('access_token', 'stale-token');
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await user.click(screen.getByText('Logout'));

    expect(localStorageMock.getItem('access_token')).toBeNull();
    expect(mockPush).toHaveBeenCalledWith('/login');
  });

  it('treats /login/callback as a public route (no redirect to /login)', async () => {
    // No token, on the OIDC callback path — the provider must not bounce
    // this to /login before the callback page has a chance to store the
    // token from the URL fragment.
    vi.mocked(usePathname).mockReturnValue('/login/callback');

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('is-authenticated')).toHaveTextContent('false');
    });
    expect(mockPush).not.toHaveBeenCalledWith('/login');
  });

  it('clears the token and redirects when getMe() rejects', async () => {
    localStorageMock.setItem('access_token', 'invalid-token');
    vi.mocked(usePathname).mockReturnValue('/dashboard'); // protected route
    vi.mocked(authAPI.getMe).mockRejectedValue(new Error('401 Unauthorized'));

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(localStorageMock.getItem('access_token')).toBeNull();
    });
    expect(mockPush).toHaveBeenCalledWith('/login');
  });
});
