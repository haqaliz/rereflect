import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockUpdateWriteback = vi.fn();
const mockTestWriteback = vi.fn();
const mockGetStatus = vi.fn();

vi.mock('@/lib/api/hubspot', () => ({
  hubspotAPI: {
    updateWriteback: (...args: unknown[]) => mockUpdateWriteback(...args),
    testWriteback: (...args: unknown[]) => mockTestWriteback(...args),
    getStatus: (...args: unknown[]) => mockGetStatus(...args),
  },
}));

import { HubSpotWritebackCard } from '@/components/settings/HubSpotWritebackCard';
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
};

const disconnectedStatus: HubSpotConnectionStatus = {
  ...baseStatus,
  connected: false,
};

describe('HubSpotWritebackCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when HubSpot is disconnected', () => {
    const { container } = render(
      <HubSpotWritebackCard status={disconnectedStatus} onStatusChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the card when connected', () => {
    render(<HubSpotWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText('Health-Score Writeback')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('prefills the field-name input with the default suggestion', () => {
    render(<HubSpotWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByDisplayValue('rereflect_health_score')).toBeInTheDocument();
  });

  it('toggling on with a valid field calls updateWriteback then refetches status', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateWriteback.mockResolvedValue({
      writeback_enabled: true,
      writeback_field_name: 'rereflect_health_score',
      last_writeback_at: null,
      last_writeback_status: null,
      last_writeback_error: null,
      contacts_written: 0,
    });
    const refetchedStatus: HubSpotConnectionStatus = {
      ...baseStatus,
      writeback_enabled: true,
      writeback_field_name: 'rereflect_health_score',
    };
    mockGetStatus.mockResolvedValue(refetchedStatus);

    render(<HubSpotWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(mockUpdateWriteback).toHaveBeenCalledWith({
        enabled: true,
        field_name: 'rereflect_health_score',
      });
    });
    await waitFor(() => {
      expect(mockGetStatus).toHaveBeenCalled();
      expect(onStatusChange).toHaveBeenCalledWith(refetchedStatus);
    });
  });

  it('does not latch the switch on optimistically before the PATCH resolves', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    let resolveUpdate: (value: any) => void = () => {};
    mockUpdateWriteback.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve;
      })
    );

    render(<HubSpotWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    // Still off — status prop hasn't changed and we don't optimistically flip it.
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');

    resolveUpdate({
      writeback_enabled: true,
      writeback_field_name: 'rereflect_health_score',
      last_writeback_at: null,
      last_writeback_status: null,
      last_writeback_error: null,
      contacts_written: 0,
    });
    mockGetStatus.mockResolvedValue({ ...baseStatus, writeback_enabled: true });
    await waitFor(() => expect(onStatusChange).toHaveBeenCalled());
  });

  it('toggling on with an empty field name blocks client-side and leaves the switch off', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    render(<HubSpotWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);

    const input = screen.getByLabelText(/field name/i);
    await user.clear(input);
    await user.click(screen.getByRole('switch'));

    expect(mockUpdateWriteback).not.toHaveBeenCalled();
    expect(onStatusChange).not.toHaveBeenCalled();
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
    expect(screen.getByText(/field name is required/i)).toBeInTheDocument();
  });

  it('toggling on with an invalid field surfaces the backend error and leaves the switch off', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateWriteback.mockRejectedValue({
      response: {
        status: 400,
        data: { detail: { reason: 'field_not_found', message: "Field 'bogus' failed writeback validation: field_not_found." } },
      },
    });

    render(<HubSpotWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(screen.getByText(/field_not_found/i)).toBeInTheDocument();
    });
    expect(onStatusChange).not.toHaveBeenCalled();
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
  });

  it('renders status row fields and a last_writeback_error alert', () => {
    const statusWithError: HubSpotConnectionStatus = {
      ...baseStatus,
      writeback_enabled: true,
      writeback_field_name: 'rereflect_health_score',
      last_writeback_at: '2026-07-01T12:00:00Z',
      last_writeback_status: 'error: missing_write_scope',
      last_writeback_error: 'HubSpot API error: insufficient scopes',
      contacts_written: 42,
    };
    render(<HubSpotWritebackCard status={statusWithError} onStatusChange={vi.fn()} />);

    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText(/insufficient scopes/i)).toBeInTheDocument();
    expect(screen.getByText(/missing write permission/i)).toBeInTheDocument();
  });

  it('Validate button calls testWriteback and renders the ok result panel', async () => {
    const user = userEvent.setup();
    mockTestWriteback.mockResolvedValue({ ok: true, reason: null });

    render(<HubSpotWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /validate/i }));

    await waitFor(() => {
      expect(mockTestWriteback).toHaveBeenCalledWith('rereflect_health_score');
    });
    await waitFor(() => {
      expect(screen.getByText(/field is valid/i)).toBeInTheDocument();
    });
  });

  it('Validate button renders the failure reason panel', async () => {
    const user = userEvent.setup();
    mockTestWriteback.mockResolvedValue({ ok: false, reason: 'wrong_type' });

    render(<HubSpotWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /validate/i }));

    await waitFor(() => {
      expect(screen.getByText(/wrong_type|not a number/i)).toBeInTheDocument();
    });
  });
});
