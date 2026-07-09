import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('@/lib/api/playbooks', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/playbooks')>('@/lib/api/playbooks');
  return {
    ...actual,
    listPlaybooks: vi.fn(),
    runPlaybookBatch: vi.fn(),
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { listPlaybooks, runPlaybookBatch } from '@/lib/api/playbooks';
import { toast } from 'sonner';
import { BulkRunPlaybookDialog } from '@/components/customers/BulkRunPlaybookDialog';
import type { Cohort } from '@/lib/api/customers';

const mockPlaybooks = [
  {
    id: 5,
    organization_id: 1,
    name: 'Win-back at-risk',
    description: null,
    probability_min: 0.5,
    probability_max: 0.9,
    action_sequence: [],
    is_template: false,
    is_active: true,
    source_template_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

function renderDialog(props?: Partial<React.ComponentProps<typeof BulkRunPlaybookDialog>>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const defaultProps: React.ComponentProps<typeof BulkRunPlaybookDialog> = {
    open: true,
    onOpenChange: vi.fn(),
    cohort: { emails: ['alice@example.com'] },
    onSuccess: vi.fn(),
    ...props,
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <BulkRunPlaybookDialog {...defaultProps} />
    </QueryClientProvider>
  );
}

describe('BulkRunPlaybookDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listPlaybooks as ReturnType<typeof vi.fn>).mockResolvedValue(mockPlaybooks);
  });

  it('email-mode cohort: preview + run both send filters.emails', async () => {
    const user = userEvent.setup();
    (runPlaybookBatch as ReturnType<typeof vi.fn>).mockResolvedValue({
      queued: 0, execution_ids: [], matched: 3,
    });
    const cohort: Cohort = { emails: ['a@co.com', 'b@co.com', 'c@co.com'] };
    renderDialog({ cohort });

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText(/Win-back at-risk/));

    await waitFor(() => {
      expect(runPlaybookBatch).toHaveBeenCalledWith(
        5,
        { emails: ['a@co.com', 'b@co.com', 'c@co.com'] },
        { countOnly: true }
      );
    });
    expect(await screen.findByText(/3 customers will be affected/i)).toBeInTheDocument();

    (runPlaybookBatch as ReturnType<typeof vi.fn>).mockResolvedValue({
      queued: 3, execution_ids: [1, 2, 3], matched: 3,
    });
    await user.click(screen.getByRole('button', { name: /run playbook/i }));

    await waitFor(() => {
      expect(runPlaybookBatch).toHaveBeenCalledWith(
        5,
        { emails: ['a@co.com', 'b@co.com', 'c@co.com'] }
      );
    });
  });

  it('segment filter-mode cohort: sends filters.segment (not emails)', async () => {
    const user = userEvent.setup();
    (runPlaybookBatch as ReturnType<typeof vi.fn>).mockResolvedValue({
      queued: 0, execution_ids: [], matched: 40,
    });
    const cohort: Cohort = { filter: { segment: 'at_risk' } };
    renderDialog({ cohort });

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText(/Win-back at-risk/));

    await waitFor(() => {
      expect(runPlaybookBatch).toHaveBeenCalledWith(5, { segment: 'at_risk' }, { countOnly: true });
    });
    const [, filters] = (runPlaybookBatch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(filters).not.toHaveProperty('emails');
  });

  it('blocks the run when the filter has no segment (unsupported cohort shape)', async () => {
    const cohort: Cohort = { filter: { risk_level: 'critical' } };
    renderDialog({ cohort });

    expect(
      await screen.findByText(/only supports a segment- or explicit-selection cohort/i)
    ).toBeInTheDocument();
    expect(runPlaybookBatch).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /run playbook/i })).toBeDisabled();
  });

  it('warns and blocks the run when matched exceeds the 500 cap', async () => {
    const user = userEvent.setup();
    (runPlaybookBatch as ReturnType<typeof vi.fn>).mockResolvedValue({
      queued: 0, execution_ids: [], matched: 900,
    });
    renderDialog({ cohort: { filter: { segment: 'at_risk' } } });

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText(/Win-back at-risk/));

    expect(await screen.findByText(/exceeds the batch cap of 500/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run playbook/i })).toBeDisabled();
  });

  it('shows a success toast and calls onSuccess on run', async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    (runPlaybookBatch as ReturnType<typeof vi.fn>).mockResolvedValue({
      queued: 3, execution_ids: [1, 2, 3], matched: 3,
    });
    renderDialog({ cohort: { emails: ['a@co.com'] }, onSuccess });

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText(/Win-back at-risk/));
    await waitFor(() => expect(runPlaybookBatch).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole('button', { name: /run playbook/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalled();
      expect(onSuccess).toHaveBeenCalled();
    });
  });

  it('shows the backend 422 detail message on cap-exceeded error', async () => {
    const user = userEvent.setup();
    (runPlaybookBatch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ queued: 0, execution_ids: [], matched: 3 })
      .mockRejectedValueOnce({
        response: { data: { detail: 'cohort of 3 exceeds batch cap of 500; narrow the filter' } },
      });
    renderDialog({ cohort: { emails: ['a@co.com'] } });

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText(/Win-back at-risk/));
    await waitFor(() => expect(runPlaybookBatch).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole('button', { name: /run playbook/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('exceeds batch cap of 500')
      );
    });
  });
});
