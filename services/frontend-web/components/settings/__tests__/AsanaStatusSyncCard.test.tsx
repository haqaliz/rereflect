import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPatchAsanaStatusSync = vi.fn();
const mockTriggerAsanaSync = vi.fn();

vi.mock('@/lib/api/asana', () => ({
  patchAsanaStatusSync: (...args: unknown[]) => mockPatchAsanaStatusSync(...args),
  triggerAsanaSync: (...args: unknown[]) => mockTriggerAsanaSync(...args),
}));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

import { AsanaStatusSyncCard } from '@/components/settings/AsanaStatusSyncCard';
import type { AsanaConnectionStatus } from '@/lib/api/asana';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const baseStatus: AsanaConnectionStatus = {
  connected: true,
  token_hint: '...abcd',
  account_gid: 'acc-1',
  display_name: 'Admin User',
  is_active: true,
  last_synced_at: '2026-01-01T00:00:00Z',
  last_sync_status: null,
  last_error: null,
  connected_at: '2026-01-01T00:00:00Z',
  status_sync_enabled: false,
  last_status_synced_at: null,
};

const disconnectedStatus: AsanaConnectionStatus = {
  ...baseStatus,
  connected: false,
};

describe('AsanaStatusSyncCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when Asana is disconnected', () => {
    const { container } = render(
      <AsanaStatusSyncCard status={disconnectedStatus} onStatusChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the card when connected', () => {
    render(<AsanaStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText('Inbound Status Sync')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('the toggle reflects status_sync_enabled = false', () => {
    render(<AsanaStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
  });

  it('the toggle reflects status_sync_enabled = true', () => {
    render(
      <AsanaStatusSyncCard status={{ ...baseStatus, status_sync_enabled: true }} onStatusChange={vi.fn()} />
    );
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'checked');
  });

  it('toggling on optimistically flips the switch and calls patchAsanaStatusSync', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    let resolvePatch: (value: any) => void = () => {};
    mockPatchAsanaStatusSync.mockReturnValue(
      new Promise((resolve) => {
        resolvePatch = resolve;
      })
    );

    render(<AsanaStatusSyncCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    expect(mockPatchAsanaStatusSync).toHaveBeenCalledWith(true);
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
    mockPatchAsanaStatusSync.mockRejectedValue({
      response: { status: 400, data: { detail: 'Invalid status mapping.' } },
    });

    render(<AsanaStatusSyncCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(onStatusChange).toHaveBeenLastCalledWith(baseStatus);
    });
    expect(mockToastError).toHaveBeenCalledWith('Invalid status mapping.');
  });

  it('renders "Never" when last_status_synced_at is null', () => {
    render(<AsanaStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/Last synced Never/)).toBeInTheDocument();
  });

  it('renders a relative synced time and status when last_status_synced_at is set', () => {
    const recentStatus: AsanaConnectionStatus = {
      ...baseStatus,
      last_status_synced_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      last_sync_status: 'success',
    };
    render(<AsanaStatusSyncCard status={recentStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/Last synced 5m ago/)).toBeInTheDocument();
    expect(screen.getByText(/success/)).toBeInTheDocument();
  });

  it('renders last_error in an error state when last_sync_status is "error"', () => {
    const errorStatus: AsanaConnectionStatus = {
      ...baseStatus,
      last_status_synced_at: '2026-07-01T12:00:00Z',
      last_sync_status: 'error',
      last_error: 'Asana API returned 401 Unauthorized.',
    };
    render(<AsanaStatusSyncCard status={errorStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText('Asana API returned 401 Unauthorized.')).toBeInTheDocument();
  });

  it('does not render last_error when last_sync_status is not "error"', () => {
    const okStatus: AsanaConnectionStatus = {
      ...baseStatus,
      last_sync_status: 'success',
      last_error: 'stale leftover error text',
    };
    render(<AsanaStatusSyncCard status={okStatus} onStatusChange={vi.fn()} />);
    expect(screen.queryByText('stale leftover error text')).not.toBeInTheDocument();
  });

  it('"Sync now" calls triggerAsanaSync and shows a success toast on 202', async () => {
    const user = userEvent.setup();
    mockTriggerAsanaSync.mockResolvedValue({ status: 'queued' });

    render(<AsanaStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /sync now/i }));

    await waitFor(() => {
      expect(mockTriggerAsanaSync).toHaveBeenCalled();
      expect(mockToastSuccess).toHaveBeenCalled();
    });
  });

  it('"Sync now" shows an error toast on a 502 broker failure', async () => {
    const user = userEvent.setup();
    mockTriggerAsanaSync.mockRejectedValue({ response: { status: 502, data: {} } });

    render(<AsanaStatusSyncCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /sync now/i }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        expect.stringMatching(/background worker is unavailable/i)
      );
    });
  });
});
