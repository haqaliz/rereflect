import apiClient from '../api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ConversationFolder {
  id: number;
  organization_id: number;
  name: string;
  sort_order: number;
  created_at: string;
}

export interface ConversationMessage {
  id: number;
  conversation_id: number;
  role: 'user' | 'assistant';
  content: string;
  structured_data: Record<string, unknown> | null;
  context_scope: string;
  query_type: 'data' | 'analysis' | 'general' | null;
  template_id: number | null;
  sql_generated: string | null;
  llm_provider: string | null;
  llm_model: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_cents: number | null;
  latency_ms: number | null;
  is_regenerated: boolean;
  created_at: string;
}

export interface Conversation {
  id: number;
  public_id: string;
  organization_id: number;
  created_by_user_id: number;
  title: string;
  folder_id: number | null;
  context_scope: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateConversationData {
  title?: string;
  context_scope?: string;
  folder_id?: number;
}

export interface UpdateConversationData {
  title?: string;
  folder_id?: number | null;
  context_scope?: string;
}

export interface CreateFolderData {
  name: string;
  sort_order?: number;
}

export interface UpdateFolderData {
  name?: string;
  sort_order?: number;
}

export interface ConversationListParams {
  folder_id?: number | null;
  page?: number;
  page_size?: number;
}

export interface TemplateStartersResponse {
  templates: string[];
}

export interface SuggestionsResponse {
  suggestions: string[];
}

export interface CopilotUsageResponse {
  queries_today: number;
  daily_limit: number | null;
  plan: string;
  tokens_used_month?: number;
  tokens_budget_month?: number | null;
  plan_tier?: string;
  days_remaining_in_billing_cycle?: number;
}

// ─── API client ───────────────────────────────────────────────────────────────

export const conversationsAPI = {
  // Conversations CRUD
  async getConversations(params?: ConversationListParams): Promise<ConversationListResponse> {
    const res = await apiClient.get('/api/v1/conversations', { params });
    return res.data;
  },

  async createConversation(data: CreateConversationData): Promise<Conversation> {
    const res = await apiClient.post('/api/v1/conversations', data);
    return res.data;
  },

  async getConversation(publicId: string): Promise<Conversation & { messages: ConversationMessage[] }> {
    const res = await apiClient.get(`/api/v1/conversations/${publicId}`);
    return res.data;
  },

  async updateConversation(publicId: string, data: UpdateConversationData): Promise<Conversation> {
    const res = await apiClient.patch(`/api/v1/conversations/${publicId}`, data);
    return res.data;
  },

  async deleteConversation(publicId: string): Promise<void> {
    await apiClient.delete(`/api/v1/conversations/${publicId}`);
  },

  // Folders CRUD
  async getFolders(): Promise<ConversationFolder[]> {
    const res = await apiClient.get('/api/v1/conversations/folders');
    return res.data;
  },

  async createFolder(data: CreateFolderData): Promise<ConversationFolder> {
    const res = await apiClient.post('/api/v1/conversations/folders', data);
    return res.data;
  },

  async updateFolder(id: number, data: UpdateFolderData): Promise<ConversationFolder> {
    const res = await apiClient.patch(`/api/v1/conversations/folders/${id}`, data);
    return res.data;
  },

  async deleteFolder(id: number): Promise<void> {
    await apiClient.delete(`/api/v1/conversations/folders/${id}`);
  },

  // Templates & Suggestions
  async getTemplateStarters(): Promise<TemplateStartersResponse> {
    const res = await apiClient.get('/api/v1/conversations/templates');
    return res.data;
  },

  async getSuggestions(): Promise<SuggestionsResponse> {
    const res = await apiClient.post('/api/v1/conversations/suggestions');
    return res.data;
  },

  // Usage
  async getCopilotUsage(): Promise<CopilotUsageResponse> {
    const res = await apiClient.get('/api/v1/copilot/usage');
    return res.data;
  },
};
