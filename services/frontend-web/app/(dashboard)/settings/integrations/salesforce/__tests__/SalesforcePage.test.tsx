/**
 * Tests for the Salesforce connect/detail page (Phase 3).
 *
 * API contract tests verify:
 * 1. salesforceAPI.getConnectUrl / getStatus / disconnect / test are callable.
 *
 * Component rendering tests verify:
 * 2. Member users are redirected to /settings/preferences; the OAuth CTA is
 *    not rendered.
 * 3. Disconnected state renders an OAuth CTA ("Connect with Salesforce")
 *    button — never a token input/form.
 * 4. Clicking the CTA calls getConnectUrl() and navigates the browser to
 *    auth_url (window.location.href).
 * 5. Connected state renders the stats grid (instance_url, sf_org_id,
 *    connected_at, last_synced_at, contacts_synced/matched) + Test/Disconnect.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const mockReplace = vi.fn();
const mockPush = vi.fn();

// Mutable so individual tests can simulate `?connected=1` / `?oauth_error=...`
// return params from the OAuth callback redirect.
let mockSearchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  useSearchParams: () => mockSearchParams,
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/lib/api/salesforce', () => ({
  salesforceAPI: {
    getConnectUrl: vi.fn(),
    getStatus: vi.fn(),
    disconnect: vi.fn(),
    test: vi.fn(),
  },
}));

import { salesforceAPI } from '@/lib/api/salesforce';
import { useAuth } from '@/contexts/AuthContext';
import SalesforceSettingsPage from '../page';

function makeAuthContext(role: string) {
  return {
    user: {
      id: 1,
      email: `${role}@test.com`,
      role,
      plan: 'business',
      organization_id: 1,
      is_system_admin: false,
    },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  };
}

const disconnectedStatus = {
  connected: false,
  instance_url: null,
  sf_org_id: null,
  last_synced_at: null,
  last_sync_status: null,
  last_error: null,
  contacts_synced: 0,
  contacts_matched: 0,
  connected_at: null,
};

const connectedStatus = {
  connected: true,
  instance_url: 'https://acme.my.salesforce.com',
  sf_org_id: '00D000000000EXAMPLE',
  last_synced_at: '2026-06-30T12:00:00Z',
  last_sync_status: 'success',
  last_error: null,
  contacts_synced: 42,
  contacts_matched: 30,
  connected_at: '2026-06-01T00:00:00Z',
};

// ─── API contract tests ─────────────────────────────────────────────────────

describe('Salesforce detail page — API contract', () => {
  beforeEach(() => vi.clearAllMocks());

  it('salesforceAPI.getConnectUrl is callable and returns auth_url', async () => {
    (salesforceAPI.getConnectUrl as any).mockResolvedValue({
      auth_url: 'https://login.salesforce.com/services/oauth2/authorize?client_id=abc',
    });
    const result = await salesforceAPI.getConnectUrl();
    expect(salesforceAPI.getConnectUrl).toHaveBeenCalled();
    expect(result.auth_url).toContain('salesforce.com');
  });

  it('salesforceAPI.getStatus is callable', async () => {
    (salesforceAPI.getStatus as any).mockResolvedValue(disconnectedStatus);
    const result = await salesforceAPI.getStatus();
    expect(salesforceAPI.getStatus).toHaveBeenCalled();
    expect(result.connected).toBe(false);
  });

  it('salesforceAPI.disconnect is callable', async () => {
    (salesforceAPI.disconnect as any).mockResolvedValue({ success: true, message: 'ok' });
    const result = await salesforceAPI.disconnect();
    expect(salesforceAPI.disconnect).toHaveBeenCalled();
    expect(result.success).toBe(true);
  });

  it('salesforceAPI.test is callable', async () => {
    (salesforceAPI.test as any).mockResolvedValue({
      success: true,
      message: 'Salesforce connection is healthy.',
    });
    const result = await salesforceAPI.test();
    expect(salesforceAPI.test).toHaveBeenCalled();
    expect(result.success).toBe(true);
  });

  it('salesforceAPI has no connect(token) method — OAuth redirect only', () => {
    expect((salesforceAPI as any).connect).toBeUndefined();
  });
});

// ─── Component rendering tests ───────────────────────────────────────────────

describe('SalesforceSettingsPage — component', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams = new URLSearchParams();
    // @ts-expect-error - overriding window.location for the test
    delete window.location;
    // @ts-expect-error - minimal stub sufficient for href assignment checks
    window.location = { href: '' };
  });

  afterEach(() => {
    window.location = originalLocation;
  });

  it('redirects a member user to /settings/preferences and does not render the OAuth CTA', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('member'));
    (salesforceAPI.getStatus as any).mockResolvedValue(disconnectedStatus);

    render(<SalesforceSettingsPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/settings/preferences');
    });

    expect(screen.queryByRole('button', { name: /connect with salesforce/i })).not.toBeInTheDocument();
  });

  it('renders an OAuth CTA (not a token form) when disconnected', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('admin'));
    (salesforceAPI.getStatus as any).mockResolvedValue(disconnectedStatus);

    render(<SalesforceSettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /connect with salesforce/i })).toBeInTheDocument();
    });

    // Never a token input/form for Salesforce (OAuth only).
    expect(screen.queryByLabelText(/access token/i)).not.toBeInTheDocument();
  });

  it('clicking the OAuth CTA calls getConnectUrl and navigates to auth_url', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('owner'));
    (salesforceAPI.getStatus as any).mockResolvedValue(disconnectedStatus);
    (salesforceAPI.getConnectUrl as any).mockResolvedValue({
      auth_url: 'https://login.salesforce.com/services/oauth2/authorize?client_id=abc',
    });

    render(<SalesforceSettingsPage />);

    const ctaButton = await screen.findByRole('button', { name: /connect with salesforce/i });
    fireEvent.click(ctaButton);

    await waitFor(() => {
      expect(salesforceAPI.getConnectUrl).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(window.location.href).toBe(
        'https://login.salesforce.com/services/oauth2/authorize?client_id=abc',
      );
    });
  });

  it('renders the stats grid + Test/Disconnect when connected', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('owner'));
    (salesforceAPI.getStatus as any).mockResolvedValue(connectedStatus);

    render(<SalesforceSettingsPage />);

    await waitFor(() => {
      expect(screen.getByText(connectedStatus.instance_url)).toBeInTheDocument();
    });

    expect(screen.getByText(connectedStatus.sf_org_id)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /test/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /disconnect/i })).toBeInTheDocument();
  });
});

// ─── OAuth callback return params ────────────────────────────────────────────
//
// The backend's Salesforce OAuth callback redirects the browser back to this
// detail page with `?connected=1` (success) or `?oauth_error=<code>`
// (failure) — see services/backend-api/src/api/routes/salesforce_integration.py
// (error_redirect_base = .../settings/integrations/salesforce). Unlike Linear,
// which redirects to the integrations index page, Salesforce must handle its
// own return params here.

describe('SalesforceSettingsPage — OAuth return params', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams = new URLSearchParams();
    // @ts-expect-error - overriding window.location for the test
    delete window.location;
    // @ts-expect-error - minimal stub sufficient for href assignment checks
    window.location = { href: '' };
  });

  afterEach(() => {
    window.location = originalLocation;
  });

  it('shows a friendly error message for ?oauth_error=another_crm_active', async () => {
    mockSearchParams = new URLSearchParams({ oauth_error: 'another_crm_active' });
    (useAuth as any).mockReturnValue(makeAuthContext('owner'));
    (salesforceAPI.getStatus as any).mockResolvedValue(disconnectedStatus);

    render(<SalesforceSettingsPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/another CRM integration is already active/i),
      ).toBeInTheDocument();
    });

    // Strips the query param so a refresh doesn't re-show the banner.
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/settings/integrations/salesforce');
    });
  });

  it('shows a success indicator for ?connected=1', async () => {
    mockSearchParams = new URLSearchParams({ connected: '1' });
    (useAuth as any).mockReturnValue(makeAuthContext('owner'));
    (salesforceAPI.getStatus as any).mockResolvedValue(connectedStatus);

    render(<SalesforceSettingsPage />);

    await waitFor(() => {
      expect(screen.getByText(/successfully connected/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/settings/integrations/salesforce');
    });
  });
});
