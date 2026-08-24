import apiClient from '../api-client';
import { REPORT_TYPE_LABELS, REPORT_TYPE_COLORS, formatDateRangeLabel } from './reports';

// ─── Types ────────────────────────────────────────────────────────────────────

export type ReportCadence = 'daily' | 'weekly' | 'monthly';

export interface ScheduledReport {
  id: number;
  report_type: keyof typeof REPORT_TYPE_LABELS;
  date_range_days: number;
  cadence: ReportCadence;
  hour_utc: number;
  day_of_week: number | null;
  day_of_month: number | null;
  recipients: string[];
  enabled: boolean;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduledReportCreatePayload {
  report_type: keyof typeof REPORT_TYPE_LABELS;
  date_range_days: number;
  cadence: ReportCadence;
  hour_utc: number;
  day_of_week?: number | null;
  day_of_month?: number | null;
  recipients?: string[];
}

export type ScheduledReportUpdatePayload = Partial<ScheduledReportCreatePayload>;

// ─── API ──────────────────────────────────────────────────────────────────────

export const scheduledReportsAPI = {
  async list(): Promise<ScheduledReport[]> {
    const response = await apiClient.get('/api/v1/report-schedules');
    return Array.isArray(response.data) ? response.data : [];
  },

  async create(payload: ScheduledReportCreatePayload): Promise<ScheduledReport> {
    const response = await apiClient.post('/api/v1/report-schedules', payload);
    return response.data;
  },

  async update(id: number, payload: ScheduledReportUpdatePayload): Promise<ScheduledReport> {
    const response = await apiClient.patch(`/api/v1/report-schedules/${id}`, payload);
    return response.data;
  },

  async delete(id: number): Promise<void> {
    await apiClient.delete(`/api/v1/report-schedules/${id}`);
  },

  async toggle(id: number): Promise<ScheduledReport> {
    const response = await apiClient.post(`/api/v1/report-schedules/${id}/toggle`);
    return response.data;
  },
};

export { REPORT_TYPE_LABELS, REPORT_TYPE_COLORS, formatDateRangeLabel };