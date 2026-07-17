import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import LoginCallbackPage from '../page';

// Mock next/navigation — the page calls router.replace('/dashboard') on success.
vi.mock('next/navigation', () => ({
  useRouter: vi.fn(),
}));

// Mock AuthContext — this page only needs login(); the loading/redirect
// behavior of AuthProvider itself is covered by AuthContext.test.tsx.
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockReplace = vi.fn();
const mockLogin = vi.fn();

// Helper to set the URL fragment/query before mount, mirroring how the
// browser lands on this page after the backend's redirect.
function setLocation(hash: string, search = '') {
  window.history.replaceState(null, '', `/login/callback${search}${hash}`);
}

describe('LoginCallbackPage', () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockLogin.mockClear();
    vi.mocked(useRouter).mockReturnValue({ replace: mockReplace } as any);
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      login: mockLogin,
      logout: vi.fn(),
    });
    setLocation('');
  });

  it('reads the token from the URL fragment, logs in, and redirects to the dashboard', async () => {
    setLocation('#token=abc.def.ghi');

    render(<LoginCallbackPage />);

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('abc.def.ghi');
    });
    expect(mockReplace).toHaveBeenCalledWith('/dashboard');
    // The fragment must be scrubbed from the URL so the token never lingers.
    expect(window.location.hash).toBe('');
  });

  it('shows an error state and does not redirect when no token is present', async () => {
    setLocation('');

    render(<LoginCallbackPage />);

    expect(await screen.findByText(/single sign-on didn.t complete/i)).toBeInTheDocument();
    expect(mockLogin).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalledWith('/dashboard');
  });

  it('shows an error state when the fragment carries an sso_error instead of a token', async () => {
    setLocation('#sso_error=domain');

    render(<LoginCallbackPage />);

    expect(await screen.findByText(/single sign-on didn.t complete/i)).toBeInTheDocument();
    expect(mockLogin).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
