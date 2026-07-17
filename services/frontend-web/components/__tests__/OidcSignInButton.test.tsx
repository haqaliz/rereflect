import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getOidcStatus } from '@/lib/api/oidc';
import { OidcSignInButton } from '../OidcSignInButton';

vi.mock('@/lib/api/oidc', () => ({
  getOidcStatus: vi.fn(),
}));

describe('OidcSignInButton', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    vi.mocked(getOidcStatus).mockReset();
    // jsdom's window.location can't be mutated in place for href assertions;
    // replacing it wholesale is the standard workaround (mirrors the
    // Salesforce settings page test).
    // @ts-expect-error - overriding window.location for the test
    delete window.location;
    // @ts-expect-error - minimal stub sufficient for href assignment checks
    window.location = { href: '' };
  });

  afterEach(() => {
    window.location = originalLocation;
  });

  it('renders a button with the backend-provided label when SSO is enabled', async () => {
    vi.mocked(getOidcStatus).mockResolvedValue({
      enabled: true,
      button_label: 'Sign in with Okta',
    });

    render(<OidcSignInButton />);

    expect(
      await screen.findByRole('button', { name: 'Sign in with Okta' })
    ).toBeInTheDocument();
  });

  it('does a full-page navigation to /api/v1/auth/oidc/start on click', async () => {
    vi.mocked(getOidcStatus).mockResolvedValue({
      enabled: true,
      button_label: 'Sign in with SSO',
    });
    const user = userEvent.setup();

    render(<OidcSignInButton />);

    const button = await screen.findByRole('button', { name: 'Sign in with SSO' });
    await user.click(button);

    expect(window.location.href).toMatch(/\/api\/v1\/auth\/oidc\/start$/);
  });

  it('renders nothing when SSO is disabled', async () => {
    vi.mocked(getOidcStatus).mockResolvedValue({ enabled: false, button_label: '' });

    const { container } = render(<OidcSignInButton />);

    await waitFor(() => expect(getOidcStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing (fails open) when the status probe throws', async () => {
    vi.mocked(getOidcStatus).mockRejectedValue(new Error('network error'));

    const { container } = render(<OidcSignInButton />);

    await waitFor(() => expect(getOidcStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
