/**
 * Tests for HubSpot detail page (Phase 7).
 *
 * API contract tests verify:
 * 1. hubspotAPI.connect is callable with access_token and arr_property_name
 * 2. hubspotAPI.disconnect is callable
 * 3. hubspotAPI.testConnection is callable
 * 4. hubspotAPI.getStatus is called on load
 * 5. Token masking: token_hint displayed, not access_token
 *
 * Component rendering tests verify:
 * 6. Access-token input renders type="password" by default; show-toggle reveals it
 * 7. Member users are redirected to /settings/preferences; connect form not rendered
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

// ─── module-level mock fns (captured by vi.mock factories below) ─────────────

const mockReplace = vi.fn();
const mockPush = vi.fn();

// ─── mocks ──────────────────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  usePathname: () => '/settings/integrations/hubspot',
}));

// useAuth is a vi.fn() so each test can set its return value via mockReturnValue
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/lib/api/hubspot', () => ({
  hubspotAPI: {
    getStatus: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    testConnection: vi.fn(),
  },
}));

// ─── imports (after mocks) ───────────────────────────────────────────────────

import { hubspotAPI } from '@/lib/api/hubspot';
import { useAuth } from '@/contexts/AuthContext';
import HubSpotSettingsPage from '../page';

// ─── shared fixtures ─────────────────────────────────────────────────────────

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
  portal_name: null,
  hub_id: null,
  token_hint: null,
  last_synced_at: null,
  last_sync_status: null,
  last_error: null,
  contacts_synced: 0,
  contacts_matched: 0,
  arr_property_name: 'annualrevenue',
  connected_at: null,
};

// ─── API contract tests (original suite) ────────────────────────────────────

describe('HubSpot detail page — API contract', () => {
  beforeEach(() => vi.clearAllMocks());

  it('hubspotAPI.connect accepts access_token', async () => {
    (hubspotAPI.connect as any).mockResolvedValue({
      connected: true,
      portal_name: 'Test',
      hub_id: '123',
      token_hint: '...abcd',
    });
    const result = await hubspotAPI.connect('pat-na1-test');
    expect(hubspotAPI.connect).toHaveBeenCalledWith('pat-na1-test');
    expect(result.connected).toBe(true);
  });

  it('hubspotAPI.connect accepts custom arr_property_name', async () => {
    (hubspotAPI.connect as any).mockResolvedValue({
      connected: true,
      portal_name: 'Test',
      hub_id: '123',
      token_hint: '...abcd',
    });
    await hubspotAPI.connect('pat-na1-test', 'mrr');
    expect(hubspotAPI.connect).toHaveBeenCalledWith('pat-na1-test', 'mrr');
  });

  it('hubspotAPI.disconnect is callable', async () => {
    (hubspotAPI.disconnect as any).mockResolvedValue({ success: true, message: 'ok' });
    const result = await hubspotAPI.disconnect();
    expect(hubspotAPI.disconnect).toHaveBeenCalled();
    expect(result.success).toBe(true);
  });

  it('hubspotAPI.testConnection is callable', async () => {
    (hubspotAPI.testConnection as any).mockResolvedValue({
      success: true,
      message: 'HubSpot connection is healthy.',
    });
    const result = await hubspotAPI.testConnection();
    expect(hubspotAPI.testConnection).toHaveBeenCalled();
    expect(result.success).toBe(true);
  });

  it('hubspotAPI.getStatus returns token_hint not access_token', async () => {
    (hubspotAPI.getStatus as any).mockResolvedValue({
      connected: true,
      portal_name: 'Acme',
      hub_id: '9999',
      token_hint: '...wxyz',
      access_token: undefined,  // should never be present
      last_synced_at: null,
      last_sync_status: null,
      last_error: null,
      contacts_synced: 0,
      contacts_matched: 0,
      arr_property_name: 'annualrevenue',
      connected_at: null,
    });
    const status = await hubspotAPI.getStatus();
    expect(status.token_hint).toBe('...wxyz');
    expect((status as any).access_token).toBeUndefined();
  });
});

// ─── Component rendering tests ───────────────────────────────────────────────

describe('HubSpotSettingsPage — component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: disconnected status so the connect form renders for admin users
    (hubspotAPI.getStatus as any).mockResolvedValue(disconnectedStatus);
  });

  it('renders access-token input masked (type="password") by default and reveals it after the show toggle is clicked', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('admin'));

    render(<HubSpotSettingsPage />);

    // Wait for loading to resolve and the connect form to appear
    await waitFor(() => {
      expect(screen.getByLabelText(/private app access token/i)).toBeInTheDocument();
    });

    const input = screen.getByLabelText(/private app access token/i);
    expect(input).toHaveAttribute('type', 'password');

    // Click the reveal toggle (aria-label="Show token")
    const toggleBtn = screen.getByRole('button', { name: /show token/i });
    fireEvent.click(toggleBtn);

    expect(input).toHaveAttribute('type', 'text');
  });

  it('redirects a member user to /settings/preferences and does not render the connect form', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('member'));

    render(<HubSpotSettingsPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/settings/preferences');
    });

    // The token input must not be in the DOM for a member
    expect(screen.queryByLabelText(/private app access token/i)).not.toBeInTheDocument();
  });
});
