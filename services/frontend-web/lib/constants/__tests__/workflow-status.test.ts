import { describe, it, expect } from 'vitest';
import { REREFLECT_STATUSES } from '@/lib/constants/workflow-status';

describe('REREFLECT_STATUSES', () => {
  it('exports the four canonical workflow statuses in order', () => {
    expect(REREFLECT_STATUSES).toEqual([
      { value: 'new', label: 'New' },
      { value: 'in_review', label: 'In Review' },
      { value: 'resolved', label: 'Resolved' },
      { value: 'closed', label: 'Closed' },
    ]);
  });
});
