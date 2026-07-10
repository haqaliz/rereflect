import apiClient from '../api-client';

/**
 * Types + client for GET /api/v1/settings/ai/sentiment/accuracy
 * (eval-harness-and-card aspect, M5.1 disclosure layer).
 *
 * Mirrors the backend's SentimentAccuracyResponse schema 1:1
 * (src/schemas/sentiment_accuracy.py). This is a disclosure card, not a
 * gated premium feature — kept self-contained per the existing precedent of
 * independent lib/api/*.ts modules (see lib/api/churn-accuracy.ts).
 */

export interface ClassMetrics {
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface ProviderEvalResult {
  provider: string;
  n: number;
  macro_precision: number;
  macro_recall: number;
  macro_f1: number;
  accuracy: number;
  per_class: Record<string, ClassMetrics>;
  confusion_matrix: Record<string, Record<string, number>>;
}

export interface EvalSetResult {
  set_name: string;
  n: number;
  vader: ProviderEvalResult | null;
  transformer: ProviderEvalResult | null;
  macro_f1_delta: number | null;
  meets_target: boolean | null;
}

export interface SentimentAccuracyResponse {
  has_results: boolean;
  generated_at: string | null;
  model_id: string | null;
  model_revision: string | null;
  public: EvalSetResult | null;
  in_domain: EvalSetResult | null;
}

/** Format a 0-1 metric fraction as a whole-number percent string, "—" for null. */
export function formatMetricPercent(n: number | null): string {
  if (n === null) return '—';
  return `${Math.round(n * 100)}%`;
}

/** Format a signed macro-F1 delta (transformer - vader), "—" for null. */
export function formatDelta(delta: number | null): string {
  if (delta === null) return '—';
  const sign = delta >= 0 ? '+' : '-';
  return `${sign}${Math.abs(delta).toFixed(2)}`;
}

/** Fetch the sentiment eval accuracy card data (no plan-gating — disclosure feature). */
export async function getSentimentAccuracy(): Promise<SentimentAccuracyResponse> {
  const response = await apiClient.get<SentimentAccuracyResponse>(
    '/api/v1/settings/ai/sentiment/accuracy'
  );
  return response.data;
}
