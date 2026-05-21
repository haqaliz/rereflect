import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

vi.mock('@/lib/api/churn-events', () => ({
  bulkMarkChurned: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { bulkMarkChurned } from '@/lib/api/churn-events';
import { toast } from 'sonner';
import { BulkMarkChurnedDialog } from '@/components/customers/BulkMarkChurnedDialog';

const selectedEmails = ['alice@example.com', 'bob@example.com', 'carol@example.com'];

function renderDialog(props?: Partial<React.ComponentProps<typeof BulkMarkChurnedDialog>>) {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    selectedEmails,
    onSuccess: vi.fn(),
    ...props,
  };
  return render(<BulkMarkChurnedDialog {...defaultProps} />);
}

describe('BulkMarkChurnedDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows selected emails count', () => {
    renderDialog();
    expect(screen.getByText(/3 customers/i)).toBeInTheDocument();
  });

  it('shows summary list of emails', () => {
    renderDialog();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
    expect(screen.getByText('carol@example.com')).toBeInTheDocument();
  });

  it('truncates list when more than 5 emails', () => {
    const manyEmails = [
      'a@x.com', 'b@x.com', 'c@x.com', 'd@x.com', 'e@x.com', 'f@x.com', 'g@x.com',
    ];
    renderDialog({ selectedEmails: manyEmails });
    expect(screen.getByText(/\+2 more/i)).toBeInTheDocument();
  });

  it('requires reason_code before submitting', async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByRole('button', { name: /mark as churned/i }));
    expect(bulkMarkChurned).not.toHaveBeenCalled();
  });

  it('calls bulkMarkChurned with all emails on submit', async () => {
    const user = userEvent.setup();
    (bulkMarkChurned as ReturnType<typeof vi.fn>).mockResolvedValue({
      created: 3,
      skipped: 0,
      errors: [],
    });
    renderDialog();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /mark as churned/i }));

    await waitFor(() => {
      expect(bulkMarkChurned).toHaveBeenCalledWith(
        expect.objectContaining({ emails: selectedEmails, reason_code: 'price' })
      );
    });
  });

  it('shows result summary after success', async () => {
    const user = userEvent.setup();
    (bulkMarkChurned as ReturnType<typeof vi.fn>).mockResolvedValue({
      created: 2,
      skipped: 1,
      errors: [],
    });
    renderDialog();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /mark as churned/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringMatching(/2 marked/i)
      );
    });
  });

  it('handles partial failure with errors list', async () => {
    const user = userEvent.setup();
    (bulkMarkChurned as ReturnType<typeof vi.fn>).mockResolvedValue({
      created: 2,
      skipped: 0,
      errors: ['carol@example.com: duplicate event'],
    });
    renderDialog();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /mark as churned/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalled();
    });
  });
});
