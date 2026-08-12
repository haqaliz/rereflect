import apiClient, { publicApiClient } from '../api-client';
import type { Cohort } from './customers';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface OutreachTemplateSummary {
  key: string;
  label: string;
  description: string;
}

export interface BulkOutreachSummary {
  matched: number;
  queued: number;
  skipped: number;
  errors: string[];
}

export interface OutreachCampaign {
  id: number;
  subject: string;
  status: 'queued' | 'in_progress' | 'done' | 'failed';
  recipient_count: number;
  counts: { queued: number; sent: number; skipped: number; failed: number };
  created_at: string;
}

export interface OutreachCampaignListResponse {
  items: OutreachCampaign[];
  total: number;
  page: number;
  page_size: number;
}

export interface OutreachDraft {
  subject: string;
  body: string;
}

export type OutreachTone = 'professional' | 'friendly' | 'empathetic' | 'concise' | 'technical';

export interface OutreachDraftRequest {
  cohort?: Cohort;
  tone?: OutreachTone;
}

export interface OutreachRetrySummary {
  matched: number;
  queued: number;
  skipped: number;
  errors: string[];
}

/**
 * Typed error for the outreach draft endpoint. Carries the HTTP status so
 * callers can distinguish 409 (no LLM configured) from 422 bad input or 502
 * provider failure and show an honest message (issueDraft precedent).
 */
export class OutreachDraftApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'OutreachDraftApiError';
    this.status = status;
  }
}

// ─── API Client ───────────────────────────────────────────────────────────────

export async function listOutreachTemplates(): Promise<OutreachTemplateSummary[]> {
  const response = await apiClient.get('/api/v1/outreach/templates');
  return response.data;
}

/**
 * Create a bulk outreach campaign — or, with `countOnly`, preview the resolved
 * cohort (matched/skipped) without queueing anything.
 * POST /api/v1/customers/bulk/outreach (+ ?count_only=true)
 */
export async function createCampaign(
  payload: { cohort: Cohort; subject: string; body: string },
  options: { countOnly?: boolean } = {}
): Promise<BulkOutreachSummary> {
  const response = await apiClient.post(
    '/api/v1/customers/bulk/outreach',
    payload,
    { params: options.countOnly ? { count_only: true } : undefined }
  );
  return response.data;
}

/**
 * AI-draft a {subject, body} outreach message from org context + tone.
 * POST /api/v1/customers/bulk/outreach/draft — never sends anything.
 */
export async function draftCampaign(request: OutreachDraftRequest): Promise<OutreachDraft> {
  try {
    const response = await apiClient.post('/api/v1/customers/bulk/outreach/draft', request);
    return response.data;
  } catch (err: any) {
    const status = err?.response?.status ?? 0;
    const message =
      err?.response?.data?.detail ||
      err?.message ||
      'Failed to draft the message. Please try again.';
    throw new OutreachDraftApiError(status, message);
  }
}

export async function listCampaigns(params: {
  page?: number;
  page_size?: number;
}): Promise<OutreachCampaignListResponse> {
  const response = await apiClient.get('/api/v1/outreach/campaigns', { params });
  return response.data;
}

/**
 * Re-enqueue the recipients of a campaign that never got sent (the worker is
 * down or the send failed before the row left the queue).
 * POST /api/v1/outreach/campaigns/{id}/retry
 */
export async function retryCampaign(id: number): Promise<OutreachRetrySummary> {
  const response = await apiClient.post(`/api/v1/outreach/campaigns/${id}/retry`);
  return response.data;
}

/**
 * Honor the tokenized List-Unsubscribe link. Public endpoint — goes through
 * publicApiClient (no auth token, no 401 redirect). Success is HTTP-status
 * based: the backend may answer with an HTML page body.
 * GET /api/v1/outreach/unsubscribe?token=…
 */
export async function unsubscribe(token: string): Promise<void> {
  try {
    await publicApiClient.get('/api/v1/outreach/unsubscribe', { params: { token } });
  } catch (err: any) {
    const message =
      err?.response?.data?.detail || err?.message || 'This unsubscribe link is invalid.';
    throw new Error(message);
  }
}

// ─── Constants ────────────────────────────────────────────────────────────────

/**
 * Contract-pinned fallback registry (outreach-core AC2). Keys are named
 * verbatim by the seeded playbook templates (`playbook_seeder.py:111,215`)
 * and the backend registry (`outreach_templates.py`); labels mirror the
 * backend registry. Used when `GET /api/v1/outreach/templates` fails so the
 * editor never bricks playbooks that already contain send_email steps.
 */
export const BUILTIN_OUTREACH_TEMPLATES: OutreachTemplateSummary[] = [
  {
    key: 're_engagement',
    label: 'Re-engagement check-in',
    description:
      'A friendly nudge for customers who have gone quiet — invites them to tell you what happened, no hard sell.',
  },
  {
    key: 'weekly_digest_entry',
    label: 'Weekly digest entry',
    description:
      'A short weekly check-in that keeps the relationship warm — highlights, fixes, and what\'s coming next.',
  },
];
