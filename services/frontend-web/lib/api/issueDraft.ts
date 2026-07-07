import apiClient from '../api-client';

// ---- Types ----

export interface IssueDraft {
  title: string;
  body: string;
}

export type IssueDraftTarget = 'jira' | 'asana';

/**
 * Typed error for the issue-draft endpoint. Carries the HTTP status so
 * callers can distinguish 409 (no LLM configured) from other failures
 * (404 cross-org feedback, 502 bad/failed draft) and show an honest message.
 */
export class IssueDraftApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'IssueDraftApiError';
    this.status = status;
  }
}

// ---- API ----

/**
 * AI-draft a {title, body} work-tracker issue for a feedback item.
 * POST /api/v1/feedback/{feedbackId}/issue-draft
 */
export async function draftIssueContent(
  feedbackId: number | string,
  target: IssueDraftTarget
): Promise<IssueDraft> {
  try {
    const response = await apiClient.post(`/api/v1/feedback/${feedbackId}/issue-draft`, { target });
    return response.data;
  } catch (err: any) {
    const status = err?.response?.status ?? 0;
    const message =
      err?.response?.data?.detail || err?.message || 'Failed to draft issue content. Please try again.';
    throw new IssueDraftApiError(status, message);
  }
}
