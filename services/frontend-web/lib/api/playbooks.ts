import apiClient from '../api-client';
import type { Cohort } from './customers';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PlaybookAction {
  type: 'assign' | 'change_status' | 'send_notification' | 'draft_response' | string;
  [k: string]: unknown;
}

export interface Playbook {
  id: number;
  organization_id: number | null;
  name: string;
  description: string | null;
  probability_min: number;
  probability_max: number;
  action_sequence: PlaybookAction[];
  is_template: boolean;
  is_active: boolean;
  source_template_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface PlaybookExecution {
  id: number;
  playbook_id: number;
  customer_email: string;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  triggered_by: string;
  action_log: unknown[];
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface PlaybookDetail extends Playbook {
  recent_executions: PlaybookExecution[];
}

export interface ExecutionListResponse {
  items: PlaybookExecution[];
  total: number;
  page: number;
  page_size: number;
}

export interface BatchRunResponse {
  queued: number;
  execution_ids: number[];
  /** Size of the resolved cohort/probability selection (backend RunBatchResponse.matched). */
  matched: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

export function formatProbabilityRange(min: number, max: number): string {
  return `${Math.round(min * 100)}%–${Math.round(max * 100)}%`;
}

// ─── API Client ───────────────────────────────────────────────────────────────

export async function listPlaybooks(): Promise<Playbook[]> {
  const response = await apiClient.get('/api/v1/playbooks');
  return Array.isArray(response.data) ? response.data : response.data.playbooks ?? [];
}

export async function getPlaybook(id: number): Promise<PlaybookDetail> {
  const response = await apiClient.get(`/api/v1/playbooks/${id}`);
  return response.data;
}

export async function createPlaybook(body: Partial<Playbook>): Promise<Playbook> {
  const response = await apiClient.post('/api/v1/playbooks', body);
  return response.data;
}

export async function updatePlaybook(id: number, body: Partial<Playbook>): Promise<Playbook> {
  const response = await apiClient.put(`/api/v1/playbooks/${id}`, body);
  return response.data;
}

export async function deletePlaybook(id: number): Promise<void> {
  await apiClient.delete(`/api/v1/playbooks/${id}`);
}

export async function runPlaybook(id: number, customer_email: string): Promise<PlaybookExecution> {
  const response = await apiClient.post(`/api/v1/playbooks/${id}/run`, { customer_email });
  return response.data;
}

/**
 * Filters for `POST /api/v1/playbooks/{id}/run-batch`. Two independent
 * selection axes that can be combined (mirrors backend `RunBatchFilters`):
 * a probability band (`probability_min`/`probability_max`,
 * `time_to_churn_bucket`), and/or a cohort — exactly one of `emails` OR
 * `segment` (the run-batch cohort only supports these two dimensions, not
 * the full `CohortFilter` used by the bulk tag/assign-owner endpoints).
 */
export interface RunBatchFilters {
  probability_min?: number;
  probability_max?: number;
  time_to_churn_bucket?: string;
  emails?: string[];
  segment?: string;
}

/**
 * Convert a segment-actions `Cohort` (`{emails}` or `{filter}`) into the
 * subset of `RunBatchFilters` the run-batch cohort dimension supports
 * (`emails` OR `segment` — not the full `CohortFilter`). Returns `null`
 * when the cohort is in filter-mode but has no `segment` set (e.g. a
 * risk_level- or search-only filter) — that filter shape has no run-batch
 * equivalent, so the caller should block the run rather than silently
 * falling back to a probability-only selection.
 */
export function cohortToRunBatchFilters(
  cohort: Cohort
): Pick<RunBatchFilters, 'emails' | 'segment'> | null {
  if ('emails' in cohort) return { emails: cohort.emails };
  if (cohort.filter.segment) return { segment: cohort.filter.segment };
  return null;
}

export async function runPlaybookBatch(
  id: number,
  filters: RunBatchFilters,
  options: { countOnly?: boolean } = {}
): Promise<BatchRunResponse> {
  const response = await apiClient.post(
    `/api/v1/playbooks/${id}/run-batch`,
    { filters },
    { params: options.countOnly ? { count_only: true } : undefined }
  );
  return response.data;
}

export async function listExecutions(params: {
  playbook_id?: number;
  customer_email?: string;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<ExecutionListResponse> {
  const response = await apiClient.get('/api/v1/playbooks/executions', { params });
  return response.data;
}

// ─── Constants ────────────────────────────────────────────────────────────────

export const PLAN_PLAYBOOK_LIMITS: Record<string, number | null> = {
  free: 0,
  pro: 0,
  business: 20,
  enterprise: null,
};

export const ACTION_TYPE_LABELS: Record<string, string> = {
  assign: 'Assign',
  change_status: 'Change Status',
  send_notification: 'Send Notification',
  draft_response: 'Draft AI Response',
};
