import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing zendesk
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import apiClient from '@/lib/api-client';
import { zendeskAPI, patchZendeskStatusSync, triggerZendeskStatusSync } from '@/lib/api/zendesk';

describe('zendeskAPI', () => {
  beforeEach(() => vi.clearAllMocks());

  it('connect calls POST /api/v1/integrations/zendesk/connect with subdomain, email, api_token', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: {
        connected: true,
        subdomain: 'acme',
        email: 'operator@acme.com',
        token_hint: '...9999',
        account_user_id: '12345',
        display_name: 'Jane Agent',
        webhook_secret: 'kf3n2-redacted-9x',
        has_feedback_source: true,
      },
    });
    const result = await zendeskAPI.connect({
      subdomain: 'acme',
      email: 'operator@acme.com',
      api_token: 'zd-token-abc',
    });
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/zendesk/connect', {
      subdomain: 'acme',
      email: 'operator@acme.com',
      api_token: 'zd-token-abc',
    });
    expect(result.connected).toBe(true);
    expect(result.subdomain).toBe('acme');
    expect(result.webhook_secret).toBe('kf3n2-redacted-9x');
    expect(result.has_feedback_source).toBe(true);
  });

  it('getStatus calls GET /api/v1/integrations/zendesk/status', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { connected: false } });
    const result = await zendeskAPI.getStatus();
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/integrations/zendesk/status');
    expect(result.connected).toBe(false);
  });

  it('getStatus returns connected status with subdomain + has_feedback_source, never webhook_secret', async () => {
    (apiClient.get as any).mockResolvedValue({
      data: {
        connected: true,
        subdomain: 'acme',
        email: 'operator@acme.com',
        token_hint: '...9999',
        account_user_id: '12345',
        display_name: 'Jane Agent',
        is_active: true,
        last_synced_at: null,
        last_sync_status: null,
        last_error: null,
        connected_at: '2026-07-05T12:00:00',
        has_feedback_source: true,
      },
    });
    const result = await zendeskAPI.getStatus();
    expect(result.subdomain).toBe('acme');
    expect(result.has_feedback_source).toBe(true);
    expect((result as any).webhook_secret).toBeUndefined();
  });

  it('disconnect calls DELETE /api/v1/integrations/zendesk/disconnect', async () => {
    (apiClient.delete as any).mockResolvedValue({ data: { success: true, message: 'ok' } });
    const result = await zendeskAPI.disconnect();
    expect(apiClient.delete).toHaveBeenCalledWith('/api/v1/integrations/zendesk/disconnect');
    expect(result.success).toBe(true);
  });

  it('testConnection calls POST /api/v1/integrations/zendesk/test', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { success: true, message: 'Zendesk connection is healthy.' },
    });
    const result = await zendeskAPI.testConnection();
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/zendesk/test');
    expect(result.success).toBe(true);
  });

  it('triggerSync calls POST /api/v1/integrations/zendesk/sync', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { status: 'queued', integration_id: 7 },
    });
    const result = await zendeskAPI.triggerSync();
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/zendesk/sync');
    expect(result.status).toBe('queued');
    expect(result.integration_id).toBe(7);
  });

  it('patchZendeskStatusSync calls PATCH /api/v1/integrations/zendesk/status-sync with { enabled }', async () => {
    (apiClient.patch as any).mockResolvedValue({
      data: {
        connected: true,
        subdomain: 'acme',
        email: 'operator@acme.com',
        token_hint: '...9999',
        account_user_id: '12345',
        display_name: 'Jane Agent',
        is_active: true,
        last_synced_at: null,
        last_sync_status: null,
        last_error: null,
        connected_at: '2026-01-01T00:00:00Z',
        status_sync_enabled: true,
        status_mapping: null,
        last_status_synced_at: null,
        last_status_sync_error: null,
      },
    });
    const result = await patchZendeskStatusSync(true);
    expect(apiClient.patch).toHaveBeenCalledWith('/api/v1/integrations/zendesk/status-sync', {
      enabled: true,
    });
    expect(result.status_sync_enabled).toBe(true);
  });

  it('patchZendeskStatusSync includes status_mapping when provided', async () => {
    (apiClient.patch as any).mockResolvedValue({ data: { status_sync_enabled: true } });
    await patchZendeskStatusSync(true, { solved: 'resolved' });
    expect(apiClient.patch).toHaveBeenCalledWith('/api/v1/integrations/zendesk/status-sync', {
      enabled: true,
      status_mapping: { solved: 'resolved' },
    });
  });

  it('triggerZendeskStatusSync calls POST /api/v1/integrations/zendesk/status-sync/sync', async () => {
    (apiClient.post as any).mockResolvedValue({ data: { status: 'queued' } });
    const result = await triggerZendeskStatusSync();
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/zendesk/status-sync/sync');
    expect(result.status).toBe('queued');
  });
});
