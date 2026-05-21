import apiClient from '../api-client';

export interface BacktestRunSummary {
  run_at: string;
  label_count: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  auc: number | null;
}

export interface AccuracyCardResponse {
  model_id: number | null;
  label_count: number;
  positive_count: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  auc: number | null;
  fit_at: string | null;
  is_global_fallback: boolean;
  history: BacktestRunSummary[];
}

export interface OrgAccuracyRow {
  organization_id: number;
  organization_name: string;
  label_count: number;
  f1: number | null;
  last_refit_at: string | null;
  is_using_global_fallback: boolean;
}

export interface SystemAccuracyResponse {
  orgs: OrgAccuracyRow[];
  global_model_id: number | null;
  global_f1: number | null;
  global_label_count: number;
  total_orgs_using_global: number;
  total_orgs_with_dedicated_model: number;
}

export interface ModelVersionSummary {
  id: number;
  is_active: boolean;
  label_count: number;
  positive_count: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  auc: number | null;
  fit_at: string;
  threshold_bands: Record<string, number>;
}

export interface OrgHistoryResponse {
  organization_id: number;
  organization_name: string;
  models: ModelVersionSummary[];
  backtest_runs: BacktestRunSummary[];
}

/** Format a 0.0–1.0 metric as a percentage string (e.g. "73%"). Returns "—" for null. */
export function formatMetricPercent(n: number | null): string {
  if (n === null) return '—';
  return `${Math.round(n * 100)}%`;
}

/** Fetch the accuracy card for the current org (Business+). */
export async function getAccuracyCard(): Promise<AccuracyCardResponse> {
  const response = await apiClient.get<AccuracyCardResponse>(
    '/api/v1/analytics/churn-accuracy',
    { headers: { 'Content-Type': 'application/json' } },
  );
  return response.data;
}

/** Fetch cross-org accuracy summary (system admin only). */
export async function getSystemAccuracy(): Promise<SystemAccuracyResponse> {
  const response = await apiClient.get<SystemAccuracyResponse>(
    '/api/v1/system/churn-accuracy',
    { headers: { 'Content-Type': 'application/json' } },
  );
  return response.data;
}

/** Fetch model version history for a specific org (system admin only). */
export async function getOrgAccuracyHistory(orgId: number): Promise<OrgHistoryResponse> {
  const response = await apiClient.get<OrgHistoryResponse>(
    `/api/v1/system/churn-accuracy/${orgId}`,
    { headers: { 'Content-Type': 'application/json' } },
  );
  return response.data;
}
