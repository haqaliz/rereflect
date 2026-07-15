import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockUpdateChurnLabels = vi.fn();
const mockGetChurnLabelOptions = vi.fn();
const mockGetStatus = vi.fn();

vi.mock('@/lib/api/salesforce', () => ({
  salesforceAPI: {
    updateChurnLabels: (...args: unknown[]) => mockUpdateChurnLabels(...args),
    getChurnLabelOptions: (...args: unknown[]) => mockGetChurnLabelOptions(...args),
    getStatus: (...args: unknown[]) => mockGetStatus(...args),
  },
}));

import { SalesforceChurnLabelsCard } from '@/components/settings/SalesforceChurnLabelsCard';
import type { SalesforceConnectionStatus } from '@/lib/api/salesforce';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const baseStatus: SalesforceConnectionStatus = {
  connected: true,
  instance_url: 'https://acme.my.salesforce.com',
  sf_org_id: '00Dxx0000001gPFEAY',
  token_hint: '...abcd',
  last_synced_at: null,
  last_sync_status: null,
  last_error: null,
  contacts_synced: 10,
  contacts_matched: 8,
  connected_at: '2026-01-01T00:00:00Z',
  writeback_enabled: false,
  writeback_field_name: null,
  last_writeback_at: null,
  last_writeback_status: null,
  last_writeback_error: null,
  contacts_written: 0,
  churn_labels_enabled: false,
  churn_label_config: { renewal_opportunity_types: ['Renewal'] },
  last_harvest_at: null,
  last_harvest_status: null,
  last_harvest_error: null,
  suggestions_created: 0,
};

const disconnectedStatus: SalesforceConnectionStatus = {
  ...baseStatus,
  connected: false,
};

const FAKE_OPTIONS = [
  { id: 'Renewal', label: 'Renewal' },
  { id: 'Existing Business', label: 'Existing Business' },
];

describe('SalesforceChurnLabelsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetChurnLabelOptions.mockResolvedValue({ options: FAKE_OPTIONS, provider: 'salesforce' });
  });

  it('renders nothing when Salesforce is disconnected', () => {
    const { container } = render(
      <SalesforceChurnLabelsCard status={disconnectedStatus} onStatusChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the card when connected', () => {
    render(<SalesforceChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/CRM Churn-Label Suggestions/i)).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('toggling on calls updateChurnLabels with the current selection, then refetches status', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateChurnLabels.mockResolvedValue({
      churn_labels_enabled: true,
      churn_label_config: { renewal_opportunity_types: ['Renewal'] },
      last_harvest_at: null,
      last_harvest_status: null,
      last_harvest_error: null,
      suggestions_created: 0,
    });
    const refreshedStatus: SalesforceConnectionStatus = {
      ...baseStatus,
      churn_labels_enabled: true,
    };
    mockGetStatus.mockResolvedValue(refreshedStatus);

    render(<SalesforceChurnLabelsCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(mockUpdateChurnLabels).toHaveBeenCalledWith({
        enabled: true,
        config: { renewal_opportunity_types: ['Renewal'] },
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

    render(<SalesforceChurnLabelsCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');

    resolveUpdate({
      churn_labels_enabled: true,
      churn_label_config: { renewal_opportunity_types: ['Renewal'] },
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
        data: { detail: { reason: 'unknown_opportunity_type' } },
      },
    });

    render(<SalesforceChurnLabelsCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(screen.getByText(/unknown.*opportunity type/i)).toBeInTheDocument();
    });
    expect(onStatusChange).not.toHaveBeenCalled();
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
  });

  it('renders the default-deny empty-state warning when enabled with an empty renewal list', () => {
    const emptyEnabledStatus: SalesforceConnectionStatus = {
      ...baseStatus,
      churn_labels_enabled: true,
      churn_label_config: { renewal_opportunity_types: [] },
    };
    render(<SalesforceChurnLabelsCard status={emptyEnabledStatus} onStatusChange={vi.fn()} />);

    expect(screen.getByText(/no renewal opportunity types selected/i)).toBeInTheDocument();
    expect(screen.getByText(/no suggestions will be created/i)).toBeInTheDocument();
  });

  it('does not render the empty-state warning when disabled', () => {
    const disabledEmptyStatus: SalesforceConnectionStatus = {
      ...baseStatus,
      churn_labels_enabled: false,
      churn_label_config: { renewal_opportunity_types: [] },
    };
    render(<SalesforceChurnLabelsCard status={disabledEmptyStatus} onStatusChange={vi.fn()} />);

    expect(screen.queryByText(/no renewal opportunity types selected/i)).not.toBeInTheDocument();
  });

  it('picker trigger is disabled when churn_labels_enabled is true', () => {
    const enabledStatus: SalesforceConnectionStatus = { ...baseStatus, churn_labels_enabled: true };
    render(<SalesforceChurnLabelsCard status={enabledStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /opportunity type/i })).toBeDisabled();
  });

  it('picker trigger is enabled when churn_labels_enabled is false', () => {
    render(<SalesforceChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /opportunity type/i })).not.toBeDisabled();
  });

  it('opening the picker fetches live options exactly once', async () => {
    const user = userEvent.setup();
    render(<SalesforceChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);

    expect(mockGetChurnLabelOptions).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: /opportunity type/i }));

    await waitFor(() => {
      expect(mockGetChurnLabelOptions).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Existing Business')).toBeInTheDocument();
    });
  });

  it('shows a message rather than a dead picker when Salesforce returns no opportunity types', async () => {
    const user = userEvent.setup();
    mockGetChurnLabelOptions.mockResolvedValue({ options: [], provider: 'salesforce' });

    render(<SalesforceChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /opportunity type/i }));

    await waitFor(() => {
      expect(screen.getByText(/no opportunity types/i)).toBeInTheDocument();
    });
  });

  it('shows a retry option when the live options fetch fails', async () => {
    const user = userEvent.setup();
    mockGetChurnLabelOptions.mockRejectedValue({
      response: { data: { detail: { reason: 'options_fetch_failed' } } },
    });

    render(<SalesforceChurnLabelsCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /opportunity type/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  it('flags a saved id no longer present in live options without pruning it', async () => {
    const user = userEvent.setup();
    const staleStatus: SalesforceConnectionStatus = {
      ...baseStatus,
      churn_label_config: { renewal_opportunity_types: ['Stale Type'] },
    };
    render(<SalesforceChurnLabelsCard status={staleStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /opportunity type/i }));

    await waitFor(() => {
      expect(screen.getByText(/Stale Type/)).toBeInTheDocument();
      expect(screen.getByText(/not found/i)).toBeInTheDocument();
    });
  });

  it('renders stats grid fields, deferred status copy, and a last_harvest_error alert', () => {
    const statusWithStats: SalesforceConnectionStatus = {
      ...baseStatus,
      last_harvest_at: '2026-07-01T12:00:00Z',
      last_harvest_status: 'deferred: daily_limit',
      last_harvest_error: 'Salesforce API error: insufficient scopes',
      suggestions_created: 47,
    };
    render(<SalesforceChurnLabelsCard status={statusWithStats} onStatusChange={vi.fn()} />);

    expect(screen.getByText('47')).toBeInTheDocument();
    expect(screen.getByText(/insufficient scopes/i)).toBeInTheDocument();
    expect(screen.getByText(/daily api limit/i)).toBeInTheDocument();
  });
});
