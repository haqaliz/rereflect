import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// Mock the API client module — include real helpers so the component's
// non-mocked verdictLabel import still works.
vi.mock('@/lib/api/churn-label-gate', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/churn-label-gate')>();
  return {
    ...actual,
    getChurnLabelGate: vi.fn(),
  };
});

import { getChurnLabelGate } from '@/lib/api/churn-label-gate';
import { ChurnLabelGateCard } from '@/components/settings/ChurnLabelGateCard';

const noResultsResponse = {
  has_results: false,
  artifact_version: null,
  generated_at: null,
  verdict: null,
  target: null,
  method: null,
  n_simulations: null,
  crossover_label_volume: null,
  fidelity_sensitivity: null,
  honest_limits: null,
  curves: null,
};

const keepVerdictResponse = {
  has_results: true,
  artifact_version: '1',
  generated_at: '2026-08-14T00:00:00Z',
  verdict: 'keep_500',
  target: 500,
  method: 'simulated learning curves: per-org logistic challenger vs calibrated-heuristic incumbent',
  n_simulations: 50,
  crossover_label_volume: 200,
  fidelity_sensitivity: {
    missing_fraction: 0.25,
    crossover_label_volume: 200,
    curves: [],
  },
  honest_limits: [
    'Simulation is a bound, not a measurement: no real org is at label volume.',
    'At the crossover volume of 200 labels, 57% of pooled simulated orgs cleared the +0.02 macro-F1 promotion bar on a single run — below 80%, so a consecutive-runs promotion rule is suggested (PRD OQ2).',
  ],
  curves: [],
};

const noGateResponse = {
  ...keepVerdictResponse,
  verdict: 'no_defensible_gate',
  target: null,
  crossover_label_volume: null,
  fidelity_sensitivity: { missing_fraction: 0.25, crossover_label_volume: null, curves: [] },
};

describe('ChurnLabelGateCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading skeleton while the request is pending', () => {
    vi.mocked(getChurnLabelGate).mockReturnValue(new Promise(() => {}));

    render(<ChurnLabelGateCard />);

    expect(screen.getByTestId('churn-label-gate-skeleton')).toBeInTheDocument();
  });

  it('shows an error state on API rejection', async () => {
    vi.mocked(getChurnLabelGate).mockRejectedValue(new Error('network error'));

    render(<ChurnLabelGateCard />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });

  it('shows an honest "study not run yet" empty state when has_results is false', async () => {
    vi.mocked(getChurnLabelGate).mockResolvedValue(noResultsResponse);

    render(<ChurnLabelGateCard />);

    await waitFor(() => {
      expect(screen.getByText(/study not run yet/i)).toBeInTheDocument();
    });
    // no fabricated verdict numbers
    expect(screen.queryByText(/labels/)).toBeNull();
  });

  it('renders the verdict, target, crossover, n, and honest-limits lines from a keep_500 payload', async () => {
    vi.mocked(getChurnLabelGate).mockResolvedValue(keepVerdictResponse);

    render(<ChurnLabelGateCard />);

    await waitFor(() => {
      expect(screen.getByText(/keep 500 labels/i)).toBeInTheDocument();
      expect(screen.getByText('500 labels')).toBeInTheDocument(); // activation gate row
      // crossover row + "with 25% missing snapshots" row are both 200 in this fixture
      expect(screen.getAllByText('200 labels')).toHaveLength(2);
      expect(screen.getByText(/n=50 simulations/)).toBeInTheDocument();
      expect(screen.getByText(/simulation is a bound, not a measurement/i)).toBeInTheDocument();
      expect(screen.getByText(/consecutive-runs promotion rule is suggested/i)).toBeInTheDocument();
      expect(screen.getByText(/25% missing snapshots/i)).toBeInTheDocument();
    });
  });

  it('renders the "no defensible gate" verdict state plainly', async () => {
    vi.mocked(getChurnLabelGate).mockResolvedValue(noGateResponse);

    render(<ChurnLabelGateCard />);

    await waitFor(() => {
      expect(screen.getByText(/no defensible gate/i)).toBeInTheDocument();
      expect(screen.getAllByText(/never/).length).toBeGreaterThan(0); // both crossovers "never"
    });
  });
});
