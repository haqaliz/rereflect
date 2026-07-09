import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the api-client so no real HTTP calls are made
vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import { customersAPI, type Cohort, type BulkActionSummary } from '@/lib/api/customers';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPost = apiClient.post as ReturnType<typeof vi.fn>;

const mockSummary: BulkActionSummary = { matched: 3, updated: 3, skipped: 0, errors: [] };

describe('customersAPI.bulkTag — cohort serialization', () => {
  beforeEach(() => vi.clearAllMocks());

  it('email-mode cohort sends { emails } (not filter)', async () => {
    mockPost.mockResolvedValue({ data: mockSummary });
    const cohort: Cohort = { emails: ['a@co.com', 'b@co.com'] };
    await customersAPI.bulkTag(cohort, ['vip'], 'add');

    expect(mockPost).toHaveBeenCalledWith('/api/v1/customers/bulk/tags', {
      cohort: { emails: ['a@co.com', 'b@co.com'] },
      tags: ['vip'],
      mode: 'add',
    });
    const body = mockPost.mock.calls[0][1];
    expect(body.cohort).not.toHaveProperty('filter');
  });

  it('filter-mode cohort sends { filter } (not emails) with backend-identical key names', async () => {
    mockPost.mockResolvedValue({ data: mockSummary });
    const cohort: Cohort = {
      filter: { segment: 'at_risk', risk_level: 'critical', search: 'acme', include_archived: false },
    };
    await customersAPI.bulkTag(cohort, ['at-risk-q3'], 'remove');

    expect(mockPost).toHaveBeenCalledWith('/api/v1/customers/bulk/tags', {
      cohort: {
        filter: { segment: 'at_risk', risk_level: 'critical', search: 'acme', include_archived: false },
      },
      tags: ['at-risk-q3'],
      mode: 'remove',
    });
    const body = mockPost.mock.calls[0][1];
    expect(body.cohort).not.toHaveProperty('emails');
  });

  it('returns the BulkActionSummary from the response', async () => {
    mockPost.mockResolvedValue({ data: mockSummary });
    const result = await customersAPI.bulkTag({ emails: ['a@co.com'] }, ['vip'], 'add');
    expect(result).toEqual(mockSummary);
  });
});

describe('customersAPI.bulkAssignOwner — cohort serialization', () => {
  beforeEach(() => vi.clearAllMocks());

  it('email-mode cohort sends { emails, user_id }', async () => {
    mockPost.mockResolvedValue({ data: mockSummary });
    const cohort: Cohort = { emails: ['a@co.com'] };
    await customersAPI.bulkAssignOwner(cohort, 42);

    expect(mockPost).toHaveBeenCalledWith('/api/v1/customers/bulk/assign-owner', {
      cohort: { emails: ['a@co.com'] },
      user_id: 42,
    });
  });

  it('filter-mode cohort sends { filter, user_id }', async () => {
    mockPost.mockResolvedValue({ data: mockSummary });
    const cohort: Cohort = { filter: { segment: 'dormant' } };
    await customersAPI.bulkAssignOwner(cohort, 7);

    expect(mockPost).toHaveBeenCalledWith('/api/v1/customers/bulk/assign-owner', {
      cohort: { filter: { segment: 'dormant' } },
      user_id: 7,
    });
  });

  it('null user_id clears the owner (Unassign)', async () => {
    mockPost.mockResolvedValue({ data: mockSummary });
    await customersAPI.bulkAssignOwner({ emails: ['a@co.com'] }, null);

    expect(mockPost).toHaveBeenCalledWith('/api/v1/customers/bulk/assign-owner', {
      cohort: { emails: ['a@co.com'] },
      user_id: null,
    });
  });
});

describe('customersAPI.exportCustomers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    if (!('createObjectURL' in window.URL)) {
      (window.URL as unknown as { createObjectURL: () => string }).createObjectURL = () => 'blob:mock';
    }
    if (!('revokeObjectURL' in window.URL)) {
      (window.URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = () => {};
    }
    vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:mock');
    vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {});
  });

  it('hits GET /api/v1/customers/export with active filters as query params', async () => {
    mockGet.mockResolvedValue({ data: new Blob(['csv']), headers: {} });
    await customersAPI.exportCustomers({
      segment: 'at_risk',
      risk_level: 'critical',
      search: 'acme',
      include_archived: true,
      sort_by: 'health_score',
      sort_order: 'desc',
    });

    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/customers/export?'),
      { responseType: 'blob' }
    );
    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain('segment=at_risk');
    expect(url).toContain('risk_level=critical');
    expect(url).toContain('search=acme');
    expect(url).toContain('include_archived=true');
    expect(url).toContain('sort_by=health_score');
    expect(url).toContain('sort_order=desc');
  });

  it('omits unset filters from the query string', async () => {
    mockGet.mockResolvedValue({ data: new Blob(['csv']), headers: {} });
    await customersAPI.exportCustomers({});

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).not.toContain('segment=');
    expect(url).not.toContain('risk_level=');
    expect(url).not.toContain('search=');
  });
});
