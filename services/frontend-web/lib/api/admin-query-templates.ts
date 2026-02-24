import apiClient from '../api-client';

export interface QueryTemplate {
  id: number;
  organization_id: number | null;
  sql_query: string;
  description: string;
  parameter_schema: Record<string, unknown>;
  created_by: 'system' | 'llm' | 'admin';
  usage_count: number;
  last_used_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface QueryTemplateListResponse {
  items: QueryTemplate[];
  total: number;
  page: number;
  page_size: number;
}

export interface QueryTemplateListParams {
  created_by?: 'system' | 'llm' | 'admin';
  is_active?: boolean;
  page?: number;
  page_size?: number;
  sort_by?: 'usage_count' | 'last_used_at' | 'created_at';
  sort_order?: 'asc' | 'desc';
}

export interface QueryTemplateUpdate {
  description?: string;
  sql_query?: string;
  is_active?: boolean;
}

export interface CopilotStats {
  total_templates: number;
  active_templates: number;
  template_hit_rate_percent: number;
  queries_today: number;
  avg_latency_ms: number;
}

export const adminQueryTemplatesAPI = {
  async list(params?: QueryTemplateListParams): Promise<QueryTemplateListResponse> {
    const res = await apiClient.get('/api/v1/admin/query-templates', { params });
    return res.data;
  },

  async get(id: number): Promise<QueryTemplate> {
    const res = await apiClient.get(`/api/v1/admin/query-templates/${id}`);
    return res.data;
  },

  async update(id: number, data: QueryTemplateUpdate): Promise<QueryTemplate> {
    const res = await apiClient.patch(`/api/v1/admin/query-templates/${id}`, data);
    return res.data;
  },

  async delete(id: number): Promise<void> {
    await apiClient.delete(`/api/v1/admin/query-templates/${id}`);
  },

  async getStats(): Promise<CopilotStats> {
    const res = await apiClient.get('/api/v1/admin/copilot/stats');
    return res.data;
  },
};
