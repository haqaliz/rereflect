import apiClient from '../api-client';

/**
 * Types + client for GET /api/v1/settings/ai/classifier/accuracy and
 * POST /api/v1/settings/ai/classifier/rollback
 * (settings-api-and-accuracy-card aspect, M5.2).
 *
 * Mirrors the backend's ClassifierAccuracyResponse schema 1:1
 * (src/schemas/classifier_accuracy.py). Disclosure card, not a gated
 * premium feature — self-contained per lib/api/sentiment-accuracy.ts's
 * precedent.
 */

export interface ClassifierEvalRunSummary {
  incumbent_macro_f1: number | null;
  challenger_macro_f1: number | null;
  macro_f1_delta: number | null;
  decision: string;
  n: number | null;
  created_at: string;
}

export interface ClassifierAccuracyResponse {
  model_kind: string;
  classifier_type: string;
  has_model: boolean;
  label_count: number;
  macro_f1: number | null;
  fit_at: string | null;
  is_ready: boolean;
  min_labels: number;
  history: ClassifierEvalRunSummary[];
}

/** Format a 0-1 metric fraction as a whole-number percent string, "—" for null. */
export function formatMetricPercent(n: number | null): string {
  if (n === null) return '—';
  return `${Math.round(n * 100)}%`;
}

/** Format a signed macro-F1 delta (challenger - incumbent), "—" for null. */
export function formatDelta(delta: number | null): string {
  if (delta === null) return '—';
  const sign = delta >= 0 ? '+' : '-';
  return `${sign}${Math.abs(delta).toFixed(2)}`;
}

/** Fetch the per-org corrections-classifier accuracy card data (no plan-gating — disclosure feature). */
export async function getClassifierAccuracy(
  classifierType: string = 'sentiment'
): Promise<ClassifierAccuracyResponse> {
  const response = await apiClient.get<ClassifierAccuracyResponse>(
    `/api/v1/settings/ai/classifier/accuracy?classifier_type=${classifierType}`
  );
  return response.data;
}

/** Roll back the org's active classifier model (reactivate prior version, or disable). Admin/owner only. */
export async function rollbackClassifier(
  classifierType: string = 'sentiment'
): Promise<ClassifierAccuracyResponse> {
  const response = await apiClient.post<ClassifierAccuracyResponse>(
    `/api/v1/settings/ai/classifier/rollback?classifier_type=${classifierType}`
  );
  return response.data;
}
