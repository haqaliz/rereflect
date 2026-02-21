import apiClient from '../api-client';

export interface CustomerHealthData {
  customer_email: string;
  customer_name: string | null;
  health_score: number;
  risk_level: string; // healthy, moderate, at_risk, critical
  churn_risk_component: number;
  sentiment_component: number;
  resolution_component: number;
  frequency_component: number;
  feedback_count: number;
  last_feedback_at: string | null;
  confidence_score: number | null;
  confidence_level: string | null;
  llm_analysis: string | null;
  llm_analyzed_at: string | null;
}

export const customerHealthAPI = {
  getByEmail: async (email: string): Promise<CustomerHealthData> => {
    const response = await apiClient.get(`/api/v1/customer-health/${encodeURIComponent(email)}`);
    return response.data;
  },
};
