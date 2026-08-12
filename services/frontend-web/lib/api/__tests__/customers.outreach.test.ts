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
import { customersAPI } from '@/lib/api/customers';

const mockPatch = apiClient.patch as ReturnType<typeof vi.fn>;

describe('customersAPI.updateOutreachOptOut', () => {
  beforeEach(() => vi.clearAllMocks());

  it('PATCHes /api/v1/customers/{encoded email} with only {"outreach_opt_out": true}', async () => {
    mockPatch.mockResolvedValue({ data: { customer_email: 'john@acme.com', outreach_opt_out: true } });

    const result = await customersAPI.updateOutreachOptOut('john+tag@acme.com', true);

    expect(mockPatch).toHaveBeenCalledWith(
      '/api/v1/customers/john%2Btag%40acme.com',
      { outreach_opt_out: true }
    );
    expect(result.outreach_opt_out).toBe(true);
  });

  it('toggles off with exactly {"outreach_opt_out": false}', async () => {
    mockPatch.mockResolvedValue({ data: { customer_email: 'john@acme.com', outreach_opt_out: false } });

    await customersAPI.updateOutreachOptOut('john@acme.com', false);

    expect(mockPatch).toHaveBeenCalledWith(
      '/api/v1/customers/john%40acme.com',
      { outreach_opt_out: false }
    );
  });
});
