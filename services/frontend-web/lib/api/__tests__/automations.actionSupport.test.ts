import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api-client', () => {
  const mockClient = { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import { automationsAPI } from '@/lib/api/automations';

const mockGet = apiClient.get as unknown as ReturnType<typeof vi.fn>;

describe('automationsAPI.getActionSupport', () => {
  beforeEach(() => vi.clearAllMocks());

  it('GETs the action-support matrix and returns it unchanged', async () => {
    const matrix = {
      feedback_category_match: ['auto_assign', 'change_status', 'send_notification', 'draft_response', 'send_customer_email'],
      usage_trend: ['send_notification', 'run_playbook', 'send_customer_email'],
    };
    mockGet.mockResolvedValue({ data: matrix });

    const result = await automationsAPI.getActionSupport();

    expect(mockGet).toHaveBeenCalledWith('/api/v1/automations/action-support');
    expect(result).toEqual(matrix);
  });
});
