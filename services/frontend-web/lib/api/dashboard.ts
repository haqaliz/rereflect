import apiClient from '../api-client';

export interface SentimentStats {
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  total_count: number;
  average_score: number | null;
}

export interface PainPoint {
  issue: string;
  count: number;
  category: string | null;
  severity: string | null;
}

export interface FeatureRequest {
  feature: string;
  count: number;
  category: string | null;
  priority: string | null;
}

export interface CategoryCount {
  category: string;
  count: number;
  severity?: string | null;
  priority?: string | null;
  response_time?: string | null;
}

export interface TopCategory {
  tag: string;
  count: number;
}

export interface UrgentFeedback {
  id: number;
  text: string;
  sentiment_label: string | null;
  created_at: string;
  category: string | null;
  response_time: string | null;
}

export interface DashboardData {
  sentiment: SentimentStats;
  pain_points: PainPoint[];
  feature_requests: FeatureRequest[];
  top_categories: TopCategory[];
  urgent_items: UrgentFeedback[];
  pain_point_categories: CategoryCount[];
  feature_request_categories: CategoryCount[];
  urgent_categories: CategoryCount[];
  total_feedback: number;
  date_range: string;
}

export const dashboardAPI = {
  get: async (days = 30): Promise<DashboardData> => {
    const response = await apiClient.get(`/api/v1/dashboard/?days=${days}`);
    return response.data;
  },
};
