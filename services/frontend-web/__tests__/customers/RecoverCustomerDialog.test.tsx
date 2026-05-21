import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

vi.mock('@/lib/api/churn-events', () => ({
  recoverCustomer: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { recoverCustomer } from '@/lib/api/churn-events';
import { toast } from 'sonner';
import { RecoverCustomerDialog } from '@/components/customers/RecoverCustomerDialog';

const mockChurnEvent = {
  id: 1,
  customer_email: 'bob@example.com',
  churned_at: '2026-04-01T00:00:00Z',
  reason_code: 'price' as const,
  reason_text: null,
  recovered_at: '2026-05-20T00:00:00Z',
  source: 'manual' as const,
  marked_by_user_id: 42,
  created_at: '2026-04-01T12:00:00Z',
};

function renderDialog(props?: Partial<React.ComponentProps<typeof RecoverCustomerDialog>>) {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    customerEmail: 'bob@example.com',
    onSuccess: vi.fn(),
    ...props,
  };
  return render(<RecoverCustomerDialog {...defaultProps} />);
}

describe('RecoverCustomerDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders confirm prompt with customer email', () => {
    renderDialog();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/bob@example\.com/i)).toBeInTheDocument();
  });

  it('defaults recovered_at to today', () => {
    renderDialog();
    const today = new Date().toISOString().split('T')[0];
    const dateInput = screen.getByLabelText(/recovery date/i) as HTMLInputElement;
    expect(dateInput.value).toBe(today);
  });

  it('shows optional note textarea', () => {
    renderDialog();
    const textarea = screen.getByPlaceholderText(/optional note/i);
    expect(textarea).toBeInTheDocument();
  });

  it('submit calls recoverCustomer with the email', async () => {
    const user = userEvent.setup();
    (recoverCustomer as ReturnType<typeof vi.fn>).mockResolvedValue(mockChurnEvent);
    renderDialog();

    await user.click(screen.getByRole('button', { name: /confirm recovery/i }));

    await waitFor(() => {
      expect(recoverCustomer).toHaveBeenCalledWith(
        'bob@example.com',
        expect.any(Object)
      );
    });
  });

  it('closes after success', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    (recoverCustomer as ReturnType<typeof vi.fn>).mockResolvedValue(mockChurnEvent);
    renderDialog({ onOpenChange });

    await user.click(screen.getByRole('button', { name: /confirm recovery/i }));

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('shows error toast on failure', async () => {
    const user = userEvent.setup();
    (recoverCustomer as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Server error'));
    renderDialog();

    await user.click(screen.getByRole('button', { name: /confirm recovery/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });
});
