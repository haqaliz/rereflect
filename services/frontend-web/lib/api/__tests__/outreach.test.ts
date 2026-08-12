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
import { listOutreachTemplates, BUILTIN_OUTREACH_TEMPLATES } from '@/lib/api/outreach';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;

describe('listOutreachTemplates', () => {
  beforeEach(() => vi.clearAllMocks());

  it('GETs /api/v1/outreach/templates and returns the registry summaries', async () => {
    const registry = [
      { key: 're_engagement', label: 'Re-engagement check-in', description: 'nudge' },
      { key: 'weekly_digest_entry', label: 'Weekly digest entry', description: 'digest' },
    ];
    mockGet.mockResolvedValue({ data: registry });

    const result = await listOutreachTemplates();

    expect(mockGet).toHaveBeenCalledWith('/api/v1/outreach/templates');
    expect(result).toEqual(registry);
  });

  it('exports the two contract-pinned built-in template keys with registry labels', () => {
    expect(BUILTIN_OUTREACH_TEMPLATES.map((t) => t.key)).toEqual([
      're_engagement',
      'weekly_digest_entry',
    ]);
    expect(BUILTIN_OUTREACH_TEMPLATES[0].label).toBe('Re-engagement check-in');
    expect(BUILTIN_OUTREACH_TEMPLATES[1].label).toBe('Weekly digest entry');
  });
});
