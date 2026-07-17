/**
 * Tests for the admin SSO settings page — the OIDC config card plus the
 * SAML config card rendered below it (SamlConfigCard, a separate child
 * component).
 *
 * Verifies:
 * 1. Non-admin (member) users are redirected to /settings/preferences; neither
 *    form renders and neither config is fetched.
 * 2. Owner/admin users see the OIDC form; getOidcConfig is called and fields
 *    populate from the response — the client secret input is NEVER prefilled
 *    with a secret, only a hint is shown.
 * 3. Saving the OIDC card calls putOidcConfig with the entered values
 *    (including a newly typed secret); a rejected (422) PUT renders a
 *    friendly inline error instead of crashing.
 * 4. Enabling OIDC with an empty allowlist shows the deny-all warning.
 * 5. Deleting the OIDC config shows a friendly message on a 404.
 * 6-10. The parallel SAML card: loads config (fingerprint hint, not the raw
 *    PEM), saves incl. a pasted cert, surfaces the cross-provider 422
 *    friendly, shows its own deny-all warning, and its own delete-404
 *    message — each scoped with `within` so it can't collide with the OIDC
 *    card's now-duplicated Save/Disconnect/switch controls.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

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

vi.mock('@/lib/api/saml', () => ({
  getSamlConfig: vi.fn(),
  putSamlConfig: vi.fn(),
  deleteSamlConfig: vi.fn(),
}));

// ─── imports (after mocks) ───────────────────────────────────────────────────

import { useAuth } from '@/contexts/AuthContext';
import { getOidcConfig, putOidcConfig, deleteOidcConfig } from '@/lib/api/oidc';
import { getSamlConfig, putSamlConfig, deleteSamlConfig } from '@/lib/api/saml';
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

const samlUnconfiguredResponse = {
  configured: false,
  idp_entity_id: null,
  idp_sso_url: null,
  cert_fingerprint: null,
  email_attribute: null,
  enabled: false,
  allowed_email_domains: [],
  button_label: null,
};

const samlConfiguredResponse = {
  configured: true,
  idp_entity_id: 'https://idp.example.com/entity',
  idp_sso_url: 'https://idp.example.com/sso',
  cert_fingerprint: 'AB:CD:EF:00',
  email_attribute: null,
  enabled: true,
  allowed_email_domains: ['example.com'],
  button_label: 'Sign in with Acme SAML',
};

describe('SsoSettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getOidcConfig as any).mockResolvedValue(unconfiguredResponse);
    (getSamlConfig as any).mockResolvedValue(samlUnconfiguredResponse);
  });

  it('redirects a member user to /settings/preferences and does not render either form', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('member'));

    render(<SsoSettingsPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/settings/preferences');
    });

    expect(screen.queryByLabelText(/issuer url/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/idp entity id/i)).not.toBeInTheDocument();
    expect(getOidcConfig).not.toHaveBeenCalled();
    expect(getSamlConfig).not.toHaveBeenCalled();
  });

  it('renders the OIDC form for an owner, loads the config, and never prefills the secret input', async () => {
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

  it('submits the entered OIDC values (including a newly typed secret) via putOidcConfig, and renders a friendly inline error on a 422', async () => {
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

    // Two "Save" buttons now exist (OIDC + SAML cards) — scope to the first (OIDC).
    fireEvent.click(screen.getAllByRole('button', { name: /^save$/i })[0]);

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

  it('shows the deny-all warning when OIDC is enabled with an empty allowlist', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('owner'));
    (getOidcConfig as any).mockResolvedValue(unconfiguredResponse);

    render(<SsoSettingsPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/issuer url/i)).toBeInTheDocument();
    });

    expect(screen.queryByText(/empty allowlist/i)).not.toBeInTheDocument();

    // Two switches now exist (OIDC + SAML cards) — scope to the first (OIDC).
    fireEvent.click(screen.getAllByRole('switch')[0]);

    await waitFor(() => {
      expect(screen.getByText(/empty allowlist = deny-all/i)).toBeInTheDocument();
    });
  });

  it('deletes the OIDC config and shows a friendly message on a 404', async () => {
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

  describe('SAML config card', () => {
    it('renders the SAML card for an owner, loads the config, and shows the cert fingerprint hint (never the raw PEM)', async () => {
      (useAuth as any).mockReturnValue(makeAuthContext('owner'));
      (getSamlConfig as any).mockResolvedValue(samlConfiguredResponse);

      render(<SsoSettingsPage />);

      await waitFor(() => {
        expect(getSamlConfig).toHaveBeenCalled();
      });

      const card = within(await screen.findByTestId('saml-config-card'));

      expect(card.getByDisplayValue('https://idp.example.com/entity')).toBeInTheDocument();
      expect(card.getByDisplayValue('https://idp.example.com/sso')).toBeInTheDocument();

      const certInput = card.getByLabelText(/idp x\.509 certificate/i) as HTMLTextAreaElement;
      expect(certInput.value).toBe('');
      expect(card.getByText(/a certificate is already stored/i)).toBeInTheDocument();
      expect(card.getByText(/AB:CD:EF:00/)).toBeInTheDocument();
    });

    it('submits the entered SAML values including a pasted cert via putSamlConfig', async () => {
      (useAuth as any).mockReturnValue(makeAuthContext('admin'));
      (getSamlConfig as any).mockResolvedValue(samlUnconfiguredResponse);

      render(<SsoSettingsPage />);

      const card = within(await screen.findByTestId('saml-config-card'));

      await waitFor(() => {
        expect(card.getByLabelText(/idp entity id/i)).toBeInTheDocument();
      });

      fireEvent.change(card.getByLabelText(/idp entity id/i), {
        target: { value: 'https://idp.example.com/entity' },
      });
      fireEvent.change(card.getByLabelText(/idp sso url/i), {
        target: { value: 'https://idp.example.com/sso' },
      });
      fireEvent.change(card.getByLabelText(/idp x\.509 certificate/i), {
        target: { value: '-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----' },
      });

      (putSamlConfig as any).mockResolvedValueOnce(samlConfiguredResponse);

      fireEvent.click(card.getByRole('button', { name: /^save$/i }));

      await waitFor(() => {
        expect(putSamlConfig).toHaveBeenCalledWith(
          expect.objectContaining({
            idp_entity_id: 'https://idp.example.com/entity',
            idp_sso_url: 'https://idp.example.com/sso',
            idp_x509_cert: '-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----',
          })
        );
      });
    });

    it('shows a friendly message when the cross-provider 422 guard rejects enabling SAML', async () => {
      (useAuth as any).mockReturnValue(makeAuthContext('owner'));
      (getSamlConfig as any).mockResolvedValue(samlUnconfiguredResponse);

      render(<SsoSettingsPage />);

      const card = within(await screen.findByTestId('saml-config-card'));

      await waitFor(() => {
        expect(card.getByLabelText(/idp entity id/i)).toBeInTheDocument();
      });

      fireEvent.change(card.getByLabelText(/idp entity id/i), {
        target: { value: 'https://idp.example.com/entity' },
      });
      fireEvent.change(card.getByLabelText(/idp sso url/i), {
        target: { value: 'https://idp.example.com/sso' },
      });
      fireEvent.change(card.getByLabelText(/idp x\.509 certificate/i), {
        target: { value: '-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----' },
      });

      (putSamlConfig as any).mockRejectedValueOnce({
        response: { status: 422, data: { detail: 'Disable OIDC before enabling SAML.' } },
      });

      fireEvent.click(card.getByRole('button', { name: /^save$/i }));

      await waitFor(() => {
        expect(card.getByText(/disable oidc before enabling saml/i)).toBeInTheDocument();
      });

      // No crash — the SAML form is still rendered and usable.
      expect(card.getByLabelText(/idp entity id/i)).toBeInTheDocument();
    });

    it('shows the deny-all warning when SAML is enabled with an empty allowlist', async () => {
      (useAuth as any).mockReturnValue(makeAuthContext('owner'));
      (getSamlConfig as any).mockResolvedValue(samlUnconfiguredResponse);

      render(<SsoSettingsPage />);

      const card = within(await screen.findByTestId('saml-config-card'));

      await waitFor(() => {
        expect(card.getByLabelText(/idp entity id/i)).toBeInTheDocument();
      });

      expect(card.queryByText(/empty allowlist/i)).not.toBeInTheDocument();

      fireEvent.click(card.getByRole('switch'));

      await waitFor(() => {
        expect(card.getByText(/empty allowlist = deny-all/i)).toBeInTheDocument();
      });
    });

    it('deletes the SAML config and shows a friendly message on a 404', async () => {
      (useAuth as any).mockReturnValue(makeAuthContext('owner'));
      (getSamlConfig as any).mockResolvedValue(samlConfiguredResponse);
      (deleteSamlConfig as any).mockRejectedValueOnce({ response: { status: 404 } });

      render(<SsoSettingsPage />);

      const card = within(await screen.findByTestId('saml-config-card'));

      await waitFor(() => {
        expect(card.getByRole('button', { name: /disconnect/i })).toBeInTheDocument();
      });

      fireEvent.click(card.getByRole('button', { name: /disconnect/i }));

      // The confirm dialog is rendered via a Radix portal (document.body),
      // so it isn't a descendant of the card testid element — query it
      // unscoped, same as the OIDC delete test.
      const confirmButtons = await screen.findAllByRole('button', { name: /disconnect/i });
      fireEvent.click(confirmButtons[confirmButtons.length - 1]);

      await waitFor(() => {
        expect(deleteSamlConfig).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(card.getByText(/nothing to remove/i)).toBeInTheDocument();
      });
    });
  });
});
