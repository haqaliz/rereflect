import apiClient from '../api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

export type ReportType =
  | 'executive_summary'
  | 'customer_health'
  | 'feature_prioritization'
  | 'churn_risk';

export interface ReportSectionData {
  type: 'table';
  columns: string[];
  rows: any[][];
}

export interface ReportSectionChart {
  type: 'line' | 'bar' | 'pie';
  data: any[];
}

export interface ReportSection {
  heading: string;
  narrative: string;
  data?: ReportSectionData;
  chart?: ReportSectionChart;
}

export interface Report {
  id: number;
  report_type: ReportType;
  date_range_days: number;
  title: string;
  sections: ReportSection[];
  metadata: Record<string, any>;
  pdf_generated: boolean;
  created_at: string;
}

export interface ReportsListResponse {
  reports: Report[];
  total: number;
}

// ─── API ──────────────────────────────────────────────────────────────────────

export const reportsAPI = {
  async list(): Promise<Report[]> {
    const response = await apiClient.get('/api/v1/reports');
    return Array.isArray(response.data) ? response.data : response.data.reports ?? [];
  },

  async get(id: number): Promise<Report> {
    const response = await apiClient.get(`/api/v1/reports/${id}`);
    return response.data;
  },

  async delete(id: number): Promise<void> {
    await apiClient.delete(`/api/v1/reports/${id}`);
  },

  async downloadPDF(id: number): Promise<void> {
    const response = await apiClient.get(`/api/v1/reports/${id}/pdf`, {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `report-${id}.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
  executive_summary: 'Executive Summary',
  customer_health: 'Customer Health',
  feature_prioritization: 'Feature Prioritization',
  churn_risk: 'Churn Risk',
};

export const REPORT_TYPE_COLORS: Record<ReportType, string> = {
  executive_summary: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  customer_health: 'bg-green-500/10 text-green-600 dark:text-green-400',
  feature_prioritization: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  churn_risk: 'bg-red-500/10 text-red-600 dark:text-red-400',
};

export function formatDateRangeLabel(days: number): string {
  if (days === 7) return 'Last 7 days';
  if (days === 30) return 'Last 30 days';
  if (days === 90) return 'Last 90 days';
  return `Last ${days} days`;
}
