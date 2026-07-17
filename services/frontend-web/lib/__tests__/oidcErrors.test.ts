import { describe, it, expect } from 'vitest';
import { getSsoErrorMessage } from '../oidcErrors';

describe('getSsoErrorMessage', () => {
  it.each([
    ['disabled', 'Single sign-on is not enabled.'],
    ['state', 'Single sign-on failed. Please try again.'],
    ['token', 'Single sign-on failed. Please try again.'],
    ['exchange', 'Single sign-on failed. Please try again.'],
    ['config', 'Single sign-on failed. Please try again.'],
    ['unverified', 'Your identity provider did not confirm a verified email.'],
    ['domain', "Your email domain isn't allowed for single sign-on. Contact your admin."],
    ['denied', 'Single sign-on was cancelled.'],
  ])('maps %s to the expected friendly message', (code, expected) => {
    expect(getSsoErrorMessage(code)).toBe(expected);
  });

  it('falls back to a generic message for an unknown code', () => {
    expect(getSsoErrorMessage('something_unexpected')).toBe(
      'Single sign-on could not be completed.'
    );
  });
});
