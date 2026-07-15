import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// Mock ai-readiness API client
vi.mock('@/lib/api/ai-readiness', () => ({
  aiReadinessAPI: {
    get: vi.fn(),
  },
}));

import { aiReadinessAPI } from '@/lib/api/ai-readiness';
import { AIReadinessCard } from '@/components/settings/AIReadinessCard';

const populatedResponse = {
  organization_id: 1,
  generated_at: '2026-07-10T00:00:00Z',
  feedback_volume: 340,
  corrections_total: 45,
  corrections_by_type: { sentiment: 30, category: 10, churn_risk: 5 },
  churn_labels_total: 120,
  churn_labels_trainable: 100,
  churn_labels_recovered: 8,
  churn_labels_by_reason: { price: 60, competitor: 40, other: 20 },
  churn_labels_by_source: { manual: 70, csv_import: 50 },
  pending_suggestions: 47,
  correction_volume_target: 200,
  churn_label_target: 500,
  correction_volume_ready: false,
  churn_labels_ready: false,
};

const readyResponse = {
  ...populatedResponse,
  corrections_total: 200,
  churn_labels_total: 500,
  churn_labels_trainable: 500,
  correction_volume_ready: true,
  churn_labels_ready: true,
};

const zeroResponse = {
  organization_id: 2,
  generated_at: '2026-07-10T00:00:00Z',
  feedback_volume: 0,
  corrections_total: 0,
  corrections_by_type: {},
  churn_labels_total: 0,
  churn_labels_trainable: 0,
  churn_labels_recovered: 0,
  churn_labels_by_reason: {},
  churn_labels_by_source: {},
  pending_suggestions: 0,
  correction_volume_target: 200,
  churn_label_target: 500,
  correction_volume_ready: false,
  churn_labels_ready: false,
};

describe('AIReadinessCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading skeleton while fetching data', () => {
    vi.mocked(aiReadinessAPI.get).mockReturnValue(new Promise(() => {}));

    render(<AIReadinessCard />);

    expect(screen.getByTestId('readiness-card-skeleton')).toBeInTheDocument();
  });

  it('renders feedback volume, corrections total and by-type breakdown when populated', async () => {
    vi.mocked(aiReadinessAPI.get).mockResolvedValue(populatedResponse);

    render(<AIReadinessCard />);

    await waitFor(() => {
      expect(screen.getByText('340')).toBeInTheDocument();
      expect(screen.getByText('45')).toBeInTheDocument();
      expect(screen.getByText('Sentiment')).toBeInTheDocument();
      expect(screen.getByText('30')).toBeInTheDocument();
    });
  });

  it('renders churn-labels total and by-reason breakdown when populated', async () => {
    vi.mocked(aiReadinessAPI.get).mockResolvedValue(populatedResponse);

    render(<AIReadinessCard />);

    await waitFor(() => {
      expect(screen.getByText('120')).toBeInTheDocument();
      expect(screen.getByText('price')).toBeInTheDocument();
      expect(screen.getByText('60')).toBeInTheDocument();
    });
  });

  it('shows not-ready badges when totals are below targets', async () => {
    vi.mocked(aiReadinessAPI.get).mockResolvedValue(populatedResponse);

    render(<AIReadinessCard />);

    await waitFor(() => {
      expect(screen.getAllByText(/not yet ready/i).length).toBeGreaterThan(0);
    });
  });

  it('shows ready badges when totals meet or exceed targets', async () => {
    vi.mocked(aiReadinessAPI.get).mockResolvedValue(readyResponse);

    render(<AIReadinessCard />);

    await waitFor(() => {
      expect(screen.getAllByText(/^ready$/i).length).toBeGreaterThan(0);
    });
  });

  it('renders an honest empty/zero state, not a blank card', async () => {
    vi.mocked(aiReadinessAPI.get).mockResolvedValue(zeroResponse);

    render(<AIReadinessCard />);

    await waitFor(() => {
      expect(screen.getByText(/no data yet/i)).toBeInTheDocument();
    });
  });

  it('shows an error state when the fetch fails', async () => {
    vi.mocked(aiReadinessAPI.get).mockRejectedValue(new Error('Network error'));

    render(<AIReadinessCard />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });

  it('renders trainable (not total) as the churn-labels progress number', async () => {
    vi.mocked(aiReadinessAPI.get).mockResolvedValue(populatedResponse);

    render(<AIReadinessCard />);

    await waitFor(() => {
      expect(screen.getByText(/Churn labels:\s*100\s*\/\s*500/i)).toBeInTheDocument();
    });
    // Never the total (120), and never trainable+pending (147)
    expect(screen.queryByText(/Churn labels:\s*120\s*\/\s*500/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Churn labels:\s*147\s*\/\s*500/i)).not.toBeInTheDocument();
  });

  it('renders pending CRM suggestions as a separate, non-gating line linking to /customers', async () => {
    vi.mocked(aiReadinessAPI.get).mockResolvedValue(populatedResponse);

    render(<AIReadinessCard />);

    await waitFor(() => {
      expect(screen.getByText(/47 CRM suggestions awaiting review/i)).toBeInTheDocument();
    });
    const link = screen.getByRole('link', { name: /47 CRM suggestions awaiting review/i });
    expect(link).toHaveAttribute('href', '/customers');
  });

  it('omits the pending-suggestions line when there are zero pending suggestions', async () => {
    vi.mocked(aiReadinessAPI.get).mockResolvedValue(zeroResponse);

    render(<AIReadinessCard />);

    await waitFor(() => {
      expect(screen.getByText(/no data yet/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/CRM suggestions awaiting review/i)).not.toBeInTheDocument();
  });
});
