import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import { getChurnLabelGate, verdictLabel } from '@/lib/api/churn-label-gate';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;

const keepVerdictPayload = {
  has_results: true,
  artifact_version: '1',
  generated_at: '2026-08-14T00:00:00Z',
  verdict: 'keep_500',
  target: 500,
  method: 'simulated learning curves',
  n_simulations: 50,
  crossover_label_volume: 200,
  fidelity_sensitivity: {
    missing_fraction: 0.25,
    crossover_label_volume: 200,
    curves: [],
  },
  honest_limits: ['Simulation is a bound, not a measurement.'],
  curves: [],
};

describe('getChurnLabelGate', () => {
  beforeEach(() => vi.clearAllMocks());

  it('GETs /api/v1/settings/ai/churn/label-gate and round-trips the verdict payload', async () => {
    mockGet.mockResolvedValue({ data: keepVerdictPayload });

    const result = await getChurnLabelGate();

    expect(mockGet).toHaveBeenCalledWith('/api/v1/settings/ai/churn/label-gate');
    expect(result.has_results).toBe(true);
    expect(result.verdict).toBe('keep_500');
    expect(result.target).toBe(500);
    expect(result.crossover_label_volume).toBe(200);
    expect(result.honest_limits).toEqual(['Simulation is a bound, not a measurement.']);
  });

  it('passes through the absent-artifact empty state shape', async () => {
    const empty = {
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
    mockGet.mockResolvedValue({ data: empty });

    const result = await getChurnLabelGate();

    expect(result.has_results).toBe(false);
    expect(result.verdict).toBeNull();
    expect(result.target).toBeNull();
  });
});

describe('verdictLabel', () => {
  it('maps the keep/raise/no-gate machine verdicts to readable labels', () => {
    expect(verdictLabel('keep_500')).toBe('Keep 500 labels');
    expect(verdictLabel('raise_to_800')).toBe('Raise to 800 labels');
    expect(verdictLabel('no_defensible_gate')).toBe('No defensible gate');
    expect(verdictLabel(null)).toBe('Study not run');
  });
});
