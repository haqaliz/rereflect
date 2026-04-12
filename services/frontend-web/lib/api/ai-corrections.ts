import apiClient from '../api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AICorrection {
  id: number;
  correction_type: string;
  entity_type: string;
  entity_id: number | null;
  signal: string;
  original_value: string | null;
  corrected_value: string | null;
  feedback_text: string | null;
  created_at: string;
}

export interface MostCorrectedItem {
  category: string;
  count: number;
}

export interface CorrectionStats {
  total: number;
  this_month: number;
  by_type: Record<string, number>;
  most_corrected: MostCorrectedItem[];
}

export interface SubmitCorrectionPayload {
  correction_type: string;
  entity_type: string;
  entity_id?: number | null;
  signal: 'thumbs_up' | 'thumbs_down' | 'correction';
  original_value?: string | null;
  corrected_value?: string | null;
  feedback_text?: string | null;
}

export interface PaginatedCorrections {
  items: AICorrection[];
  total: number;
  page: number;
  page_size: number;
}

// ─── API client ───────────────────────────────────────────────────────────────

export const aiCorrectionsAPI = {
  /**
   * Submit a correction or rating signal for an AI output.
   * Available to all authenticated users.
   */
  async submit(payload: SubmitCorrectionPayload): Promise<AICorrection> {
    const response = await apiClient.post<AICorrection>(
      '/api/v1/ai-corrections',
      payload,
    );
    return response.data;
  },

  /**
   * Fetch correction stats for the AI Settings "AI Accuracy" section.
   */
  async getStats(): Promise<CorrectionStats> {
    const response = await apiClient.get<CorrectionStats>(
      '/api/v1/ai-corrections/stats',
    );
    return response.data;
  },

  /**
   * List all corrections (admin/owner only), paginated.
   */
  async list(page = 1, pageSize = 20): Promise<PaginatedCorrections> {
    const response = await apiClient.get<PaginatedCorrections>(
      `/api/v1/ai-corrections?page=${page}&page_size=${pageSize}`,
    );
    return response.data;
  },
};
