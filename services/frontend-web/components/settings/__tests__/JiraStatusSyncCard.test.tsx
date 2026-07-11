import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPatchJiraStatusSync = vi.fn();
const mockTriggerJiraSync = vi.fn();

vi.mock('@/lib/api/jira', () => ({
  patchJiraStatusSync: (...args: unknown[]) => mockPatchJiraStatusSync(...args),
  triggerJiraSync: (...args: unknown[]) => mockTriggerJiraSync(...args),
}));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

import { JiraStatusSyncCard } from '@/components/settings/JiraStatusSyncCard';
import type { JiraConnectionStatus } from '@/lib/api/jira';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const baseStatus: JiraConnectionStatus = {
  connected: true,
  site_url: 'acme.atlassian.net',
  email: 'admin@acme.com',
  token_hint: '...abcd',
  account_id: 'acc-1',
  display_name: 'Admin User',
  is_active: true,
  last_synced_at: '2026-01-01T00:00:00Z',
  last_sync_status: null,
  last_error: null,
  connected_at: '2026-01-01T00:00:00Z',
  status_sync_enabled: false,
  last_status_synced_at: null,
};

const disconnectedStatus: JiraConnectionStatus = {
  ...baseStatus,
  connected: false,
};

describe('JiraStatusSyncCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when Jira is disconnected', () => {
    const { container } = render(
      <JiraStatusSyncCard status={disconnectedStatus} onStatusChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the card when connected', () => {
    render(<JiraStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText('Inbound Status Sync')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('the toggle reflects status_sync_enabled = false', () => {
    render(<JiraStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
  });

  it('the toggle reflects status_sync_enabled = true', () => {
    render(
      <JiraStatusSyncCard status={{ ...baseStatus, status_sync_enabled: true }} onStatusChange={vi.fn()} />
    );
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'checked');
  });

  it('toggling on optimistically flips the switch and calls patchJiraStatusSync', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    let resolvePatch: (value: any) => void = () => {};
    mockPatchJiraStatusSync.mockReturnValue(
      new Promise((resolve) => {
        resolvePatch = resolve;
      })
    );

    render(<JiraStatusSyncCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    expect(mockPatchJiraStatusSync).toHaveBeenCalledWith(true);
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
    mockPatchJiraStatusSync.mockRejectedValue({
      response: { status: 400, data: { detail: 'Invalid status mapping.' } },
    });

    render(<JiraStatusSyncCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(onStatusChange).toHaveBeenLastCalledWith(baseStatus);
    });
    expect(mockToastError).toHaveBeenCalledWith('Invalid status mapping.');
  });

  it('renders "Never" when last_status_synced_at is null', () => {
    render(<JiraStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/Last synced Never/)).toBeInTheDocument();
  });

  it('renders a relative synced time and status when last_status_synced_at is set', () => {
    const recentStatus: JiraConnectionStatus = {
      ...baseStatus,
      last_status_synced_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      last_sync_status: 'success',
    };
    render(<JiraStatusSyncCard status={recentStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/Last synced 5m ago/)).toBeInTheDocument();
    expect(screen.getByText(/success/)).toBeInTheDocument();
  });

  it('renders last_error in an error state when last_sync_status is "error"', () => {
    const errorStatus: JiraConnectionStatus = {
      ...baseStatus,
      last_status_synced_at: '2026-07-01T12:00:00Z',
      last_sync_status: 'error',
      last_error: 'Jira API returned 401 Unauthorized.',
    };
    render(<JiraStatusSyncCard status={errorStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText('Jira API returned 401 Unauthorized.')).toBeInTheDocument();
  });

  it('does not render last_error when last_sync_status is not "error"', () => {
    const okStatus: JiraConnectionStatus = {
      ...baseStatus,
      last_sync_status: 'success',
      last_error: 'stale leftover error text',
    };
    render(<JiraStatusSyncCard status={okStatus} onStatusChange={vi.fn()} />);
    expect(screen.queryByText('stale leftover error text')).not.toBeInTheDocument();
  });

  it('"Sync now" calls triggerJiraSync and shows a success toast on 202', async () => {
    const user = userEvent.setup();
    mockTriggerJiraSync.mockResolvedValue({ status: 'queued' });

    render(<JiraStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /sync now/i }));

    await waitFor(() => {
      expect(mockTriggerJiraSync).toHaveBeenCalled();
      expect(mockToastSuccess).toHaveBeenCalled();
    });
  });

  it('"Sync now" shows an error toast on a 502 broker failure', async () => {
    const user = userEvent.setup();
    mockTriggerJiraSync.mockRejectedValue({ response: { status: 502, data: {} } });

    render(<JiraStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /sync now/i }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        expect.stringMatching(/background worker is unavailable/i)
      );
    });
  });
});
