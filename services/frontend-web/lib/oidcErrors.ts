/**
 * SSO error code → friendly message mapping, for the `?sso_error=` the
 * backend appends when it redirects back to `/login` after a failed OIDC
 * flow. Kept separate from `lib/oauthErrors.ts` (integrations-specific
 * CRM/OAuth codes) so the two error spaces don't drift together.
 */
const SSO_ERROR_MESSAGES: Record<string, string> = {
  disabled: 'Single sign-on is not enabled.',
  state: 'Single sign-on failed. Please try again.',
  token: 'Single sign-on failed. Please try again.',
  exchange: 'Single sign-on failed. Please try again.',
  config: 'Single sign-on failed. Please try again.',
  unverified: 'Your identity provider did not confirm a verified email.',
  domain: "Your email domain isn't allowed for single sign-on. Contact your admin.",
  denied: 'Single sign-on was cancelled.',
};

export function getSsoErrorMessage(code: string): string {
  return SSO_ERROR_MESSAGES[code] ?? 'Single sign-on could not be completed.';
}
