import apiClient from '../api-client';

export type ChurnReasonCode =
  | 'price'
  | 'competitor'
  | 'product_quality'
  | 'no_longer_needed'
  | 'silent_churn'
  | 'other';

export interface ChurnEvent {
  id: number;
  customer_email: string;
  churned_at: string;
  reason_code: ChurnReasonCode;
  reason_text: string | null;
  recovered_at: string | null;
  source: 'manual' | 'csv_import' | 'auto_suggested';
  marked_by_user_id: number | null;
  created_at: string;
}

export interface ChurnEventCreate {
  churned_at?: string;
  reason_code: ChurnReasonCode;
  reason_text?: string;
}

export interface BulkCreateInput {
  emails: string[];
  churned_at: string;
  reason_code: ChurnReasonCode;
  reason_text?: string;
}

export interface BulkCreateResult {
  created: number;
  skipped: number;
  errors: string[];
}

export interface ChurnEventsListParams {
  page?: number;
  page_size?: number;
  active?: boolean;
  reason_code?: ChurnReasonCode;
  from_date?: string;
  to_date?: string;
  /** Search by customer email (partial match). System admin endpoint only. */
  customer_email?: string;
}

export interface ChurnEventsListResponse {
  items: ChurnEvent[];
  total: number;
  page: number;
  page_size: number;
}

export async function markCustomerChurned(
  email: string,
  body: ChurnEventCreate
): Promise<ChurnEvent> {
  const response = await apiClient.post(
    `/api/v1/customers/${encodeURIComponent(email)}/churn-event`,
    body
  );
  return response.data;
}

export async function recoverCustomer(
  email: string,
  body?: { recovered_at?: string; note?: string }
): Promise<ChurnEvent> {
  const response = await apiClient.post(
    `/api/v1/customers/${encodeURIComponent(email)}/recover`,
    body ?? {}
  );
  return response.data;
}

export async function deleteChurnEvent(
  email: string,
  eventId: number
): Promise<void> {
  await apiClient.delete(
    `/api/v1/customers/${encodeURIComponent(email)}/churn-event/${eventId}`
  );
}

export async function bulkMarkChurned(body: BulkCreateInput): Promise<BulkCreateResult> {
  const response = await apiClient.post('/api/v1/customers/churn-events/bulk', body);
  return response.data;
}

export async function importChurnEventsCsv(file: File): Promise<BulkCreateResult> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post('/api/v1/customers/churn-events/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export async function listChurnEvents(
  params: ChurnEventsListParams = {}
): Promise<ChurnEventsListResponse> {
  const query = new URLSearchParams();
  if (params.page !== undefined) query.set('page', String(params.page));
  if (params.page_size !== undefined) query.set('page_size', String(params.page_size));
  if (params.active !== undefined) query.set('active', String(params.active));
  if (params.reason_code) query.set('reason_code', params.reason_code);
  if (params.from_date) query.set('from_date', params.from_date);
  if (params.to_date) query.set('to_date', params.to_date);
  if (params.customer_email) query.set('customer_email', params.customer_email);
  const response = await apiClient.get(`/api/v1/customers/churn-events?${query.toString()}`);
  return response.data;
}

/**
 * Export all churn events matching the given filters as a CSV file download.
 * Paginates through all pages client-side and generates the CSV from the
 * collected results.
 *
 * TODO (follow-up): Add a dedicated backend export endpoint that returns
 * enriched fields (organization_name, marked_by_email) so the CSV includes
 * human-readable org/user data instead of IDs.
 */
export async function exportChurnEventsCsv(
  filters: Omit<ChurnEventsListParams, 'page' | 'page_size'> = {}
): Promise<void> {
  const PAGE_SIZE = 100;
  let page = 1;
  const allItems: ChurnEvent[] = [];

  while (true) {
    const data = await listChurnEvents({ ...filters, page, page_size: PAGE_SIZE });
    allItems.push(...data.items);
    if (allItems.length >= data.total || data.items.length < PAGE_SIZE) break;
    page += 1;
  }

  const headers = [
    'id',
    'organization_id',
    'customer_email',
    'churned_at',
    'reason_code',
    'reason_text',
    'status',
    'source',
    'marked_by_user_id',
    'created_at',
  ];

  const rows = allItems.map((e) => [
    String(e.id),
    String(e.organization_id ?? ''),
    e.customer_email,
    e.churned_at,
    e.reason_code,
    e.reason_text ?? '',
    e.recovered_at ? 'recovered' : 'active',
    e.source,
    e.marked_by_user_id != null ? String(e.marked_by_user_id) : '',
    e.created_at,
  ]);

  const csvContent = [headers, ...rows]
    .map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(','))
    .join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `churn-events-${new Date().toISOString().slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}
