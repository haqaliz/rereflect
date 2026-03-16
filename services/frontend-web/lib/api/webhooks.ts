import apiClient from '../api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface WebhookEndpoint {
  id: number;
  name: string;
  url: string;
  events: string[];
  category_filters: string[];
  retry_mode: 'fire_and_forget' | 'exponential_backoff';
  is_active: boolean;
  consecutive_failures: number;
  custom_headers: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface WebhookDelivery {
  id: number;
  event: string;
  feedback_id: number | null;
  status: 'sent' | 'failed' | 'retrying';
  attempt: number;
  response_code: number | null;
  response_body: string | null;
  error_message: string | null;
  latency_ms: number | null;
  created_at: string;
}

export interface CreateWebhookRequest {
  name: string;
  url: string;
  events: string[];
  category_filters?: string[];
  retry_mode: 'fire_and_forget' | 'exponential_backoff';
  custom_headers?: Record<string, string>;
}

export interface CreateWebhookResponse extends WebhookEndpoint {
  signing_secret: string; // only present on create
}

export interface UpdateWebhookRequest {
  name?: string;
  url?: string;
  events?: string[];
  category_filters?: string[];
  retry_mode?: 'fire_and_forget' | 'exponential_backoff';
  custom_headers?: Record<string, string>;
  is_active?: boolean;
}

export interface TestWebhookResult {
  success: boolean;
  response_code: number | null;
  response_body: string | null;
  latency_ms: number | null;
  error_message?: string | null;
}

export interface RotateSecretResult extends WebhookEndpoint {
  signing_secret: string;
}

// ─── API ──────────────────────────────────────────────────────────────────────

export const webhooksAPI = {
  list: async (): Promise<{ webhooks: WebhookEndpoint[]; count: number; limit: number }> => {
    const response = await apiClient.get('/api/v1/webhooks');
    return response.data;
  },

  create: async (data: CreateWebhookRequest): Promise<CreateWebhookResponse> => {
    const response = await apiClient.post('/api/v1/webhooks', data);
    return response.data;
  },

  get: async (id: number): Promise<WebhookEndpoint> => {
    const response = await apiClient.get(`/api/v1/webhooks/${id}`);
    return response.data;
  },

  update: async (id: number, data: UpdateWebhookRequest): Promise<WebhookEndpoint> => {
    const response = await apiClient.put(`/api/v1/webhooks/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/webhooks/${id}`);
  },

  test: async (id: number): Promise<TestWebhookResult> => {
    const response = await apiClient.post(`/api/v1/webhooks/${id}/test`);
    return response.data;
  },

  rotateSecret: async (id: number): Promise<RotateSecretResult> => {
    const response = await apiClient.post(`/api/v1/webhooks/${id}/rotate-secret`);
    return response.data;
  },

  listDeliveries: async (id: number): Promise<WebhookDelivery[]> => {
    const response = await apiClient.get(`/api/v1/webhooks/${id}/deliveries`);
    return response.data.deliveries;
  },
};

// ─── Constants ────────────────────────────────────────────────────────────────

export const WEBHOOK_EVENTS: { id: string; label: string }[] = [
  { id: 'feedback.created', label: 'Feedback Created' },
  { id: 'feedback.analyzed', label: 'Feedback Analyzed' },
  { id: 'feedback.status_changed', label: 'Status Changed' },
  { id: 'feedback.urgent', label: 'Feedback Urgent' },
  { id: 'feedback.category_match', label: 'Category Match' },
];

export const PLAN_WEBHOOK_LIMITS: Record<string, number | null> = {
  free: 2,
  pro: 5,
  business: 10,
  enterprise: null,
};
