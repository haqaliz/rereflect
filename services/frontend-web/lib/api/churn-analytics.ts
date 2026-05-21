import apiClient from '../api-client';
import type { ChurnReasonCode } from './churn-events';

export type { ChurnReasonCode };

export interface CohortBucket {
  label: string;
  total_customers: number;
  churned_customers: number;
  churn_rate: number;
  avg_probability: number | null;
  top_reason_codes: { code: ChurnReasonCode; count: number }[];
}

export interface CohortGridCell {
  cohort_label: string;
  time_bucket: string;
  churn_rate: number;
  churned_count: number;
}

export interface CohortAnalyticsResponse {
  dimension: 'source' | 'month' | 'volume';
  range: '30d' | '90d' | 'all';
  cohorts: CohortBucket[];
  grid: CohortGridCell[];
  overall_churn_rate: number;
  total_customers: number;
  total_churned: number;
}

export type CohortDimension = 'source' | 'month' | 'volume';
export type CohortRange = '30d' | '90d' | 'all';

export interface CohortParams {
  dimension: CohortDimension;
  range: CohortRange;
}

/** Fetch churn cohort analytics for the given dimension and date range. */
export async function getChurnCohorts(params: CohortParams): Promise<CohortAnalyticsResponse> {
  const response = await apiClient.get<CohortAnalyticsResponse>(
    '/api/v1/analytics/churn-cohorts',
    {
      params,
      headers: { 'Content-Type': 'application/json' },
    },
  );
  return response.data;
}

/** Map dimension value to a human-readable label. */
export function cohortDimensionLabel(dim: CohortDimension): string {
  switch (dim) {
    case 'source':
      return 'Source';
    case 'month':
      return 'Acquisition Month';
    case 'volume':
      return 'Volume Segment';
  }
}

/** Format a 0.0–1.0 probability as a percentage string (e.g. "12%"). */
export function formatPercent(p: number): string {
  return `${Math.round(p * 100)}%`;
}
