/**
 * SSO error code → friendly message mapping, for the `?sso_error=` the
 * backend appends when it redirects back to `/login` after a failed SAML
 * flow. Kept separate from `lib/oidcErrors.ts` (OIDC-specific codes) so the
 * two protocol error spaces don't drift together; the login page merges
 * both maps (see `app/login/page.tsx`).
 */
const SAML_ERROR_MESSAGES: Record<string, string> = {
  signature: "We couldn't verify the response from your identity provider. Please try again.",
  assertion: "The identity provider's response was invalid. Please try again.",
  audience: "This sign-on response wasn't intended for this application. Contact your admin.",
  recipient: "This sign-on response wasn't intended for this application. Contact your admin.",
  expired: 'Your sign-on session expired. Please try again.',
  replay: 'This sign-on response was already used. Please try again.',
  unsolicited: "We couldn't match this sign-on response to a request. Please try again.",
  disabled: 'Single sign-on is not enabled.',
  unverified: "Your identity provider didn't provide an email address.",
  domain: "Your email domain isn't allowed for single sign-on. Contact your admin.",
  config: 'Single sign-on failed. Please try again.',
  state: "Your sign-on session couldn't be verified. Please try again.",
  token: "Your identity provider didn't identify you correctly. Contact your admin.",
};

export function getSamlErrorMessage(code: string): string {
  return SAML_ERROR_MESSAGES[code] ?? 'Single sign-on could not be completed.';
}

/**
 * Every `sso_error` code the SAML flow can produce, i.e. the key set of
 * `SAML_ERROR_MESSAGES` above. Exported so tests can assert this stays in
 * exact lockstep with the backend's `SAML_SSO_ERROR_CODES`
 * (src/api/routes/auth.py) and so callers (e.g. the login page) can do a
 * deterministic code-set lookup instead of string-comparing fallback text.
 */
export const SAML_ERROR_CODES = new Set(Object.keys(SAML_ERROR_MESSAGES));
