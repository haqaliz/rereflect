import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing intercom
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import apiClient from '@/lib/api-client';
import { intercomAPI } from '@/lib/api/intercom';

describe('intercomAPI', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getStatus calls GET /api/v1/integrations/intercom/status', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { connected: false } });
    const result = await intercomAPI.getStatus();
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/integrations/intercom/status',
    );
    expect(result.connected).toBe(false);
  });

  it('updateWriteback calls PATCH /api/v1/integrations/intercom/writeback with {enabled, action}', async () => {
    (apiClient.patch as any).mockResolvedValue({
      data: {
        writeback_enabled: true,
        writeback_action: 'note_only',
        last_writeback_at: null,
        last_writeback_status: null,
        last_writeback_error: null,
      },
    });
    const result = await intercomAPI.updateWriteback({
      enabled: true,
      action: 'note_only',
    });
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/api/v1/integrations/intercom/writeback',
      { enabled: true, action: 'note_only' },
    );
    expect(result.writeback_enabled).toBe(true);
  });

  it('updateWriteback omits action when not passed', async () => {
    (apiClient.patch as any).mockResolvedValue({
      data: {
        writeback_enabled: false,
        writeback_action: 'note_and_close',
        last_writeback_at: null,
        last_writeback_status: null,
        last_writeback_error: null,
      },
    });
    await intercomAPI.updateWriteback({ enabled: false });
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/api/v1/integrations/intercom/writeback',
      { enabled: false, action: undefined },
    );
  });

  it('updateWriteback returns the five writeback fields', async () => {
    (apiClient.patch as any).mockResolvedValue({
      data: {
        writeback_enabled: true,
        writeback_action: 'note_and_close',
        last_writeback_at: '2026-08-14T12:00:00Z',
        last_writeback_status: 'ok',
        last_writeback_error: null,
      },
    });
    const result = await intercomAPI.updateWriteback({ enabled: true });
    expect(result).toEqual({
      writeback_enabled: true,
      writeback_action: 'note_and_close',
      last_writeback_at: '2026-08-14T12:00:00Z',
      last_writeback_status: 'ok',
      last_writeback_error: null,
    });
  });

  it('testWriteback calls POST /api/v1/integrations/intercom/writeback/test with no body', async () => {
    (apiClient.post as any).mockResolvedValue({ data: { ok: true, reason: null } });
    const result = await intercomAPI.testWriteback();
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/integrations/intercom/writeback/test',
    );
    expect(result.ok).toBe(true);
  });

  it('testWriteback surfaces {ok: false, reason} untouched', async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { ok: false, reason: 'missing_write_scope' },
    });
    const result = await intercomAPI.testWriteback();
    expect(result.ok).toBe(false);
    expect(result.reason).toBe('missing_write_scope');
  });
});
