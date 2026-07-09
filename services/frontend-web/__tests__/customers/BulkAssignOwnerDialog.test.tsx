import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    bulkAssignOwner: vi.fn(),
  },
}));

vi.mock('@/lib/api/team', () => ({
  teamAPI: {
    getTeam: vi.fn(),
  },
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { customersAPI, type Cohort } from '@/lib/api/customers';
import { teamAPI } from '@/lib/api/team';
import { toast } from 'sonner';
import { BulkAssignOwnerDialog } from '@/components/customers/BulkAssignOwnerDialog';

const mockMembers = {
  members: [
    { id: 1, email: 'owner@acme.com', role: 'owner' as const, last_active_at: null, joined_at: null, invited_by_id: null },
    { id: 2, email: 'admin@acme.com', role: 'admin' as const, last_active_at: null, joined_at: null, invited_by_id: null },
  ],
  total: 2,
  seats_used: 2,
  seats_limit: 10,
};

function renderDialog(props?: Partial<React.ComponentProps<typeof BulkAssignOwnerDialog>>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const defaultProps: React.ComponentProps<typeof BulkAssignOwnerDialog> = {
    open: true,
    onOpenChange: vi.fn(),
    cohort: { emails: ['alice@example.com'] },
    cohortCount: 1,
    onSuccess: vi.fn(),
    ...props,
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <BulkAssignOwnerDialog {...defaultProps} />
    </QueryClientProvider>
  );
}

describe('BulkAssignOwnerDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (teamAPI.getTeam as ReturnType<typeof vi.fn>).mockResolvedValue(mockMembers);
  });

  it('loads and lists org members plus an Unassign option', async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByRole('combobox'));
    expect(await screen.findByText('owner@acme.com')).toBeInTheDocument();
    expect(screen.getByText('admin@acme.com')).toBeInTheDocument();
    expect(screen.getByText('Unassign')).toBeInTheDocument();
  });

  it('email-mode cohort: calls bulkAssignOwner with { emails } and the selected user_id', async () => {
    const user = userEvent.setup();
    (customersAPI.bulkAssignOwner as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 1, updated: 1, skipped: 0, errors: [],
    });
    const cohort: Cohort = { emails: ['alice@example.com'] };
    renderDialog({ cohort, cohortCount: 1 });

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText('admin@acme.com'));
    await user.click(screen.getByRole('button', { name: /assign owner/i }));

    await waitFor(() => {
      expect(customersAPI.bulkAssignOwner).toHaveBeenCalledWith(cohort, 2);
    });
  });

  it('filter-mode cohort: calls bulkAssignOwner with { filter }', async () => {
    const user = userEvent.setup();
    (customersAPI.bulkAssignOwner as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 12, updated: 12, skipped: 0, errors: [],
    });
    const cohort: Cohort = { filter: { segment: 'dormant' } };
    renderDialog({ cohort, cohortCount: 12 });

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText('owner@acme.com'));
    await user.click(screen.getByRole('button', { name: /assign owner/i }));

    await waitFor(() => {
      expect(customersAPI.bulkAssignOwner).toHaveBeenCalledWith(cohort, 1);
    });
  });

  it('Unassign sends user_id: null', async () => {
    const user = userEvent.setup();
    (customersAPI.bulkAssignOwner as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 1, updated: 1, skipped: 0, errors: [],
    });
    renderDialog();

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText('Unassign'));
    await user.click(screen.getByRole('button', { name: /unassign/i }));

    await waitFor(() => {
      expect(customersAPI.bulkAssignOwner).toHaveBeenCalledWith(
        expect.anything(),
        null
      );
    });
  });

  it('shows a success toast and calls onSuccess', async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    (customersAPI.bulkAssignOwner as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: 1, updated: 1, skipped: 0, errors: [],
    });
    renderDialog({ onSuccess });

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText('owner@acme.com'));
    await user.click(screen.getByRole('button', { name: /assign owner/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalled();
      expect(onSuccess).toHaveBeenCalled();
    });
  });

  it('shows an error toast on failure', async () => {
    const user = userEvent.setup();
    (customersAPI.bulkAssignOwner as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
    renderDialog();

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText('owner@acme.com'));
    await user.click(screen.getByRole('button', { name: /assign owner/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });
});
