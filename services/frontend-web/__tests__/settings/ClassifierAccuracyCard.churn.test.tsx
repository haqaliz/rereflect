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
    getClassifierVersions: vi.fn(),
    rollbackClassifier: vi.fn(),
    resumeClassifier: vi.fn(),
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import {
  getClassifierAccuracy,
  getClassifierVersions,
  rollbackClassifier,
  resumeClassifier,
} from '@/lib/api/classifier-accuracy';
import { ClassifierAccuracyCard } from '@/components/settings/ClassifierAccuracyCard';

const churnEmptyResponse = {
  model_kind: 'per-org TF-IDF + logistic regression',
  classifier_type: 'churn',
  has_model: false,
  label_count: 0,
  macro_f1: null,
  fit_at: null,
  is_ready: false,
  min_labels: 500,
  history: [],
  hold: false,
};

const churnPopulatedResponse = {
  model_kind: 'per-org TF-IDF + logistic regression',
  classifier_type: 'churn',
  has_model: true,
  label_count: 610,
  macro_f1: 0.64,
  fit_at: '2026-07-20T12:00:00Z',
  is_ready: true,
  min_labels: 500,
  hold: false,
  history: [
    {
      incumbent_macro_f1: 0.58,
      challenger_macro_f1: 0.64,
      macro_f1_delta: 0.06,
      decision: 'promoted',
      n: 55,
      created_at: '2026-07-19T12:00:00Z',
    },
    {
      incumbent_macro_f1: 0.6,
      challenger_macro_f1: 0.59,
      macro_f1_delta: -0.01,
      decision: 'retained',
      n: 41,
      created_at: '2026-07-12T12:00:00Z',
    },
  ],
};

const churnHeldResponse = {
  ...churnPopulatedResponse,
  hold: true,
};

const churnVersionsResponse = {
  classifier_type: 'churn',
  hold: false,
  versions: [
    {
      id: 3,
      fit_at: '2026-07-20T12:00:00Z',
      macro_f1: 0.64,
      label_count: 610,
      is_active: true,
    },
    {
      id: 2,
      fit_at: '2026-07-13T12:00:00Z',
      macro_f1: 0.57,
      label_count: 520,
      is_active: false,
    },
  ],
};

const churnHeldVersionsResponse = {
  ...churnVersionsResponse,
  hold: true,
  versions: [
    { ...churnVersionsResponse.versions[0], is_active: false },
    { ...churnVersionsResponse.versions[1], is_active: true },
  ],
};

const emptyVersionsResponse = {
  classifier_type: 'churn',
  hold: false,
  versions: [],
};

describe('ClassifierAccuracyCard — churn classifierType prop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getClassifierVersions).mockResolvedValue(emptyVersionsResponse);
  });

  it('fetches with classifierType="churn" when the prop is passed', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(churnEmptyResponse);

    render(<ClassifierAccuracyCard classifierType="churn" />);

    await waitFor(() => {
      expect(getClassifierAccuracy).toHaveBeenCalledWith('churn');
    });
    expect(getClassifierVersions).toHaveBeenCalledWith('churn');
  });

  it('header copy reflects "Churn model" and the incumbent provenance line', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(churnEmptyResponse);

    render(<ClassifierAccuracyCard classifierType="churn" />);

    await waitFor(() => {
      expect(screen.getByText(/churn model/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/sentiment/i)).toBeNull();
  });

  it('renders the honest "no model yet" empty state for churn with no fabricated numbers', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(churnEmptyResponse);

    render(<ClassifierAccuracyCard classifierType="churn" />);

    await waitFor(() => {
      expect(screen.getByText(/no model/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('renders the incumbent-vs-challenger payload: macro-F1, delta, n, decisions', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(churnPopulatedResponse);

    render(<ClassifierAccuracyCard classifierType="churn" />);

    await waitFor(() => {
      expect(screen.getAllByText(/64%/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Promoted')).toBeInTheDocument();
      expect(screen.getByText('Retained')).toBeInTheDocument();
      expect(screen.getByText(/n=55/)).toBeInTheDocument();
      expect(screen.getByText(/n=41/)).toBeInTheDocument();
      // the loss (negative delta) run is still rendered, not hidden
      expect(screen.getByText(/-0\.01/)).toBeInTheDocument();
      expect(screen.getByText(/610\/500/)).toBeInTheDocument();
    });
  });

  it('surfaces the hold banner and resume action for churn when hold is true', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(churnHeldResponse);
    vi.mocked(getClassifierVersions).mockResolvedValue(churnHeldVersionsResponse);

    render(<ClassifierAccuracyCard classifierType="churn" isAdminOrOwner />);

    await waitFor(() => {
      expect(screen.getByText(/auto-promotion paused/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /resume auto-promotion/i })).toBeInTheDocument();
    });
  });

  it('rollback with classifierType="churn" calls rollbackClassifier("churn", versionId)', async () => {
    const user = userEvent.setup();
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(churnPopulatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(churnVersionsResponse);
    vi.mocked(rollbackClassifier).mockResolvedValue(churnEmptyResponse);
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(churnEmptyResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(emptyVersionsResponse);

    render(<ClassifierAccuracyCard classifierType="churn" isAdminOrOwner />);

    const rollbackButtons = await screen.findAllByRole('button', { name: /roll back to this/i });
    await user.click(rollbackButtons[0]);

    const confirmButton = await screen.findByRole('button', { name: /confirm rollback/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(rollbackClassifier).toHaveBeenCalledWith('churn', churnVersionsResponse.versions[1].id);
    });
  });

  it('resume with classifierType="churn" calls resumeClassifier("churn")', async () => {
    const user = userEvent.setup();
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(churnHeldResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(churnHeldVersionsResponse);
    vi.mocked(resumeClassifier).mockResolvedValue(churnPopulatedResponse);
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(churnPopulatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(churnVersionsResponse);

    render(<ClassifierAccuracyCard classifierType="churn" isAdminOrOwner />);

    const resumeButton = await screen.findByRole('button', { name: /resume auto-promotion/i });
    await user.click(resumeButton);

    const confirmButton = await screen.findByRole('button', { name: /confirm resume/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(resumeClassifier).toHaveBeenCalledWith('churn');
    });
  });
});
