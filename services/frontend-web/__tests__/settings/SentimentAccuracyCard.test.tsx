import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// Mock the API client module — include real formatters so the component's
// non-mocked formatMetricPercent/formatDelta imports still work.
vi.mock('@/lib/api/sentiment-accuracy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/sentiment-accuracy')>();
  return {
    ...actual,
    getSentimentAccuracy: vi.fn(),
  };
});

import { getSentimentAccuracy } from '@/lib/api/sentiment-accuracy';
import { SentimentAccuracyCard } from '@/components/settings/SentimentAccuracyCard';

const perClass = {
  positive: { precision: 0.8, recall: 0.75, f1: 0.77, support: 60 },
  neutral: { precision: 0.6, recall: 0.6, f1: 0.6, support: 60 },
  negative: { precision: 0.7, recall: 0.7, f1: 0.7, support: 60 },
};

function makeProviderResult(overrides = {}) {
  return {
    provider: 'vader',
    n: 180,
    macro_precision: 0.7,
    macro_recall: 0.68,
    macro_f1: 0.69,
    accuracy: 0.7,
    per_class: perClass,
    confusion_matrix: {},
    ...overrides,
  };
}

const noResultsResponse = {
  has_results: false,
  generated_at: null,
  model_id: null,
  model_revision: null,
  public: null,
  in_domain: null,
};

const winningResponse = {
  has_results: true,
  generated_at: '2026-07-10T12:00:00Z',
  model_id: 'cardiffnlp/twitter-roberta-base-sentiment-latest',
  model_revision: 'main',
  public: {
    set_name: 'public',
    n: 180,
    vader: makeProviderResult({ provider: 'vader', macro_f1: 0.69 }),
    transformer: makeProviderResult({ provider: 'transformer', macro_f1: 0.79 }),
    macro_f1_delta: 0.1,
    meets_target: null,
  },
  in_domain: {
    set_name: 'in_domain',
    n: 169,
    vader: makeProviderResult({ provider: 'vader', macro_f1: 0.53, n: 169 }),
    transformer: makeProviderResult({ provider: 'transformer', macro_f1: 0.59, n: 169 }),
    macro_f1_delta: 0.06,
    meets_target: true,
  },
};

const losingResponse = {
  ...winningResponse,
  in_domain: {
    ...winningResponse.in_domain,
    transformer: makeProviderResult({ provider: 'transformer', macro_f1: 0.5, n: 169 }),
    macro_f1_delta: -0.03,
    meets_target: false,
  },
};

const transformerNotEvaluatedResponse = {
  ...winningResponse,
  public: {
    ...winningResponse.public,
    transformer: null,
    macro_f1_delta: null,
    meets_target: null,
  },
};

describe('SentimentAccuracyCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading skeleton while the request is pending', () => {
    vi.mocked(getSentimentAccuracy).mockReturnValue(new Promise(() => {}));

    render(<SentimentAccuracyCard />);

    expect(screen.getByTestId('sentiment-accuracy-skeleton')).toBeInTheDocument();
  });

  it('shows an error state on API rejection', async () => {
    vi.mocked(getSentimentAccuracy).mockRejectedValue(new Error('network error'));

    render(<SentimentAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });

  it('shows an honest "not run yet" empty state when has_results is false', async () => {
    vi.mocked(getSentimentAccuracy).mockResolvedValue(noResultsResponse);

    render(<SentimentAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/not.*run yet|no eval results yet/i)).toBeInTheDocument();
    });
    // no fabricated numbers
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('renders both providers macro-F1, n, and a "beats VADER" badge when meets_target is true', async () => {
    vi.mocked(getSentimentAccuracy).mockResolvedValue(winningResponse);

    render(<SentimentAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/69%/)).toBeInTheDocument(); // public vader macro-F1
      expect(screen.getByText(/79%/)).toBeInTheDocument(); // public transformer macro-F1
      expect(screen.getByText(/53%/)).toBeInTheDocument(); // in-domain vader macro-F1
      expect(screen.getByText(/59%/)).toBeInTheDocument(); // in-domain transformer macro-F1
      expect(screen.getByText(/n=180/)).toBeInTheDocument();
      expect(screen.getByText(/n=169/)).toBeInTheDocument();
      expect(screen.getByText(/beats vader/i)).toBeInTheDocument();
    });
  });

  it('renders an honest "does not currently beat VADER" badge when meets_target is false', async () => {
    vi.mocked(getSentimentAccuracy).mockResolvedValue(losingResponse);

    render(<SentimentAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/does not (currently )?beat vader/i)).toBeInTheDocument();
      // the loss numbers are still rendered, not hidden
      expect(screen.getByText(/50%/)).toBeInTheDocument(); // losing transformer macro-F1
    });
  });

  it('renders VADER-only with a "transformer not evaluated" note when transformer is null for a set', async () => {
    vi.mocked(getSentimentAccuracy).mockResolvedValue(transformerNotEvaluatedResponse);

    render(<SentimentAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/transformer not evaluated/i)).toBeInTheDocument();
      expect(screen.getByText(/69%/)).toBeInTheDocument(); // public vader still shown
    });
  });
});
