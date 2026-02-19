import apiClient from '../api-client';

export interface SourceMetadata {
  author_id?: string;
  author_name?: string;
  channel_id?: string;
  channel_name?: string;
  thread_ts?: string;
  url?: string;
  [key: string]: string | undefined;
}

export interface FeedbackItem {
  id: number;
  organization_id: number;
  text: string;
  source: string | null;
  // Source tracking
  source_id: number | null;
  source_name: string | null;  // From FeedbackSource.name
  source_metadata: SourceMetadata | null;
  sentiment_score: number | null;
  sentiment_label: string | null;
  extracted_issue: string | null;
  tags: string[] | null;
  is_urgent: boolean;
  created_at: string;
  // Pain point categorization
  pain_point_category: string | null;
  pain_point_severity: string | null;
  pain_point_text: string | null;
  // Feature request categorization
  feature_request_category: string | null;
  feature_request_priority: string | null;
  feature_request_text: string | null;
  // Urgent categorization
  urgent_category: string | null;
  urgent_response_time: string | null;
  // Confidence score
  categorization_confidence: number | null;
  // Churn risk
  churn_risk_score: number | null;
  suggested_action: string | null;
  // Customer
  customer_email: string | null;
  // Workflow
  workflow_status: string;
  assigned_to: number | null;
  assigned_to_email: string | null;
}

// Category type definitions
export type PainPointCategory =
  | 'security_breach' | 'data_loss' | 'payment_issue'
  | 'system_crash' | 'authentication' | 'functionality_broken'
  | 'performance' | 'usability' | 'compatibility'
  | 'missing_feature' | 'documentation' | 'cosmetic';

export type PainPointSeverity = 'critical' | 'major' | 'moderate' | 'minor' | 'trivial';

export type FeatureRequestCategory =
  | 'core_functionality' | 'automation' | 'integration'
  | 'reporting' | 'customization' | 'collaboration'
  | 'export_import' | 'mobile' | 'notifications' | 'ui_enhancement';

export type FeatureRequestPriority = 'high' | 'medium' | 'low';

export type UrgentCategory =
  | 'service_outage' | 'data_breach' | 'payment_failure' | 'data_corruption'
  | 'account_locked' | 'critical_bug'
  | 'billing_dispute' | 'churn_risk' | 'compliance' | 'reputation_risk';

export type UrgentResponseTime = 'immediate' | '1_hour' | '4_hours' | '24_hours';

export interface FeedbackListResponse {
  items: FeedbackItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CreateFeedbackData {
  text: string;
  source?: string;
}

export interface CSVImportResponse {
  total_rows: number;
  imported_count: number;
  failed_count: number;
  errors: string[];
}

export interface FeedbackFilters {
  search?: string;
  sentiment?: string;
  source?: string;
  is_urgent?: boolean;
  tag?: string;
  pain_point_category?: string;
  pain_point_severity?: string;
  feature_request_category?: string;
  feature_request_priority?: string;
  urgent_category?: string;
  urgent_response_time?: string;
  churn_risk_min?: number;
  churn_risk_max?: number;
  customer_email?: string;
  workflow_status?: string;
  assigned_to?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export const feedbackAPI = {
  list: async (page = 1, pageSize = 20, filters?: FeedbackFilters): Promise<FeedbackListResponse> => {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    });

    if (filters?.search) params.append('search', filters.search);
    if (filters?.sentiment) params.append('sentiment', filters.sentiment);
    if (filters?.source) params.append('source', filters.source);
    if (filters?.is_urgent !== undefined) params.append('is_urgent', filters.is_urgent.toString());
    if (filters?.tag) params.append('tag', filters.tag);
    if (filters?.pain_point_category) params.append('pain_point_category', filters.pain_point_category);
    if (filters?.pain_point_severity) params.append('pain_point_severity', filters.pain_point_severity);
    if (filters?.feature_request_category) params.append('feature_request_category', filters.feature_request_category);
    if (filters?.feature_request_priority) params.append('feature_request_priority', filters.feature_request_priority);
    if (filters?.urgent_category) params.append('urgent_category', filters.urgent_category);
    if (filters?.urgent_response_time) params.append('urgent_response_time', filters.urgent_response_time);
    if (filters?.churn_risk_min !== undefined) params.append('churn_risk_min', filters.churn_risk_min.toString());
    if (filters?.churn_risk_max !== undefined) params.append('churn_risk_max', filters.churn_risk_max.toString());
    if (filters?.customer_email) params.append('customer_email', filters.customer_email);
    if (filters?.workflow_status) params.append('workflow_status', filters.workflow_status);
    if (filters?.assigned_to !== undefined) params.append('assigned_to', filters.assigned_to.toString());
    if (filters?.sort_by) params.append('sort_by', filters.sort_by);
    if (filters?.sort_order) params.append('sort_order', filters.sort_order);

    const response = await apiClient.get(`/api/v1/feedback/?${params.toString()}`);
    return response.data;
  },

  get: async (id: number): Promise<FeedbackItem> => {
    const response = await apiClient.get(`/api/v1/feedback/${id}`);
    return response.data;
  },

  create: async (data: CreateFeedbackData): Promise<FeedbackItem> => {
    const response = await apiClient.post('/api/v1/feedback/', data);
    return response.data;
  },

  update: async (id: number, data: CreateFeedbackData): Promise<FeedbackItem> => {
    const response = await apiClient.patch(`/api/v1/feedback/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/feedback/${id}`);
  },

  bulkDelete: async (feedbackIds: number[]): Promise<{deleted_count: number; message: string}> => {
    const response = await apiClient.post('/api/v1/feedback/bulk-delete', {
      feedback_ids: feedbackIds,
    });
    return response.data;
  },

  analyze: async (feedbackIds: number[]): Promise<{analyzed_count: number; message: string}> => {
    const response = await apiClient.post('/api/v1/analyze/', {
      feedback_ids: feedbackIds,
    });
    return response.data;
  },

  importCSV: async (file: File): Promise<CSVImportResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post('/api/v1/feedback/import-csv', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};
