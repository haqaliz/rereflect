/**
 * R6 (automation-action-support): the New rule page only offers the actions
 * the selected trigger supports (served by GET /automations/action-support),
 * warns on an unsupported action instead of dropping it, blocks submit while
 * one exists, and falls back to every action type if the endpoint fails.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import matrix from '../../../../../../worker-service/tests/fixtures/automation_action_support.json';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/automations/new',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => mockUseAuth() }));

const mockCreate = vi.fn();
const mockGetActionSupport = vi.fn();
vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    create: (...args: any[]) => mockCreate(...args),
    getActionSupport: (...args: any[]) => mockGetActionSupport(...args),
    list: vi.fn().mockResolvedValue({ rules: [], count: 0, limit: 5 }),
    listTemplates: vi.fn().mockResolvedValue([]),
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

import NewAutomationPage from '../new/page';

const ownerUser = { id: 1, email: 'o@test.com', role: 'owner', plan: 'business', organization_id: 1, is_system_admin: false };

async function chooseTrigger(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(screen.getByTestId('trigger-type-select'));
  await user.click(await screen.findByRole('option', { name: label }));
}

async function offeredActions(user: ReturnType<typeof userEvent.setup>, index = 0) {
  await user.click(screen.getByTestId(`action-type-select-${index}`));
  const listbox = await screen.findByRole('listbox');
  const names = within(listbox).getAllByRole('option').map(o => o.textContent);
  await user.keyboard('{Escape}');
  return names;
}

describe('NewAutomationPage — action support (R6)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
    mockGetActionSupport.mockResolvedValue(matrix);
  });

  it('offers exactly the usage_trend-supported actions', async () => {
    const user = userEvent.setup();
    render(<NewAutomationPage />);
    await chooseTrigger(user, 'Usage Trend');
    await user.click(screen.getByRole('button', { name: /add action/i }));

    expect(await offeredActions(user)).toEqual([
      'Send Notification',
      'Run churn playbook',
      'Send Customer Email',
    ]);
    expect(mockGetActionSupport).toHaveBeenCalledTimes(1);
  });

  it('does not offer run_playbook for feedback_category_match', async () => {
    const user = userEvent.setup();
    render(<NewAutomationPage />);
    await chooseTrigger(user, 'Category Match');
    await user.click(screen.getByRole('button', { name: /add action/i }));

    const names = await offeredActions(user);
    expect(names).not.toContain('Run churn playbook');
    expect(names).toContain('Auto-Assign');
  });

  it('warns on, and blocks submitting, an action the new trigger does not support', async () => {
    const user = userEvent.setup();
    render(<NewAutomationPage />);
    await user.type(screen.getByTestId('rule-name-input'), 'Switcheroo');
    await chooseTrigger(user, 'Category Match');
    await user.click(screen.getByRole('button', { name: /add action/i }));
    await user.click(screen.getByTestId('action-type-select-0'));
    await user.click(await screen.findByRole('option', { name: 'Auto-Assign' }));

    await chooseTrigger(user, 'Usage Trend');

    const warning = await screen.findByTestId('action-unsupported-warning-0');
    expect(warning).toHaveTextContent(/Auto-Assign isn.t supported for this trigger/);
    expect(screen.getByTestId('action-type-select-0')).toHaveTextContent('Auto-Assign');

    await user.click(screen.getByRole('button', { name: /save rule/i }));
    expect(mockToastError).toHaveBeenCalledWith(expect.stringMatching(/not supported|isn.t supported/i));
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('offers all six action types when the endpoint fails', async () => {
    mockGetActionSupport.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<NewAutomationPage />);
    await chooseTrigger(user, 'Usage Trend');
    await user.click(screen.getByRole('button', { name: /add action/i }));
    await waitFor(() => expect(mockGetActionSupport).toHaveBeenCalled());

    expect(await offeredActions(user)).toHaveLength(6);
  });
});
