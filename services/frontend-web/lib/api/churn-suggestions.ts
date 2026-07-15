import apiClient from '../api-client';
import type { ChurnReasonCode } from './churn-events';

// Mirrors backend `ChurnLabelSuggestion` (review-queue aspect). Confirm is
// the ONLY path that turns one of these into a trainable CustomerChurnEvent.

export type ChurnSuggestionStatus = 'pending' | 'confirmed' | 'rejected';
export type ChurnSuggestionProvider = 'hubspot' | 'salesforce';

export interface ChurnSuggestion {
  id: number;
  organization_id: number;
  customer_email: string;
  provider: ChurnSuggestionProvider;
  external_opportunity_id: string;
  suggested_churned_at: string;
  evidence: Record<string, unknown> | null;
  status: ChurnSuggestionStatus;
  reviewed_by_user_id: number | null;
  reviewed_at: string | null;
  churn_event_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ChurnSuggestionsListParams {
  page?: number;
  page_size?: number;
  status?: ChurnSuggestionStatus;
  provider?: ChurnSuggestionProvider;
  search?: string;
}

export interface ChurnSuggestionsListResponse {
  items: ChurnSuggestion[];
  total: number;
  page: number;
  page_size: number;
}

// Suggestion cohort — this aspect's own filter vocabulary (NOT the customer
// Cohort from lib/api/customers.ts — see plan §7 delta 2).
export interface SuggestionCohortFilter {
  status?: ChurnSuggestionStatus;
  provider?: ChurnSuggestionProvider;
  search?: string;
}

export type SuggestionCohort = { emails: string[] } | { filter: SuggestionCohortFilter };

export interface ConfirmSuggestionInput {
  reason_code: ChurnReasonCode;
  reason_text?: string;
}

export interface RejectSuggestionInput {
  note?: string;
}

export interface SuggestionActionResult {
  id: number;
  status: 'confirmed' | 'rejected' | 'skipped';
  churn_event_id: number | null;
  reason?: string | null;
}

export interface BulkReviewInput {
  action: 'confirm' | 'reject';
  cohort: SuggestionCohort;
  reason_code?: ChurnReasonCode;
  reason_text?: string;
}

export interface BulkReviewResultItem {
  id: number;
  status: 'confirmed' | 'skipped' | 'error';
  reason?: string | null;
}

export interface BulkReviewResult {
  matched: number;
  confirmed: number;
  skipped: number;
  results: BulkReviewResultItem[];
  capped: boolean;
  cap: number | null;
}

export async function listChurnSuggestions(
  params: ChurnSuggestionsListParams = {}
): Promise<ChurnSuggestionsListResponse> {
  const query = new URLSearchParams();
  if (params.page !== undefined) query.set('page', String(params.page));
  if (params.page_size !== undefined) query.set('page_size', String(params.page_size));
  if (params.status) query.set('status', params.status);
  if (params.provider) query.set('provider', params.provider);
  if (params.search) query.set('search', params.search);
  const response = await apiClient.get(
    `/api/v1/customers/churn-suggestions?${query.toString()}`
  );
  return response.data;
}

export async function confirmChurnSuggestion(
  id: number,
  body: ConfirmSuggestionInput
): Promise<SuggestionActionResult> {
  const response = await apiClient.post(
    `/api/v1/customers/churn-suggestions/${id}/confirm`,
    body
  );
  return response.data;
}

export async function rejectChurnSuggestion(
  id: number,
  body: RejectSuggestionInput = {}
): Promise<SuggestionActionResult> {
  const response = await apiClient.post(
    `/api/v1/customers/churn-suggestions/${id}/reject`,
    body
  );
  return response.data;
}

export async function bulkReviewChurnSuggestions(
  body: BulkReviewInput
): Promise<BulkReviewResult> {
  const response = await apiClient.post('/api/v1/customers/churn-suggestions/bulk', body);
  return response.data;
}
