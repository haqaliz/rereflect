import apiClient from '../api-client';

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AIReadiness {
  organization_id: number;
  generated_at: string;
  feedback_volume: number;
  corrections_total: number;
  corrections_by_type: Record<string, number>;
  churn_labels_total: number;
  churn_labels_recovered: number;
  churn_labels_by_reason: Record<string, number>;
  churn_labels_by_source: Record<string, number>;
  correction_volume_target: number;
  churn_label_target: number;
  correction_volume_ready: boolean;
  churn_labels_ready: boolean;
}

// ─── API ─────────────────────────────────────────────────────────────────────

export const aiReadinessAPI = {
  async get(): Promise<AIReadiness> {
    const response = await apiClient.get<AIReadiness>('/api/v1/analytics/ai-readiness');
    return response.data;
  },
};
