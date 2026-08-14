import apiClient from '../api-client';

/**
 * Types + client for GET /api/v1/settings/ai/churn/label-gate
 * (churn-label-gate-study aspect 2, M5.3 disclosure layer).
 *
 * Mirrors the backend's ChurnLabelGateResponse schema 1:1
 * (src/schemas/churn_label_gate.py). This is a disclosure card, not a
 * gated premium feature — kept self-contained per the existing precedent of
 * independent lib/api/*.ts modules (see lib/api/sentiment-accuracy.ts).
 */

export interface GateCurvePoint {
  label_volume: number;
  challenger_macro_f1: number;
  incumbent_macro_f1: number;
  macro_f1_delta: number;
  delta_ci_low: number;
  delta_ci_high: number;
  promotion_rate: number;
}

export interface FidelitySensitivity {
  missing_fraction: number;
  crossover_label_volume: number | null;
  curves: GateCurvePoint[];
}

export interface ChurnLabelGateResponse {
  has_results: boolean;
  artifact_version: string | null;
  generated_at: string | null;
  verdict: string | null;
  target: number | null;
  method: string | null;
  n_simulations: number | null;
  crossover_label_volume: number | null;
  fidelity_sensitivity: FidelitySensitivity | null;
  honest_limits: string[] | null;
  curves: GateCurvePoint[] | null;
}

/** Human-readable verdict label for the machine verdict string. */
export function verdictLabel(verdict: string | null): string {
  switch (verdict) {
    case 'keep_500':
      return 'Keep 500 labels';
    case 'no_defensible_gate':
      return 'No defensible gate';
    default:
      if (verdict?.startsWith('raise_to_')) {
        return `Raise to ${verdict.replace('raise_to_', '')} labels`;
      }
      // Unknown machine slug — show it raw rather than fabricate a meaning.
      return verdict ?? 'Study not run';
  }
}

/** Fetch the churn label-gate study verdict (no plan-gating — disclosure feature). */
export async function getChurnLabelGate(): Promise<ChurnLabelGateResponse> {
  const response = await apiClient.get<ChurnLabelGateResponse>(
    '/api/v1/settings/ai/churn/label-gate'
  );
  return response.data;
}
