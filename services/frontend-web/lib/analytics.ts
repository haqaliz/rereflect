/**
 * Mixpanel Analytics Integration
 *
 * Tracks key user events for conversion optimization.
 * Free tier: 20M events/month
 */
import mixpanel from "mixpanel-browser";

const MIXPANEL_TOKEN = process.env.NEXT_PUBLIC_MIXPANEL_TOKEN;
const IS_PRODUCTION = process.env.NODE_ENV === "production";

// Initialize Mixpanel (production only)
export function initAnalytics() {
  if (typeof window === "undefined") return;
  if (!IS_PRODUCTION || !MIXPANEL_TOKEN) return;

  mixpanel.init(MIXPANEL_TOKEN, {
    autocapture: true,
    record_sessions_percent: 100,
  });
}

// Identify user (call after login/signup)
export function identifyUser(userId: string, properties?: Record<string, unknown>) {
  if (!IS_PRODUCTION || !MIXPANEL_TOKEN) return;

  mixpanel.identify(userId);
  if (properties) {
    mixpanel.people.set(properties);
  }
}

// Reset on logout
export function resetAnalytics() {
  if (!IS_PRODUCTION || !MIXPANEL_TOKEN) return;
  mixpanel.reset();
}

// Track custom event
export function trackEvent(eventName: string, properties?: Record<string, unknown>) {
  if (!IS_PRODUCTION || !MIXPANEL_TOKEN) return;
  mixpanel.track(eventName, properties);
}

// ============================================================================
// Pre-defined Events (for consistency)
// ============================================================================

// Auth events
export const analytics = {
  // Auth
  signup: (method: "email" | "google") => {
    trackEvent("Signup", { method });
  },

  login: (method: "email" | "google") => {
    trackEvent("Login", { method });
  },

  logout: () => {
    trackEvent("Logout");
    resetAnalytics();
  },

  // Activation events (key for conversion)
  csvUploaded: (rowCount: number) => {
    trackEvent("CSV Uploaded", { row_count: rowCount });
  },

  slackConnected: () => {
    trackEvent("Slack Connected");
  },

  analysisViewed: (feedbackCount: number) => {
    trackEvent("Analysis Viewed", { feedback_count: feedbackCount });
  },

  // Engagement
  feedbackViewed: (feedbackId: number, sentiment: string) => {
    trackEvent("Feedback Viewed", { feedback_id: feedbackId, sentiment });
  },

  dashboardViewed: () => {
    trackEvent("Dashboard Viewed");
  },

  filterApplied: (filterType: string, filterValue: string) => {
    trackEvent("Filter Applied", { filter_type: filterType, filter_value: filterValue });
  },

  // Team
  teamMemberInvited: (role: string) => {
    trackEvent("Team Member Invited", { role });
  },

  // Billing
  pricingViewed: () => {
    trackEvent("Pricing Viewed");
  },

  checkoutStarted: (plan: string) => {
    trackEvent("Checkout Started", { plan });
  },

  subscriptionCreated: (plan: string) => {
    trackEvent("Subscription Created", { plan });
  },

  // Promo
  promoSignup: (promoCode: string, method: "email" | "google") => {
    trackEvent("Promo Signup", { promo_code: promoCode, method });
  },

  promoCheckoutStarted: (promoCode: string, plan: string) => {
    trackEvent("Promo Checkout Started", { promo_code: promoCode, plan });
  },

  // Feature usage
  featureUsed: (feature: string) => {
    trackEvent("Feature Used", { feature });
  },
};
