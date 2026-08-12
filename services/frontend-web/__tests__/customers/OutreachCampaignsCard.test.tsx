import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('@/lib/api/outreach', () => ({
  listCampaigns: vi.fn(),
  retryCampaign: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { listCampaigns, retryCampaign } from '@/lib/api/outreach';
import { toast } from 'sonner';
import { OutreachCampaignsCard } from '@/components/customers/OutreachCampaignsCard';

const mockListCampaigns = listCampaigns as ReturnType<typeof vi.fn>;
const mockRetryCampaign = retryCampaign as ReturnType<typeof vi.fn>;

const CAMPAIGN_DONE = {
  id: 1,
  subject: 'We miss you',
  status: 'done',
  recipient_count: 10,
  counts: { queued: 0, sent: 10, skipped: 0, failed: 0 },
  created_at: '2026-08-12T10:00:00Z',
};

const CAMPAIGN_IN_PROGRESS = {
  id: 2,
  subject: 'New pricing update',
  status: 'in_progress',
  recipient_count: 10,
  counts: { queued: 4, sent: 3, skipped: 2, failed: 1 },
  created_at: '2026-08-12T08:00:00Z',
};

function renderCard(campaigns: unknown[] = []) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
  mockListCampaigns.mockResolvedValue({
    items: campaigns,
    total: campaigns.length,
    page: 1,
    page_size: 5,
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <OutreachCampaignsCard />
    </QueryClientProvider>
  );
  return { ...utils, invalidateSpy };
}

describe('OutreachCampaignsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRetryCampaign.mockResolvedValue({ matched: 4, queued: 4, skipped: 0, errors: [] });
  });

  it('fetches the 5 most recent campaigns and renders subject, status, date and per-recipient counts', async () => {
    renderCard([CAMPAIGN_DONE, CAMPAIGN_IN_PROGRESS]);

    await waitFor(() => {
      expect(listCampaigns).toHaveBeenCalledWith({ page: 1, page_size: 5 });
    });

    expect(await screen.findByText('We miss you')).toBeInTheDocument();
    expect(screen.getByText('New pricing update')).toBeInTheDocument();
    expect(screen.getByText('Done')).toBeInTheDocument();
    expect(screen.getByText('In progress')).toBeInTheDocument();
    expect(screen.getByText(/3 sent · 1 failed · 2 skipped · 4 queued/)).toBeInTheDocument();
    expect(screen.getByText(/10 sent · 0 failed · 0 skipped · 0 queued/)).toBeInTheDocument();
    expect(screen.getAllByText(/\d+[mhd] ago/)).toHaveLength(2);
  });

  it('renders an empty state when there are no campaigns yet', async () => {
    renderCard([]);

    expect(await screen.findByText('No outreach campaigns yet')).toBeInTheDocument();
  });

  it('renders an honest error state when the fetch fails', async () => {
    mockListCampaigns.mockRejectedValueOnce(new Error('network'));
    renderCard([]);

    expect(
      await screen.findByText('Failed to load outreach campaigns')
    ).toBeInTheDocument();
  });

  it('shows "Retry queued" only when counts.queued > 0', async () => {
    renderCard([CAMPAIGN_DONE, CAMPAIGN_IN_PROGRESS]);

    expect(await screen.findByRole('button', { name: /retry queued/i })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /retry queued/i })).toHaveLength(1);
  });

  it('retries the campaign, toasts success and invalidates the campaigns query', async () => {
    const user = userEvent.setup();
    const { invalidateSpy } = renderCard([CAMPAIGN_IN_PROGRESS]);

    await user.click(await screen.findByRole('button', { name: /retry queued/i }));

    await waitFor(() => {
      expect(mockRetryCampaign).toHaveBeenCalledWith(2);
    });
    expect(toast.success).toHaveBeenCalled();
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['outreach-campaigns'] });
    });
  });

  it('toasts the backend detail when a retry fails', async () => {
    mockRetryCampaign.mockRejectedValue({
      response: { status: 422, data: { detail: 'nothing is queued to retry' } },
    });
    const user = userEvent.setup();
    renderCard([CAMPAIGN_IN_PROGRESS]);

    await user.click(await screen.findByRole('button', { name: /retry queued/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('nothing is queued'));
    });
  });
});
