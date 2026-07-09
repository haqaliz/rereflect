import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    bulkTag: vi.fn(),
  },
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { customersAPI, type Cohort } from '@/lib/api/customers';
import { toast } from 'sonner';
import { BulkTagDialog } from '@/components/customers/BulkTagDialog';

function renderDialog(props?: Partial<React.ComponentProps<typeof BulkTagDialog>>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const defaultProps: React.ComponentProps<typeof BulkTagDialog> = {
    open: true,
    onOpenChange: vi.fn(),
    cohort: { emails: ['alice@example.com', 'bob@example.com'] },
    cohortCount: 2,
    onSuccess: vi.fn(),
    ...props,
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <BulkTagDialog {...defaultProps} />
    </QueryClientProvider>
  );
}

async function addTag(user: ReturnType<typeof userEvent.setup>, tag: string) {
  const input = screen.getByLabelText('Tag input');
  await user.type(input, `${tag}{Enter}`);
}

describe('BulkTagDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the cohort count', () => {
    renderDialog({ cohortCount: 7 });
    expect(screen.getByText(/7 customers/i)).toBeInTheDocument();
  });

  it('disables submit until at least one tag is entered', () => {
    renderDialog();
    expect(screen.getByRole('button', { name: /add tags/i })).toBeDisabled();
  });

  it('email-mode cohort: calls bulkTag with { emails } (not filter)', async () => {
    const user = userEvent.setup();
    (customersAPI.bulkTag as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 2, updated: 2, skipped: 0, errors: [],
    });
    const cohort: Cohort = { emails: ['alice@example.com', 'bob@example.com'] };
    renderDialog({ cohort, cohortCount: 2 });

    await addTag(user, 'vip');
    await user.click(screen.getByRole('button', { name: /add tags/i }));

    await waitFor(() => {
      expect(customersAPI.bulkTag).toHaveBeenCalledWith(cohort, ['vip'], 'add');
    });
    const [passedCohort] = (customersAPI.bulkTag as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(passedCohort).not.toHaveProperty('filter');
  });

  it('filter-mode cohort: calls bulkTag with { filter } (not emails)', async () => {
    const user = userEvent.setup();
    (customersAPI.bulkTag as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 40, updated: 40, skipped: 0, errors: [],
    });
    const cohort: Cohort = { filter: { segment: 'at_risk' } };
    renderDialog({ cohort, cohortCount: 40 });

    await addTag(user, 'q3-risk');
    await user.click(screen.getByRole('button', { name: /add tags/i }));

    await waitFor(() => {
      expect(customersAPI.bulkTag).toHaveBeenCalledWith(cohort, ['q3-risk'], 'add');
    });
    const [passedCohort] = (customersAPI.bulkTag as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(passedCohort).not.toHaveProperty('emails');
  });

  it('remove mode passes mode="remove"', async () => {
    const user = userEvent.setup();
    (customersAPI.bulkTag as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 2, updated: 2, skipped: 0, errors: [],
    });
    renderDialog();

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText('Remove tags'));
    await addTag(user, 'vip');
    await user.click(screen.getByRole('button', { name: /remove tags/i }));

    await waitFor(() => {
      expect(customersAPI.bulkTag).toHaveBeenCalledWith(expect.anything(), ['vip'], 'remove');
    });
  });

  it('shows a success toast and calls onSuccess', async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    (customersAPI.bulkTag as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 2, updated: 2, skipped: 0, errors: [],
    });
    renderDialog({ onSuccess });

    await addTag(user, 'vip');
    await user.click(screen.getByRole('button', { name: /add tags/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalled();
      expect(onSuccess).toHaveBeenCalled();
    });
  });

  it('shows an error toast on failure', async () => {
    const user = userEvent.setup();
    (customersAPI.bulkTag as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
    renderDialog();

    await addTag(user, 'vip');
    await user.click(screen.getByRole('button', { name: /add tags/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });
});
