import apiClient from '../api-client';

// Plan types
export interface PlanFeature {
  id: string;
  name: string;
  included: boolean;
}

export interface Plan {
  id: string;
  name: string;
  description: string;
  price_monthly: number | null;
  price_annual: number | null;
  feedback_limit: number | null;
  seat_limit: number | null;
  features: PlanFeature[];
  is_popular?: boolean;
  overage_enabled: boolean;
  overage_price_cents?: number;
}

export interface PlansResponse {
  plans: Plan[];
}

// Subscription types
export interface Subscription {
  id: number;
  plan: string;
  billing_cycle: string | null;
  status: string;
  is_trial: boolean;
  trial_days_remaining: number | null;
  trial_end: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  canceled_at: string | null;
  stripe_subscription_id: string | null;
}

export interface SubscriptionResponse {
  subscription: Subscription;
  can_manage_billing: boolean;
}

// Usage types
export interface Usage {
  feedback_used: number;
  feedback_limit: number | null;
  feedback_percentage: number;
  seats_used: number;
  seats_limit: number | null;
  seats_percentage: number;
  period_start: string;
  period_end: string;
  overage_count: number;
}

// Invoice types
export interface Invoice {
  id: string;
  number: string | null;
  amount_due: number;
  amount_paid: number;
  currency: string;
  status: string;
  created: string;
  due_date: string | null;
  paid_at: string | null;
  hosted_invoice_url: string | null;
  invoice_pdf: string | null;
}

export interface InvoicesResponse {
  invoices: Invoice[];
}

export interface UpcomingInvoice {
  amount_due: number;
  currency: string;
  period_start: string;
  period_end: string;
  lines: {
    description: string;
    amount: number;
    quantity: number;
  }[];
}

// Request types
export interface StartTrialRequest {
  plan?: string;
}

export interface CreateCheckoutRequest {
  plan: string;
  billing_cycle: 'monthly' | 'annual';
  success_url?: string;
  cancel_url?: string;
  promo_code?: string;
}

export interface CreatePortalRequest {
  return_url?: string;
}

// Response types
export interface CheckoutResponse {
  checkout_url: string;
}

export interface PortalResponse {
  portal_url: string;
}

export interface TrialResponse {
  message: string;
  subscription: Subscription;
}

// Billing cycle options
export const BILLING_CYCLES = [
  { value: 'monthly', label: 'Monthly', discount: null },
  { value: 'annual', label: 'Annual', discount: '17% off (2 months free)' },
] as const;

export const billingAPI = {
  /**
   * Get all available plans with pricing and features
   */
  getPlans: async (): Promise<PlansResponse> => {
    const response = await apiClient.get('/api/v1/billing/plans');
    return response.data;
  },

  /**
   * Get current organization's subscription
   */
  getSubscription: async (): Promise<SubscriptionResponse> => {
    const response = await apiClient.get('/api/v1/billing/subscription');
    return response.data;
  },

  /**
   * Sync subscription status from Stripe
   * Call this after checkout success to immediately update the local subscription
   */
  syncSubscription: async (): Promise<SubscriptionResponse> => {
    const response = await apiClient.post('/api/v1/billing/sync-subscription');
    return response.data;
  },

  /**
   * Get current usage for the billing period
   */
  getUsage: async (): Promise<Usage> => {
    const response = await apiClient.get('/api/v1/billing/usage');
    return response.data;
  },

  /**
   * Start a 14-day free trial (Pro plan by default)
   */
  startTrial: async (data?: StartTrialRequest): Promise<TrialResponse> => {
    const response = await apiClient.post('/api/v1/billing/start-trial', data || {});
    return response.data;
  },

  /**
   * Create a Stripe Checkout session for subscription
   */
  createCheckout: async (data: CreateCheckoutRequest): Promise<CheckoutResponse> => {
    const response = await apiClient.post('/api/v1/billing/checkout', data);
    return response.data;
  },

  /**
   * Create a Stripe Customer Portal session
   */
  createPortal: async (data?: CreatePortalRequest): Promise<PortalResponse> => {
    const response = await apiClient.post('/api/v1/billing/portal', data || {});
    return response.data;
  },

  /**
   * Get invoice history
   */
  getInvoices: async (limit = 10): Promise<InvoicesResponse> => {
    const response = await apiClient.get('/api/v1/billing/invoices', {
      params: { limit },
    });
    return response.data;
  },

  /**
   * Get upcoming invoice preview
   */
  getUpcomingInvoice: async (): Promise<UpcomingInvoice | null> => {
    try {
      const response = await apiClient.get('/api/v1/billing/invoices/upcoming');
      return response.data;
    } catch {
      return null;
    }
  },
};

// Helper functions
export function formatPrice(cents: number | null, currency = 'USD'): string {
  if (cents === null) return 'Contact Sales';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

export function formatPriceWithCents(cents: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

export function getStatusColor(status: string): string {
  switch (status) {
    case 'active':
      return 'text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950';
    case 'trialing':
      return 'text-blue-600 border-blue-600/30 bg-blue-50 dark:bg-blue-950';
    case 'past_due':
      return 'text-yellow-600 border-yellow-600/30 bg-yellow-50 dark:bg-yellow-950';
    case 'canceled':
    case 'incomplete':
      return 'text-red-600 border-red-600/30 bg-red-50 dark:bg-red-950';
    default:
      return 'text-muted-foreground';
  }
}

export function getStatusLabel(status: string): string {
  switch (status) {
    case 'active':
      return 'Active';
    case 'trialing':
      return 'Trial';
    case 'past_due':
      return 'Past Due';
    case 'canceled':
      return 'Canceled';
    case 'incomplete':
      return 'Incomplete';
    default:
      return status;
  }
}

export function isPaidPlan(plan: string): boolean {
  return plan !== 'free';
}

export function canUpgrade(currentPlan: string, targetPlan: string): boolean {
  const planOrder = ['free', 'pro', 'business', 'enterprise'];
  return planOrder.indexOf(targetPlan) > planOrder.indexOf(currentPlan);
}

export function canDowngrade(currentPlan: string, targetPlan: string): boolean {
  const planOrder = ['free', 'pro', 'business', 'enterprise'];
  return planOrder.indexOf(targetPlan) < planOrder.indexOf(currentPlan);
}
