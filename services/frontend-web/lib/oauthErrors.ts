/**
 * Shared OAuth error code → friendly message mapping.
 *
 * Used by both the integrations index page (`/settings/integrations`, which
 * handles the Linear OAuth return) and per-provider detail pages such as
 * `/settings/integrations/salesforce` (which handle their own OAuth return).
 * Keeping this in one place avoids the two pages drifting out of sync.
 */
export const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  access_denied: 'You cancelled the authorization.',
  invalid_state: 'Session expired. Please try again.',
  missing_params: 'Missing OAuth parameters. Please try again.',
  another_crm_active: 'Another CRM integration is already active. Disconnect it before connecting a new one.',
  network_error: 'Network error during authorization. Please try again.',
  incomplete_token_response: 'Salesforce did not return a complete token response. Please try again.',
  validation_failed: 'Could not validate the Salesforce connection. Please try again.',
  unexpected_error: 'An unexpected error occurred. Please try again.',
};

export function getOauthErrorMessage(code: string): string {
  return OAUTH_ERROR_MESSAGES[code] ?? `OAuth error: ${code}`;
}
