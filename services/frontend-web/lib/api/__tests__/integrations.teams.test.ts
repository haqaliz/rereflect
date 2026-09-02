import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing integrations
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import apiClient from '@/lib/api-client';
import { integrationsAPI } from '@/lib/api/integrations';

describe('integrationsAPI - Teams endpoints', () => {
  beforeEach(() => vi.clearAllMocks());

  it('createTeamsWebhook POSTs /api/v1/integrations/teams/webhook with the Discord-shaped payload', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { id: 42, type: 'teams', name: 'Product Alerts' },
    });

    const data = {
      name: 'Product Alerts',
      webhook_url: 'https://outlook.office.com/webhook/abc/def',
      triggers: ['urgent'],
      included_fields: ['text', 'sentiment'],
      digest_time: '09:00',
      message_template: 'New feedback: {{text}}',
    };
    const result = await integrationsAPI.createTeamsWebhook(data);

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/integrations/teams/webhook',
      data,
    );
    expect(result).toEqual({ id: 42, type: 'teams', name: 'Product Alerts' });
  });

  it('createTeamsWebhook accepts an optional-only payload (name + webhook_url)', async () => {
    (apiClient.post as any).mockResolvedValue({ data: { id: 43, type: 'teams' } });

    await integrationsAPI.createTeamsWebhook({
      name: 'Minimal',
      webhook_url: 'https://webhook.office.com/webhookb2/xyz',
    });

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/teams/webhook', {
      name: 'Minimal',
      webhook_url: 'https://webhook.office.com/webhookb2/xyz',
    });
  });

  it('testTeams POSTs /api/v1/integrations/teams/test with integration_id', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { success: true, message: 'Teams test sent' },
    });

    const result = await integrationsAPI.testTeams(7);

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/teams/test', {
      integration_id: 7,
    });
    expect(result).toEqual({ success: true, message: 'Teams test sent' });
  });
});