import apiClient from '../api-client';

export interface SentimentTrend {
  direction: 'improving' | 'declining' | 'stable';
  change_percent: number;
}

export interface CustomerListItem {
  customer_email: string;
  customer_name: string | null;
  health_score: number;
  risk_level: 'healthy' | 'moderate' | 'at_risk' | 'critical';
  confidence_level: 'low' | 'medium' | 'high';
  feedback_count: number;
  last_feedback_at: string | null;
  sentiment_trend: SentimentTrend;
  is_archived: boolean;
  has_llm_analysis: boolean;
}

export interface RiskDistribution {
  healthy: number;
  moderate: number;
  at_risk: number;
  critical: number;
}

export interface CustomerListSummary {
  total_customers: number;
  avg_health_score: number;
  risk_distribution: RiskDistribution;
}

export interface CustomerListResponse {
  items: CustomerListItem[];
  total: number;
  page: number;
  page_size: number;
  summary: CustomerListSummary;
}

export interface CustomerListParams {
  page?: number;
  page_size?: number;
  sort_by?: 'health_score' | 'feedback_count' | 'last_feedback_at' | 'customer_email';
  sort_order?: 'asc' | 'desc';
  risk_level?: string;
  search?: string;
  include_archived?: boolean;
}

export interface ActionItem {
  id: number;
  action_text: string;
  status: 'pending' | 'completed' | 'dismissed';
  completed_by: number | null;
  completed_at: string | null;
  created_at: string | null;
}

export interface CustomerProfileData {
  customer_email: string;
  customer_name: string | null;
  health_score: number;
  risk_level: string;
  confidence_level: 'low' | 'medium' | 'high';
  confidence_score: number | null;
  feedback_count: number;
  last_feedback_at: string | null;
  churn_risk_component: number;
  sentiment_component: number;
  resolution_component: number;
  frequency_component: number;
  // Structured LLM analysis fields
  llm_analysis_summary: string | null;
  llm_recommended_actions: string[] | null;
  llm_risk_drivers: string[] | null;
  llm_urgency: string | null;
  llm_analysis_type: string | null;
  llm_analyzed_at: string | null;
  llm_actions: ActionItem[] | null;  // Business+ only
  // Legacy field (transition period)
  llm_analysis: string | null;
  is_archived: boolean;
  created_at: string;
}

export interface HealthHistoryEntry {
  health_score: number;
  churn_risk_component: number;
  sentiment_component: number;
  resolution_component: number;
  frequency_component: number;
  risk_level: string;
  recorded_at: string;
}

export interface CustomerHealthHistoryResponse {
  history: HealthHistoryEntry[];
  period_start: string;
  period_end: string;
}

export interface CustomerFeedbackItem {
  id: number;
  text_snippet: string;
  sentiment_label: string | null;
  sentiment_score: number | null;
  churn_risk_score: number | null;
  workflow_status: string | null;
  created_at: string;
  source: string | null;
}

export interface CustomerFeedbacksResponse {
  feedbacks: CustomerFeedbackItem[];
  total_count: number;
  view_all_url: string;
}

export interface ActivityEvent {
  type: 'feedback_created' | 'status_changed' | 'health_score_changed' | 'llm_analysis_generated' | 'action_completed';
  description: string;
  feedback_id?: number;
  old_score?: number;
  new_score?: number;
  timestamp: string;
}

export interface CustomerActivityResponse {
  events: ActivityEvent[];
}

export interface AnalyzeResponse {
  message: string;
  estimated_wait_seconds: number;
}

export interface AggregatedFactor {
  avg_score: number;
  max: number;
  description: string;
}

export interface ChurnFactorsResponse {
  customer_email: string;
  period_days: number;
  feedback_count: number;
  aggregated_factors: Record<string, AggregatedFactor>;
  top_risk_drivers: string[];
}

export const customersAPI = {
  list: async (params: CustomerListParams = {}): Promise<CustomerListResponse> => {
    const query = new URLSearchParams();
    if (params.page) query.set('page', String(params.page));
    if (params.page_size) query.set('page_size', String(params.page_size));
    if (params.sort_by) query.set('sort_by', params.sort_by);
    if (params.sort_order) query.set('sort_order', params.sort_order);
    if (params.risk_level) query.set('risk_level', params.risk_level);
    if (params.search) query.set('search', params.search);
    if (params.include_archived !== undefined)
      query.set('include_archived', String(params.include_archived));

    const response = await apiClient.get(`/api/v1/customers/?${query.toString()}`);
    return response.data;
  },

  getByEmail: async (email: string): Promise<CustomerProfileData> => {
    const response = await apiClient.get(`/api/v1/customers/${encodeURIComponent(email)}`);
    return response.data;
  },

  getHistory: async (email: string, days = 30): Promise<CustomerHealthHistoryResponse> => {
    const response = await apiClient.get(
      `/api/v1/customers/${encodeURIComponent(email)}/history?days=${days}`
    );
    return response.data;
  },

  getFeedbacks: async (email: string): Promise<CustomerFeedbacksResponse> => {
    const response = await apiClient.get(
      `/api/v1/customers/${encodeURIComponent(email)}/feedbacks`
    );
    return response.data;
  },

  getActivity: async (email: string): Promise<CustomerActivityResponse> => {
    const response = await apiClient.get(
      `/api/v1/customers/${encodeURIComponent(email)}/activity`
    );
    return response.data;
  },

  requestAnalysis: async (email: string): Promise<AnalyzeResponse> => {
    const response = await apiClient.post(
      `/api/v1/customers/${encodeURIComponent(email)}/analyze`
    );
    return response.data;
  },

  updateAction: async (email: string, actionId: number, status: 'completed' | 'dismissed'): Promise<ActionItem> => {
    const response = await apiClient.patch(
      `/api/v1/customers/${encodeURIComponent(email)}/actions/${actionId}`,
      { status }
    );
    return response.data;
  },

  batchAnalyze: async (): Promise<{ message: string; customer_count: number }> => {
    const response = await apiClient.post('/api/v1/customers/batch-analyze');
    return response.data;
  },

  getChurnFactors: async (email: string): Promise<ChurnFactorsResponse> => {
    const response = await apiClient.get(
      `/api/v1/customers/${encodeURIComponent(email)}/churn-factors`
    );
    return response.data;
  },
};
