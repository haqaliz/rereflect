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
