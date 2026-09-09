import apiClient from '../api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

/**
 * Outcome of `POST /api/v1/copilot/actions/execute` (backend
 * `BulkActionSummary`). `errors[]` carries per-customer failures verbatim
 * (e.g. the 20-tag cap message) and must never be swallowed by the UI.
 */
export interface BulkActionSummary {
  matched: number;
  updated: number;
  skipped: number;
  errors: string[];
}

// ─── API Client ───────────────────────────────────────────────────────────────

/**
 * Execute a copilot-suggested action. `params` carries only user-supplied
 * values (the tag); the cohort comes from the proposal frozen in the
 * message's structured_data — never from the client.
 *
 * Errors propagate to the caller: the shared client handles auth + 401
 * redirect, and a 403 (insufficient role) rejects through so the call site
 * can check `error.response.status === 403` and surface a clear message.
 */
export async function executeCopilotAction(
  conversationId: number,
  proposalId: string,
  action: string,
  params: Record<string, unknown>
): Promise<BulkActionSummary> {
  const response = await apiClient.post('/api/v1/copilot/actions/execute', {
    conversation_id: conversationId,
    proposal_id: proposalId,
    action,
    params,
  });
  return response.data;
}