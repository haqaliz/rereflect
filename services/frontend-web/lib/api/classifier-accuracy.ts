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
  /** True when a manual rollback has paused the weekly retrain job's
   * auto-promotion for this classifier_type; cleared by resumeClassifier(). */
  hold: boolean;
}

/** One OrgClassifierModel row, as surfaced by getClassifierVersions(). */
export interface ClassifierVersionSummary {
  id: number;
  fit_at: string;
  macro_f1: number | null;
  label_count: number;
  is_active: boolean;
}

export interface ClassifierVersionsResponse {
  classifier_type: string;
  hold: boolean;
  versions: ClassifierVersionSummary[];
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

/** Fetch every stored version of the org's classifier of this type, newest-first. Read access: any authenticated user. */
export async function getClassifierVersions(
  classifierType: string = 'sentiment'
): Promise<ClassifierVersionsResponse> {
  const response = await apiClient.get<ClassifierVersionsResponse>(
    `/api/v1/settings/ai/classifier/versions?classifier_type=${classifierType}`
  );
  return response.data;
}

/**
 * Roll back the org's active classifier model. Admin/owner only.
 *
 * With no `toVersionId`: reactivate the most recent prior version, or
 * disable-only if none exists. With `toVersionId`: reactivate exactly that
 * (inactive) version. Reactivating a prior/target version engages the
 * per-type auto-promotion hold on the backend.
 */
export async function rollbackClassifier(
  classifierType: string = 'sentiment',
  toVersionId?: number
): Promise<ClassifierAccuracyResponse> {
  const toVersionParam = toVersionId !== undefined ? `&to_version_id=${toVersionId}` : '';
  const response = await apiClient.post<ClassifierAccuracyResponse>(
    `/api/v1/settings/ai/classifier/rollback?classifier_type=${classifierType}${toVersionParam}`
  );
  return response.data;
}

/** Clear the per-type auto-promotion hold, letting the weekly retrain job resume promoting again. Admin/owner only. */
export async function resumeClassifier(
  classifierType: string = 'sentiment'
): Promise<ClassifierAccuracyResponse> {
  const response = await apiClient.post<ClassifierAccuracyResponse>(
    `/api/v1/settings/ai/classifier/resume?classifier_type=${classifierType}`
  );
  return response.data;
}
