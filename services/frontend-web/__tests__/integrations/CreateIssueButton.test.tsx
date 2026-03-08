/**
 * Task #11: Tests for "Create Issue" button placement on
 * - Feedback detail page
 * - Pain points page
 * - Feature requests page
 *
 * Button behavior:
 * - Hidden if no integration is connected
 * - Disabled if user is on Free plan
 * - Visible for Pro+ users with connected integration
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// ── Next.js navigation ───────────────────────────────────────────────────────
const mockPush = vi.fn();
const mockBack = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, back: mockBack }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: '42' }),
  usePathname: () => '/feedbacks/42',
}));

// ── Auth ─────────────────────────────────────────────────────────────────────
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// ── Feedback API ─────────────────────────────────────────────────────────────
vi.mock('@/lib/api/feedback', () => ({
  feedbackAPI: {
    get: vi.fn(),
    list: vi.fn(),
    analyze: vi.fn(),
    delete: vi.fn(),
  },
}));

// ── Customer health API ───────────────────────────────────────────────────────
vi.mock('@/lib/api/customer-health', () => ({
  customerHealthAPI: { getByEmail: vi.fn() },
}));

// ── Linear API ────────────────────────────────────────────────────────────────
vi.mock('@/lib/api/linear', () => ({
  linearAPI: {
    getStatus: vi.fn(),
    getLinkedIssues: vi.fn(),
    createIssue: vi.fn(),
    getTeams: vi.fn(),
    getProjects: vi.fn(),
    getLabels: vi.fn(),
  },
  LINEAR_PRIORITY_LABELS: { 0: 'No priority', 1: 'Urgent', 2: 'High', 3: 'Medium', 4: 'Low' },
}));

// ── Analytics ─────────────────────────────────────────────────────────────────
vi.mock('@/lib/analytics', () => ({
  analytics: { feedbackViewed: vi.fn() },
}));

// ── Realtime ──────────────────────────────────────────────────────────────────
vi.mock('@/hooks/useRealtimeEvents', () => ({
  useRealtimeEvents: vi.fn(),
}));

import { feedbackAPI } from '@/lib/api/feedback';
import { linearAPI } from '@/lib/api/linear';

const proUser = {
  id: 1, email: 'user@test.com', role: 'owner', plan: 'pro',
  organization_id: 1, is_system_admin: false,
};
const freeUser = { ...proUser, plan: 'free' };

const connectedStatus = {
  connected: true, org_name: 'Acme Corp', org_id: 'oid',
  connected_by_email: 'admin@test.com', connected_at: '2026-01-01T00:00:00Z', is_active: true,
};
const disconnectedStatus = {
  connected: false, org_name: null, org_id: null,
  connected_by_email: null, connected_at: null, is_active: false,
};

const mockFeedback = {
  id: 42,
  organization_id: 1,
  text: 'This is a test feedback',
  source: null, source_id: null, source_name: null, source_metadata: null,
  sentiment_score: -0.5, sentiment_label: 'negative',
  extracted_issue: null, tags: ['performance'],
  is_urgent: false, created_at: '2026-03-01T00:00:00Z',
  pain_point_category: 'performance', pain_point_severity: 'medium', pain_point_text: null,
  feature_request_category: null, feature_request_priority: null, feature_request_text: null,
  urgent_category: null, urgent_response_time: null,
  categorization_confidence: 0.8, churn_risk_score: 20,
  churn_risk_factors: null, customer_confidence_score: null,
  suggested_action: null, customer_email: null,
  workflow_status: 'new', assigned_to: null, assigned_to_email: null,
};

const mockFeedbackList = {
  items: [mockFeedback],
  total: 1, page: 1, page_size: 1000, total_pages: 1,
};

// ── Feedback Detail Page ─────────────────────────────────────────────────────
describe('Feedback Detail Page - Create Issue button', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(feedbackAPI.get).mockResolvedValue(mockFeedback);
    vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue([]);
    vi.mocked(linearAPI.getTeams).mockResolvedValue([]);
    vi.mocked(linearAPI.getLabels).mockResolvedValue([]);
  });

  it('shows "Create Issue" button for Pro user with connected integration', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    vi.mocked(linearAPI.getStatus).mockResolvedValue(connectedStatus);

    const FeedbackDetailPage = (await import('@/app/(dashboard)/feedbacks/[id]/page')).default;
    render(<FeedbackDetailPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create issue/i })).toBeInTheDocument();
    });
  });

  it('hides "Create Issue" button when no integration is connected', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    vi.mocked(linearAPI.getStatus).mockResolvedValue(disconnectedStatus);

    const FeedbackDetailPage = (await import('@/app/(dashboard)/feedbacks/[id]/page')).default;
    render(<FeedbackDetailPage />);
    await waitFor(() => {
      // Wait for page to load
      expect(screen.getByText(/test feedback/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /create issue/i })).not.toBeInTheDocument();
  });

  it('shows disabled "Create Issue" button for Free plan user', async () => {
    mockUseAuth.mockReturnValue({ user: freeUser });
    vi.mocked(linearAPI.getStatus).mockResolvedValue(connectedStatus);

    const FeedbackDetailPage = (await import('@/app/(dashboard)/feedbacks/[id]/page')).default;
    render(<FeedbackDetailPage />);
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /create issue/i });
      expect(btn).toBeDisabled();
    });
  });
});

// ── Pain Points Page ─────────────────────────────────────────────────────────
describe('Pain Points Page - Create Issue button', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(feedbackAPI.list).mockResolvedValue(mockFeedbackList);
    vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue([]);
    vi.mocked(linearAPI.getTeams).mockResolvedValue([]);
    vi.mocked(linearAPI.getLabels).mockResolvedValue([]);
  });

  it('shows "Create Issue" action for Pro user with connected integration', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    vi.mocked(linearAPI.getStatus).mockResolvedValue(connectedStatus);

    const PainPointsPage = (await import('@/app/(dashboard)/pain-points/page')).default;
    render(<PainPointsPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create issue/i })).toBeInTheDocument();
    });
  });

  it('hides "Create Issue" button when no integration is connected', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    vi.mocked(linearAPI.getStatus).mockResolvedValue(disconnectedStatus);

    const PainPointsPage = (await import('@/app/(dashboard)/pain-points/page')).default;
    render(<PainPointsPage />);
    await waitFor(() => {
      // Wait for page to load (table or empty state)
      expect(screen.getByText(/pain point/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /create issue/i })).not.toBeInTheDocument();
  });
});

// ── Feature Requests Page ────────────────────────────────────────────────────
describe('Feature Requests Page - Create Issue button', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(feedbackAPI.list).mockResolvedValue({
      ...mockFeedbackList,
      items: [{ ...mockFeedback, sentiment_label: 'positive', pain_point_category: null, feature_request_category: 'core_functionality' }],
    });
    vi.mocked(linearAPI.getLinkedIssues).mockResolvedValue([]);
    vi.mocked(linearAPI.getTeams).mockResolvedValue([]);
    vi.mocked(linearAPI.getLabels).mockResolvedValue([]);
  });

  it('shows "Create Issue" action for Pro user with connected integration', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    vi.mocked(linearAPI.getStatus).mockResolvedValue(connectedStatus);

    const FeatureRequestsPage = (await import('@/app/(dashboard)/feature-requests/page')).default;
    render(<FeatureRequestsPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create issue/i })).toBeInTheDocument();
    });
  });

  it('hides "Create Issue" button when no integration is connected', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    vi.mocked(linearAPI.getStatus).mockResolvedValue(disconnectedStatus);

    const FeatureRequestsPage = (await import('@/app/(dashboard)/feature-requests/page')).default;
    render(<FeatureRequestsPage />);
    await waitFor(() => {
      expect(screen.getByText(/feature request/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /create issue/i })).not.toBeInTheDocument();
  });
});
