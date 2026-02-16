import apiClient from '../api-client';

export interface ComparisonData {
  total_feedback_delta_pct: number;
  positive_delta_pct: number;
  neutral_delta_pct: number;
  negative_delta_pct: number;
  urgent_delta_pct: number;
  pain_points_delta_pct: number;
  feature_requests_delta_pct: number;
  churn_high_delta_pct: number;
}

export interface TrendDataPoint {
  date: string;
  count?: number;
  positive?: number;
  neutral?: number;
  negative?: number;
  avg_score?: number;
}

export interface TrendResponse {
  metric: string;
  granularity: string;
  data: TrendDataPoint[];
}

export interface ActivityFeedItem {
  id: number;
  type: string;
  title: string;
  subtitle: string | null;
  severity: 'info' | 'warning' | 'critical' | 'positive';
  created_at: string;
  link: string | null;
}

export interface ActivityFeedResponse {
  items: ActivityFeedItem[];
  last_updated: string;
}

export interface TeamMember {
  user_id: number;
  email: string;
  role: string;
  last_active_at: string | null;
  feedback_imported_count: number;
  actions_count: number;
}

export interface DashboardLayoutWidget {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardLayoutData {
  layouts: {
    lg: DashboardLayoutWidget[];
    md: DashboardLayoutWidget[];
    sm: DashboardLayoutWidget[];
  };
  version: number;
}

export const dashboardV2API = {
  getTrends: async (
    metric: 'volume' | 'sentiment' | 'churn_risk',
    days = 30,
    granularity = 'daily'
  ): Promise<TrendResponse> => {
    const response = await apiClient.get(
      `/api/v1/dashboard/trends?metric=${metric}&days=${days}&granularity=${granularity}`
    );
    return response.data;
  },

  getComparison: async (days = 30): Promise<ComparisonData> => {
    const response = await apiClient.get(`/api/v1/dashboard/comparison?days=${days}`);
    return response.data;
  },

  getActivityFeed: async (limit = 20): Promise<ActivityFeedResponse> => {
    const response = await apiClient.get(`/api/v1/dashboard/activity-feed?limit=${limit}`);
    return response.data;
  },

  getTeamActivity: async (): Promise<TeamMember[]> => {
    const response = await apiClient.get('/api/v1/dashboard/team-activity');
    return response.data.members ?? [];
  },

  getLayout: async (): Promise<DashboardLayoutData> => {
    const response = await apiClient.get('/api/v1/user/dashboard-layout/');
    return response.data.layout_json;
  },

  saveLayout: async (layout: DashboardLayoutData): Promise<DashboardLayoutData> => {
    const response = await apiClient.put('/api/v1/user/dashboard-layout/', { layout_json: layout });
    return response.data.layout_json;
  },

  resetLayout: async (): Promise<DashboardLayoutData> => {
    const response = await apiClient.delete('/api/v1/user/dashboard-layout/');
    return response.data.layout_json;
  },
};
