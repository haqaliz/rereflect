import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// Mock the API client module — include real formatters so the component's
// non-mocked formatMetricPercent/formatDelta imports still work.
vi.mock('@/lib/api/embedding-accuracy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/embedding-accuracy')>();
  return {
    ...actual,
    getEmbeddingAccuracy: vi.fn(),
  };
});

import { getEmbeddingAccuracy } from '@/lib/api/embedding-accuracy';
import { RetrievalAccuracyCard } from '@/components/settings/RetrievalAccuracyCard';

function makeProviderResult(overrides = {}) {
  return {
    provider: 'ollama',
    model: 'nomic-embed-text',
    n: 69,
    n_pos: 45,
    n_neg: 24,
    recall_at_1: 0.08888888888888889,
    mrr: 0.7483597883597883,
    false_match_rate: 0.125,
    ...overrides,
  };
}

const noResultsResponse = {
  has_results: false,
  generated_at: null,
  threshold: null,
  n: null,
  n_positives: null,
  n_negatives: null,
  baseline: null,
  candidate: null,
  recall_at_1_delta: null,
  meets_target: null,
};

const winningResponse = {
  has_results: true,
  generated_at: '2026-07-25T01:17:41.783498+00:00',
  threshold: 0.85,
  n: 69,
  n_positives: 45,
  n_negatives: 24,
  baseline: makeProviderResult(),
  candidate: makeProviderResult({
    provider: 'local',
    model: 'BAAI/bge-small-en-v1.5',
    recall_at_1: 0.17777777777777778,
    mrr: 0.7468967452300785,
  }),
  recall_at_1_delta: 0.08888888888888889,
  meets_target: true,
};

const losingResponse = {
  ...winningResponse,
  candidate: makeProviderResult({
    provider: 'local',
    model: 'BAAI/bge-small-en-v1.5',
    recall_at_1: 0.05,
    mrr: 0.5,
  }),
  recall_at_1_delta: -0.038888888888888886,
  meets_target: false,
};

describe('RetrievalAccuracyCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading skeleton while the request is pending', () => {
    vi.mocked(getEmbeddingAccuracy).mockReturnValue(new Promise(() => {}));

    render(<RetrievalAccuracyCard />);

    expect(screen.getByTestId('retrieval-accuracy-skeleton')).toBeInTheDocument();
  });

  it('shows an honest "no eval results yet" empty state when has_results is false', async () => {
    vi.mocked(getEmbeddingAccuracy).mockResolvedValue(noResultsResponse);

    render(<RetrievalAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/no eval results yet/i)).toBeInTheDocument();
    });
    // no fabricated numbers
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('renders baseline/candidate recall@1, n, and a "beats nomic-embed-text baseline" badge when meets_target is true', async () => {
    vi.mocked(getEmbeddingAccuracy).mockResolvedValue(winningResponse);

    render(<RetrievalAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/9%/)).toBeInTheDocument(); // baseline recall@1 ~9%
      expect(screen.getByText(/18%/)).toBeInTheDocument(); // candidate recall@1 ~18%
      expect(screen.getByText(/n=69/)).toBeInTheDocument();
      expect(screen.getByText(/beats nomic-embed-text baseline/i)).toBeInTheDocument();
    });
  });

  it('renders an honest "does not currently beat baseline" badge when meets_target is false', async () => {
    vi.mocked(getEmbeddingAccuracy).mockResolvedValue(losingResponse);

    render(<RetrievalAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/does not currently beat baseline/i)).toBeInTheDocument();
      // the loss numbers are still rendered, not hidden
      expect(screen.getByText(/5%/)).toBeInTheDocument();
    });
  });
});
