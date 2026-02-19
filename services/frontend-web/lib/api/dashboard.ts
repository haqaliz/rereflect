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

export interface ChurnRiskSummary {
  high_count: number;
  medium_count: number;
  low_count: number;
  total_at_risk: number;
}

export interface ChurnRiskItem {
  id: number;
  text: string;
  churn_risk_score: number;
  sentiment_label: string | null;
  suggested_action: string | null;
  created_at: string;
}

export interface CustomerHealthSummary {
  customer_email: string;
  customer_name: string | null;
  health_score: number;
  risk_level: string;
  feedback_count: number;
  last_feedback_at: string | null;
  churn_risk_component: number;
  sentiment_component: number;
  resolution_component: number;
  frequency_component: number;
  llm_analysis: string | null;
  llm_analyzed_at: string | null;
  llm_analysis_summary: string | null;
  llm_analysis_type: string | null;
  llm_urgency: string | null;
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
  churn_risk_summary: ChurnRiskSummary;
  top_churn_risks: ChurnRiskItem[];
  at_risk_customers: CustomerHealthSummary[];
  total_feedback: number;
  date_range: string;
}

export const dashboardAPI = {
  get: async (days = 30): Promise<DashboardData> => {
    const response = await apiClient.get(`/api/v1/dashboard/?days=${days}`);
    return response.data;
  },
};
