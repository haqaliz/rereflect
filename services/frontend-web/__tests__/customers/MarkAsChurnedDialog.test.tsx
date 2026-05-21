import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

vi.mock('@/lib/api/churn-events', () => ({
  markCustomerChurned: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { markCustomerChurned } from '@/lib/api/churn-events';
import { toast } from 'sonner';
import { MarkAsChurnedDialog } from '@/components/customers/MarkAsChurnedDialog';

const mockChurnEvent = {
  id: 1,
  customer_email: 'alice@example.com',
  churned_at: '2026-05-20T00:00:00Z',
  reason_code: 'price' as const,
  reason_text: null,
  recovered_at: null,
  source: 'manual' as const,
  marked_by_user_id: 42,
  created_at: '2026-05-20T12:00:00Z',
};

function renderDialog(props?: Partial<React.ComponentProps<typeof MarkAsChurnedDialog>>) {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    customerEmail: 'alice@example.com',
    onSuccess: vi.fn(),
    ...props,
  };
  return render(<MarkAsChurnedDialog {...defaultProps} />);
}

describe('MarkAsChurnedDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when open=true', () => {
    renderDialog();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /mark as churned/i })).toBeInTheDocument();
  });

  it('shows reason_code Select with all 6 options', async () => {
    const user = userEvent.setup();
    renderDialog();
    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => {
      expect(screen.getByText('Price')).toBeInTheDocument();
      expect(screen.getByText('Competitor')).toBeInTheDocument();
      expect(screen.getByText('Product Quality')).toBeInTheDocument();
      expect(screen.getByText('No Longer Needed')).toBeInTheDocument();
      expect(screen.getByText('Silent Churn')).toBeInTheDocument();
      expect(screen.getByText('Other')).toBeInTheDocument();
    });
  });

  it('defaults churned_at to today\'s date', () => {
    renderDialog();
    const today = new Date().toISOString().split('T')[0];
    const dateInput = screen.getByLabelText(/churned date/i) as HTMLInputElement;
    expect(dateInput.value).toBe(today);
  });

  it('requires reason_code selection before submitting', async () => {
    const user = userEvent.setup();
    renderDialog();
    const submitButton = screen.getByRole('button', { name: /mark as churned/i });
    await user.click(submitButton);
    expect(markCustomerChurned).not.toHaveBeenCalled();
  });

  it('shows reason_text textarea as optional', () => {
    renderDialog();
    const textarea = screen.getByPlaceholderText(/optional note/i);
    expect(textarea).toBeInTheDocument();
  });

  it('calls markCustomerChurned with correct args on submit', async () => {
    const user = userEvent.setup();
    (markCustomerChurned as ReturnType<typeof vi.fn>).mockResolvedValue(mockChurnEvent);
    renderDialog();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    const submitButton = screen.getByRole('button', { name: /mark as churned/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(markCustomerChurned).toHaveBeenCalledWith(
        'alice@example.com',
        expect.objectContaining({ reason_code: 'price' })
      );
    });
  });

  it('shows error toast on API failure', async () => {
    const user = userEvent.setup();
    (markCustomerChurned as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));
    renderDialog();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /mark as churned/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });

  it('closes dialog after success', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    (markCustomerChurned as ReturnType<typeof vi.fn>).mockResolvedValue(mockChurnEvent);
    renderDialog({ onOpenChange });

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /mark as churned/i }));

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('shows loading state during submit', async () => {
    const user = userEvent.setup();
    let resolve: (v: unknown) => void;
    (markCustomerChurned as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((res) => { resolve = res; })
    );
    renderDialog();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /mark as churned/i }));

    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /mark as churned/i });
      expect(btn).toBeDisabled();
    });

    resolve!(mockChurnEvent);
  });

  it('Cancel button closes without calling API', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderDialog({ onOpenChange });

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(markCustomerChurned).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
