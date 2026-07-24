import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { toast } from 'sonner';

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
  hold: false,
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
  hold: false,
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

const heldResponse = {
  ...populatedResponse,
  hold: true,
};

const emptyVersionsResponse = {
  classifier_type: 'sentiment',
  hold: false,
  versions: [],
};

const versionsResponse = {
  classifier_type: 'sentiment',
  hold: false,
  versions: [
    {
      id: 3,
      fit_at: '2026-07-10T12:00:00Z',
      macro_f1: 0.71,
      label_count: 140,
      is_active: true,
    },
    {
      id: 2,
      fit_at: '2026-06-25T12:00:00Z',
      macro_f1: 0.58,
      label_count: 90,
      is_active: false,
    },
    {
      id: 1,
      fit_at: '2026-06-01T12:00:00Z',
      macro_f1: 0.5,
      label_count: 40,
      is_active: false,
    },
  ],
};

const heldVersionsResponse = {
  ...versionsResponse,
  hold: true,
  versions: [
    { ...versionsResponse.versions[0], is_active: false },
    { ...versionsResponse.versions[1], is_active: true },
    versionsResponse.versions[2],
  ],
};

describe('ClassifierAccuracyCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getClassifierVersions).mockResolvedValue(emptyVersionsResponse);
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

  it('calls rollbackClassifier and refreshes when a "Roll back to this" action is confirmed', async () => {
    const user = userEvent.setup();
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(populatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(versionsResponse);
    vi.mocked(rollbackClassifier).mockResolvedValue(emptyResponse);
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(emptyResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(emptyVersionsResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    const rollbackButtons = await screen.findAllByRole('button', { name: /roll back to this/i });
    await user.click(rollbackButtons[0]);

    const confirmButton = await screen.findByRole('button', { name: /confirm rollback/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(rollbackClassifier).toHaveBeenCalledWith('sentiment', versionsResponse.versions[1].id);
      expect(toast.success).toHaveBeenCalled();
      expect(screen.getByText(/no model/i)).toBeInTheDocument();
    });
  });
});

describe('ClassifierAccuracyCard — category classifierType prop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getClassifierVersions).mockResolvedValue(emptyVersionsResponse);
  });

  it('fetches with classifierType="category" when the prop is passed', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(emptyResponse);

    render(<ClassifierAccuracyCard classifierType="category" />);

    await waitFor(() => {
      expect(getClassifierAccuracy).toHaveBeenCalledWith('category');
    });
  });

  it('header copy reflects "Category" and never mentions "sentiment"', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(emptyResponse);

    render(<ClassifierAccuracyCard classifierType="category" />);

    await waitFor(() => {
      expect(screen.getAllByText(/category/i).length).toBeGreaterThan(0);
    });
    expect(screen.queryByText(/sentiment/i)).toBeNull();
  });

  it('carries the required fair-A/B honesty disclosure when populated', async () => {
    // Fixture's classifier_type field is left 'sentiment' intentionally — the component
    // never reads that field back, only the classifierType prop it was given.
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);

    render(<ClassifierAccuracyCard classifierType="category" />);

    await waitFor(() => {
      expect(screen.getByText(/beats the keyword categorizer/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/labels the keyword categorizer can produce/i)).toBeInTheDocument();
  });

  it('renders the honest "no model yet" empty state for category with no fabricated numbers', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue({ ...emptyResponse, classifier_type: 'category' });

    render(<ClassifierAccuracyCard classifierType="category" />);

    await waitFor(() => {
      expect(screen.getByText(/no model/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/category corrections/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('renders the not-ready state identically for category (label_count/min_labels)', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(notReadyResponse);

    render(<ClassifierAccuracyCard classifierType="category" />);

    await waitFor(() => {
      expect(screen.getByText(/12\s*\/\s*20/)).toBeInTheDocument();
    });
  });

  it('renders the populated state identically for category (macro-F1, decisions, runs)', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);

    render(<ClassifierAccuracyCard classifierType="category" />);

    await waitFor(() => {
      expect(screen.getAllByText(/71%/).length).toBeGreaterThanOrEqual(1);
      // Exact case-sensitive match — the decision label "Promoted" is distinct from the
      // lowercase "promoted" that appears inside the fair-A/B honesty disclosure copy.
      expect(screen.getByText('Promoted')).toBeInTheDocument();
      expect(screen.getByText('Retained')).toBeInTheDocument();
    });
  });

  it('rollback with classifierType="category" calls rollbackClassifier("category", versionId)', async () => {
    const user = userEvent.setup();
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(populatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(versionsResponse);
    vi.mocked(rollbackClassifier).mockResolvedValue(emptyResponse);
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(emptyResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(emptyVersionsResponse);

    render(<ClassifierAccuracyCard classifierType="category" isAdminOrOwner />);

    const rollbackButtons = await screen.findAllByRole('button', { name: /roll back to this/i });
    await user.click(rollbackButtons[0]);

    const confirmButton = await screen.findByRole('button', { name: /confirm rollback/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(rollbackClassifier).toHaveBeenCalledWith('category', versionsResponse.versions[1].id);
    });
  });
});

describe('ClassifierAccuracyCard — urgency classifierType prop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getClassifierVersions).mockResolvedValue(emptyVersionsResponse);
  });

  it('fetches with classifierType="urgency" when the prop is passed', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(emptyResponse);

    render(<ClassifierAccuracyCard classifierType="urgency" />);

    await waitFor(() => {
      expect(getClassifierAccuracy).toHaveBeenCalledWith('urgency');
    });
  });

  it('header copy reflects "Urgency" and never mentions "sentiment"', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(emptyResponse);

    render(<ClassifierAccuracyCard classifierType="urgency" />);

    await waitFor(() => {
      expect(screen.getAllByText(/urgency/i).length).toBeGreaterThan(0);
    });
    expect(screen.queryByText(/sentiment/i)).toBeNull();
  });

  it('carries the required honesty disclosure: beats the keyword urgency heuristic', async () => {
    // Fixture's classifier_type field is left 'sentiment' intentionally — the component
    // never reads that field back, only the classifierType prop it was given.
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);

    render(<ClassifierAccuracyCard classifierType="urgency" />);

    await waitFor(() => {
      expect(screen.getByText(/beats the keyword urgency heuristic/i)).toBeInTheDocument();
    });
  });

  it('discloses that auto mode is add-only (escalates, never de-escalates)', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);

    render(<ClassifierAccuracyCard classifierType="urgency" />);

    await waitFor(() => {
      expect(screen.getByText(/never de-escalates/i)).toBeInTheDocument();
    });
  });

  it('renders the honest "no model yet" empty state for urgency with no fabricated numbers', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue({ ...emptyResponse, classifier_type: 'urgency' });

    render(<ClassifierAccuracyCard classifierType="urgency" />);

    await waitFor(() => {
      expect(screen.getByText(/no model/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/urgency corrections/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('renders the not-ready state identically for urgency (label_count/min_labels)', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(notReadyResponse);

    render(<ClassifierAccuracyCard classifierType="urgency" />);

    await waitFor(() => {
      expect(screen.getByText(/12\s*\/\s*20/)).toBeInTheDocument();
    });
  });

  it('renders the populated state identically for urgency (macro-F1, decisions, runs)', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);

    render(<ClassifierAccuracyCard classifierType="urgency" />);

    await waitFor(() => {
      expect(screen.getAllByText(/71%/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Promoted')).toBeInTheDocument();
      expect(screen.getByText('Retained')).toBeInTheDocument();
    });
  });

  it('rollback with classifierType="urgency" calls rollbackClassifier("urgency", versionId)', async () => {
    const user = userEvent.setup();
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(populatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(versionsResponse);
    vi.mocked(rollbackClassifier).mockResolvedValue(emptyResponse);
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(emptyResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(emptyVersionsResponse);

    render(<ClassifierAccuracyCard classifierType="urgency" isAdminOrOwner />);

    const rollbackButtons = await screen.findAllByRole('button', { name: /roll back to this/i });
    await user.click(rollbackButtons[0]);

    const confirmButton = await screen.findByRole('button', { name: /confirm rollback/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(rollbackClassifier).toHaveBeenCalledWith('urgency', versionsResponse.versions[1].id);
    });
  });
});

describe('ClassifierAccuracyCard — version history table', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a version-history table with an Active badge on the active row and no rollback action on it', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValue(versionsResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    await waitFor(() => {
      expect(screen.getByText(/active/i)).toBeInTheDocument();
    });
    // 2 inactive versions -> 2 "Roll back to this" actions, none on the active row.
    const rollbackButtons = screen.getAllByRole('button', { name: /roll back to this/i });
    expect(rollbackButtons).toHaveLength(2);
  });

  it('renders the table read-only (no rollback actions) when isAdminOrOwner is false, but the table stays visible', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValue(versionsResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner={false} />);

    await waitFor(() => {
      expect(screen.getByText(/active/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /roll back to this/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /resume auto-promotion/i })).toBeNull();
  });

  it('error path toasts the FastAPI detail when rollback fails', async () => {
    const user = userEvent.setup();
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValue(versionsResponse);
    vi.mocked(rollbackClassifier).mockRejectedValue({
      response: { data: { detail: 'Version already active.' } },
    });

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    const rollbackButtons = await screen.findAllByRole('button', { name: /roll back to this/i });
    await user.click(rollbackButtons[0]);

    const confirmButton = await screen.findByRole('button', { name: /confirm rollback/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Version already active.');
    });
  });

  it('caps the visible rows so the card stays compact even with many versions', async () => {
    const manyVersions = {
      classifier_type: 'sentiment',
      hold: false,
      versions: Array.from({ length: 15 }, (_, i) => ({
        id: 15 - i,
        fit_at: `2026-0${(i % 9) + 1}-01T12:00:00Z`,
        macro_f1: 0.5,
        label_count: 30,
        is_active: i === 0,
      })),
    };
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValue(manyVersions);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    await waitFor(() => {
      expect(screen.getAllByRole('row').length).toBeLessThanOrEqual(11); // header + <=10 rows
    });
  });
});

describe('ClassifierAccuracyCard — hold / resume', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders "Auto-promotion paused" + Resume button when hold is true', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(heldResponse);
    vi.mocked(getClassifierVersions).mockResolvedValue(heldVersionsResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    await waitFor(() => {
      expect(screen.getByText(/auto-promotion paused/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /resume auto-promotion/i })).toBeInTheDocument();
    });
  });

  it('does not render the hold indicator when hold is false', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue(populatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValue(versionsResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    await waitFor(() => {
      expect(screen.getAllByText(/71%/).length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByText(/auto-promotion paused/i)).toBeNull();
  });

  it('Resume opens a confirm dialog; confirming calls resumeClassifier and refetches', async () => {
    const user = userEvent.setup();
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(heldResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(heldVersionsResponse);
    vi.mocked(resumeClassifier).mockResolvedValue(populatedResponse);
    vi.mocked(getClassifierAccuracy).mockResolvedValueOnce(populatedResponse);
    vi.mocked(getClassifierVersions).mockResolvedValueOnce(versionsResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    const resumeButton = await screen.findByRole('button', { name: /resume auto-promotion/i });
    await user.click(resumeButton);

    const confirmButton = await screen.findByRole('button', { name: /confirm resume/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(resumeClassifier).toHaveBeenCalledWith('sentiment');
      expect(toast.success).toHaveBeenCalled();
      expect(screen.queryByText(/auto-promotion paused/i)).toBeNull();
    });
  });

  it('error path toasts the FastAPI detail when resume fails', async () => {
    const user = userEvent.setup();
    vi.mocked(getClassifierAccuracy).mockResolvedValue(heldResponse);
    vi.mocked(getClassifierVersions).mockResolvedValue(heldVersionsResponse);
    vi.mocked(resumeClassifier).mockRejectedValue({
      response: { data: { detail: 'Not allowed.' } },
    });

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    const resumeButton = await screen.findByRole('button', { name: /resume auto-promotion/i });
    await user.click(resumeButton);

    const confirmButton = await screen.findByRole('button', { name: /confirm resume/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Not allowed.');
    });
  });

  it('S1 nudge: shows a resume prompt with the positive delta when held and the latest run beat the held version', async () => {
    const heldWithPositiveDelta = {
      ...heldResponse,
      history: [
        {
          incumbent_macro_f1: 0.6,
          challenger_macro_f1: 0.68,
          macro_f1_delta: 0.08,
          decision: 'held',
          n: 30,
          created_at: '2026-07-15T12:00:00Z',
        },
        ...heldResponse.history,
      ],
    };
    vi.mocked(getClassifierAccuracy).mockResolvedValue(heldWithPositiveDelta);
    vi.mocked(getClassifierVersions).mockResolvedValue(heldVersionsResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    await waitFor(() => {
      expect(screen.getByText(/would beat your held version/i)).toBeInTheDocument();
      expect(screen.getByText(/\+8%/)).toBeInTheDocument();
    });
  });

  it('S1 nudge: does not render when the latest run has a non-positive delta', async () => {
    const heldWithNegativeDelta = {
      ...heldResponse,
      history: [
        {
          incumbent_macro_f1: 0.6,
          challenger_macro_f1: 0.52,
          macro_f1_delta: -0.08,
          decision: 'held',
          n: 30,
          created_at: '2026-07-15T12:00:00Z',
        },
        ...heldResponse.history,
      ],
    };
    vi.mocked(getClassifierAccuracy).mockResolvedValue(heldWithNegativeDelta);
    vi.mocked(getClassifierVersions).mockResolvedValue(heldVersionsResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    await waitFor(() => {
      expect(screen.getByText(/auto-promotion paused/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/would beat your held version/i)).toBeNull();
  });

  it('S1 nudge: degrades gracefully (no crash, no nudge) when history is empty', async () => {
    vi.mocked(getClassifierAccuracy).mockResolvedValue({ ...heldResponse, history: [] });
    vi.mocked(getClassifierVersions).mockResolvedValue(heldVersionsResponse);

    render(<ClassifierAccuracyCard isAdminOrOwner />);

    await waitFor(() => {
      expect(screen.getByText(/auto-promotion paused/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/would beat your held version/i)).toBeNull();
  });
});
