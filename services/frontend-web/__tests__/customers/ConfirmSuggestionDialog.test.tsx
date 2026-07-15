import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

vi.mock('@/lib/api/churn-suggestions', () => ({
  confirmChurnSuggestion: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { confirmChurnSuggestion } from '@/lib/api/churn-suggestions';
import { toast } from 'sonner';
import { ConfirmSuggestionDialog } from '@/components/customers/ConfirmSuggestionDialog';

const mockSuggestion = {
  id: 7,
  customer_email: 'alice@example.com',
  provider: 'hubspot' as const,
  suggested_churned_at: '2026-05-20T00:00:00Z',
  evidence: { deal_name: 'Acme Renewal', amount: 5000 },
};

function renderDialog(props?: Partial<React.ComponentProps<typeof ConfirmSuggestionDialog>>) {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    suggestion: mockSuggestion,
    onSuccess: vi.fn(),
    ...props,
  };
  return render(<ConfirmSuggestionDialog {...defaultProps} />);
}

describe('ConfirmSuggestionDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when open=true', () => {
    renderDialog();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('shows the CRM close date as read-only, not an editable date input', () => {
    renderDialog();
    expect(screen.queryByLabelText(/churned date/i)).not.toBeInTheDocument();
    expect(screen.getByText(/2026-05-20|may 20, 2026/i)).toBeInTheDocument();
  });

  it('requires reason_code selection before submitting', async () => {
    const user = userEvent.setup();
    renderDialog();
    const submitButton = screen.getByRole('button', { name: /confirm/i });
    await user.click(submitButton);
    expect(confirmChurnSuggestion).not.toHaveBeenCalled();
  });

  it('submit button is disabled until a reason code is picked', async () => {
    const user = userEvent.setup();
    renderDialog();
    const submitButton = screen.getByRole('button', { name: /confirm/i });
    expect(submitButton).toBeDisabled();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    expect(submitButton).not.toBeDisabled();
  });

  it('calls confirmChurnSuggestion with the suggestion id and reason_code on submit', async () => {
    const user = userEvent.setup();
    (confirmChurnSuggestion as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 7,
      status: 'confirmed',
      churn_event_id: 99,
      reason: null,
    });
    renderDialog();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(confirmChurnSuggestion).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ reason_code: 'price' })
      );
    });
  });

  it('shows a distinct toast when the result is skipped (already marked)', async () => {
    const user = userEvent.setup();
    (confirmChurnSuggestion as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 7,
      status: 'skipped',
      churn_event_id: 55,
      reason: 'already_marked',
    });
    renderDialog();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/already marked/i));
    });
  });

  it('closes dialog after a successful confirm', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    (confirmChurnSuggestion as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 7,
      status: 'confirmed',
      churn_event_id: 99,
      reason: null,
    });
    renderDialog({ onOpenChange });

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('shows error toast on API failure', async () => {
    const user = userEvent.setup();
    (confirmChurnSuggestion as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));
    renderDialog();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });

  it('Cancel button closes without calling API', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderDialog({ onOpenChange });

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(confirmChurnSuggestion).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
