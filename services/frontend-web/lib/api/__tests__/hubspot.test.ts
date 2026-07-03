import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing hubspot
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import apiClient from '@/lib/api-client';
import { hubspotAPI } from '@/lib/api/hubspot';

describe('hubspotAPI', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getStatus calls GET /api/v1/integrations/hubspot/status', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { connected: false } });
    const result = await hubspotAPI.getStatus();
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/integrations/hubspot/status',
    );
    expect(result.connected).toBe(false);
  });

  it('connect calls POST /api/v1/integrations/hubspot/connect', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { connected: true, portal_name: 'Acme', hub_id: '123', token_hint: '...abcd' },
    });
    const result = await hubspotAPI.connect('pat-na1-xxxxx');
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/integrations/hubspot/connect',
      { access_token: 'pat-na1-xxxxx', arr_property_name: 'annualrevenue' },
    );
    expect(result.connected).toBe(true);
  });

  it('connect passes custom arr_property_name', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { connected: true, portal_name: 'Acme', hub_id: '123', token_hint: '...abcd' },
    });
    await hubspotAPI.connect('tok', 'mrr');
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/integrations/hubspot/connect',
      { access_token: 'tok', arr_property_name: 'mrr' },
    );
  });

  it('disconnect calls DELETE /api/v1/integrations/hubspot/disconnect', async () => {
    (apiClient.delete as any).mockResolvedValue({ data: { success: true } });
    await hubspotAPI.disconnect();
    expect(apiClient.delete).toHaveBeenCalledWith(
      '/api/v1/integrations/hubspot/disconnect',
    );
  });

  it('testConnection calls POST /api/v1/integrations/hubspot/test', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { success: true, message: 'HubSpot connection is healthy.' },
    });
    const result = await hubspotAPI.testConnection();
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/integrations/hubspot/test',
    );
    expect(result.success).toBe(true);
  });

  it('updateWriteback calls PATCH /api/v1/integrations/hubspot/writeback with enabled + field_name', async () => {
    (apiClient.patch as any).mockResolvedValue({
      data: {
        writeback_enabled: true,
        writeback_field_name: 'rereflect_health_score',
        last_writeback_at: null,
        last_writeback_status: null,
        last_writeback_error: null,
        contacts_written: 0,
      },
    });
    const result = await hubspotAPI.updateWriteback({
      enabled: true,
      field_name: 'rereflect_health_score',
    });
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/api/v1/integrations/hubspot/writeback',
      { enabled: true, field_name: 'rereflect_health_score' },
    );
    expect(result.writeback_enabled).toBe(true);
  });

  it('updateWriteback allows disabling with a null field_name', async () => {
    (apiClient.patch as any).mockResolvedValue({
      data: {
        writeback_enabled: false,
        writeback_field_name: null,
        last_writeback_at: null,
        last_writeback_status: null,
        last_writeback_error: null,
        contacts_written: 0,
      },
    });
    const result = await hubspotAPI.updateWriteback({ enabled: false, field_name: null });
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/api/v1/integrations/hubspot/writeback',
      { enabled: false, field_name: null },
    );
    expect(result.writeback_enabled).toBe(false);
  });

  it('testWriteback calls POST /api/v1/integrations/hubspot/writeback/test with field_name', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { ok: true, reason: null },
    });
    const result = await hubspotAPI.testWriteback('rereflect_health_score');
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/integrations/hubspot/writeback/test',
      { field_name: 'rereflect_health_score' },
    );
    expect(result.ok).toBe(true);
  });

  it('testWriteback surfaces a failed validation reason', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { ok: false, reason: 'field_not_found' },
    });
    const result = await hubspotAPI.testWriteback('bogus_field');
    expect(result.ok).toBe(false);
    expect(result.reason).toBe('field_not_found');
  });
});
