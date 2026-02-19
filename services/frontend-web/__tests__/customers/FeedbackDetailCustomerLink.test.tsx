import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: '1234' }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/feedbacks/1234',
}));

// Mock AuthContext - Pro plan user
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@test.com', role: 'owner', plan: 'pro', organization_id: 1, is_system_admin: false },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

// Mock feedback API
vi.mock('@/lib/api/feedback', () => ({
  feedbackAPI: {
    get: vi.fn(),
    analyze: vi.fn(),
    delete: vi.fn(),
  },
}));

// Mock customer health API
vi.mock('@/lib/api/customer-health', () => ({
  customerHealthAPI: {
    getByEmail: vi.fn(),
  },
}));

// Mock analytics
vi.mock('@/lib/analytics', () => ({
  analytics: {
    feedbackViewed: vi.fn(),
    logout: vi.fn(),
  },
  identifyUser: vi.fn(),
}));

// Mock workflow components
vi.mock('@/components/workflow/WorkflowSection', () => ({
  WorkflowSection: () => <div data-testid="workflow-section" />,
}));

vi.mock('@/components/workflow/FeedbackTimeline', () => ({
  FeedbackTimeline: () => <div data-testid="feedback-timeline" />,
}));

import { feedbackAPI } from '@/lib/api/feedback';
import { customerHealthAPI } from '@/lib/api/customer-health';
import FeedbackDetailPage from '../../app/(dashboard)/feedbacks/[id]/page';

const mockFeedbackWithCustomer = {
  id: 1234,
  text: 'The billing page keeps crashing when I try to update my payment method.',
  customer_email: 'john@acme.com',
  customer_name: 'John Doe',
  sentiment_label: 'negative',
  sentiment_score: -0.72,
  churn_risk_score: 68,
  workflow_status: 'in_review',
  assigned_to: null,
  assigned_to_email: null,
  created_at: '2026-02-18T14:30:00Z',
  source: 'slack',
  source_name: null,
  source_metadata: null,
  is_urgent: false,
  extracted_issue: null,
  tags: [],
  categorization_confidence: null,
  pain_point_category: null,
  pain_point_severity: null,
  pain_point_text: null,
  feature_request_category: null,
  feature_request_priority: null,
  feature_request_text: null,
  urgent_category: null,
  urgent_response_time: null,
  suggested_action: null,
};

const mockCustomerHealth = {
  customer_email: 'john@acme.com',
  health_score: 34,
  risk_level: 'at_risk',
  confidence_level: 'high',
  feedback_count: 28,
};

describe('FeedbackDetailPage - customer email link (Pro+)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'localStorage', {
      value: { getItem: vi.fn(() => 'mock-token'), setItem: vi.fn(), removeItem: vi.fn() },
      writable: true,
    });
    (feedbackAPI.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockFeedbackWithCustomer);
    (customerHealthAPI.getByEmail as ReturnType<typeof vi.fn>).mockResolvedValue(mockCustomerHealth);
  });

  it('renders a clickable link from customer_email to the profile page', async () => {
    render(<FeedbackDetailPage />);
    await waitFor(() => {
      const link = screen.getByRole('link', { name: /john@acme.com/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', `/customers/${encodeURIComponent('john@acme.com')}`);
    });
  });
});
