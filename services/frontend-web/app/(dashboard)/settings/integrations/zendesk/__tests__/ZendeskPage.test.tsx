/**
 * Tests for the Zendesk connect page (frontend Phase 2).
 *
 * Mirrors HubSpotPage.test.tsx's pattern (closer structural match than
 * Jira's untested page): full RTL render of an own-auth token-paste
 * connect page.
 *
 * API contract tests verify:
 * 1. zendeskAPI.connect is callable with { subdomain, email, api_token }
 * 2. zendeskAPI.disconnect is callable
 * 3. zendeskAPI.testConnection is callable
 * 4. zendeskAPI.getStatus is called on load
 *
 * Component rendering tests verify:
 * 5. Member users are redirected to /settings/preferences; connect form not rendered
 * 6. Disconnected + admin: subdomain/email/token fields render; token input
 *    defaults to type="password"; the Eye toggle reveals it
 * 7. Submitting the connect form calls zendeskAPI.connect with trimmed
 *    values; on success the token input clears and a one-time webhook
 *    URL + secret block renders
 * 8. Connected state renders Test Connection -> zendeskAPI.testConnection()
 *    and Disconnect (behind the confirm dialog) -> zendeskAPI.disconnect()
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

// ─── module-level mock fns (captured by vi.mock factories below) ─────────────

const mockReplace = vi.fn();
const mockPush = vi.fn();

// ─── mocks ──────────────────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  usePathname: () => '/settings/integrations/zendesk',
}));

// useAuth is a vi.fn() so each test can set its return value via mockReturnValue
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockPatchZendeskStatusSync = vi.fn();
const mockTriggerZendeskStatusSync = vi.fn();

vi.mock('@/lib/api/zendesk', () => ({
  zendeskAPI: {
    getStatus: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    testConnection: vi.fn(),
    triggerSync: vi.fn(),
  },
  patchZendeskStatusSync: (...args: unknown[]) => mockPatchZendeskStatusSync(...args),
  triggerZendeskStatusSync: (...args: unknown[]) => mockTriggerZendeskStatusSync(...args),
}));

// ─── imports (after mocks) ───────────────────────────────────────────────────

import { zendeskAPI } from '@/lib/api/zendesk';
import { useAuth } from '@/contexts/AuthContext';
import ZendeskSettingsPage from '../page';

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
  subdomain: null,
  email: null,
  token_hint: null,
  account_user_id: null,
  display_name: null,
  is_active: null,
  last_synced_at: null,
  last_sync_status: null,
  last_error: null,
  connected_at: null,
  has_feedback_source: false,
  status_sync_enabled: false,
  status_mapping: null,
  last_status_synced_at: null,
  last_status_sync_error: null,
};

const connectedStatus = {
  connected: true,
  subdomain: 'acme',
  email: 'operator@acme.com',
  token_hint: '...9999',
  account_user_id: '12345',
  display_name: 'Jane Agent',
  is_active: true,
  last_synced_at: null,
  last_sync_status: null,
  last_error: null,
  connected_at: '2026-07-05T12:00:00',
  has_feedback_source: true,
  status_sync_enabled: false,
  status_mapping: null,
  last_status_synced_at: null,
  last_status_sync_error: null,
};

// ─── API contract tests (original suite) ────────────────────────────────────

describe('Zendesk detail page — API contract', () => {
  beforeEach(() => vi.clearAllMocks());

  it('zendeskAPI.connect accepts { subdomain, email, api_token }', async () => {
    (zendeskAPI.connect as any).mockResolvedValue({
      connected: true,
      subdomain: 'acme',
      email: 'operator@acme.com',
      token_hint: '...9999',
      webhook_secret: 'plain-secret',
      has_feedback_source: true,
    });
    const result = await zendeskAPI.connect({
      subdomain: 'acme',
      email: 'operator@acme.com',
      api_token: 'zd-token',
    });
    expect(zendeskAPI.connect).toHaveBeenCalledWith({
      subdomain: 'acme',
      email: 'operator@acme.com',
      api_token: 'zd-token',
    });
    expect(result.connected).toBe(true);
  });

  it('zendeskAPI.disconnect is callable', async () => {
    (zendeskAPI.disconnect as any).mockResolvedValue({ success: true, message: 'ok' });
    const result = await zendeskAPI.disconnect();
    expect(zendeskAPI.disconnect).toHaveBeenCalled();
    expect(result.success).toBe(true);
  });

  it('zendeskAPI.testConnection is callable', async () => {
    (zendeskAPI.testConnection as any).mockResolvedValue({
      success: true,
      message: 'Zendesk connection is healthy.',
    });
    const result = await zendeskAPI.testConnection();
    expect(zendeskAPI.testConnection).toHaveBeenCalled();
    expect(result.success).toBe(true);
  });

  it('zendeskAPI.getStatus returns token_hint + has_feedback_source, never webhook_secret', async () => {
    (zendeskAPI.getStatus as any).mockResolvedValue(connectedStatus);
    const status = await zendeskAPI.getStatus();
    expect(status.token_hint).toBe('...9999');
    expect(status.has_feedback_source).toBe(true);
    expect((status as any).webhook_secret).toBeUndefined();
  });
});

// ─── Component rendering tests ───────────────────────────────────────────────

describe('ZendeskSettingsPage — component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: disconnected status so the connect form renders for admin users
    (zendeskAPI.getStatus as any).mockResolvedValue(disconnectedStatus);
  });

  it('renders subdomain/email/token fields; token input masked by default and revealed after the show toggle is clicked', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('admin'));

    render(<ZendeskSettingsPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/api token/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/subdomain/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();

    const input = screen.getByLabelText(/api token/i);
    expect(input).toHaveAttribute('type', 'password');

    const toggleBtn = screen.getByRole('button', { name: /show token/i });
    fireEvent.click(toggleBtn);

    expect(input).toHaveAttribute('type', 'text');
  });

  it('redirects a member user to /settings/preferences and does not render the connect form', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('member'));

    render(<ZendeskSettingsPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/settings/preferences');
    });

    expect(screen.queryByLabelText(/api token/i)).not.toBeInTheDocument();
  });

  it('submits the connect form with trimmed values, clears the token input, and shows the one-time webhook block', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('admin'));
    (zendeskAPI.connect as any).mockResolvedValue({
      connected: true,
      subdomain: 'acme',
      email: 'operator@acme.com',
      token_hint: '...9999',
      account_user_id: '12345',
      display_name: 'Jane Agent',
      webhook_secret: 'plain-secret-value',
      has_feedback_source: true,
    });

    render(<ZendeskSettingsPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/api token/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/subdomain/i), { target: { value: '  acme  ' } });
    fireEvent.change(screen.getByLabelText(/^email$/i), { target: { value: '  operator@acme.com  ' } });
    fireEvent.change(screen.getByLabelText(/api token/i), { target: { value: '  zd-token  ' } });

    fireEvent.click(screen.getByRole('button', { name: /connect zendesk/i }));

    await waitFor(() => {
      expect(zendeskAPI.connect).toHaveBeenCalledWith({
        subdomain: 'acme',
        email: 'operator@acme.com',
        api_token: 'zd-token',
      });
    });

    // Connect form (with the masked token input) is replaced by the
    // connected-state view — the token was cleared and is no longer shown.
    await waitFor(() => {
      expect(screen.queryByLabelText(/api token/i)).not.toBeInTheDocument();
    });

    // One-time webhook secret reveal block renders (readonly input value)
    expect(screen.getByDisplayValue('plain-secret-value')).toBeInTheDocument();
  });

  it('connected state renders Test Connection and Disconnect (behind confirm dialog)', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('admin'));
    (zendeskAPI.getStatus as any).mockResolvedValue(connectedStatus);
    (zendeskAPI.testConnection as any).mockResolvedValue({
      success: true,
      message: 'Zendesk connection is healthy.',
    });
    (zendeskAPI.disconnect as any).mockResolvedValue({ success: true, message: 'ok' });

    render(<ZendeskSettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /test connection/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /test connection/i }));
    await waitFor(() => {
      expect(zendeskAPI.testConnection).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole('button', { name: /^disconnect$/i }));
    // Confirm dialog gate — disconnect not called until confirmed
    expect(zendeskAPI.disconnect).not.toHaveBeenCalled();

    const dialogDisconnectBtn = await screen.findAllByRole('button', { name: /disconnect/i });
    fireEvent.click(dialogDisconnectBtn[dialogDisconnectBtn.length - 1]);

    await waitFor(() => {
      expect(zendeskAPI.disconnect).toHaveBeenCalled();
    });
  });

  it('connected + admin: renders the ingestion "Sync tickets" button and the status-sync card\'s distinct "Sync Now" button', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('admin'));
    (zendeskAPI.getStatus as any).mockResolvedValue(connectedStatus);

    render(<ZendeskSettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /sync tickets/i })).toBeInTheDocument();
    });

    // Status-sync card (Phase 3 mount) — distinct label from ingestion sync.
    expect(screen.getByText('Inbound Status Sync')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^sync now$/i })).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('clicking "Sync tickets" calls zendeskAPI.triggerSync (ingestion), not the status-sync trigger', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('admin'));
    (zendeskAPI.getStatus as any).mockResolvedValue(connectedStatus);
    (zendeskAPI.triggerSync as any).mockResolvedValue({ status: 'queued', integration_id: 1 });

    render(<ZendeskSettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /sync tickets/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /sync tickets/i }));

    await waitFor(() => {
      expect(zendeskAPI.triggerSync).toHaveBeenCalled();
    });
    expect(mockTriggerZendeskStatusSync).not.toHaveBeenCalled();
  });

  it('does not render the status-sync card when disconnected', async () => {
    (useAuth as any).mockReturnValue(makeAuthContext('admin'));
    (zendeskAPI.getStatus as any).mockResolvedValue(disconnectedStatus);

    render(<ZendeskSettingsPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/api token/i)).toBeInTheDocument();
    });

    expect(screen.queryByText('Inbound Status Sync')).not.toBeInTheDocument();
  });
});
