const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface ChangelogEntry {
  id: number;
  title: string;
  description: string | null;
  entry_type: string;
  is_breaking: boolean;
  committed_at: string;
}

export interface ChangelogListResponse {
  items: ChangelogEntry[];
  total: number;
  has_more: boolean;
}

export async function getPublicChangelog(params?: {
  entry_type?: string;
  days?: number;
  offset?: number;
  limit?: number;
}): Promise<ChangelogListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.entry_type) searchParams.set('entry_type', params.entry_type);
  if (params?.days) searchParams.set('days', String(params.days));
  if (params?.offset) searchParams.set('offset', String(params.offset));
  if (params?.limit) searchParams.set('limit', String(params.limit));
  const qs = searchParams.toString();
  const response = await fetch(`${API_URL}/api/v1/changelog${qs ? `?${qs}` : ''}`);
  if (!response.ok) throw new Error(`Changelog API error: ${response.status}`);
  return response.json();
}
