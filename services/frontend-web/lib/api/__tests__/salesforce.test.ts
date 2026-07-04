import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing salesforce
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
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

  it('updateWriteback calls PATCH /api/v1/integrations/salesforce/writeback with enabled + field_name', async () => {
    (apiClient.patch as any).mockResolvedValue({
      data: {
        writeback_enabled: true,
        writeback_field_name: 'Rereflect_Health_Score__c',
        last_writeback_at: null,
        last_writeback_status: null,
        last_writeback_error: null,
        contacts_written: 0,
      },
    });
    const result = await salesforceAPI.updateWriteback({
      enabled: true,
      field_name: 'Rereflect_Health_Score__c',
    });
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/api/v1/integrations/salesforce/writeback',
      { enabled: true, field_name: 'Rereflect_Health_Score__c' },
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
    const result = await salesforceAPI.updateWriteback({ enabled: false, field_name: null });
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/api/v1/integrations/salesforce/writeback',
      { enabled: false, field_name: null },
    );
    expect(result.writeback_enabled).toBe(false);
  });

  it('testWriteback calls POST /api/v1/integrations/salesforce/writeback/test with field_name', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { ok: true, reason: null },
    });
    const result = await salesforceAPI.testWriteback('Rereflect_Health_Score__c');
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/integrations/salesforce/writeback/test',
      { field_name: 'Rereflect_Health_Score__c' },
    );
    expect(result.ok).toBe(true);
  });

  it('testWriteback surfaces a failed validation reason', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { ok: false, reason: 'field_not_found' },
    });
    const result = await salesforceAPI.testWriteback('Bogus__c');
    expect(result.ok).toBe(false);
    expect(result.reason).toBe('field_not_found');
  });
});
