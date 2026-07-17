import { describe, it, expect } from 'vitest';
import { getSamlErrorMessage } from '../samlErrors';

describe('getSamlErrorMessage', () => {
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
    ['denied', 'Single sign-on was cancelled.'],
  ])('maps %s to the expected friendly message', (code, expected) => {
    expect(getSamlErrorMessage(code)).toBe(expected);
  });

  it('falls back to a generic message for an unknown code', () => {
    expect(getSamlErrorMessage('something_unexpected')).toBe(
      'Single sign-on could not be completed.'
    );
  });
});
