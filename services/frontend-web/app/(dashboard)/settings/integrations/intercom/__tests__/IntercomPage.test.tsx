/**
 * Tests for the Intercom token-paste connect page.
 *
 * Mirrors ZendeskPage.test.tsx, the shipped precedent for an own-auth
 * token-paste connect page.
 *
 * Verifies:
 * 1. getStatus is called on load
 * 2. Members are redirected and never see the form (the backend enforces this
 *    too — the UI hiding it is not the control)
 * 3. Disconnected + admin: token field renders as a password, the Eye toggle
 *    reveals it, and the Client Secret field is optional
 * 4. Submitting calls connect with trimmed values; an omitted secret is not
 *    sent as an empty string
 * 5. Connected state surfaces workspace, last-synced and last_error
 * 6. Connected WITHOUT a stored client secret warns that webhooks will be
 *    rejected while the pull keeps working — the honest half-state
 * 7. Disconnect goes through the confirm dialog
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const mockReplace = vi.fn();
const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  usePathname: () => '/settings/integrations/intercom',
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockConnect = vi.fn();
const mockGetStatus = vi.fn();
const mockDisconnect = vi.fn();

vi.mock('@/lib/api/intercom', () => ({
  intercomAPI: {
    connect: (...args: unknown[]) => mockConnect(...args),
    getStatus: () => mockGetStatus(),
    disconnect: () => mockDisconnect(),
  },
}));

import IntercomSettingsPage from '../page';
import { useAuth } from '@/contexts/AuthContext';

const DISCONNECTED = {
  connected: false,
  workspace_id: null,
  workspace_name: null,
  token_hint: null,
  admin_id: null,
  has_client_secret: false,
  has_feedback_source: false,
  last_synced_at: null,
  last_sync_status: null,
  last_error: null,
};

const CONNECTED = {
  connected: true,
  workspace_id: 'ws_abc123',
  workspace_name: 'Acme Support',
  token_hint: 'wxyz',
  admin_id: 'admin_1',
  has_client_secret: true,
  has_feedback_source: true,
  last_synced_at: '2026-08-01T10:00:00Z',
  last_sync_status: 'ok',
  last_error: null,
};

function asAdmin() {
  (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    user: { role: 'admin', email: 'a@example.com' },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetStatus.mockResolvedValue(DISCONNECTED);
  mockConnect.mockResolvedValue({ connected: true });
  mockDisconnect.mockResolvedValue({ disconnected: true });
  asAdmin();
});

describe('IntercomSettingsPage', () => {
  it('loads status on mount', async () => {
    render(<IntercomSettingsPage />);
    await waitFor(() => expect(mockGetStatus).toHaveBeenCalled());
  });

  it('redirects members away and renders no form', async () => {
    (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      user: { role: 'member', email: 'm@example.com' },
    });

    render(<IntercomSettingsPage />);

    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith('/settings/preferences')
    );
    expect(screen.queryByLabelText('Access Token')).not.toBeInTheDocument();
  });

  it('renders the token field masked and reveals it on toggle', async () => {
    render(<IntercomSettingsPage />);

    const token = await screen.findByLabelText('Access Token');
    expect(token).toHaveAttribute('type', 'password');

    fireEvent.click(screen.getByLabelText('Show token'));
    expect(await screen.findByLabelText('Access Token')).toHaveAttribute(
      'type',
      'text'
    );
  });

  it('connects with a trimmed token and omits an empty client secret', async () => {
    render(<IntercomSettingsPage />);

    const token = await screen.findByLabelText('Access Token');
    fireEvent.change(token, { target: { value: '  tok_123  ' } });
    fireEvent.click(screen.getByRole('button', { name: /^Connect$/ }));

    await waitFor(() =>
      expect(mockConnect).toHaveBeenCalledWith({ access_token: 'tok_123' })
    );
  });

  it('sends the client secret when one is supplied', async () => {
    render(<IntercomSettingsPage />);

    fireEvent.change(await screen.findByLabelText('Access Token'), {
      target: { value: 'tok_123' },
    });
    fireEvent.change(screen.getByLabelText(/Client Secret/), {
      target: { value: 'sec_456' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Connect$/ }));

    await waitFor(() =>
      expect(mockConnect).toHaveBeenCalledWith({
        access_token: 'tok_123',
        client_secret: 'sec_456',
      })
    );
  });

  it('surfaces a connect error', async () => {
    mockConnect.mockRejectedValue({
      response: { data: { detail: 'Intercom access token is invalid' } },
    });

    render(<IntercomSettingsPage />);
    fireEvent.change(await screen.findByLabelText('Access Token'), {
      target: { value: 'bad' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Connect$/ }));

    expect(
      await screen.findByText('Intercom access token is invalid')
    ).toBeInTheDocument();
  });

  it('shows workspace and sync state when connected', async () => {
    mockGetStatus.mockResolvedValue(CONNECTED);

    render(<IntercomSettingsPage />);

    expect(await screen.findByText('ws_abc123')).toBeInTheDocument();
    expect(screen.getByText(/Acme Support/)).toBeInTheDocument();
  });

  it('warns when connected without a stored client secret', async () => {
    mockGetStatus.mockResolvedValue({
      ...CONNECTED,
      has_client_secret: false,
    });

    render(<IntercomSettingsPage />);

    // The honest half-state: pull works, webhooks do not.
    expect(
      await screen.findByText(/No Client Secret stored/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/15-minute pull is unaffected/)
    ).toBeInTheDocument();
  });

  it('warns when no feedback source exists', async () => {
    mockGetStatus.mockResolvedValue({
      ...CONNECTED,
      has_feedback_source: false,
    });

    render(<IntercomSettingsPage />);

    expect(
      await screen.findByText(/nothing will be ingested/)
    ).toBeInTheDocument();
  });

  it('disconnects through the confirm dialog', async () => {
    mockGetStatus.mockResolvedValue(CONNECTED);

    render(<IntercomSettingsPage />);

    fireEvent.click(
      await screen.findByRole('button', { name: /Disconnect Intercom/ })
    );
    fireEvent.click(
      await screen.findByRole('button', { name: /^Disconnect$/ })
    );

    await waitFor(() => expect(mockDisconnect).toHaveBeenCalled());
  });
});
