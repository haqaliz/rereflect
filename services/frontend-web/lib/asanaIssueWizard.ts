import { CreateAsanaTaskResponse } from '@/lib/api/asana';

/**
 * True when the backend responded 200 with `{warning: "duplicate", ...}`
 * instead of a created task (feedback already linked to an Asana task and
 * `force` was not set).
 */
export function isDuplicateAsanaResponse(
  response: Pick<CreateAsanaTaskResponse, 'warning'>,
): boolean {
  return response?.warning === 'duplicate';
}

/**
 * Build a user-facing error message for a failed `asanaAPI.createTask` (or
 * `getWorkspaces` / `getProjects`) call, given the HTTP status and the
 * backend's `detail` string (if any).
 *
 * 403 means the stored Asana token is invalid/expired or lacks project
 * permissions — the user needs to reconnect Asana from Settings.
 */
export function getAsanaCreateTaskErrorMessage(
  status: number | undefined,
  detail?: string | null,
): string {
  if (status === 403 || status === 401) {
    return (
      detail ||
      'Your Asana connection appears to be invalid or missing permissions. Reconnect Asana in Settings → Integrations, then try again.'
    );
  }
  if (status === 422) {
    return detail || 'Asana rejected the request. Double-check the workspace, project, and name.';
  }
  return detail || 'Failed to create task. Please try again.';
}

/** True when the create-task error should prompt the user to reconnect Asana. */
export function isStaleAsanaTokenStatus(status: number | undefined): boolean {
  return status === 403 || status === 401;
}
