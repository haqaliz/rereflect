import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import type { ReactNode } from 'react';

// Mock @react-oauth/google — capture the onSuccess handler passed to
// useGoogleLogin so tests can invoke it directly with a synthetic token
// response, without going through the real Google popup flow.
let capturedOnSuccess: ((tokenResponse: { access_token: string }) => void) | undefined;

vi.mock('@react-oauth/google', () => ({
  useGoogleLogin: (opts: { onSuccess: (tokenResponse: { access_token: string }) => void }) => {
    capturedOnSuccess = opts.onSuccess;
    return vi.fn();
  },
  GoogleOAuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

// NEXT_PUBLIC_GOOGLE_CLIENT_ID is read into a module-level const on first
// import of GoogleSignInButton.tsx, so each test that needs a different value
// re-imports the module fresh via vi.resetModules() rather than mutating
// process.env after the fact.
describe('GoogleSignInButton', () => {
  const originalClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

  afterEach(() => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = originalClientId;
    capturedOnSuccess = undefined;
    vi.resetModules();
  });

  it('renders nothing when NEXT_PUBLIC_GOOGLE_CLIENT_ID is unset', async () => {
    delete process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    vi.resetModules();
    const { GoogleSignInButton } = await import('../GoogleSignInButton');

    const { container } = render(
      <GoogleSignInButton mode="login" onSuccess={vi.fn()} onError={vi.fn()} />
    );

    expect(container.firstChild).toBeNull();
  });

  it('calls onSuccess with the access_token when useGoogleLogin succeeds', async () => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = 'test-client-id';
    vi.resetModules();
    const { GoogleSignInButton } = await import('../GoogleSignInButton');
    const onSuccess = vi.fn();

    render(<GoogleSignInButton mode="login" onSuccess={onSuccess} onError={vi.fn()} />);

    expect(capturedOnSuccess).toBeDefined();
    act(() => {
      capturedOnSuccess!({ access_token: 'fake-access-token' });
    });

    expect(onSuccess).toHaveBeenCalledWith('fake-access-token');
  });
});
