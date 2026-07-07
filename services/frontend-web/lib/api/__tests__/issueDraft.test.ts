import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing issueDraft
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import apiClient from '@/lib/api-client';
import { draftIssueContent, IssueDraftApiError } from '@/lib/api/issueDraft';

describe('draftIssueContent', () => {
  beforeEach(() => vi.clearAllMocks());

  it('POSTs /api/v1/feedback/{id}/issue-draft with target and parses {title, body}', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { title: 'Payment sync fails', body: 'Customer reports that payments do not sync.' },
    });

    const result = await draftIssueContent(42, 'jira');

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/feedback/42/issue-draft', { target: 'jira' });
    expect(result).toEqual({
      title: 'Payment sync fails',
      body: 'Customer reports that payments do not sync.',
    });
  });

  it('supports the asana target', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { title: 'Title', body: 'Body' },
    });

    await draftIssueContent(7, 'asana');

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/feedback/7/issue-draft', { target: 'asana' });
  });

  it('throws an IssueDraftApiError carrying status 409 on "no LLM configured"', async () => {
    (apiClient.post as any).mockRejectedValue({
      response: { status: 409, data: { detail: 'No AI model configured.' } },
    });

    await expect(draftIssueContent(42, 'jira')).rejects.toMatchObject({
      status: 409,
      message: 'No AI model configured.',
    });
    await expect(draftIssueContent(42, 'jira')).rejects.toBeInstanceOf(IssueDraftApiError);
  });

  it('throws an IssueDraftApiError carrying status 502 on a bad/failed draft', async () => {
    (apiClient.post as any).mockRejectedValue({
      response: { status: 502, data: { detail: 'The AI model returned an unusable draft. Try again.' } },
    });

    await expect(draftIssueContent(42, 'jira')).rejects.toMatchObject({
      status: 502,
      message: 'The AI model returned an unusable draft. Try again.',
    });
  });

  it('throws an IssueDraftApiError carrying status 404 for cross-org feedback', async () => {
    (apiClient.post as any).mockRejectedValue({
      response: { status: 404, data: { detail: 'Feedback item 42 not found' } },
    });

    await expect(draftIssueContent(42, 'jira')).rejects.toMatchObject({ status: 404 });
  });

  it('falls back to a generic message when the error has no response body', async () => {
    (apiClient.post as any).mockRejectedValue(new Error('Network error'));

    await expect(draftIssueContent(42, 'jira')).rejects.toMatchObject({
      status: 0,
      message: 'Network error',
    });
  });
});
