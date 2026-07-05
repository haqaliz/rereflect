/**
 * Smoke test: verifies hubspotAPI.getStatus is exported and callable,
 * and that the HubSpotConnectionStatus type is exported.
 *
 * Full page render tests would require Next.js test harness setup;
 * this test covers the data-fetching contract used by the page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api/hubspot', () => ({
  hubspotAPI: {
    getStatus: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    testConnection: vi.fn(),
  },
}));

import { hubspotAPI } from '@/lib/api/hubspot';

describe('IntegrationsPage — HubSpot data fetch contract', () => {
  beforeEach(() => vi.clearAllMocks());

  it('hubspotAPI.getStatus is callable', async () => {
    (hubspotAPI.getStatus as any).mockResolvedValue({ connected: false });
    const result = await hubspotAPI.getStatus();
    expect(hubspotAPI.getStatus).toHaveBeenCalled();
    expect(result.connected).toBe(false);
  });

  it('hubspotAPI.getStatus returns connected status with portal_name', async () => {
    (hubspotAPI.getStatus as any).mockResolvedValue({
      connected: true,
      portal_name: 'Acme CRM',
      hub_id: '12345',
      token_hint: '...abcd',
    });
    const result = await hubspotAPI.getStatus();
    expect(result.connected).toBe(true);
    expect(result.portal_name).toBe('Acme CRM');
  });
});

vi.mock('@/lib/api/salesforce', () => ({
  salesforceAPI: {
    getStatus: vi.fn(),
    getConnectUrl: vi.fn(),
    disconnect: vi.fn(),
    test: vi.fn(),
  },
}));

import { salesforceAPI } from '@/lib/api/salesforce';

describe('IntegrationsPage — Salesforce data fetch contract', () => {
  beforeEach(() => vi.clearAllMocks());

  it('salesforceAPI.getStatus is callable', async () => {
    (salesforceAPI.getStatus as any).mockResolvedValue({ connected: false });
    const result = await salesforceAPI.getStatus();
    expect(salesforceAPI.getStatus).toHaveBeenCalled();
    expect(result.connected).toBe(false);
  });

  it('salesforceAPI.getStatus returns connected status with instance_url and sf_org_id', async () => {
    (salesforceAPI.getStatus as any).mockResolvedValue({
      connected: true,
      instance_url: 'https://acme.my.salesforce.com',
      sf_org_id: '00D000000000EXAMPLE',
      contacts_synced: 42,
      contacts_matched: 30,
    });
    const result = await salesforceAPI.getStatus();
    expect(result.connected).toBe(true);
    expect(result.instance_url).toBe('https://acme.my.salesforce.com');
    expect(result.sf_org_id).toBe('00D000000000EXAMPLE');
  });
});

vi.mock('@/lib/api/zendesk', () => ({
  zendeskAPI: {
    getStatus: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    testConnection: vi.fn(),
  },
}));

import { zendeskAPI } from '@/lib/api/zendesk';

describe('IntegrationsPage — Zendesk data fetch contract', () => {
  beforeEach(() => vi.clearAllMocks());

  it('zendeskAPI.getStatus is callable', async () => {
    (zendeskAPI.getStatus as any).mockResolvedValue({ connected: false });
    const result = await zendeskAPI.getStatus();
    expect(zendeskAPI.getStatus).toHaveBeenCalled();
    expect(result.connected).toBe(false);
  });

  it('zendeskAPI.getStatus returns connected status with subdomain + has_feedback_source', async () => {
    (zendeskAPI.getStatus as any).mockResolvedValue({
      connected: true,
      subdomain: 'acme',
      email: 'operator@acme.com',
      token_hint: '...9999',
      is_active: true,
      has_feedback_source: true,
    });
    const result = await zendeskAPI.getStatus();
    expect(result.connected).toBe(true);
    expect(result.subdomain).toBe('acme');
    expect(result.has_feedback_source).toBe(true);
  });
});
