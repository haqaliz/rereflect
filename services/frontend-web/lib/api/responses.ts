import apiClient from '../api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ResponseTemplate {
  id: number;
  name: string;
  category: string;
  body: string;
  is_system: boolean;
  usage_count: number;
}

export interface FeedbackResponseRecord {
  id: number;
  feedback_id: number;
  user_id: number;
  response_text: string;
  channel: 'clipboard' | 'slack' | 'intercom' | 'linear' | 'email';
  source: 'template' | 'ai_generated' | 'manual';
  template_id: number | null;
  tone: string | null;
  status: 'sent' | 'copied' | 'send_failed';
  error_message: string | null;
  created_at: string;
  user_name?: string;
}

export interface ResponseSettings {
  brand_voice: string | null;
  default_tone: string;
  product_name_display: string | null;
  support_email_display: string | null;
}

export interface ResponseUsage {
  ai_responses_generated: number;
  monthly_limit: number;
  templates_used: number;
  responses_sent: number;
}

export type ToneOption = 'professional' | 'friendly' | 'empathetic' | 'concise' | 'technical';

export interface CreateTemplateRequest {
  name: string;
  category: string;
  body: string;
}

export interface GenerateResponseResult {
  response_text: string;
  tokens_used: number;
  remaining_this_month: number;
}

export interface SendResponseRequest {
  response_text: string;
  channel: 'clipboard' | 'slack' | 'intercom' | 'linear' | 'email';
  source: 'template' | 'ai_generated' | 'manual';
  template_id: number | null;
  tone: string | null;
}

export interface SendResponseResult {
  success: boolean;
  response_id: number;
  channel: string;
  error: string | null;
}

export interface SuggestTemplateResult {
  template: ResponseTemplate | null;
  score: number;
}

// ─── API ──────────────────────────────────────────────────────────────────────

export const responsesAPI = {
  // Response Templates
  listTemplates: async (): Promise<ResponseTemplate[]> => {
    const response = await apiClient.get('/api/v1/response-templates');
    return response.data.templates;
  },

  createTemplate: async (data: CreateTemplateRequest): Promise<ResponseTemplate> => {
    const response = await apiClient.post('/api/v1/response-templates', data);
    return response.data;
  },

  updateTemplate: async (
    id: number,
    data: Partial<CreateTemplateRequest>
  ): Promise<ResponseTemplate> => {
    const response = await apiClient.put(`/api/v1/response-templates/${id}`, data);
    return response.data;
  },

  deleteTemplate: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/response-templates/${id}`);
  },

  suggestTemplate: async (feedbackId: number): Promise<SuggestTemplateResult> => {
    const response = await apiClient.post('/api/v1/response-templates/suggest', {
      feedback_id: feedbackId,
    });
    return response.data;
  },

  // Feedback Responses
  listResponses: async (feedbackId: number): Promise<FeedbackResponseRecord[]> => {
    const response = await apiClient.get(`/api/v1/feedback/${feedbackId}/responses`);
    return response.data;
  },

  generateResponse: async (
    feedbackId: number,
    tone?: string
  ): Promise<GenerateResponseResult> => {
    const response = await apiClient.post(`/api/v1/feedback/${feedbackId}/responses/generate`, {
      tone,
    });
    return response.data;
  },

  sendResponse: async (
    feedbackId: number,
    data: SendResponseRequest
  ): Promise<SendResponseResult> => {
    const response = await apiClient.post(`/api/v1/feedback/${feedbackId}/responses/send`, data);
    return response.data;
  },

  // Response Settings
  getResponseSettings: async (): Promise<ResponseSettings> => {
    const response = await apiClient.get('/api/v1/response-settings');
    return response.data;
  },

  updateResponseSettings: async (
    data: Partial<ResponseSettings>
  ): Promise<ResponseSettings> => {
    const response = await apiClient.put('/api/v1/response-settings', data);
    return response.data;
  },

  getResponseUsage: async (): Promise<ResponseUsage> => {
    const response = await apiClient.get('/api/v1/response-settings/usage');
    return response.data;
  },
};

// ─── Constants ────────────────────────────────────────────────────────────────

export const TONE_OPTIONS: { value: ToneOption; label: string }[] = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'empathetic', label: 'Empathetic' },
  { value: 'concise', label: 'Concise' },
  { value: 'technical', label: 'Technical' },
];

export const RESPONSE_VARIABLES = [
  { name: 'customer_name', description: 'Customer name from feedback metadata' },
  { name: 'customer_email', description: 'Customer email address' },
  { name: 'company_name', description: 'Customer company or org name' },
  { name: 'feedback_excerpt', description: 'First 200 characters of feedback text' },
  { name: 'category', description: 'AI-assigned category' },
  { name: 'sentiment', description: 'Sentiment label (Positive/Negative/Neutral)' },
  { name: 'source', description: 'Feedback source name' },
  { name: 'product_name', description: 'Product name from org settings' },
  { name: 'agent_name', description: "Current user's name" },
  { name: 'support_email', description: 'Support email from org settings' },
] as const;
