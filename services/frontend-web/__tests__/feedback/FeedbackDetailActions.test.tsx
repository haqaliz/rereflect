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

vi.mock('@/lib/api/feedback', () => ({
  feedbackAPI: {
    get: (...args: unknown[]) => mockFeedbackGet(...args),
    analyze: (...args: unknown[]) => mockFeedbackAnalyze(...args),
    delete: (...args: unknown[]) => mockFeedbackDelete(...args),
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

const mockFeedback = {
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
  is_urgent: false,
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

// Import after all mocks are set up
import FeedbackDetailPage from '@/app/(dashboard)/feedbacks/[id]/page';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function setup() {
  mockUseAuth.mockReturnValue({ user: mockUser, isLoading: false, isAuthenticated: true });
  mockFeedbackGet.mockResolvedValue(mockFeedback);
  mockFeedbackAnalyze.mockResolvedValue({});
  mockFeedbackDelete.mockResolvedValue({});

  // jsdom doesn't have window.location properly set up for URL manipulation
  Object.defineProperty(window, 'location', {
    value: { href: 'http://localhost/feedbacks/42', search: '' },
    writable: true,
  });
}

async function renderAndWait() {
  const result = render(<FeedbackDetailPage />);
  // Wait for data to load (feedback text appears)
  await waitFor(() => expect(screen.getByText('The export feature keeps failing.')).toBeInTheDocument());
  return result;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('FeedbackDetailPage – action bar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setup();
  });

  // ── Change 1: No standalone Refresh button ───────────────────────────────

  describe('Change 1: Refresh button removed', () => {
    it('does NOT render a standalone refresh icon button (h-8 w-8 icon-only) in the action bar', async () => {
      await renderAndWait();

      // The old refresh button was: variant="ghost" size="icon" className="h-8 w-8"
      // It contained only a RefreshCw SVG with class "lucide-refresh-cw" and no text.
      // We find all buttons and assert none is a ghost icon-only button (h-8 w-8 with no text).
      const allButtons = screen.getAllByRole('button');
      const iconOnlyRefreshButtons = allButtons.filter((btn) => {
        const hasH8W8 = btn.className.includes('h-8') && btn.className.includes('w-8');
        const hasNoText = btn.textContent?.trim() === '';
        const hasSvg = btn.querySelector('svg') !== null;
        return hasH8W8 && hasNoText && hasSvg;
      });
      expect(iconOnlyRefreshButtons).toHaveLength(0);
    });

    it('does NOT render a standalone "Refresh" button separate from the Actions dropdown', async () => {
      await renderAndWait();

      // The Back button should still exist
      const backButton = screen.getByRole('button', { name: /back/i });
      expect(backButton).toBeInTheDocument();

      // No standalone button named "Refresh"
      expect(screen.queryByRole('button', { name: /^refresh$/i })).not.toBeInTheDocument();

      // Count total buttons in header area — Back + TabsList buttons + Actions = reasonable amount
      // The old page had: Back, Overview tab, Analysis tab, Timeline tab, Refresh(icon), Create Issue, Respond, Re-analyze, Delete
      // New page should have: Back, Overview tab, Analysis tab, Timeline tab, Actions
      // We assert there is no 6th+ button before "Actions" by checking we don't have >5 buttons in the bar
      // (Back + 3 tabs + Actions = 5)
      const allButtons = screen.getAllByRole('button');
      // Just confirm the icon-only h-8 w-8 empty-text button is gone
      const iconOnlyButtons = allButtons.filter((btn) => {
        return btn.className.includes('h-8') && btn.className.includes('w-8') && btn.textContent?.trim() === '';
      });
      expect(iconOnlyButtons).toHaveLength(0);
    });
  });

  // ── Change 2: Actions dropdown ───────────────────────────────────────────

  describe('Change 2: Actions dropdown', () => {
    it('renders an "Actions" button', async () => {
      await renderAndWait();
      expect(screen.getByRole('button', { name: /actions/i })).toBeInTheDocument();
    });

    it('opens a dropdown with Respond, Re-analyze, Create Issue, and Delete items', async () => {
      const user = userEvent.setup();
      await renderAndWait();

      const actionsBtn = screen.getByRole('button', { name: /actions/i });
      await user.click(actionsBtn);

      await waitFor(() => {
        expect(screen.getByRole('menuitem', { name: /respond/i })).toBeInTheDocument();
        expect(screen.getByRole('menuitem', { name: /re-analyze/i })).toBeInTheDocument();
        expect(screen.getByRole('menuitem', { name: /create issue/i })).toBeInTheDocument();
        expect(screen.getByRole('menuitem', { name: /delete/i })).toBeInTheDocument();
      });
    });

    it('clicking Respond opens the ResponseModal', async () => {
      const user = userEvent.setup();
      await renderAndWait();

      expect(screen.queryByTestId('response-modal')).not.toBeInTheDocument();

      const actionsBtn = screen.getByRole('button', { name: /actions/i });
      await user.click(actionsBtn);

      await waitFor(() => screen.getByRole('menuitem', { name: /respond/i }));
      await user.click(screen.getByRole('menuitem', { name: /respond/i }));

      await waitFor(() => expect(screen.getByTestId('response-modal')).toBeInTheDocument());
    });

    it('clicking Re-analyze calls feedbackAPI.analyze', async () => {
      const user = userEvent.setup();
      await renderAndWait();

      const actionsBtn = screen.getByRole('button', { name: /actions/i });
      await user.click(actionsBtn);

      await waitFor(() => screen.getByRole('menuitem', { name: /re-analyze/i }));
      await user.click(screen.getByRole('menuitem', { name: /re-analyze/i }));

      await waitFor(() => expect(mockFeedbackAnalyze).toHaveBeenCalledWith([42], true));
    });

    it('clicking Delete calls feedbackAPI.delete after confirmation', async () => {
      const user = userEvent.setup();
      // Mock window.confirm to return true
      vi.spyOn(window, 'confirm').mockReturnValue(true);
      await renderAndWait();

      const actionsBtn = screen.getByRole('button', { name: /actions/i });
      await user.click(actionsBtn);

      await waitFor(() => screen.getByRole('menuitem', { name: /delete/i }));
      await user.click(screen.getByRole('menuitem', { name: /delete/i }));

      await waitFor(() => expect(mockFeedbackDelete).toHaveBeenCalledWith(42));
    });

    it('Delete item has destructive styling', async () => {
      const user = userEvent.setup();
      await renderAndWait();

      const actionsBtn = screen.getByRole('button', { name: /actions/i });
      await user.click(actionsBtn);

      await waitFor(() => screen.getByRole('menuitem', { name: /delete/i }));
      const deleteItem = screen.getByRole('menuitem', { name: /delete/i });
      // shadcn destructive menu items get a data-variant or class including "destructive"
      // We check for the destructive class pattern
      expect(deleteItem.className).toMatch(/destructive/i);
    });

    it('individual Respond, Re-analyze, Delete buttons are NOT present outside dropdown', async () => {
      await renderAndWait();

      // These were standalone buttons before — now only exist in dropdown
      // (The dropdown is closed, so menu items are not in DOM)
      expect(screen.queryByRole('button', { name: /^respond$/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^re-analyze$/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^delete$/i })).not.toBeInTheDocument();
    });
  });

  // ── Change 3: Create Issue navigates to page ─────────────────────────────

  describe('Change 3: Create Issue navigates to /feedbacks/42/create-issue', () => {
    it('clicking Create Issue in dropdown calls router.push with correct URL', async () => {
      const user = userEvent.setup();
      await renderAndWait();

      const actionsBtn = screen.getByRole('button', { name: /actions/i });
      await user.click(actionsBtn);

      await waitFor(() => screen.getByRole('menuitem', { name: /create issue/i }));
      await user.click(screen.getByRole('menuitem', { name: /create issue/i }));

      await waitFor(() =>
        expect(mockPush).toHaveBeenCalledWith('/feedbacks/42/create-issue')
      );
    });
  });
});
