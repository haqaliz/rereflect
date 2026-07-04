import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockUpdateWriteback = vi.fn();
const mockTestWriteback = vi.fn();
const mockGetStatus = vi.fn();

vi.mock('@/lib/api/salesforce', () => ({
  salesforceAPI: {
    updateWriteback: (...args: unknown[]) => mockUpdateWriteback(...args),
    testWriteback: (...args: unknown[]) => mockTestWriteback(...args),
    getStatus: (...args: unknown[]) => mockGetStatus(...args),
  },
}));

import { SalesforceWritebackCard } from '@/components/settings/SalesforceWritebackCard';
import type { SalesforceConnectionStatus } from '@/lib/api/salesforce';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const baseStatus: SalesforceConnectionStatus = {
  connected: true,
  instance_url: 'https://acme.my.salesforce.com',
  sf_org_id: '00Dxx0000001abc',
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
};

const disconnectedStatus: SalesforceConnectionStatus = {
  ...baseStatus,
  connected: false,
};

describe('SalesforceWritebackCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when Salesforce is disconnected', () => {
    const { container } = render(
      <SalesforceWritebackCard status={disconnectedStatus} onStatusChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the card when connected', () => {
    render(<SalesforceWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByText('Health-Score Writeback')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('prefills the field-name input with the default suggestion', () => {
    render(<SalesforceWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByDisplayValue('Rereflect_Health_Score__c')).toBeInTheDocument();
  });

  it('toggling on with a valid field calls updateWriteback then refetches status', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    mockUpdateWriteback.mockResolvedValue({
      writeback_enabled: true,
      writeback_field_name: 'Rereflect_Health_Score__c',
      last_writeback_at: null,
      last_writeback_status: null,
      last_writeback_error: null,
      contacts_written: 0,
    });
    const refetchedStatus: SalesforceConnectionStatus = {
      ...baseStatus,
      writeback_enabled: true,
      writeback_field_name: 'Rereflect_Health_Score__c',
    };
    mockGetStatus.mockResolvedValue(refetchedStatus);

    render(<SalesforceWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(mockUpdateWriteback).toHaveBeenCalledWith({
        enabled: true,
        field_name: 'Rereflect_Health_Score__c',
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

    render(<SalesforceWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    // Still off — status prop hasn't changed and we don't optimistically flip it.
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');

    resolveUpdate({
      writeback_enabled: true,
      writeback_field_name: 'Rereflect_Health_Score__c',
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
    render(<SalesforceWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);

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
        data: { detail: { reason: 'field_not_found', message: "Field 'Bogus__c' failed writeback validation: field_not_found." } },
      },
    });

    render(<SalesforceWritebackCard status={baseStatus} onStatusChange={onStatusChange} />);
    await user.click(screen.getByRole('switch'));

    await waitFor(() => {
      expect(screen.getByText(/field_not_found/i)).toBeInTheDocument();
    });
    expect(onStatusChange).not.toHaveBeenCalled();
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
  });

  it('locks the field-name input once writeback is enabled', () => {
    const enabledStatus: SalesforceConnectionStatus = {
      ...baseStatus,
      writeback_enabled: true,
      writeback_field_name: 'Rereflect_Health_Score__c',
    };
    render(<SalesforceWritebackCard status={enabledStatus} onStatusChange={vi.fn()} />);
    expect(screen.getByLabelText(/field name/i)).toBeDisabled();
  });

  it('renders status row fields and a last_writeback_error alert', () => {
    const statusWithError: SalesforceConnectionStatus = {
      ...baseStatus,
      writeback_enabled: true,
      writeback_field_name: 'Rereflect_Health_Score__c',
      last_writeback_at: '2026-07-01T12:00:00Z',
      last_writeback_status: 'error: missing_write_scope',
      last_writeback_error: 'Salesforce API error: insufficient scopes',
      contacts_written: 42,
    };
    render(<SalesforceWritebackCard status={statusWithError} onStatusChange={vi.fn()} />);

    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText(/insufficient scopes/i)).toBeInTheDocument();
    expect(screen.getByText(/missing write permission/i)).toBeInTheDocument();
  });

  it('renders a friendly note for an ambiguous contact match', () => {
    const statusAmbiguous: SalesforceConnectionStatus = {
      ...baseStatus,
      writeback_enabled: true,
      writeback_field_name: 'Rereflect_Health_Score__c',
      last_writeback_at: '2026-07-01T12:00:00Z',
      last_writeback_status: 'ok',
      last_writeback_error: 'ambiguous_contact',
      contacts_written: 5,
    };
    render(<SalesforceWritebackCard status={statusAmbiguous} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/ambiguous|multiple matching contacts/i)).toBeInTheDocument();
  });

  it('renders a friendly note when writeback is deferred for the daily API limit', () => {
    const statusDeferred: SalesforceConnectionStatus = {
      ...baseStatus,
      writeback_enabled: true,
      writeback_field_name: 'Rereflect_Health_Score__c',
      last_writeback_at: '2026-07-01T12:00:00Z',
      last_writeback_status: 'deferred: daily_limit',
      contacts_written: 5,
    };
    render(<SalesforceWritebackCard status={statusDeferred} onStatusChange={vi.fn()} />);
    expect(screen.getByText(/daily.*limit/i)).toBeInTheDocument();
  });

  it('Validate button calls testWriteback and renders the ok result panel', async () => {
    const user = userEvent.setup();
    mockTestWriteback.mockResolvedValue({ ok: true, reason: null });

    render(<SalesforceWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /validate/i }));

    await waitFor(() => {
      expect(mockTestWriteback).toHaveBeenCalledWith('Rereflect_Health_Score__c');
    });
    await waitFor(() => {
      expect(screen.getByText(/field is valid/i)).toBeInTheDocument();
    });
  });

  it('Validate button renders the failure reason panel', async () => {
    const user = userEvent.setup();
    mockTestWriteback.mockResolvedValue({ ok: false, reason: 'wrong_type' });

    render(<SalesforceWritebackCard status={baseStatus} onStatusChange={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /validate/i }));

    await waitFor(() => {
      expect(screen.getByText(/wrong_type|not a (writable )?number/i)).toBeInTheDocument();
    });
  });
});
