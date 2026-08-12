import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient, publicApiClient: mockClient };
});

import apiClient, { publicApiClient } from '@/lib/api-client';
import {
  createCampaign,
  draftCampaign,
  listCampaigns,
  retryCampaign,
  unsubscribe,
  OutreachDraftApiError,
} from '@/lib/api/outreach';

const mockPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPublicGet = publicApiClient.get as ReturnType<typeof vi.fn>;

const COHORT = { emails: ['a@co.com', 'b@co.com'] };

describe('createCampaign — POST /api/v1/customers/bulk/outreach', () => {
  beforeEach(() => vi.clearAllMocks());

  it('POSTs {cohort, subject, body} and parses the 202 send summary', async () => {
    mockPost.mockResolvedValue({
      status: 202,
      data: { matched: 2, queued: 1, skipped: 1, errors: ['b@co.com: send failed'] },
    });

    const result = await createCampaign({
      cohort: COHORT,
      subject: 'We miss you',
      body: 'Want to tell us what happened?',
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/customers/bulk/outreach',
      { cohort: COHORT, subject: 'We miss you', body: 'Want to tell us what happened?' },
      { params: undefined }
    );
    expect(result).toEqual({ matched: 2, queued: 1, skipped: 1, errors: ['b@co.com: send failed'] });
  });

  it('countOnly: true appends ?count_only=true with an identical payload (zero mutation)', async () => {
    mockPost.mockResolvedValue({
      status: 200,
      data: { matched: 250, queued: 0, skipped: 5, errors: [] },
    });

    const result = await createCampaign(
      { cohort: COHORT, subject: 'We miss you', body: 'Want to tell us what happened?' },
      { countOnly: true }
    );

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/customers/bulk/outreach',
      { cohort: COHORT, subject: 'We miss you', body: 'Want to tell us what happened?' },
      { params: { count_only: true } }
    );
    expect(result.matched).toBe(250);
    expect(result.queued).toBe(0);
    expect(result.errors).toEqual([]);
  });
});

describe('draftCampaign — POST /api/v1/customers/bulk/outreach/draft', () => {
  beforeEach(() => vi.clearAllMocks());

  it('POSTs {tone} and parses {subject, body}', async () => {
    mockPost.mockResolvedValue({
      data: { subject: 'A note from Acme', body: 'Hi there — we noticed you went quiet.' },
    });

    const result = await draftCampaign({ tone: 'friendly' });

    expect(mockPost).toHaveBeenCalledWith('/api/v1/customers/bulk/outreach/draft', {
      tone: 'friendly',
    });
    expect(result).toEqual({
      subject: 'A note from Acme',
      body: 'Hi there — we noticed you went quiet.',
    });
  });

  it('sends the optional cohort for context', async () => {
    mockPost.mockResolvedValue({
      data: { subject: 'S', body: 'B' },
    });

    await draftCampaign({ cohort: COHORT, tone: 'professional' });

    expect(mockPost).toHaveBeenCalledWith('/api/v1/customers/bulk/outreach/draft', {
      cohort: COHORT,
      tone: 'professional',
    });
  });

  it('throws an OutreachDraftApiError carrying status 409 on "no LLM configured"', async () => {
    mockPost.mockRejectedValue({
      response: { status: 409, data: { detail: 'No AI model configured.' } },
    });

    await expect(draftCampaign({ tone: 'friendly' })).rejects.toMatchObject({
      status: 409,
      message: 'No AI model configured.',
    });
    await expect(draftCampaign({ tone: 'friendly' })).rejects.toBeInstanceOf(OutreachDraftApiError);
  });

  it('throws an OutreachDraftApiError carrying status 422 on bad input', async () => {
    mockPost.mockRejectedValue({
      response: { status: 422, data: { detail: 'tone must be one of professional, friendly, ...' } },
    });

    await expect(draftCampaign({ tone: 'bossy' })).rejects.toMatchObject({ status: 422 });
  });

  it('throws an OutreachDraftApiError carrying status 502 on provider failure', async () => {
    mockPost.mockRejectedValue({
      response: { status: 502, data: { detail: 'The AI provider returned an unusable draft.' } },
    });

    await expect(draftCampaign({ tone: 'friendly' })).rejects.toMatchObject({
      status: 502,
      message: 'The AI provider returned an unusable draft.',
    });
  });

  it('falls back to a generic message when the error has no response body', async () => {
    mockPost.mockRejectedValue(new Error('Network error'));

    await expect(draftCampaign({ tone: 'friendly' })).rejects.toMatchObject({
      status: 0,
      message: 'Network error',
    });
  });
});

describe('listCampaigns — GET /api/v1/outreach/campaigns', () => {
  beforeEach(() => vi.clearAllMocks());

  it('GETs with page params and returns the paged envelope with per-recipient counts', async () => {
    const campaign = {
      id: 7,
      subject: 'We miss you',
      status: 'in_progress',
      recipient_count: 3,
      counts: { queued: 1, sent: 1, skipped: 1, failed: 0 },
      created_at: '2026-08-12T10:00:00Z',
    };
    mockGet.mockResolvedValue({
      data: { items: [campaign], total: 1, page: 1, page_size: 5 },
    });

    const result = await listCampaigns({ page: 1, page_size: 5 });

    expect(mockGet).toHaveBeenCalledWith('/api/v1/outreach/campaigns', {
      params: { page: 1, page_size: 5 },
    });
    expect(result).toEqual({ items: [campaign], total: 1, page: 1, page_size: 5 });
    expect(result.items[0].counts).toEqual({ queued: 1, sent: 1, skipped: 1, failed: 0 });
  });
});

describe('retryCampaign — POST /api/v1/outreach/campaigns/{id}/retry', () => {
  beforeEach(() => vi.clearAllMocks());

  it('POSTs the retry path and parses {matched, queued, skipped, errors}', async () => {
    mockPost.mockResolvedValue({
      data: { matched: 2, queued: 2, skipped: 0, errors: [] },
    });

    const result = await retryCampaign(42);

    expect(mockPost).toHaveBeenCalledWith('/api/v1/outreach/campaigns/42/retry');
    expect(result).toEqual({ matched: 2, queued: 2, skipped: 0, errors: [] });
  });
});

describe('unsubscribe — GET /api/v1/outreach/unsubscribe (public)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uses publicApiClient (no auth token) and resolves on a 2xx, whatever the body', async () => {
    mockPublicGet.mockResolvedValue({
      status: 200,
      data: '<html>you are unsubscribed</html>',
    });

    await expect(unsubscribe('signed-token-abc')).resolves.toBeUndefined();

    expect(mockPublicGet).toHaveBeenCalledWith('/api/v1/outreach/unsubscribe', {
      params: { token: 'signed-token-abc' },
    });
  });

  it('rejects on a 400 invalid token, surfacing the backend detail', async () => {
    mockPublicGet.mockRejectedValue({
      response: { status: 400, data: { detail: 'Invalid unsubscribe token.' } },
    });

    await expect(unsubscribe('garbage')).rejects.toThrow('Invalid unsubscribe token.');
  });
});
