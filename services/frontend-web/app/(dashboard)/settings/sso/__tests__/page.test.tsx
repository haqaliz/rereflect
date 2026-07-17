/**
 * Tests for the admin OIDC SSO settings page.
 *
 * Verifies:
 * 1. Non-admin (member) users are redirected to /settings/preferences; form not rendered.
 * 2. Owner/admin users see the form; getOidcConfig is called and fields populate from the
 *    response — the client secret input is NEVER prefilled with a secret, only a hint is shown.
 * 3. Saving calls putOidcConfig with the entered values (including a newly typed secret); a
 *    rejected (422) PUT renders a friendly inline error instead of crashing.
 * 4. Enabling SSO with an empty allowlist shows the deny-all warning.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

// ─── module-level mock fns ─────────────────────────────────────────────────

const mockReplace = vi.fn();
const mockPush = vi.fn();

// ─── mocks ──────────────────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  usePathname: () => '/settings/sso',
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/lib/api/oidc', () => ({
  getOidcConfig: vi.fn(),
  putOidcConfig: vi.fn(),
  deleteOidcConfig: vi.fn(),
}));

// ─── imports (after mocks) ───────────────────────────────────────────────────

import { useAuth } from '@/contexts/AuthContext';
import { getOidcConfig, putOidcConfig, deleteOidcConfig } from '@/lib/api/oidc';
import SsoSettingsPage from '../page';

// ─── shared fixtures ─────────────────────────────────────────────────────────

function makeAuthContext(role: string) {
  return {
    user: {
      id: 1,
      email: `${role}@test.com`,
      role,
      plan: 'enterprise',
      organization_id: 1,
      is_system_admin: false,
    },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  };
}

const unconfiguredResponse = {
  configured: false,
  issuer_url: null,
  client_id: null,
  secret_hint: null,
  enabled: false,
  allowed_email_domains: [],
  button_label: null,
};

const configuredResponse = {
  configured: true,
  issuer_url: 'https://idp.example.com',
  client_id: 'client-abc',
  secret_hint: '...wxyz',
  enabled: true,
  allowed_email_domains: ['example.com'],
  button_label: 'Sign in with Acme SSO',
};

describe('SsoSettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getOidcConfig as any).mockResolvedValue(unconfiguredResponse);
  });

  it('redirects a member user to /settings/preferences and does not render the form', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('member'));

    render(<SsoSettingsPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/settings/preferences');
    });

    expect(screen.queryByLabelText(/issuer url/i)).not.toBeInTheDocument();
    expect(getOidcConfig).not.toHaveBeenCalled();
  });

  it('renders the form for an owner, loads the config, and never prefills the secret input', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('owner'));
    (getOidcConfig as any).mockResolvedValue(configuredResponse);

    render(<SsoSettingsPage />);

    await waitFor(() => {
      expect(getOidcConfig).toHaveBeenCalled();
    });

    expect(await screen.findByDisplayValue('https://idp.example.com')).toBeInTheDocument();
    expect(screen.getByDisplayValue('client-abc')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Sign in with Acme SSO')).toBeInTheDocument();

    const secretInput = screen.getByLabelText(/client secret/i) as HTMLInputElement;
    expect(secretInput.value).toBe('');
    expect(secretInput).toHaveAttribute('type', 'password');
    expect(secretInput.placeholder).toContain('...wxyz');

    // The secret hint is shown in helper text, but the raw secret never appears anywhere.
    expect(screen.getByText(/a secret is already stored/i)).toBeInTheDocument();
  });

  it('submits the entered values (including a newly typed secret) via putOidcConfig, and renders a friendly inline error on a 422', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('admin'));
    (getOidcConfig as any).mockResolvedValue(unconfiguredResponse);

    render(<SsoSettingsPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/issuer url/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/issuer url/i), {
      target: { value: 'https://new-idp.example.com' },
    });
    fireEvent.change(screen.getByLabelText(/client id/i), {
      target: { value: 'new-client-id' },
    });
    fireEvent.change(screen.getByLabelText(/client secret/i), {
      target: { value: 'super-secret-value' },
    });

    // First save: rejected with a 422 (D5 duplicate-enabled-config style error).
    (putOidcConfig as any).mockRejectedValueOnce({
      response: { status: 422, data: { detail: 'Another SSO configuration is already enabled.' } },
    });

    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      expect(putOidcConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          issuer_url: 'https://new-idp.example.com',
          client_id: 'new-client-id',
          client_secret: 'super-secret-value',
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/another sso configuration is already enabled/i)).toBeInTheDocument();
    });

    // No crash — the form is still rendered and usable.
    expect(screen.getByLabelText(/issuer url/i)).toBeInTheDocument();
  });

  it('shows the deny-all warning when SSO is enabled with an empty allowlist', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('owner'));
    (getOidcConfig as any).mockResolvedValue(unconfiguredResponse);

    render(<SsoSettingsPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/issuer url/i)).toBeInTheDocument();
    });

    expect(screen.queryByText(/empty allowlist/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(screen.getByText(/empty allowlist = deny-all/i)).toBeInTheDocument();
    });
  });

  it('deletes the config and shows a friendly message on a 404', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('owner'));
    (getOidcConfig as any).mockResolvedValue(configuredResponse);
    (deleteOidcConfig as any).mockRejectedValueOnce({ response: { status: 404 } });

    render(<SsoSettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /disconnect/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /disconnect/i }));

    const confirmButtons = await screen.findAllByRole('button', { name: /disconnect/i });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(deleteOidcConfig).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText(/nothing to remove/i)).toBeInTheDocument();
    });
  });
});
