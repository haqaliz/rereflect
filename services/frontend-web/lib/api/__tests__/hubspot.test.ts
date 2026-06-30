import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing hubspot
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
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
});
