import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiClient before importing scheduled-reports
vi.mock('@/lib/api-client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import apiClient from '@/lib/api-client';
import {
  scheduledReportsAPI,
  type ScheduledReport,
} from '@/lib/api/scheduled-reports';

describe('scheduledReportsAPI', () => {
  beforeEach(() => vi.clearAllMocks());

  it('list calls GET /api/v1/report-schedules', async () => {
    const schedules: ScheduledReport[] = [
      {
        id: 1,
        report_type: 'executive_summary',
        date_range_days: 30,
        cadence: 'weekly',
        hour_utc: 9,
        day_of_week: 0,
        day_of_month: null,
        recipients: ['owner@acme.com'],
        enabled: true,
        last_run_at: '2026-08-25T09:00:00Z',
        created_at: '2026-08-01T00:00:00Z',
        updated_at: '2026-08-01T00:00:00Z',
      },
    ];
    (apiClient.get as any).mockResolvedValue({ data: schedules });

    const result = await scheduledReportsAPI.list();

    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/report-schedules');
    expect(result).toEqual(schedules);
  });

  it('create calls POST /api/v1/report-schedules with the payload', async () => {
    const created: ScheduledReport = {
      id: 2,
      report_type: 'customer_health',
      date_range_days: 7,
      cadence: 'daily',
      hour_utc: 8,
      day_of_week: null,
      day_of_month: null,
      recipients: ['cs@acme.com'],
      enabled: true,
      last_run_at: null,
      created_at: '2026-08-25T00:00:00Z',
      updated_at: '2026-08-25T00:00:00Z',
    };
    (apiClient.post as any).mockResolvedValue({ data: created });

    const payload = {
      report_type: 'customer_health' as const,
      date_range_days: 7,
      cadence: 'daily' as const,
      hour_utc: 8,
      recipients: ['cs@acme.com'],
    };

    const result = await scheduledReportsAPI.create(payload);

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/report-schedules', payload);
    expect(result).toEqual(created);
  });

  it('update calls PATCH /api/v1/report-schedules/{id} with the payload', async () => {
    const updated: ScheduledReport = {
      id: 1,
      report_type: 'executive_summary',
      date_range_days: 90,
      cadence: 'weekly',
      hour_utc: 10,
      day_of_week: 1,
      day_of_month: null,
      recipients: ['owner@acme.com'],
      enabled: true,
      last_run_at: null,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-25T00:00:00Z',
    };
    (apiClient.patch as any).mockResolvedValue({ data: updated });

    const result = await scheduledReportsAPI.update(1, { hour_utc: 10 });

    expect(apiClient.patch).toHaveBeenCalledWith('/api/v1/report-schedules/1', {
      hour_utc: 10,
    });
    expect(result).toEqual(updated);
  });

  it('delete calls DELETE /api/v1/report-schedules/{id}', async () => {
    (apiClient.delete as any).mockResolvedValue({ data: null });

    await scheduledReportsAPI.delete(3);

    expect(apiClient.delete).toHaveBeenCalledWith('/api/v1/report-schedules/3');
  });

  it('toggle calls POST /api/v1/report-schedules/{id}/toggle and returns flipped schedule', async () => {
    const toggled: ScheduledReport = {
      id: 1,
      report_type: 'executive_summary',
      date_range_days: 30,
      cadence: 'weekly',
      hour_utc: 9,
      day_of_week: 0,
      day_of_month: null,
      recipients: ['owner@acme.com'],
      enabled: false,
      last_run_at: null,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-25T00:00:00Z',
    };
    (apiClient.post as any).mockResolvedValue({ data: toggled });

    const result = await scheduledReportsAPI.toggle(1);

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/report-schedules/1/toggle');
    expect(result.enabled).toBe(false);
  });
});