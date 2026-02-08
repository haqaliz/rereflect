import apiClient, { publicApiClient } from '../api-client';

// ─── Types ─────────────────────────────────────────────────────

export interface TrendDataPoint {
  date: string;
  feedback_count: number;
  avg_sentiment_score: number | null;
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  urgent_count: number;
  pain_points_count: number;
  feature_requests_count: number;
}

export interface SentimentDistribution {
  positive: number;
  neutral: number;
  negative: number;
}

export interface SourceDistributionItem {
  source: string;
  count: number;
  percentage: number;
}

export interface TopItem {
  name: string;
  count: number;
  trend: 'up' | 'down' | 'stable';
  avg_sentiment: number | null;
}

export interface AnalyticsTrendsData {
  data_points: TrendDataPoint[];
  sentiment_distribution: SentimentDistribution;
  source_distribution: SourceDistributionItem[];
  top_pain_points: TopItem[];
  top_feature_requests: TopItem[];
  total_feedback: number;
  date_range: string;
  granularity: 'daily' | 'weekly';
}

export type DateRange = '7d' | '30d' | '90d';

// ─── API ───────────────────────────────────────────────────────

export const analyticsAPI = {
  getTrends: async (range: DateRange = '7d'): Promise<AnalyticsTrendsData> => {
    const response = await apiClient.get(`/api/v1/analytics/trends?range=${range}`);
    return response.data;
  },
};

// ─── Shared Links Types ───────────────────────────────────────

export interface SharedLink {
  id: number;
  token: string;
  page: string;
  expires_at: string | null;
  is_active: boolean;
  view_count: number;
  has_password: boolean;
  created_at: string;
}

export interface PublicAnalyticsData {
  requires_password: boolean;
  org_name: string | null;
  data: {
    total_feedback: number;
    date_range: string;
    granularity: string;
    sentiment_distribution: SentimentDistribution;
    source_distribution: SourceDistributionItem[];
    data_points: TrendDataPoint[];
    top_pain_points: TopItem[];
    top_feature_requests: TopItem[];
  } | null;
}

export interface PaginatedSharedLinks {
  items: SharedLink[];
  total: number;
  page: number;
  page_size: number;
}

export interface SharedLinksFilter {
  page?: number;
  page_size?: number;
  status?: 'active' | 'expired' | 'deactivated';
  search?: string;
  date_from?: string;
  date_to?: string;
}

// ─── Shared Links API ─────────────────────────────────────────

export const sharedLinksAPI = {
  create: async (data: { expiration: string; password?: string }): Promise<SharedLink> => {
    const response = await apiClient.post('/api/v1/shared-links/', data);
    return response.data;
  },

  list: async (): Promise<SharedLink[]> => {
    const response = await apiClient.get('/api/v1/shared-links/');
    return response.data;
  },

  deactivate: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/shared-links/${id}`);
  },

  listAll: async (filters: SharedLinksFilter = {}): Promise<PaginatedSharedLinks> => {
    const params = new URLSearchParams();
    if (filters.page) params.set('page', String(filters.page));
    if (filters.page_size) params.set('page_size', String(filters.page_size));
    if (filters.status) params.set('status', filters.status);
    if (filters.search) params.set('search', filters.search);
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);
    const response = await apiClient.get(`/api/v1/shared-links/all?${params.toString()}`);
    return response.data;
  },

  getPublic: async (token: string): Promise<PublicAnalyticsData> => {
    const response = await publicApiClient.get(`/api/v1/public/analytics/${token}`);
    return response.data;
  },

  verifyPassword: async (token: string, password: string): Promise<PublicAnalyticsData> => {
    const response = await publicApiClient.post(`/api/v1/public/analytics/${token}/verify`, { password });
    return response.data;
  },
};
