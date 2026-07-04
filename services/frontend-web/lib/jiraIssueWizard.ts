import { CreateJiraIssueResponse } from '@/lib/api/jira';

/**
 * True when the backend responded 200 with `{warning: "duplicate", ...}`
 * instead of a created issue (feedback already linked to a Jira issue and
 * `force` was not set).
 */
export function isDuplicateJiraResponse(
  response: Pick<CreateJiraIssueResponse, 'warning'>,
): boolean {
  return response?.warning === 'duplicate';
}

/**
 * Build a user-facing error message for a failed `jiraAPI.createIssue` (or
 * `getProjects` / `getIssueTypes`) call, given the HTTP status and the
 * backend's `detail` string (if any).
 *
 * 403 means the stored Jira token is invalid/expired or lacks project
 * permissions — the user needs to reconnect Jira from Settings.
 */
export function getJiraCreateIssueErrorMessage(
  status: number | undefined,
  detail?: string | null,
): string {
  if (status === 403) {
    return (
      detail ||
      'Your Jira connection appears to be invalid or missing permissions. Reconnect Jira in Settings → Integrations, then try again.'
    );
  }
  if (status === 422) {
    return detail || 'Jira rejected the request. Double-check the project, issue type, and summary.';
  }
  return detail || 'Failed to create issue. Please try again.';
}

/** True when the create-issue error should prompt the user to reconnect Jira. */
export function isStaleJiraTokenStatus(status: number | undefined): boolean {
  return status === 403;
}
