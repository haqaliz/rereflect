import apiClient from '../api-client';

export interface InsightItem {
  title: string;
  description: string;
  category: string;
  priority: string;
}

export interface WeeklyInsight {
  id: number;
  organization_id: number;
  week_start: string;
  week_end: string;
  insights: InsightItem[];
  generated_at: string;
}

export interface WeeklyInsightListResponse {
  items: WeeklyInsight[];
  total: number;
}

export const insightsAPI = {
  getLatest: async (): Promise<WeeklyInsight | null> => {
    const response = await apiClient.get('/api/v1/insights/weekly');
    return response.data;
  },

  getHistory: async (limit = 10): Promise<WeeklyInsightListResponse> => {
    const response = await apiClient.get(`/api/v1/insights/weekly/history?limit=${limit}`);
    return response.data;
  },
};
