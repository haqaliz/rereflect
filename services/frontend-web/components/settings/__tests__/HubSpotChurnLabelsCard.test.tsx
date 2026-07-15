import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockUpdateChurnLabels = vi.fn();
const mockGetChurnLabelOptions = vi.fn();
const mockGetStatus = vi.fn();
const mockTriggerChurnBackfill = vi.fn();
const mockCancelChurnBackfill = vi.fn();

vi.mock('@/lib/api/hubspot', () => ({
  hubspotAPI: {
    updateChurnLabels: (...args: unknown[]) => mockUpdateChurnLabels(...args),
    getChurnLabelOptions: (...args: unknown[]) => mockGetChurnLabelOptions(...args),
    getStatus: (...args: unknown[]) => mockGetStatus(...args),
    triggerChurnBackfill: (...args: unknown[]) => mockTriggerChurnBackfill(...args),
    cancelChurnBackfill: (...args: unknown[]) => mockCancelChurnBackfill(...args),
  },
}));

import { HubSpotChurnLabelsCard } from '@/components/settings/HubSpotChurnLabelsCard';
import type { HubSpotConnectionStatus } from '@/lib/api/hubspot';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const baseStatus: HubSpotConnectionStatus = {
  connected: true,
  portal_name: 'Acme',
  hub_id: '123',
  token_hint: '...abcd',
  last_synced_at: null,
  last_sync_status: null,
  last_error: null,
  contacts_synced: 10,
  contacts_matched: 8,
  arr_property_name: 'annualrevenue',
  connected_at: '2026-01-01T00:00:00Z',
  writeback_enabled: false,
  writeback_field_name: null,
  last_writeback_at: null,
  last_writeback_status: null,
  last_writeback_error: null,
  contacts_written: 0,
  churn_labels_enabled: false,
  churn_label_config: { renewal_pipeline_ids: ['default'] },
  last_harvest_at: null,
  last_harvest_status: null,
  last_harvest_error: null,
  suggestions_created: 0,
};

const disconnectedStatus: HubSpotConnectionStatus = {
  ...baseStatus,
  connected: false,
};

const FAKE_OPTIONS = [
  { id: 'default', label: 'Sales Pipeline' },
  { id: '12345678', label: 'Renewals' },
];

describe('HubSpotChurnLabelsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetChurnLabelOptions.mockResolvedValue({ options: FAKE_OPTIONS, provider: 'hubspot' });
  });

  it('renders nothing when HubSpot is disconnected', () => {
    const { container } = render(
      <HubSpotChurnLabelsCard status={disconnectedStatus} onStatusChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the card when connected', () => {
    render(<HubSpotChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/CRM Churn-Label Suggestions/i)).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('toggling on calls updateChurnLabels with the current selection, then refetches status', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateChurnLabels.mockResolvedValue({
      churn_labels_enabled: true,
      churn_label_config: { renewal_pipeline_ids: ['default'] },
      last_harvest_at: null,
      last_harvest_status: null,
      last_harvest_error: null,
      suggestions_created: 0,
    });
    const refreshedStatus: HubSpotConnectionStatus = {
      ...baseStatus,
      churn_labels_enabled: true,
    };
    mockGetStatus.mockResolvedValue(refreshedStatus);

    render(<HubSpotChurnLabelsCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(mockUpdateChurnLabels).toHaveBeenCalledWith({
        enabled: true,
        config: { renewal_pipeline_ids: ['default'] },
      });
    });
    await waitFor(() => {
      expect(mockGetStatus).toHaveBeenCalled();
      expect(onStatusChange).toHaveBeenCalledWith(refreshedStatus);
    });

    const updateOrder = mockUpdateChurnLabels.mock.invocationCallOrder[0];
    const statusOrder = mockGetStatus.mock.invocationCallOrder[0];
    expect(updateOrder).toBeLessThan(statusOrder);
  });

  it('does not latch the switch on optimistically before the PATCH resolves', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    let resolveUpdate: (value: any) => void = () => {};
    mockUpdateChurnLabels.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve;
      })
    );

    render(<HubSpotChurnLabelsCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');

    resolveUpdate({
      churn_labels_enabled: true,
      churn_label_config: { renewal_pipeline_ids: ['default'] },
      last_harvest_at: null,
      last_harvest_status: null,
      last_harvest_error: null,
      suggestions_created: 0,
    });
    mockGetStatus.mockResolvedValue({ ...baseStatus, churn_labels_enabled: true });
    await waitFor(() => expect(onStatusChange).toHaveBeenCalled());
  });

  it('a rejected PATCH surfaces REASON_COPY text and leaves the switch unchecked', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateChurnLabels.mockRejectedValue({
      response: {
        status: 422,
        data: { detail: { reason: 'unknown_pipeline' } },
      },
    });

    render(<HubSpotChurnLabelsCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(screen.getByText(/unknown.*pipeline/i)).toBeInTheDocument();
    });
    expect(onStatusChange).not.toHaveBeenCalled();
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
  });

  it('renders the default-deny empty-state warning when enabled with an empty renewal list', () => {
    const emptyEnabledStatus: HubSpotConnectionStatus = {
      ...baseStatus,
      churn_labels_enabled: true,
      churn_label_config: { renewal_pipeline_ids: [] },
    };
    render(<HubSpotChurnLabelsCard status={emptyEnabledStatus} onStatusChange={vi.fn()} />);

    expect(screen.getByText(/no renewal pipelines selected/i)).toBeInTheDocument();
    expect(screen.getByText(/no suggestions will be created/i)).toBeInTheDocument();
  });

  it('does not render the empty-state warning when disabled', () => {
    const disabledEmptyStatus: HubSpotConnectionStatus = {
      ...baseStatus,
      churn_labels_enabled: false,
      churn_label_config: { renewal_pipeline_ids: [] },
    };
    render(<HubSpotChurnLabelsCard status={disabledEmptyStatus} onStatusChange={vi.fn()} />);

    expect(screen.queryByText(/no renewal pipelines selected/i)).not.toBeInTheDocument();
  });

  it('picker trigger is disabled when churn_labels_enabled is true', () => {
    const enabledStatus: HubSpotConnectionStatus = { ...baseStatus, churn_labels_enabled: true };
    render(<HubSpotChurnLabelsCard status={enabledStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /pipeline/i })).toBeDisabled();
  });

  it('picker trigger is enabled when churn_labels_enabled is false', () => {
    render(<HubSpotChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /pipeline/i })).not.toBeDisabled();
  });

  it('opening the picker fetches live options exactly once', async () => {
    const user = userEvent.setup();
    render(<HubSpotChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);

    expect(mockGetChurnLabelOptions).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: /pipeline/i }));

    await waitFor(() => {
      expect(mockGetChurnLabelOptions).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Renewals')).toBeInTheDocument();
    });
  });

  it('shows a message rather than a dead picker when HubSpot returns no pipelines', async () => {
    const user = userEvent.setup();
    mockGetChurnLabelOptions.mockResolvedValue({ options: [], provider: 'hubspot' });

    render(<HubSpotChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /pipeline/i }));

    await waitFor(() => {
      expect(screen.getByText(/no deal pipelines/i)).toBeInTheDocument();
    });
  });

  it('shows a retry option when the live options fetch fails', async () => {
    const user = userEvent.setup();
    mockGetChurnLabelOptions.mockRejectedValue({
      response: { data: { detail: { reason: 'options_fetch_failed' } } },
    });

    render(<HubSpotChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /pipeline/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  it('flags a saved id no longer present in live options without pruning it', async () => {
    const user = userEvent.setup();
    const staleStatus: HubSpotConnectionStatus = {
      ...baseStatus,
      churn_label_config: { renewal_pipeline_ids: ['stale-id'] },
    };
    render(<HubSpotChurnLabelsCard status={staleStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /pipeline/i }));

    await waitFor(() => {
      expect(screen.getByText(/stale-id/)).toBeInTheDocument();
      expect(screen.getByText(/not found/i)).toBeInTheDocument();
    });
  });

  it('renders stats grid fields and a last_harvest_error alert', () => {
    const statusWithStats: HubSpotConnectionStatus = {
      ...baseStatus,
      last_harvest_at: '2026-07-01T12:00:00Z',
      last_harvest_status: 'error: missing_read_scope',
      last_harvest_error: 'HubSpot API error: insufficient scopes',
      suggestions_created: 47,
    };
    render(<HubSpotChurnLabelsCard status={statusWithStats} onStatusChange={vi.fn()} />);

    expect(screen.getByText('47')).toBeInTheDocument();
    expect(screen.getByText(/insufficient scopes/i)).toBeInTheDocument();
    expect(screen.getByText(/missing read permission/i)).toBeInTheDocument();
  });

  describe('Backfill history (historical-backfill aspect)', () => {
    const enabledStatus: HubSpotConnectionStatus = {
      ...baseStatus,
      churn_labels_enabled: true,
      churn_label_config: { renewal_pipeline_ids: ['default'] },
    };

    it('renders the backfill section with a 24-month default and a Run button', () => {
      render(<HubSpotChurnLabelsCard status={enabledStatus} onStatusChange={vi.fn()} />);
      expect(screen.getByText(/Backfill history/i)).toBeInTheDocument();
      expect(screen.getByText('24')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^run$/i })).toBeInTheDocument();
    });

    it('Run is disabled when churn labels are disabled', () => {
      render(<HubSpotChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);
      expect(screen.getByRole('button', { name: /^run$/i })).toBeDisabled();
    });

    it('Run is disabled when the renewal set is empty even if enabled', () => {
      const emptyEnabled: HubSpotConnectionStatus = {
        ...baseStatus,
        churn_labels_enabled: true,
        churn_label_config: { renewal_pipeline_ids: [] },
      };
      render(<HubSpotChurnLabelsCard status={emptyEnabled} onStatusChange={vi.fn()} />);
      expect(screen.getByRole('button', { name: /^run$/i })).toBeDisabled();
    });

    it('clicking Run triggers a backfill with the default 24-month window', async () => {
      const user = userEvent.setup();
      const onStatusChange = vi.fn();
      mockTriggerChurnBackfill.mockResolvedValue({
        status: 'queued',
        backfill_status: 'running',
        backfill_progress: { scanned: 0, suggested: 0 },
        backfill_last_run_at: null,
        backfill_error: null,
      });
      mockGetStatus.mockResolvedValue({ ...enabledStatus, backfill_status: 'running' });

      render(<HubSpotChurnLabelsCard status={enabledStatus} onStatusChange={onStatusChange} />);
      await user.click(screen.getByRole('button', { name: /^run$/i }));

      await waitFor(() => {
        expect(mockTriggerChurnBackfill).toHaveBeenCalledWith(24);
      });
    });

    it('selecting a different window and clicking Run passes that value', async () => {
      const user = userEvent.setup();
      mockTriggerChurnBackfill.mockResolvedValue({
        status: 'queued',
        backfill_status: 'running',
        backfill_progress: {},
        backfill_last_run_at: null,
        backfill_error: null,
      });
      mockGetStatus.mockResolvedValue({ ...enabledStatus, backfill_status: 'running' });

      render(<HubSpotChurnLabelsCard status={enabledStatus} onStatusChange={vi.fn()} />);
      await user.click(screen.getByLabelText(/backfill window/i));
      await user.click(screen.getByText('60'));
      await user.click(screen.getByRole('button', { name: /^run$/i }));

      await waitFor(() => {
        expect(mockTriggerChurnBackfill).toHaveBeenCalledWith(60);
      });
    });

    it('shows Cancel instead of Run while a backfill is running', () => {
      const runningStatus: HubSpotConnectionStatus = {
        ...enabledStatus,
        backfill_status: 'running',
        backfill_progress: { scanned: 10, suggested: 2, skipped_existing: 1 },
      };
      render(<HubSpotChurnLabelsCard status={runningStatus} onStatusChange={vi.fn()} />);
      expect(screen.queryByRole('button', { name: /^run$/i })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    });

    it('clicking Cancel calls cancelChurnBackfill and refreshes status', async () => {
      const user = userEvent.setup();
      const onStatusChange = vi.fn();
      const runningStatus: HubSpotConnectionStatus = {
        ...enabledStatus,
        backfill_status: 'running',
        backfill_progress: { scanned: 10, suggested: 2 },
      };
      mockCancelChurnBackfill.mockResolvedValue({
        status: 'cancelling',
        backfill_status: 'cancelling',
        backfill_progress: { scanned: 10, suggested: 2 },
        backfill_last_run_at: null,
        backfill_error: null,
      });
      mockGetStatus.mockResolvedValue({ ...runningStatus, backfill_status: 'cancelling' });

      render(<HubSpotChurnLabelsCard status={runningStatus} onStatusChange={onStatusChange} />);
      await user.click(screen.getByRole('button', { name: /cancel/i }));

      await waitFor(() => {
        expect(mockCancelChurnBackfill).toHaveBeenCalled();
        expect(onStatusChange).toHaveBeenCalled();
      });
    });

    it('renders scanned/suggested/skipped progress numbers', () => {
      const runningStatus: HubSpotConnectionStatus = {
        ...enabledStatus,
        backfill_status: 'running',
        backfill_progress: { scanned: 40, suggested: 12, skipped_existing: 5 },
      };
      render(<HubSpotChurnLabelsCard status={runningStatus} onStatusChange={vi.fn()} />);
      expect(screen.getByText('40')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('renders backfill_error', () => {
      const failedStatus: HubSpotConnectionStatus = {
        ...enabledStatus,
        backfill_status: 'failed',
        backfill_error: 'missing_encryption_key',
      };
      render(<HubSpotChurnLabelsCard status={failedStatus} onStatusChange={vi.fn()} />);
      expect(screen.getByText(/missing_encryption_key/i)).toBeInTheDocument();
    });

    it('shows an explicit dropped-by-cap warning naming the count and covered window — no silent caps', () => {
      const cappedStatus: HubSpotConnectionStatus = {
        ...enabledStatus,
        backfill_status: 'completed',
        backfill_progress: {
          scanned: 3000,
          suggested: 2000,
          dropped_by_cap: 137,
          since: '2024-07-15T00:00:00',
        },
      };
      render(<HubSpotChurnLabelsCard status={cappedStatus} onStatusChange={vi.fn()} />);
      expect(screen.getByText(/137/)).toBeInTheDocument();
      expect(screen.getByText(/dropped by the per-run cap/i)).toBeInTheDocument();
      expect(screen.getByText(/covered window/i)).toBeInTheDocument();
    });

    it('does not show the dropped-by-cap warning when nothing was dropped', () => {
      const okStatus: HubSpotConnectionStatus = {
        ...enabledStatus,
        backfill_status: 'completed',
        backfill_progress: { scanned: 10, suggested: 10, dropped_by_cap: 0 },
      };
      render(<HubSpotChurnLabelsCard status={okStatus} onStatusChange={vi.fn()} />);
      expect(screen.queryByText(/dropped by the per-run cap/i)).not.toBeInTheDocument();
    });

    it('polls status while running and stops once no longer running', async () => {
      vi.useFakeTimers();
      const onStatusChange = vi.fn();
      const runningStatus: HubSpotConnectionStatus = {
        ...enabledStatus,
        backfill_status: 'running',
        backfill_progress: { scanned: 1, suggested: 0 },
      };
      mockGetStatus.mockResolvedValue({ ...runningStatus, backfill_status: 'completed' });

      render(<HubSpotChurnLabelsCard status={runningStatus} onStatusChange={onStatusChange} />);

      await vi.advanceTimersByTimeAsync(5000);
      expect(mockGetStatus).toHaveBeenCalled();

      vi.useRealTimers();
    });
  });
});
