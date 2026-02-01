import apiClient from '../api-client';

export interface Integration {
  id: number;
  type: string;
  name: string | null;
  integration_type: 'webhook' | 'oauth';
  channel_name: string | null;
  team_name: string | null;
  triggers: string[];
  included_fields: string[];
  digest_time: string | null;
  message_template: string | null;
  is_active: boolean;
  last_used_at: string | null;
  error_count: number;
  last_error: string | null;
  created_at: string;
}

export interface OAuthConnectResponse {
  auth_url: string;
  state: string;
}

export interface IntegrationListResponse {
  integrations: Integration[];
  total: number;
}

export interface CreateSlackWebhookData {
  name: string;
  webhook_url: string;
  triggers?: string[];
  included_fields?: string[];
  digest_time?: string;
  message_template?: string;
}

export interface UpdateIntegrationData {
  name?: string;
  triggers?: string[];
  included_fields?: string[];
  digest_time?: string;
  is_active?: boolean;
  message_template?: string;
}

export interface SlackTestResponse {
  success: boolean;
  message: string;
}

export interface AlertLog {
  id: number;
  integration_id: number;
  feedback_id: number | null;
  alert_type: string;
  status: string;
  error_message: string | null;
  sent_at: string;
}

export interface TemplateVariable {
  name: string;
  description: string;
  example: string;
}

export interface TemplateVariablesResponse {
  variables: TemplateVariable[];
  default_template: string;
}

// Valid trigger options
export const TRIGGER_OPTIONS = [
  { value: 'urgent', label: 'Urgent Feedback', description: 'Alert when urgent/churn-risk feedback is detected' },
  { value: 'negative', label: 'Negative Sentiment', description: 'Alert on negative sentiment feedback' },
  { value: 'all', label: 'All Feedback', description: 'Alert on every new feedback item' },
  { value: 'daily_digest', label: 'Daily Digest', description: 'Send a daily summary at scheduled time' },
  { value: 'weekly_digest', label: 'Weekly Digest', description: 'Send a weekly summary at scheduled time' },
];

// Valid field options (legacy - for backwards compatibility)
export const FIELD_OPTIONS = [
  { value: 'text', label: 'Feedback Text' },
  { value: 'sentiment', label: 'Sentiment Label' },
  { value: 'sentiment_score', label: 'Sentiment Score' },
  { value: 'pain_point_category', label: 'Pain Point Category' },
  { value: 'pain_point_severity', label: 'Pain Point Severity' },
  { value: 'feature_request_category', label: 'Feature Request Category' },
  { value: 'feature_request_priority', label: 'Feature Request Priority' },
  { value: 'urgent_category', label: 'Urgent Category' },
  { value: 'urgent_response_time', label: 'Response Time' },
  { value: 'source', label: 'Source' },
  { value: 'link', label: 'Link' },
];

export const integrationsAPI = {
  list: async (): Promise<IntegrationListResponse> => {
    const response = await apiClient.get('/api/v1/integrations/');
    return response.data;
  },

  get: async (id: number): Promise<Integration> => {
    const response = await apiClient.get(`/api/v1/integrations/${id}`);
    return response.data;
  },

  createSlackWebhook: async (data: CreateSlackWebhookData): Promise<Integration> => {
    const response = await apiClient.post('/api/v1/integrations/slack/webhook', data);
    return response.data;
  },

  update: async (id: number, data: UpdateIntegrationData): Promise<Integration> => {
    const response = await apiClient.patch(`/api/v1/integrations/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/integrations/${id}`);
  },

  testSlack: async (integrationId: number): Promise<SlackTestResponse> => {
    const response = await apiClient.post('/api/v1/integrations/slack/test', {
      integration_id: integrationId,
    });
    return response.data;
  },

  getLogs: async (integrationId: number, limit = 50): Promise<AlertLog[]> => {
    const response = await apiClient.get(`/api/v1/integrations/${integrationId}/logs`, {
      params: { limit },
    });
    return response.data;
  },

  getTemplateVariables: async (): Promise<TemplateVariablesResponse> => {
    const response = await apiClient.get('/api/v1/integrations/slack/template-variables');
    return response.data;
  },

  // OAuth methods
  getSlackOAuthUrl: async (name: string): Promise<OAuthConnectResponse> => {
    const response = await apiClient.get('/api/v1/integrations/slack/oauth/connect', {
      params: { name },
    });
    return response.data;
  },
};
