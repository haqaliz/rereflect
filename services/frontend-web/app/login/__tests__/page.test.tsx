import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRouter } from 'next/navigation';
import { authAPI } from '@/lib/api/auth';
import { useAuth } from '@/contexts/AuthContext';
import LoginPage, { resolveSsoErrorMessage } from '../page';

// Mock next/navigation — the page calls router.push('/dashboard') on success.
vi.mock('next/navigation', () => ({
  useRouter: vi.fn(),
}));

// Mock the auth API module boundary — no real network calls.
vi.mock('@/lib/api/auth', () => ({
  authAPI: {
    login: vi.fn(),
    googleLogin: vi.fn(),
  },
}));

// Mock AuthContext — this is a smoke test of the submit paths, not of the
// auth-loading/redirect behavior already covered by AuthContext.test.tsx.
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

// Mock analytics — avoids pulling mixpanel-browser into this test's concerns.
vi.mock('@/lib/analytics', () => ({
  analytics: { login: vi.fn() },
}));

// Mock gsap — the page runs entrance animations on mount via gsap.context();
// skipping the animation callback keeps this test focused on submit behavior.
vi.mock('gsap', () => ({
  default: {
    context: (_fn: () => void) => ({ revert: vi.fn() }),
    set: vi.fn(),
    to: vi.fn(),
  },
}));

// Mock GoogleSignInButton — its own behavior (reading the client id env var,
// wiring useGoogleLogin) is characterized in GoogleSignInButton.test.tsx.
// Here it's stubbed as a single button that invokes onSuccess with a fake
// access token, so this test only exercises LoginPage's own handler.
vi.mock('@/components/GoogleSignInButton', () => ({
  GoogleSignInButton: ({ onSuccess }: { onSuccess: (token: string) => void }) => (
    <button onClick={() => onSuccess('fake-google-access-token')}>
      google-signin-stub
    </button>
  ),
}));

// Mock the OIDC status probe — OidcSignInButton's own render/hide behavior
// is characterized in OidcSignInButton.test.tsx. Rejecting here keeps this
// test free of real network calls and matches the "not configured" default.
vi.mock('@/lib/api/oidc', () => ({
  getOidcStatus: vi.fn().mockRejectedValue(new Error('not configured')),
}));

// Mock localStorage (same pattern as AuthContext.test.tsx / api-client.test.ts)
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

const mockPush = vi.fn();
const originalClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

describe('LoginPage', () => {
  beforeEach(() => {
    localStorageMock.clear();
    mockPush.mockClear();
    vi.mocked(useRouter).mockReturnValue({ push: mockPush } as any);
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
    vi.mocked(authAPI.login).mockReset();
    vi.mocked(authAPI.googleLogin).mockReset();
    // Google branch is gated by this env var read inline at render time (not
    // module-load time, unlike GoogleSignInButton.tsx's own const), so it can
    // be toggled per-test without vi.resetModules().
    delete process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = originalClientId;
  });

  it('password submit calls authAPI.login and stores the returned token', async () => {
    vi.mocked(authAPI.login).mockResolvedValue({
      access_token: 'password-token',
      token_type: 'bearer',
    });
    const user = userEvent.setup();

    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'hunter2');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));

    await waitFor(() => {
      expect(authAPI.login).toHaveBeenCalledWith({
        email: 'user@example.com',
        password: 'hunter2',
      });
    });
    expect(localStorageMock.getItem('access_token')).toBe('password-token');
    expect(mockPush).toHaveBeenCalledWith('/dashboard');
  });

  it('Google branch calls authAPI.googleLogin and stores the returned token', async () => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = 'stub-client-id';
    vi.mocked(authAPI.googleLogin).mockResolvedValue({
      access_token: 'google-token',
      token_type: 'bearer',
    });
    const user = userEvent.setup();

    render(<LoginPage />);

    await user.click(screen.getByRole('button', { name: 'google-signin-stub' }));

    await waitFor(() => {
      expect(authAPI.googleLogin).toHaveBeenCalledWith({
        access_token: 'fake-google-access-token',
      });
    });
    expect(localStorageMock.getItem('access_token')).toBe('google-token');
    expect(mockPush).toHaveBeenCalledWith('/dashboard');
  });
});

// M-2: deterministic, protocol-aware `sso_error` code resolution. Replaces
// the old magic-string compare (`oidcMessage !== '<fallback literal>'`) with
// a code-set lookup — these tests exercise the extracted helper directly so
// they pin the resolution rule itself, independent of page rendering.
describe('resolveSsoErrorMessage', () => {
  it('renders SAML wording for a SAML-specific code (e.g. signature)', () => {
    expect(resolveSsoErrorMessage('signature')).toBe(
      "We couldn't verify the response from your identity provider. Please try again."
    );
  });

  it('renders SAML wording for "unverified" — NOT the OIDC wording', () => {
    const message = resolveSsoErrorMessage('unverified');
    expect(message).toBe("Your identity provider didn't provide an email address.");
    expect(message).not.toBe('Your identity provider did not confirm a verified email.');
  });

  it('renders OIDC wording for an OIDC-only code (e.g. exchange)', () => {
    expect(resolveSsoErrorMessage('exchange')).toBe('Single sign-on failed. Please try again.');
  });

  it('falls back to the generic message for an unknown code', () => {
    expect(resolveSsoErrorMessage('something_unexpected')).toBe(
      'Single sign-on could not be completed.'
    );
  });
});
