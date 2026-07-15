import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

vi.mock('@/lib/api/churn-suggestions', () => ({
  bulkReviewChurnSuggestions: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { bulkReviewChurnSuggestions } from '@/lib/api/churn-suggestions';
import { toast } from 'sonner';
import { BulkReviewSuggestionsDialog } from '@/components/customers/BulkReviewSuggestionsDialog';

const cohort = { emails: ['alice@example.com', 'bob@example.com'] };

function renderDialog(props?: Partial<React.ComponentProps<typeof BulkReviewSuggestionsDialog>>) {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    action: 'confirm' as const,
    cohort,
    cohortCount: 2,
    onSuccess: vi.fn(),
    ...props,
  };
  return render(<BulkReviewSuggestionsDialog {...defaultProps} />);
}

describe('BulkReviewSuggestionsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when open=true', () => {
    renderDialog();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('shows the cohort count', () => {
    renderDialog();
    expect(screen.getByText(/2/)).toBeInTheDocument();
  });

  it('confirm action: submit disabled until a reason code is picked', async () => {
    const user = userEvent.setup();
    renderDialog({ action: 'confirm' });
    const submitButton = screen.getByRole('button', { name: /confirm/i });
    expect(submitButton).toBeDisabled();

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    expect(submitButton).not.toBeDisabled();
  });

  it('reject action: no reason code select is required', () => {
    renderDialog({ action: 'reject' });
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    const submitButton = screen.getByRole('button', { name: /reject/i });
    expect(submitButton).not.toBeDisabled();
  });

  it('calls bulkReviewChurnSuggestions with the cohort and action on submit', async () => {
    const user = userEvent.setup();
    (bulkReviewChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 2,
      confirmed: 2,
      skipped: 0,
      results: [],
      capped: false,
      cap: null,
    });
    renderDialog({ action: 'confirm' });

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(bulkReviewChurnSuggestions).toHaveBeenCalledWith(
        expect.objectContaining({ action: 'confirm', cohort, reason_code: 'price' })
      );
    });
  });

  it('shows result toast with skipped clause when skipped > 0', async () => {
    const user = userEvent.setup();
    (bulkReviewChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 2,
      confirmed: 1,
      skipped: 1,
      results: [],
      capped: false,
      cap: null,
    });
    renderDialog({ action: 'confirm' });

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringMatching(/1 confirmed, 1 skipped \(already marked\)/i)
      );
    });
  });

  it('omits the skipped clause when skipped is 0', async () => {
    const user = userEvent.setup();
    (bulkReviewChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 2,
      confirmed: 2,
      skipped: 0,
      results: [],
      capped: false,
      cap: null,
    });
    renderDialog({ action: 'confirm' });

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('2 confirmed.');
    });
  });

  it('appends a cap notice toast when capped', async () => {
    const user = userEvent.setup();
    (bulkReviewChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 731,
      confirmed: 490,
      skipped: 10,
      results: [],
      capped: true,
      cap: 500,
    });
    renderDialog({ action: 'confirm' });

    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await waitFor(() => screen.getByText('Price'));
    await user.click(screen.getByText('Price'));

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringMatching(/231 not processed \(cap 500\)/i)
      );
    });
  });

  it('Cancel button closes without calling API', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderDialog({ onOpenChange });

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(bulkReviewChurnSuggestions).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
