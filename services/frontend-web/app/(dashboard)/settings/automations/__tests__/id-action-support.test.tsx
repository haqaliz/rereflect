/**
 * R6 (automation-action-support) on the rule detail/edit page: the action
 * select is filtered by the trigger's supported actions, a rule saved before
 * the matrix existed shows an inline warning, saving is blocked while an
 * unsupported action remains, and an endpoint failure never blocks editing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import matrix from '../../../../../../worker-service/tests/fixtures/automation_action_support.json';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: '9' }),
  usePathname: () => '/settings/automations/9',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => mockUseAuth() }));

const mockGet = vi.fn();
const mockUpdate = vi.fn();
const mockGetActionSupport = vi.fn();
vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    get: (...args: any[]) => mockGet(...args),
    update: (...args: any[]) => mockUpdate(...args),
    getActionSupport: (...args: any[]) => mockGetActionSupport(...args),
    listExecutions: vi.fn().mockResolvedValue([]),
    listDeliveries: vi.fn().mockResolvedValue([]),
  },
  TRIGGER_TYPE_LABELS: {
    health_score_threshold: 'Health Score Threshold',
    sentiment_pattern: 'Sentiment Pattern',
    churn_risk_level_change: 'Churn Risk Level Change',
    feedback_category_match: 'Category Match',
    churn_probability_threshold: 'Churn probability threshold',
    usage_trend: 'Usage Trend',
  },
  ACTION_TYPE_LABELS: {
    auto_assign: 'Auto-Assign',
    change_status: 'Change Status',
    send_notification: 'Send Notification',
    draft_response: 'Draft AI Response',
    run_playbook: 'Run churn playbook',
    send_customer_email: 'Send Customer Email',
  },
}));

const mockListPlaybooks = vi.fn();
vi.mock('@/lib/api/playbooks', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api/playbooks')>()),
  listPlaybooks: (...args: any[]) => mockListPlaybooks(...args),
}));

const mockToastError = vi.fn();
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: (...a: any[]) => mockToastError(...a) } }));

import AutomationDetailPage from '../[id]/page';

const ownerUser = { id: 1, email: 'o@test.com', role: 'owner', plan: 'business', organization_id: 1, is_system_admin: false };

const baseRule = {
  id: 9,
  name: 'Usage decline outreach',
  description: null,
  is_active: true,
  mode: 'active' as const,
  trigger_type: 'usage_trend' as const,
  trigger_config: { states: ['declining'] },
  actions: [{ type: 'send_notification', config: { recipients: 'admins', channels: ['dashboard'] } }],
  cooldown_hours: 24,
  execution_count: 0,
  last_executed_at: null,
  is_template: false,
  template_id: null,
  created_at: '2026-07-01T00:00:00Z',
};

async function offeredActions(user: ReturnType<typeof userEvent.setup>, index = 0) {
  await user.click(await screen.findByTestId(`action-type-select-${index}`));
  const listbox = await screen.findByRole('listbox');
  const names = within(listbox).getAllByRole('option').map(o => o.textContent);
  await user.keyboard('{Escape}');
  return names;
}

describe('AutomationDetailPage — action support (R6)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
    mockGetActionSupport.mockResolvedValue(matrix);
  });

  it('offers exactly the usage_trend-supported actions', async () => {
    mockGet.mockResolvedValue(baseRule);
    const user = userEvent.setup();
    render(<AutomationDetailPage />);

    expect(await offeredActions(user)).toEqual([
      'Send Notification',
      'Run churn playbook',
      'Send Customer Email',
    ]);
  });

  it('does not offer run_playbook for a feedback_category_match rule', async () => {
    mockGet.mockResolvedValue({
      ...baseRule,
      trigger_type: 'feedback_category_match',
      trigger_config: { categories: ['billing'], is_urgent: false },
    });
    const user = userEvent.setup();
    render(<AutomationDetailPage />);

    const names = await offeredActions(user);
    expect(names).not.toContain('Run churn playbook');
    expect(names).toContain('Auto-Assign');
  });

  it('warns on a saved usage_trend + auto_assign action and blocks saving it', async () => {
    mockGet.mockResolvedValue({
      ...baseRule,
      actions: [{ type: 'auto_assign', config: { assign_to: 'round_robin' } }],
    });
    const user = userEvent.setup();
    render(<AutomationDetailPage />);

    const warning = await screen.findByTestId('action-unsupported-warning-0');
    expect(warning).toHaveTextContent(/Auto-Assign isn.t supported for this trigger/);
    expect(screen.getByTestId('action-type-select-0')).toHaveTextContent('Auto-Assign');

    await user.click(screen.getByRole('button', { name: /save changes/i }));
    expect(mockToastError).toHaveBeenCalledWith(expect.stringMatching(/not supported|isn.t supported/i));
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('offers all six action types and shows no warning when the endpoint fails', async () => {
    mockGetActionSupport.mockRejectedValue(new Error('boom'));
    mockGet.mockResolvedValue({
      ...baseRule,
      actions: [{ type: 'auto_assign', config: { assign_to: 'round_robin' } }],
    });
    const user = userEvent.setup();
    render(<AutomationDetailPage />);

    expect(await offeredActions(user)).toHaveLength(6);
    expect(screen.queryByTestId('action-unsupported-warning-0')).not.toBeInTheDocument();
  });
});
