import apiClient from '../api-client';

export interface CouponSummary {
  id: string;
  name: string | null;
  percent_off: number | null;
  amount_off: number | null;
  currency: string | null;
  duration: string;
  duration_in_months: number | null;
}

export interface PromoCode {
  id: string;
  code: string;
  active: boolean;
  coupon: CouponSummary;
  max_redemptions: number | null;
  times_redeemed: number;
  expires_at: string | null;
  created: string;
  metadata: Record<string, string> | null;
}

export interface PromoRedemption {
  organization_id: number;
  organization_name: string;
  redeemed_at: string | null;
}

export interface PromoCodeDetail extends PromoCode {
  customer: string | null;
  first_time_transaction: boolean;
  minimum_amount: number | null;
  minimum_amount_currency: string | null;
  redeemed_by: PromoRedemption[];
}

export interface PromoCodeListResponse {
  promo_codes: PromoCode[];
  total: number;
}

export interface CreatePromoRequest {
  code: string;
  coupon_name: string;
  discount_type: 'percent' | 'amount';
  percent_off?: number;
  amount_off?: number;
  currency?: string;
  duration: 'once' | 'repeating' | 'forever';
  duration_in_months?: number;
  max_redemptions?: number | null;
  first_time_transaction?: boolean;
  expires_at?: string | null;
  applies_to_prices?: string[];
}

export const adminPromoAPI = {
  list: async (): Promise<PromoCodeListResponse> => {
    const response = await apiClient.get('/api/v1/admin/promo-codes');
    return response.data;
  },

  get: async (id: string): Promise<PromoCodeDetail> => {
    const response = await apiClient.get(`/api/v1/admin/promo-codes/${id}`);
    return response.data;
  },

  create: async (data: CreatePromoRequest): Promise<PromoCode> => {
    const response = await apiClient.post('/api/v1/admin/promo-codes', data);
    return response.data;
  },

  deactivate: async (id: string): Promise<PromoCode> => {
    const response = await apiClient.post(`/api/v1/admin/promo-codes/${id}/deactivate`);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/v1/admin/promo-codes/${id}`);
  },
};
