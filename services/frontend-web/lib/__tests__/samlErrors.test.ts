import { describe, it, expect } from 'vitest';
import { getSamlErrorMessage, SAML_ERROR_CODES } from '../samlErrors';

// This is the authoritative set of `sso_error` codes the backend's
// `SAML_SSO_ERROR_CODES` (src/api/routes/auth.py) can emit for the SAML flow.
// Keeping this list in the test (not just in samlErrors.ts) means a future
// drift between the two — a code added/removed on one side only — fails this
// test instead of silently rendering the generic fallback in production.
const BACKEND_SAML_SSO_ERROR_CODES = [
  'disabled',
  'config',
  'state',
  'signature',
  'assertion',
  'audience',
  'recipient',
  'expired',
  'replay',
  'unsolicited',
  'unverified',
  'domain',
  'token',
];

describe('getSamlErrorMessage', () => {
  it('has an entry for EXACTLY the 13 backend SAML_SSO_ERROR_CODES — no more, no less', () => {
    expect([...SAML_ERROR_CODES].sort()).toEqual([...BACKEND_SAML_SSO_ERROR_CODES].sort());
  });

  it.each([
    ['signature', "We couldn't verify the response from your identity provider. Please try again."],
    ['assertion', "The identity provider's response was invalid. Please try again."],
    ['audience', "This sign-on response wasn't intended for this application. Contact your admin."],
    ['recipient', "This sign-on response wasn't intended for this application. Contact your admin."],
    ['expired', 'Your sign-on session expired. Please try again.'],
    ['replay', 'This sign-on response was already used. Please try again.'],
    ['unsolicited', "We couldn't match this sign-on response to a request. Please try again."],
    ['disabled', 'Single sign-on is not enabled.'],
    ['unverified', "Your identity provider didn't provide an email address."],
    ['domain', "Your email domain isn't allowed for single sign-on. Contact your admin."],
    ['config', 'Single sign-on failed. Please try again.'],
    ['state', "Your sign-on session couldn't be verified. Please try again."],
    ['token', "Your identity provider didn't identify you correctly. Contact your admin."],
  ])('maps %s to the expected friendly message', (code, expected) => {
    expect(getSamlErrorMessage(code)).toBe(expected);
  });

  it('falls back to a generic message for an unknown code', () => {
    expect(getSamlErrorMessage('something_unexpected')).toBe(
      'Single sign-on could not be completed.'
    );
  });

  it('no longer maps the dead "denied" code (SAML never emits it)', () => {
    expect(getSamlErrorMessage('denied')).toBe('Single sign-on could not be completed.');
  });
});
