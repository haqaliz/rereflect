import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPatchZendeskStatusSync = vi.fn();
const mockTriggerZendeskStatusSync = vi.fn();

vi.mock('@/lib/api/zendesk', () => ({
  patchZendeskStatusSync: (...args: unknown[]) => mockPatchZendeskStatusSync(...args),
  triggerZendeskStatusSync: (...args: unknown[]) => mockTriggerZendeskStatusSync(...args),
}));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

import { ZendeskStatusSyncCard } from '@/components/settings/ZendeskStatusSyncCard';
import type { ZendeskConnectionStatus } from '@/lib/api/zendesk';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const baseStatus: ZendeskConnectionStatus = {
  connected: true,
  subdomain: 'acme',
  email: 'operator@acme.com',
  token_hint: '...9999',
  account_user_id: '12345',
  display_name: 'Jane Agent',
  is_active: true,
  last_synced_at: '2026-01-01T00:00:00Z',
  last_sync_status: null,
  last_error: null,
  connected_at: '2026-01-01T00:00:00Z',
  has_feedback_source: true,
  status_sync_enabled: false,
  status_mapping: null,
  last_status_synced_at: null,
  last_status_sync_error: null,
};

const disconnectedStatus: ZendeskConnectionStatus = {
  ...baseStatus,
  connected: false,
};

describe('ZendeskStatusSyncCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when Zendesk is disconnected', () => {
    const { container } = render(
      <ZendeskStatusSyncCard status={disconnectedStatus} onStatusChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the card when connected', () => {
    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('the toggle reflects status_sync_enabled = false', () => {
    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
  });

  it('the toggle reflects status_sync_enabled = true', () => {
    render(
      <ZendeskStatusSyncCard
        status={{ ...baseStatus, status_sync_enabled: true }}
        onStatusChange={vi.fn()}
      />
    );
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'checked');
  });

  it('toggling on optimistically flips the switch and calls patchZendeskStatusSync', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    let resolvePatch: (value: any) => void = () => {};
    mockPatchZendeskStatusSync.mockReturnValue(
      new Promise((resolve) => {
        resolvePatch = resolve;
      })
    );

    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    expect(mockPatchZendeskStatusSync).toHaveBeenCalledWith(true);
    // Optimistic update fires synchronously before the PATCH resolves.
    expect(onStatusChange).toHaveBeenCalledWith({ ...baseStatus, status_sync_enabled: true });

    resolvePatch({ ...baseStatus, status_sync_enabled: true, last_status_synced_at: null });
    await waitFor(() => {
      expect(onStatusChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ status_sync_enabled: true })
      );
    });
  });

  it('reverts the toggle and shows a toast on PATCH failure', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockPatchZendeskStatusSync.mockRejectedValue({
      response: { status: 400, data: { detail: 'Invalid status mapping.' } },
    });

    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(onStatusChange).toHaveBeenLastCalledWith(baseStatus);
    });
    expect(mockToastError).toHaveBeenCalledWith('Invalid status mapping.');
  });

  it('renders "Never" when last_status_synced_at is null', () => {
    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/Last synced Never/)).toBeInTheDocument();
  });

  it('renders a relative synced time when last_status_synced_at is set', () => {
    const recentStatus: ZendeskConnectionStatus = {
      ...baseStatus,
      last_status_synced_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    };
    render(<ZendeskStatusSyncCard status={recentStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/Last synced 5m ago/)).toBeInTheDocument();
  });

  it('renders last_status_sync_error when present', () => {
    const errorStatus: ZendeskConnectionStatus = {
      ...baseStatus,
      last_status_synced_at: '2026-07-01T12:00:00Z',
      last_status_sync_error: 'Zendesk API returned 401 Unauthorized.',
    };
    render(<ZendeskStatusSyncCard status={errorStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText('Zendesk API returned 401 Unauthorized.')).toBeInTheDocument();
  });

  it('does not render an error line when last_status_sync_error is null', () => {
    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.queryByText(/Unauthorized/)).not.toBeInTheDocument();
  });

  it('"Sync now" calls triggerZendeskStatusSync and shows a success toast on 202', async () => {
    const user = userEvent.setup();
    mockTriggerZendeskStatusSync.mockResolvedValue({ status: 'queued' });

    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /sync now/i }));

    await waitFor(() => {
      expect(mockTriggerZendeskStatusSync).toHaveBeenCalled();
      expect(mockToastSuccess).toHaveBeenCalled();
    });
  });

  it('"Sync now" shows an error toast on a 502 broker failure', async () => {
    const user = userEvent.setup();
    mockTriggerZendeskStatusSync.mockRejectedValue({ response: { status: 502, data: {} } });

    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /sync now/i }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        expect.stringMatching(/background worker is unavailable/i)
      );
    });
  });

  // ─── Status mapping editor (mapping-editor aspect) ──────────────────────────

  it('renders the status mapping editor with the six raw Zendesk statuses', () => {
    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getByText('On-hold')).toBeInTheDocument();
    expect(screen.getByText('Solved')).toBeInTheDocument();
    expect(screen.getAllByRole('combobox')).toHaveLength(6);
  });

  it('pre-selects the row values from status.status_mapping', () => {
    render(
      <ZendeskStatusSyncCard
        status={{ ...baseStatus, status_mapping: { solved: 'resolved', closed: 'closed' } }}
        onStatusChange={vi.fn()}
      />
    );
    const triggers = screen.getAllByRole('combobox');
    // Row order: new, open, pending, hold, solved, closed
    expect(triggers[4]).toHaveTextContent('Resolved');
    expect(triggers[5]).toHaveTextContent('Closed');
  });

  it('saving the mapping editor calls patchZendeskStatusSync with (enabled, mapping)', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockPatchZendeskStatusSync.mockResolvedValue({
      ...baseStatus,
      status_mapping: { solved: 'resolved' },
    });

    render(<ZendeskStatusSyncCard status={baseStatus} onStatusChange={onStatusChange} />);

    const triggers = screen.getAllByRole('combobox');
    await user.click(triggers[4]); // "solved" row
    await waitFor(() => screen.getByText('Resolved'));
    await user.click(screen.getByText('Resolved'));

    await user.click(screen.getByRole('button', { name: /save mapping/i }));

    await waitFor(() => {
      expect(mockPatchZendeskStatusSync).toHaveBeenCalledWith(false, { solved: 'resolved' });
      expect(onStatusChange).toHaveBeenCalledWith(
        expect.objectContaining({ status_mapping: { solved: 'resolved' } })
      );
    });
  });
});
