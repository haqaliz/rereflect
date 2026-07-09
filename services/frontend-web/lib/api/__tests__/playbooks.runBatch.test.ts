import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import { runPlaybookBatch } from '@/lib/api/playbooks';

const mockPost = apiClient.post as ReturnType<typeof vi.fn>;

describe('runPlaybookBatch — cohort/filters payload', () => {
  beforeEach(() => vi.clearAllMocks());

  it('email-mode cohort sends filters.emails', async () => {
    mockPost.mockResolvedValue({ data: { queued: 2, execution_ids: [1, 2], matched: 2 } });
    await runPlaybookBatch(5, { emails: ['a@co.com', 'b@co.com'] });

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/playbooks/5/run-batch',
      { filters: { emails: ['a@co.com', 'b@co.com'] } },
      { params: undefined }
    );
  });

  it('filter/segment-mode cohort sends filters.segment (not emails)', async () => {
    mockPost.mockResolvedValue({ data: { queued: 10, execution_ids: [], matched: 10 } });
    await runPlaybookBatch(5, { segment: 'at_risk' });

    const [, body] = mockPost.mock.calls[0];
    expect(body).toEqual({ filters: { segment: 'at_risk' } });
    expect(body.filters).not.toHaveProperty('emails');
  });

  it('combines cohort with a probability band', async () => {
    mockPost.mockResolvedValue({ data: { queued: 0, execution_ids: [], matched: 4 } });
    await runPlaybookBatch(5, { segment: 'at_risk', probability_min: 0.5, probability_max: 0.9 });

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/playbooks/5/run-batch',
      { filters: { segment: 'at_risk', probability_min: 0.5, probability_max: 0.9 } },
      { params: undefined }
    );
  });

  it('countOnly=true passes ?count_only=true and does not queue', async () => {
    mockPost.mockResolvedValue({ data: { queued: 0, execution_ids: [], matched: 250 } });
    const result = await runPlaybookBatch(5, { segment: 'at_risk' }, { countOnly: true });

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/playbooks/5/run-batch',
      { filters: { segment: 'at_risk' } },
      { params: { count_only: true } }
    );
    expect(result.matched).toBe(250);
    expect(result.queued).toBe(0);
  });
});
