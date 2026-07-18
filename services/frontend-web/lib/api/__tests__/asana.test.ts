import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing asana
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import apiClient from '@/lib/api-client';
import { asanaAPI, patchAsanaStatusSync, triggerAsanaSync } from '@/lib/api/asana';

describe('asanaAPI', () => {
  beforeEach(() => vi.clearAllMocks());

  it('connect calls POST /api/v1/integrations/asana/connect with only api_token', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: {
        connected: true,
        token_hint: '...abcd',
        account_gid: 'acc-1',
        display_name: 'Admin User',
      },
    });
    const result = await asanaAPI.connect({ api_token: '1/abcdef' });
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/asana/connect', {
      api_token: '1/abcdef',
    });
    expect(result.connected).toBe(true);
    expect(result.token_hint).toBe('...abcd');
  });

  it('getStatus calls GET /api/v1/integrations/asana/status', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { connected: false } });
    const result = await asanaAPI.getStatus();
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/integrations/asana/status');
    expect(result.connected).toBe(false);
  });

  it('getStatus parses status_mapping from the response', async () => {
    (apiClient.get as any).mockResolvedValue({
      data: { connected: true, status_mapping: { new: 'new', done: 'resolved' } },
    });
    const result = await asanaAPI.getStatus();
    expect(result.status_mapping).toEqual({ new: 'new', done: 'resolved' });
  });

  it('getStatus parses a null status_mapping when unset', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { connected: true, status_mapping: null } });
    const result = await asanaAPI.getStatus();
    expect(result.status_mapping).toBeNull();
  });

  it('disconnect calls DELETE /api/v1/integrations/asana/disconnect', async () => {
    (apiClient.delete as any).mockResolvedValue({ data: { success: true, message: 'ok' } });
    const result = await asanaAPI.disconnect();
    expect(apiClient.delete).toHaveBeenCalledWith('/api/v1/integrations/asana/disconnect');
    expect(result.success).toBe(true);
  });

  it('testConnection calls POST /api/v1/integrations/asana/test', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { success: true, message: 'Asana connection is healthy.' },
    });
    const result = await asanaAPI.testConnection();
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/asana/test');
    expect(result.success).toBe(true);
  });

  it('getWorkspaces calls GET /api/v1/integrations/asana/workspaces', async () => {
    (apiClient.get as any).mockResolvedValue({
      data: [{ gid: '111', name: 'Acme Workspace' }],
    });
    const result = await asanaAPI.getWorkspaces();
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/integrations/asana/workspaces');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('Acme Workspace');
  });

  it('getProjects calls GET /api/v1/integrations/asana/projects with workspace_gid param', async () => {
    (apiClient.get as any).mockResolvedValue({
      data: [{ gid: '222', name: 'Engineering' }],
    });
    const result = await asanaAPI.getProjects('111');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/integrations/asana/projects', {
      params: { workspace_gid: '111' },
    });
    expect(result[0].name).toBe('Engineering');
  });

  it('createTask calls POST /api/v1/integrations/asana/tasks', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: {
        asana_task_gid: '333',
        asana_task_url: 'https://app.asana.com/0/222/333',
        asana_task_name: 'Fix the bug',
      },
    });
    const result = await asanaAPI.createTask({
      feedback_id: 42,
      workspace_gid: '111',
      project_gid: '222',
      name: 'Fix the bug',
      notes: 'Details here',
    });
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/asana/tasks', {
      feedback_id: 42,
      workspace_gid: '111',
      project_gid: '222',
      name: 'Fix the bug',
      notes: 'Details here',
    });
    expect(result.asana_task_gid).toBe('333');
  });

  it('createTask surfaces a 200 duplicate warning response', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: {
        warning: 'duplicate',
        existing_tasks: [
          { id: 1, asana_task_gid: '999', asana_task_url: 'https://app.asana.com/0/222/999', asana_task_name: 'Existing' },
        ],
      },
    });
    const result = await asanaAPI.createTask({
      feedback_id: 42,
      workspace_gid: '111',
      project_gid: '222',
      name: 'Fix the bug',
    });
    expect(result.warning).toBe('duplicate');
    expect(result.existing_tasks).toHaveLength(1);
  });

  it('getLinkedTasks calls GET /api/v1/integrations/asana/tasks with feedback_id param', async () => {
    (apiClient.get as any).mockResolvedValue({
      data: [
        {
          id: 1,
          feedback_id: 42,
          asana_task_gid: '333',
          asana_task_url: 'https://app.asana.com/0/222/333',
          asana_task_name: 'Fix the bug',
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
    });
    const result = await asanaAPI.getLinkedTasks(42);
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/integrations/asana/tasks', {
      params: { feedback_id: 42 },
    });
    expect(result).toHaveLength(1);
    expect(result[0].asana_task_gid).toBe('333');
  });

  it('patchAsanaStatusSync calls PATCH /api/v1/integrations/asana/status-sync with { enabled }', async () => {
    (apiClient.patch as any).mockResolvedValue({
      data: {
        connected: true,
        token_hint: '...abcd',
        account_gid: 'acc-1',
        display_name: 'Admin User',
        is_active: true,
        last_synced_at: null,
        last_sync_status: null,
        last_error: null,
        connected_at: '2026-01-01T00:00:00Z',
        status_sync_enabled: true,
        last_status_synced_at: null,
      },
    });
    const result = await patchAsanaStatusSync(true);
    expect(apiClient.patch).toHaveBeenCalledWith('/api/v1/integrations/asana/status-sync', {
      enabled: true,
    });
    expect(result.status_sync_enabled).toBe(true);
  });

  it('patchAsanaStatusSync includes status_mapping when provided', async () => {
    (apiClient.patch as any).mockResolvedValue({ data: { status_sync_enabled: true } });
    await patchAsanaStatusSync(true, { done: 'resolved' });
    expect(apiClient.patch).toHaveBeenCalledWith('/api/v1/integrations/asana/status-sync', {
      enabled: true,
      status_mapping: { done: 'resolved' },
    });
  });

  it('triggerAsanaSync calls POST /api/v1/integrations/asana/sync', async () => {
    (apiClient.post as any).mockResolvedValue({ data: { status: 'queued' } });
    const result = await triggerAsanaSync();
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/asana/sync');
    expect(result.status).toBe('queued');
  });
});
