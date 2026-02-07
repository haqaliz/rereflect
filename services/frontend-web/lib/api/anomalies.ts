import apiClient from '../api-client';

export interface SentimentAnomaly {
  id: number;
  organization_id: number;
  detected_at: string;
  anomaly_type: string;
  severity: 'warning' | 'critical';
  baseline_negative_pct: number;
  current_negative_pct: number;
  deviation_pct: number;
  time_window_hours: number;
  feedback_count: number;
  is_resolved: boolean;
  resolved_at: string | null;
}

export interface AnomalyListResponse {
  items: SentimentAnomaly[];
  total: number;
}

export const anomaliesAPI = {
  list: async (isResolved?: boolean): Promise<AnomalyListResponse> => {
    const params = new URLSearchParams();
    if (isResolved !== undefined) {
      params.set('is_resolved', String(isResolved));
    }
    const response = await apiClient.get(`/api/v1/anomalies/?${params.toString()}`);
    return response.data;
  },

  resolve: async (anomalyId: number): Promise<SentimentAnomaly> => {
    const response = await apiClient.patch(`/api/v1/anomalies/${anomalyId}/resolve`);
    return response.data;
  },
};
