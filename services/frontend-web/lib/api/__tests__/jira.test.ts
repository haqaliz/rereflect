import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing jira
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import apiClient from '@/lib/api-client';
import { jiraAPI } from '@/lib/api/jira';

describe('jiraAPI', () => {
  beforeEach(() => vi.clearAllMocks());

  it('connect calls POST /api/v1/integrations/jira/connect with site_url, email, api_token', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: {
        connected: true,
        site_url: 'https://acme.atlassian.net',
        email: 'admin@acme.com',
        token_hint: '...abcd',
        account_id: 'acc-1',
        display_name: 'Admin User',
      },
    });
    const result = await jiraAPI.connect({
      site_url: 'acme.atlassian.net',
      email: 'admin@acme.com',
      api_token: 'ATATT3xFfGF0',
    });
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/jira/connect', {
      site_url: 'acme.atlassian.net',
      email: 'admin@acme.com',
      api_token: 'ATATT3xFfGF0',
    });
    expect(result.connected).toBe(true);
    expect(result.site_url).toBe('https://acme.atlassian.net');
  });

  it('getStatus calls GET /api/v1/integrations/jira/status', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { connected: false } });
    const result = await jiraAPI.getStatus();
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/integrations/jira/status');
    expect(result.connected).toBe(false);
  });

  it('disconnect calls DELETE /api/v1/integrations/jira/disconnect', async () => {
    (apiClient.delete as any).mockResolvedValue({ data: { success: true, message: 'ok' } });
    const result = await jiraAPI.disconnect();
    expect(apiClient.delete).toHaveBeenCalledWith('/api/v1/integrations/jira/disconnect');
    expect(result.success).toBe(true);
  });

  it('testConnection calls POST /api/v1/integrations/jira/test', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { success: true, message: 'Jira connection is healthy.' },
    });
    const result = await jiraAPI.testConnection();
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/jira/test');
    expect(result.success).toBe(true);
  });

  it('getProjects calls GET /api/v1/integrations/jira/projects', async () => {
    (apiClient.get as any).mockResolvedValue({
      data: [{ id: '10001', key: 'ENG', name: 'Engineering' }],
    });
    const result = await jiraAPI.getProjects();
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/integrations/jira/projects');
    expect(result).toHaveLength(1);
    expect(result[0].key).toBe('ENG');
  });

  it('getIssueTypes calls GET /api/v1/integrations/jira/issuetypes with project_id param', async () => {
    (apiClient.get as any).mockResolvedValue({
      data: [{ id: '10000', name: 'Bug' }],
    });
    const result = await jiraAPI.getIssueTypes('10001');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/integrations/jira/issuetypes', {
      params: { project_id: '10001' },
    });
    expect(result[0].name).toBe('Bug');
  });

  it('createIssue calls POST /api/v1/integrations/jira/issues', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: {
        jira_issue_id: '10050',
        jira_issue_key: 'ENG-123',
        jira_issue_url: 'https://acme.atlassian.net/browse/ENG-123',
        jira_issue_title: 'Fix the bug',
      },
    });
    const result = await jiraAPI.createIssue({
      feedback_id: 42,
      project_id: '10001',
      issue_type_id: '10000',
      summary: 'Fix the bug',
      description: 'Details here',
    });
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/jira/issues', {
      feedback_id: 42,
      project_id: '10001',
      issue_type_id: '10000',
      summary: 'Fix the bug',
      description: 'Details here',
    });
    expect(result.jira_issue_key).toBe('ENG-123');
  });

  it('createIssue surfaces a 200 duplicate warning response', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: {
        warning: 'duplicate',
        existing_issues: [
          { id: 1, jira_issue_key: 'ENG-100', jira_issue_url: 'https://acme.atlassian.net/browse/ENG-100', jira_issue_title: 'Existing' },
        ],
      },
    });
    const result = await jiraAPI.createIssue({
      feedback_id: 42,
      project_id: '10001',
      issue_type_id: '10000',
      summary: 'Fix the bug',
    });
    expect(result.warning).toBe('duplicate');
    expect(result.existing_issues).toHaveLength(1);
  });

  it('getLinkedIssues calls GET /api/v1/integrations/jira/issues with feedback_id param', async () => {
    (apiClient.get as any).mockResolvedValue({
      data: [
        {
          id: 1,
          feedback_id: 42,
          jira_issue_id: '10050',
          jira_issue_key: 'ENG-123',
          jira_issue_url: 'https://acme.atlassian.net/browse/ENG-123',
          jira_issue_title: 'Fix the bug',
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
    });
    const result = await jiraAPI.getLinkedIssues(42);
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/integrations/jira/issues', {
      params: { feedback_id: 42 },
    });
    expect(result).toHaveLength(1);
    expect(result[0].jira_issue_key).toBe('ENG-123');
  });
});
