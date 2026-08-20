import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import {
  ACTION_TYPE_LABELS,
  automationsAPI,
  type ActionType,
  type AutomationEmailDelivery,
  type SendCustomerEmailConfig,
} from '@/lib/api/automations';

const mockGet = apiClient.get as unknown as ReturnType<typeof vi.fn>;

describe('automations send_customer_email surface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('adds send_customer_email to the ActionType union', () => {
    const type: ActionType = 'send_customer_email';
    expect(type).toBe('send_customer_email');
  });

  it('labels the action type', () => {
    expect(ACTION_TYPE_LABELS.send_customer_email).toBe('Send Customer Email');
  });

  it('type-checks the config shape the backend accepts', () => {
    const cfg: SendCustomerEmailConfig = {
      template: 're_engagement',
      recipient: 'customer',
    };
    expect(Object.keys(cfg).sort()).toEqual(['recipient', 'template']);

    // @ts-expect-error — recipient is 'customer' | 'cs_assignee'
    const bad: SendCustomerEmailConfig = { template: 're_engagement', recipient: 'bogus' };
    expect(bad.recipient).toBe('bogus');
  });

  it('listDeliveries GETs the rule-scoped endpoint', async () => {
    mockGet.mockResolvedValue({ data: { deliveries: [], total: 0 } });
    await automationsAPI.listDeliveries(5);
    expect(mockGet).toHaveBeenCalledWith('/api/v1/automations/5/deliveries');
  });

  it('normalizes both an envelope body and a bare array body', async () => {
    const row: AutomationEmailDelivery = {
      id: 1,
      rule_id: 5,
      customer_email: 'a@b.com',
      to_email: 'a@b.com',
      template_key: 're_engagement',
      subject: 'Hi',
      status: 'queued',
      reason: null,
      created_at: '2026-08-01T00:00:00Z',
    };

    mockGet.mockResolvedValue({ data: { deliveries: [row], total: 1 } });
    expect(await automationsAPI.listDeliveries(5)).toEqual([row]);

    mockGet.mockResolvedValue({ data: [row] });
    expect(await automationsAPI.listDeliveries(5)).toEqual([row]);

    mockGet.mockResolvedValue({ data: {} });
    expect(await automationsAPI.listDeliveries(5)).toEqual([]);
  });
});
