import { describe, it, expect } from 'vitest';
import {
  isDuplicateJiraResponse,
  getJiraCreateIssueErrorMessage,
  isStaleJiraTokenStatus,
} from '@/lib/jiraIssueWizard';

describe('isDuplicateJiraResponse', () => {
  it('is true when warning is "duplicate"', () => {
    expect(isDuplicateJiraResponse({ warning: 'duplicate' })).toBe(true);
  });

  it('is false when there is no warning', () => {
    expect(isDuplicateJiraResponse({})).toBe(false);
  });

  it('is false for an unrelated warning value', () => {
    expect(isDuplicateJiraResponse({ warning: 'something-else' })).toBe(false);
  });
});

describe('getJiraCreateIssueErrorMessage', () => {
  it('returns the backend detail for a 403 (stale token) response', () => {
    const msg = getJiraCreateIssueErrorMessage(403, 'Jira token is invalid or lacks required project permissions.');
    expect(msg).toBe('Jira token is invalid or lacks required project permissions.');
  });

  it('falls back to a reconnect message for 403 with no detail', () => {
    const msg = getJiraCreateIssueErrorMessage(403, undefined);
    expect(msg).toMatch(/reconnect jira/i);
  });

  it('falls back to a validation message for 422 with no detail', () => {
    const msg = getJiraCreateIssueErrorMessage(422, null);
    expect(msg).toMatch(/project, issue type, and summary/i);
  });

  it('falls back to a generic message for other statuses with no detail', () => {
    const msg = getJiraCreateIssueErrorMessage(502, undefined);
    expect(msg).toBe('Failed to create issue. Please try again.');
  });

  it('prefers the backend detail when present regardless of status', () => {
    const msg = getJiraCreateIssueErrorMessage(502, 'Jira API returned a transient error');
    expect(msg).toBe('Jira API returned a transient error');
  });
});

describe('isStaleJiraTokenStatus', () => {
  it('is true only for 403', () => {
    expect(isStaleJiraTokenStatus(403)).toBe(true);
    expect(isStaleJiraTokenStatus(422)).toBe(false);
    expect(isStaleJiraTokenStatus(undefined)).toBe(false);
  });
});
