import { describe, it, expect, vi } from 'vitest';

// linear.ts imports apiClient at module scope — mock it before importing.
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

import { REREFLECT_STATUSES } from '@/lib/api/linear';
import { REREFLECT_STATUSES as SHARED_REREFLECT_STATUSES } from '@/lib/constants/workflow-status';

describe('linear.ts REREFLECT_STATUSES re-export', () => {
  it('re-exports the shared workflow-status constant unchanged', () => {
    expect(REREFLECT_STATUSES).toBe(SHARED_REREFLECT_STATUSES);
  });

  it('still exposes the four canonical statuses', () => {
    expect(REREFLECT_STATUSES).toEqual([
      { value: 'new', label: 'New' },
      { value: 'in_review', label: 'In Review' },
      { value: 'resolved', label: 'Resolved' },
      { value: 'closed', label: 'Closed' },
    ]);
  });
});
