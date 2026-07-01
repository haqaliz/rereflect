import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing salesforce
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import apiClient from '@/lib/api-client';
import { salesforceAPI } from '@/lib/api/salesforce';

describe('salesforceAPI', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getConnectUrl calls GET /api/v1/integrations/salesforce/connect-url with credentials and returns auth_url', async () => {
    (apiClient.get as any).mockResolvedValue({
      data: { auth_url: 'https://login.salesforce.com/services/oauth2/authorize?...' },
    });
    const result = await salesforceAPI.getConnectUrl();
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/integrations/salesforce/connect-url',
      { withCredentials: true },
    );
    expect(result.auth_url).toBe(
      'https://login.salesforce.com/services/oauth2/authorize?...',
    );
  });

  it('getStatus calls GET /api/v1/integrations/salesforce/status', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { connected: false } });
    const result = await salesforceAPI.getStatus();
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/integrations/salesforce/status',
    );
    expect(result.connected).toBe(false);
  });

  it('disconnect calls DELETE /api/v1/integrations/salesforce/disconnect', async () => {
    (apiClient.delete as any).mockResolvedValue({
      data: { success: true, message: 'Salesforce integration disconnected.' },
    });
    const result = await salesforceAPI.disconnect();
    expect(apiClient.delete).toHaveBeenCalledWith(
      '/api/v1/integrations/salesforce/disconnect',
    );
    expect(result.success).toBe(true);
  });

  it('test calls POST /api/v1/integrations/salesforce/test', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { success: true, message: 'Salesforce connection is healthy.' },
    });
    const result = await salesforceAPI.test();
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/integrations/salesforce/test',
    );
    expect(result.success).toBe(true);
  });

  it('does not expose a connect(token) method — OAuth redirect only', () => {
    expect((salesforceAPI as any).connect).toBeUndefined();
  });
});
