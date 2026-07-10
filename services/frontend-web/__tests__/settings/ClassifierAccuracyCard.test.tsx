import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// Mock the API client module — include real formatters so the component's
// non-mocked formatMetricPercent/formatDelta imports still work.
vi.mock('@/lib/api/classifier-accuracy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/classifier-accuracy')>();
  return {
    ...actual,
    getClassifierAccuracy: vi.fn(),
    rollbackClassifier: vi.fn(),
  };
});

import { getClassifierAccuracy, rollbackClassifier } from '@/lib/api/classifier-accuracy';
import { ClassifierAccuracyCard } from '@/components/settings/ClassifierAccuracyCard';

const emptyResponse = {
  model_kind: 'per-org TF-IDF + logistic regression',
  classifier_type: 'sentiment',
  has_model: false,
  label_count: 0,
  macro_f1: null,
  fit_at: null,
  is_ready: false,
  min_labels: 20,
  history: [],
};

const notReadyResponse = {
  ...emptyResponse,
  has_model: true,
  label_count: 12,
};

const populatedResponse = {
  model_kind: 'per-org TF-IDF + logistic regression',
  classifier_type: 'sentiment',
  has_model: true,
  label_count: 140,
  macro_f1: 0.71,
  fit_at: '2026-07-10T12:00:00Z',
  is_ready: true,
  min_labels: 20,
  history: [
    {
      incumbent_macro_f1: 0.65,
      challenger_macro_f1: 0.71,
      macro_f1_delta: 0.06,
      decision: 'promoted',
      n: 40,
      created_at: '2026-07-08T12:00:00Z',
    },
    {
      incumbent_macro_f1: 0.58,
      challenger_macro_f1: 0.55,
      macro_f1_delta: -0.03,
      decision: 'retained',
      n: 20,
      created_at: '2026-06-25T12:00:00Z',
    },
  ],
};

describe('ClassifierAccuracyCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading skeleton while the request is pending', () => {
    vi.mocked(getClassifierAccuracy).mockReturnValue(new Promise(() => {}));

    render(<ClassifierAccuracyCard />);

    expect(screen.getByTestId('classifier-accuracy-skeleton')).toBeInTheDocument();
  });

  it('shows an error state on API rejection', async () => {
    vi.mocked(getClassifierAccuracy).mockRejectedValue(new Error('network error'));

    render(<ClassifierAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });

  it('shows an honest "no model yet" empty state when has_model is false, with no fabricated numbers', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(emptyResponse);

    render(<ClassifierAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/no model/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('shows a not-ready state with label_count/min_labels when is_ready is false and has_model is true', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(notReadyResponse);

    render(<ClassifierAccuracyCard />);

    await waitFor(() => {
      expect(screen.getByText(/12\s*\/\s*20/)).toBeInTheDocument();
    });
  });

  it('renders macro-F1, delta, n, and last-N runs (with decision labels) when populated', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);

    render(<ClassifierAccuracyCard />);

    await waitFor(() => {
      // 71% appears twice: the summary macro-F1 and the first run's challenger_macro_f1.
      expect(screen.getAllByText(/71%/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/promoted/i)).toBeInTheDocument();
      expect(screen.getByText(/retained/i)).toBeInTheDocument();
      expect(screen.getByText(/n=40/)).toBeInTheDocument();
      expect(screen.getByText(/n=20/)).toBeInTheDocument();
      // the loss (negative delta) run is still rendered, not hidden
      expect(screen.getByText(/-0\.03/)).toBeInTheDocument();
    });
  });

  it('calls rollbackClassifier and refreshes when the Roll back action is used', async () => {
    const user = userEvent.setup();
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(populatedResponse);
    vi.mocked(rollbackClassifier).mockResolvedValue(emptyResponse);
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(emptyResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    const rollbackButton = await screen.findByRole('button', { name: /roll back/i });
    await user.click(rollbackButton);

    await waitFor(() => {
      expect(rollbackClassifier).toHaveBeenCalled();
      expect(screen.getByText(/no model/i)).toBeInTheDocument();
    });
  });
});
