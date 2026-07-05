import { describe, it, expect } from 'vitest';
import {
  isDuplicateAsanaResponse,
  getAsanaCreateTaskErrorMessage,
  isStaleAsanaTokenStatus,
} from '@/lib/asanaIssueWizard';

describe('isDuplicateAsanaResponse', () => {
  it('is true when warning is "duplicate"', () => {
    expect(isDuplicateAsanaResponse({ warning: 'duplicate' })).toBe(true);
  });

  it('is false when there is no warning', () => {
    expect(isDuplicateAsanaResponse({})).toBe(false);
  });

  it('is false for an unrelated warning value', () => {
    expect(isDuplicateAsanaResponse({ warning: 'something-else' })).toBe(false);
  });
});

describe('getAsanaCreateTaskErrorMessage', () => {
  it('returns the backend detail for a 403 (stale token) response', () => {
    const msg = getAsanaCreateTaskErrorMessage(
      403,
      'Asana token is invalid or lacks required project permissions.',
    );
    expect(msg).toBe('Asana token is invalid or lacks required project permissions.');
  });

  it('falls back to a reconnect message for 403 with no detail', () => {
    const msg = getAsanaCreateTaskErrorMessage(403, undefined);
    expect(msg).toMatch(/reconnect asana/i);
  });

  it('falls back to a validation message for 422 with no detail', () => {
    const msg = getAsanaCreateTaskErrorMessage(422, null);
    expect(msg).toMatch(/workspace, project, and name/i);
  });

  it('falls back to a generic message for other statuses with no detail', () => {
    const msg = getAsanaCreateTaskErrorMessage(502, undefined);
    expect(msg).toBe('Failed to create task. Please try again.');
  });

  it('prefers the backend detail when present regardless of status', () => {
    const msg = getAsanaCreateTaskErrorMessage(502, 'Asana API returned a transient error');
    expect(msg).toBe('Asana API returned a transient error');
  });
});

describe('isStaleAsanaTokenStatus', () => {
  it('is true for 401 and 403 (backend emits 403; 401 covered defensively for metadata calls)', () => {
    expect(isStaleAsanaTokenStatus(403)).toBe(true);
    expect(isStaleAsanaTokenStatus(401)).toBe(true);
    expect(isStaleAsanaTokenStatus(422)).toBe(false);
    expect(isStaleAsanaTokenStatus(undefined)).toBe(false);
  });
});
