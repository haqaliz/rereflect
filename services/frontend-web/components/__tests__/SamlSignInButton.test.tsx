import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getSamlStatus } from '@/lib/api/saml';
import { SamlSignInButton } from '../SamlSignInButton';

vi.mock('@/lib/api/saml', () => ({
  getSamlStatus: vi.fn(),
}));

describe('SamlSignInButton', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    vi.mocked(getSamlStatus).mockReset();
    // jsdom's window.location can't be mutated in place for href assertions;
    // replacing it wholesale is the standard workaround (mirrors
    // OidcSignInButton's test).
    // @ts-expect-error - overriding window.location for the test
    delete window.location;
    // @ts-expect-error - minimal stub sufficient for href assignment checks
    window.location = { href: '' };
  });

  afterEach(() => {
    window.location = originalLocation;
  });

  it('renders a button with the backend-provided label when SSO is enabled', async () => {
    vi.mocked(getSamlStatus).mockResolvedValue({
      enabled: true,
      button_label: 'Sign in with Okta SAML',
    });

    render(<SamlSignInButton />);

    expect(
      await screen.findByRole('button', { name: 'Sign in with Okta SAML' })
    ).toBeInTheDocument();
  });

  it('does a full-page navigation to /api/v1/auth/saml/login on click', async () => {
    vi.mocked(getSamlStatus).mockResolvedValue({
      enabled: true,
      button_label: 'Sign in with SSO',
    });
    const user = userEvent.setup();

    render(<SamlSignInButton />);

    const button = await screen.findByRole('button', { name: 'Sign in with SSO' });
    await user.click(button);

    expect(window.location.href).toMatch(/\/api\/v1\/auth\/saml\/login$/);
  });

  it('renders nothing when SSO is disabled', async () => {
    vi.mocked(getSamlStatus).mockResolvedValue({ enabled: false, button_label: '' });

    const { container } = render(<SamlSignInButton />);

    await waitFor(() => expect(getSamlStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing (fails open) when the status probe throws', async () => {
    vi.mocked(getSamlStatus).mockRejectedValue(new Error('network error'));

    const { container } = render(<SamlSignInButton />);

    await waitFor(() => expect(getSamlStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
