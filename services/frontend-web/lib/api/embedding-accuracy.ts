import apiClient from '../api-client';

/**
 * Types + client for GET /api/v1/settings/ai/embeddings/accuracy
 * (retrieval-eval-card aspect, M5.4 disclosure layer).
 *
 * Mirrors the backend's RetrievalAccuracyResponse schema 1:1
 * (src/schemas/embedding_accuracy.py). This is a disclosure card, not a
 * gated premium feature — kept self-contained per the existing precedent of
 * independent lib/api/*.ts modules (see lib/api/sentiment-accuracy.ts).
 */

export interface ProviderRetrievalResult {
  provider: string;
  model: string | null;
  n: number;
  n_pos: number;
  n_neg: number;
  recall_at_1: number;
  mrr: number;
  false_match_rate: number;
}

export interface RetrievalAccuracyResponse {
  has_results: boolean;
  generated_at: string | null;
  threshold: number | null;
  n: number | null;
  n_positives: number | null;
  n_negatives: number | null;
  baseline: ProviderRetrievalResult | null;
  candidate: ProviderRetrievalResult | null;
  recall_at_1_delta: number | null;
  meets_target: boolean | null;
}

/** Format a 0-1 metric fraction as a whole-number percent string, "—" for null. */
export function formatMetricPercent(n: number | null): string {
  if (n === null) return '—';
  return `${Math.round(n * 100)}%`;
}

/** Format a signed recall@1 delta (candidate - baseline), "—" for null. */
export function formatDelta(delta: number | null): string {
  if (delta === null) return '—';
  const sign = delta >= 0 ? '+' : '-';
  return `${sign}${Math.abs(delta).toFixed(2)}`;
}

/** Fetch the embedding retrieval eval accuracy card data (no plan-gating — disclosure feature). */
export async function getEmbeddingAccuracy(): Promise<RetrievalAccuracyResponse> {
  const response = await apiClient.get<RetrievalAccuracyResponse>(
    '/api/v1/settings/ai/embeddings/accuracy'
  );
  return response.data;
}
