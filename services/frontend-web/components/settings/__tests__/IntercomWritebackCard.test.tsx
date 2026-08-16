import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockUpdateWriteback = vi.fn();
const mockTestWriteback = vi.fn();
const mockGetStatus = vi.fn();

vi.mock('@/lib/api/intercom', () => ({
  intercomAPI: {
    updateWriteback: (...args: unknown[]) => mockUpdateWriteback(...args),
    testWriteback: (...args: unknown[]) => mockTestWriteback(...args),
    getStatus: (...args: unknown[]) => mockGetStatus(...args),
  },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { IntercomWritebackCard } from '@/components/settings/IntercomWritebackCard';
import type { IntercomConnectionStatus } from '@/lib/api/intercom';
import { toast } from 'sonner';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const baseStatus: IntercomConnectionStatus = {
  connected: true,
  workspace_id: 'ws_abc123',
  workspace_name: 'Acme Support',
  token_hint: 'wxyz',
  admin_id: 'admin_1',
  has_client_secret: true,
  has_feedback_source: true,
  last_synced_at: null,
  last_sync_status: null,
  last_error: null,
  feedback_items_ingested: 42,
  backlog_remaining: null,
  writeback_enabled: false,
  writeback_action: null,
  last_writeback_at: null,
  last_writeback_status: null,
  last_writeback_error: null,
};

const disconnectedStatus: IntercomConnectionStatus = {
  ...baseStatus,
  connected: false,
};

const writebackResponse = (overrides: Partial<IntercomConnectionStatus> = {}) => ({
  writeback_enabled: true,
  writeback_action: 'note_and_close',
  last_writeback_at: null,
  last_writeback_status: null,
  last_writeback_error: null,
  ...overrides,
});

describe('IntercomWritebackCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── AC1 — render gating + five writeback fields ───────────────────────────

  it('renders nothing when Intercom is disconnected', () => {
    const { container } = render(
      <IntercomWritebackCard status={disconnectedStatus} onStatusChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the card when connected', () => {
    render(<IntercomWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText('Resolve Write-Back')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('renders the five writeback fields', () => {
    const statusWithHistory: IntercomConnectionStatus = {
      ...baseStatus,
      writeback_enabled: true,
      writeback_action: 'note_and_close',
      last_writeback_at: '2026-07-01T12:00:00Z',
      last_writeback_status: 'error: missing_write_scope',
      last_writeback_error: 'missing_write_scope',
    };
    render(
      <IntercomWritebackCard status={statusWithHistory} onStatusChange={vi.fn()} />
    );

    expect(screen.getByText('Last Write-back')).toBeInTheDocument();
    expect(
      screen.getByText('Intercom token is missing the conversation:write scope')
    ).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Intercom token is missing the conversation:write scope.'
    );
  });

  // ── AC2 — toggle round-trip, never-optimistic ──────────────────────────────

  it('toggling calls updateWriteback({enabled: true}) then refetches status and calls onStatusChange', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateWriteback.mockResolvedValue(writebackResponse());
    const refetchedStatus: IntercomConnectionStatus = {
      ...baseStatus,
      writeback_enabled: true,
      writeback_action: 'note_and_close',
    };
    mockGetStatus.mockResolvedValue(refetchedStatus);

    render(<IntercomWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(mockUpdateWriteback).toHaveBeenCalledWith({ enabled: true });
    });
    await waitFor(() => {
      expect(mockGetStatus).toHaveBeenCalled();
      expect(onStatusChange).toHaveBeenCalledWith(refetchedStatus);
    });
  });

  it('does not latch the switch before the PATCH resolves', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    let resolveUpdate: (value: unknown) => void = () => {};
    mockUpdateWriteback.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve;
      })
    );

    render(<IntercomWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    // Still off — status prop hasn't changed and we don't optimistically flip it.
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');

    resolveUpdate(writebackResponse());
    mockGetStatus.mockResolvedValue({ ...baseStatus, writeback_enabled: true });
    await waitFor(() => expect(onStatusChange).toHaveBeenCalled());
  });

  it('a failed PATCH surfaces the error and leaves the switch at the server state', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateWriteback.mockRejectedValue({
      response: {
        status: 404,
        data: { detail: 'No active Intercom integration found.' },
      },
    });

    render(<IntercomWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(screen.getByText('No active Intercom integration found.')).toBeInTheDocument();
    });
    expect(onStatusChange).not.toHaveBeenCalled();
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
  });

  it('a failed PATCH with detail.reason surfaces the friendly reason copy', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateWriteback.mockRejectedValue({
      response: {
        status: 400,
        data: { detail: { reason: 'missing_write_scope' } },
      },
    });

    render(<IntercomWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(
        screen.getByText('Intercom token is missing the conversation:write scope.')
      ).toBeInTheDocument();
    });
    expect(onStatusChange).not.toHaveBeenCalled();
  });

  it('toggling off sends {enabled: false}', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    const enabledStatus = { ...baseStatus, writeback_enabled: true };
    mockUpdateWriteback.mockResolvedValue(writebackResponse({ writeback_enabled: false }));
    mockGetStatus.mockResolvedValue({ ...enabledStatus, writeback_enabled: false });

    render(<IntercomWritebackCard status={enabledStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(mockUpdateWriteback).toHaveBeenCalledWith({ enabled: false });
    });
  });

  // ── AC3 — action selector round-trip ───────────────────────────────────────

  it('changing the action Select PATCHes {enabled, action} and refetches', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateWriteback.mockResolvedValue(writebackResponse({ writeback_action: 'note_only' }));
    const refetchedStatus: IntercomConnectionStatus = {
      ...baseStatus,
      writeback_enabled: false,
      writeback_action: 'note_only',
    };
    mockGetStatus.mockResolvedValue(refetchedStatus);

    render(<IntercomWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('combobox'));
    await waitFor(() =>
      screen.getByText('Add a note only — leave closing to your team')
    );
    await user.click(screen.getByText('Add a note only — leave closing to your team'));

    await waitFor(() => {
      expect(mockUpdateWriteback).toHaveBeenCalledWith({
        enabled: false,
        action: 'note_only',
      });
    });
    await waitFor(() => {
      expect(onStatusChange).toHaveBeenCalledWith(refetchedStatus);
    });
  });

  it('the Select reflects the server value', () => {
    render(
      <IntercomWritebackCard
        status={{ ...baseStatus, writeback_action: 'note_only' }}
        onStatusChange={vi.fn()}
      />
    );
    expect(screen.getByRole('combobox')).toHaveTextContent(
      'Add a note only — leave closing to your team'
    );
  });

  // ── AC4 — Test write-back button ───────────────────────────────────────────

  it('Test write-back calls testWriteback and shows a success toast', async () => {
    const user = userEvent.setup();
    mockTestWriteback.mockResolvedValue({ ok: true, reason: null });

    render(<IntercomWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /test write-back/i }));

    await waitFor(() => expect(mockTestWriteback).toHaveBeenCalledWith());
    expect(toast.success).toHaveBeenCalledWith(
      'Write-back test passed — scope is valid.'
    );
  });

  it('Test write-back is disabled while the probe is in flight', async () => {
    const user = userEvent.setup();
    let resolveTest: (value: unknown) => void = () => {};
    mockTestWriteback.mockReturnValue(
      new Promise((resolve) => {
        resolveTest = resolve;
      })
    );

    render(<IntercomWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /test write-back/i }));

    expect(screen.getByRole('button', { name: /test write-back/i })).toBeDisabled();

    resolveTest({ ok: true, reason: null });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('Test write-back with {ok: false} shows the reason copy without erroring', async () => {
    const user = userEvent.setup();
    mockTestWriteback.mockResolvedValue({ ok: false, reason: 'missing_write_scope' });

    render(<IntercomWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /test write-back/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        'Intercom token is missing the conversation:write scope.'
      );
    });
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('Test write-back network failure shows a fallback error toast', async () => {
    const user = userEvent.setup();
    mockTestWriteback.mockRejectedValue(new Error('network down'));

    render(<IntercomWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /test write-back/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Could not run write-back test.');
    });
  });

  // ── STATUS_COPY keys render copy, never the raw string ─────────────────────

  const STATUS_KEY_EXPECTATIONS: Array<[string | null, string]> = [
    ['ok', 'Last write succeeded'],
    ['retrying', 'Retrying after a transient error'],
    ['error: missing_write_scope', 'Intercom token is missing the conversation:write scope'],
    ['noop: already_closed', 'Conversation was already closed — nothing to do'],
    ['error: no_admin', 'Could not resolve an Intercom admin'],
  ];

  it.each(STATUS_KEY_EXPECTATIONS)(
    'renders friendly copy for last_writeback_status %s',
    (statusKey, expectedCopy) => {
      render(
        <IntercomWritebackCard
          status={{ ...baseStatus, last_writeback_status: statusKey }}
          onStatusChange={vi.fn()}
        />
      );
      expect(screen.getByText(expectedCopy)).toBeInTheDocument();
    }
  );

  it('hides the status grid when last_writeback_at and last_writeback_status are null', () => {
    render(<IntercomWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.queryByText('Last Write-back')).not.toBeInTheDocument();
    expect(screen.queryByText('Last Status')).not.toBeInTheDocument();
  });
});
