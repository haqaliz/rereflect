/**
 * Test for the M8 shadow-badge fix on the automation rule detail page's
 * execution log: an execution with status "shadow" must render a distinct,
 * non-destructive badge — not the red "failed" badge it currently falls
 * through to.
 *
 * This is a pre-existing M4.1.5 defect (AutomationExecution['status'] is
 * missing 'shadow', so StatusBadge falls through to the destructive/"failed"
 * branch). This test is intentionally kept in its own file so the fix can be
 * committed separately from the usage_trend trigger feature.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// ─── mocks ──────────────────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => ({ id: '11' }),
  usePathname: () => '/settings/automations/11',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockGet = vi.fn();
const mockListExecutions = vi.fn();

vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    create: vi.fn(),
    list: vi.fn(),
    get: (...args: any[]) => mockGet(...args),
    update: vi.fn(),
    delete: vi.fn(),
    toggle: vi.fn(),
    listExecutions: (...args: any[]) => mockListExecutions(...args),
    listTemplates: vi.fn().mockResolvedValue([]),
    enableTemplate: vi.fn(),
  },
  TRIGGER_TYPE_LABELS: {
    health_score_threshold: 'Health Score Threshold',
    churn_probability_threshold: 'Churn probability threshold',
    usage_trend: 'Usage Trend',
  },
  ACTION_TYPE_LABELS: {
    run_playbook: 'Run churn playbook',
  },
}));

const mockListPlaybooks = vi.fn();
vi.mock('@/lib/api/playbooks', () => ({
  listPlaybooks: (...args: any[]) => mockListPlaybooks(...args),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── import after mocks ───────────────────────────────────────────────────

import AutomationDetailPage from '../[id]/page';

// ─── fixtures ─────────────────────────────────────────────────────────────

const ownerUser = {
  id: 1,
  email: 'owner@test.com',
  role: 'owner',
  plan: 'business',
  organization_id: 1,
  is_system_admin: false,
};

const usageTrendRule = {
  id: 11,
  name: 'Usage decline outreach',
  description: null,
  is_active: true,
  mode: 'shadow' as const,
  trigger_type: 'usage_trend' as const,
  trigger_config: { states: ['declining', 'sharp_decline'] },
  actions: [{ type: 'run_playbook', config: { playbook_id: 1 } }],
  cooldown_hours: 24,
  execution_count: 1,
  last_executed_at: '2026-07-20T00:00:00Z',
  is_template: false,
  template_id: null,
  created_at: '2026-07-01T00:00:00Z',
};

const shadowExecution = {
  id: 1,
  rule_id: 11,
  feedback_id: null,
  customer_email: 'quiet-customer@example.com',
  trigger_snapshot: { old_trend_state: 'stable', new_trend_state: 'sharp_decline' },
  actions_executed: [{ type: 'run_playbook', result: 'would_run', error: null }],
  status: 'shadow',
  executed_at: '2026-07-21T04:00:00Z',
};

describe('AutomationDetailPage — shadow execution badge (AC7)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(usageTrendRule);
    mockListExecutions.mockResolvedValue([shadowExecution]);
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('renders a distinct, non-destructive badge for a shadow execution — not the red "failed" badge', async () => {
    const user = userEvent.setup();
    render(<AutomationDetailPage />);

    await waitFor(() => {
      expect(screen.getByText(usageTrendRule.name)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: /execution log/i }));

    const statusCell = await screen.findByText(/shadow/i);
    expect(statusCell).toBeInTheDocument();

    // The badge must not be the destructive "failed" rendering.
    expect(screen.queryByText('failed')).not.toBeInTheDocument();
    expect(statusCell.className).not.toMatch(/destructive/i);
  });
});
