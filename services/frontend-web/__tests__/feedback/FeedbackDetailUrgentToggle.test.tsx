import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockBack = vi.fn();
const mockRouterReplace = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, back: mockBack, replace: mockRouterReplace }),
  useParams: () => ({ id: '42' }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const mockFeedbackGet = vi.fn();
const mockFeedbackAnalyze = vi.fn();
const mockFeedbackDelete = vi.fn();
const mockFeedbackSetUrgent = vi.fn();

vi.mock('@/lib/api/feedback', () => ({
  feedbackAPI: {
    get: (...args: unknown[]) => mockFeedbackGet(...args),
    analyze: (...args: unknown[]) => mockFeedbackAnalyze(...args),
    delete: (...args: unknown[]) => mockFeedbackDelete(...args),
    setUrgent: (...args: unknown[]) => mockFeedbackSetUrgent(...args),
  },
}));

vi.mock('@/lib/api/customer-health', () => ({
  customerHealthAPI: {
    getByEmail: vi.fn().mockRejectedValue(new Error('no health')),
  },
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/hooks/useRealtimeEvents', () => ({
  useRealtimeEvents: vi.fn(),
}));

vi.mock('@/lib/analytics', () => ({
  analytics: { feedbackViewed: vi.fn() },
}));

vi.mock('@/lib/api/linear', () => ({
  linearAPI: {
    getStatus: vi.fn().mockResolvedValue({ connected: false, is_active: false }),
    getTeams: vi.fn().mockResolvedValue([]),
    getLabels: vi.fn().mockResolvedValue([]),
    getLinkedIssues: vi.fn().mockResolvedValue([]),
    getProjects: vi.fn().mockResolvedValue([]),
  },
  LINEAR_PRIORITY_LABELS: { '1': 'Urgent', '2': 'High', '3': 'Medium', '4': 'Low', '0': 'None' },
}));

vi.mock('@/lib/api/responses', () => ({
  responsesAPI: {
    suggestTemplate: vi.fn(),
    generateResponse: vi.fn(),
    sendResponse: vi.fn(),
    getResponseUsage: vi.fn(),
  },
  TONE_OPTIONS: [],
}));

vi.mock('@/components/workflow/WorkflowSection', () => ({
  WorkflowSection: () => <div data-testid="workflow-section" />,
}));

vi.mock('@/components/workflow/FeedbackTimeline', () => ({
  FeedbackTimeline: () => <div data-testid="feedback-timeline" />,
}));

vi.mock('@/components/feedback/LinkedIssuesCard', () => ({
  LinkedIssuesCard: () => <div data-testid="linked-issues-card" />,
}));

vi.mock('@/components/feedback/ResponseModal', () => ({
  ResponseModal: ({ open, onClose }: { open: boolean; onClose: () => void; feedback: unknown }) => (
    open ? <div data-testid="response-modal" role="dialog"><button onClick={onClose}>Close</button></div> : null
  ),
}));

vi.mock('@/components/integrations/CreateIssueDialog', () => ({
  CreateIssueDialog: () => <div data-testid="create-issue-dialog" />,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// Silence the history.replaceState cross-origin error in jsdom
vi.spyOn(window.history, 'replaceState').mockImplementation(() => {});

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const mockUser = {
  id: 1,
  email: 'user@test.com',
  role: 'owner',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const baseFeedback = {
  id: 42,
  text: 'The export feature keeps failing.',
  sentiment_label: 'negative',
  sentiment_score: -0.8,
  pain_point_category: null,
  pain_point_severity: null,
  pain_point_text: null,
  feature_request_category: null,
  feature_request_priority: null,
  feature_request_text: null,
  urgent_category: null,
  urgent_response_time: null,
  extracted_issue: 'Export broken',
  tags: [],
  source: null,
  source_name: null,
  source_metadata: null,
  customer_email: null,
  created_at: '2024-01-15T10:30:00Z',
  workflow_status: 'open',
  assigned_to: null,
  assigned_to_email: null,
  categorization_confidence: null,
  churn_risk_score: null,
  churn_risk_factors: null,
  customer_confidence_score: null,
  suggested_action: null,
};

// ─── Import under test ─────────────────────────────────────────────────────────

import FeedbackDetailPage from '@/app/(dashboard)/feedbacks/[id]/page';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function setup(isUrgent: boolean) {
  mockUseAuth.mockReturnValue({ user: mockUser, isLoading: false, isAuthenticated: true });
  mockFeedbackGet.mockResolvedValue({ ...baseFeedback, is_urgent: isUrgent });
  mockFeedbackAnalyze.mockResolvedValue({});
  mockFeedbackDelete.mockResolvedValue({});
  mockFeedbackSetUrgent.mockResolvedValue({ ...baseFeedback, is_urgent: !isUrgent });

  Object.defineProperty(window, 'location', {
    value: { href: 'http://localhost/feedbacks/42', search: '' },
    writable: true,
  });
}

async function renderAndWait() {
  const result = render(<FeedbackDetailPage />);
  await waitFor(() => expect(screen.getByText('The export feature keeps failing.')).toBeInTheDocument());
  return result;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('FeedbackDetailPage – urgent toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a "Mark as urgent" control when the item is not urgent', async () => {
    setup(false);
    await renderAndWait();

    expect(
      screen.getByRole('button', { name: /mark as urgent/i })
    ).toBeInTheDocument();
  });

  it('renders a "Mark as not urgent" control when the item is urgent', async () => {
    setup(true);
    await renderAndWait();

    expect(
      screen.getByRole('button', { name: /mark as not urgent/i })
    ).toBeInTheDocument();
  });

  it('clicking the toggle calls feedbackAPI.setUrgent with (id, newValue)', async () => {
    const user = userEvent.setup();
    setup(false);
    await renderAndWait();

    const toggleBtn = screen.getByRole('button', { name: /mark as urgent/i });
    await user.click(toggleBtn);

    await waitFor(() => expect(mockFeedbackSetUrgent).toHaveBeenCalledWith(42, true));
  });

  it('reflects the updated urgency state returned by the API after toggling', async () => {
    const user = userEvent.setup();
    setup(false);
    await renderAndWait();

    const toggleBtn = screen.getByRole('button', { name: /mark as urgent/i });
    await user.click(toggleBtn);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /mark as not urgent/i })).toBeInTheDocument()
    );
  });

  it('toggling from urgent calls the API with false', async () => {
    const user = userEvent.setup();
    setup(true);
    await renderAndWait();

    const toggleBtn = screen.getByRole('button', { name: /mark as not urgent/i });
    await user.click(toggleBtn);

    await waitFor(() => expect(mockFeedbackSetUrgent).toHaveBeenCalledWith(42, false));
  });
});
