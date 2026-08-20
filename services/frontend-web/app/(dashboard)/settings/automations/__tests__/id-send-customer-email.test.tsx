/**
 * Tests for the `send_customer_email` action editor on the automation rule
 * detail/edit page (automation-send-customer-email, frontend-editor Phase 2).
 *
 * The contract this pins: switching an EXISTING action to send_customer_email
 * must replace the stale config, because the backend model is `extra="forbid"`
 * and a leftover `recipients`/`channels` key would 422 the save.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: '5' }),
  usePathname: () => '/settings/automations/5',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockGet = vi.fn();
const mockUpdate = vi.fn();
const mockListExecutions = vi.fn();
const mockListDeliveries = vi.fn();

vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    create: vi.fn(),
    list: vi.fn(),
    get: (...args: any[]) => mockGet(...args),
    update: (...args: any[]) => mockUpdate(...args),
    delete: vi.fn(),
    toggle: vi.fn(),
    listExecutions: (...args: any[]) => mockListExecutions(...args),
    listDeliveries: (...args: any[]) => mockListDeliveries(...args),
    listTemplates: vi.fn().mockResolvedValue([]),
    enableTemplate: vi.fn(),
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
vi.mock('@/lib/api/playbooks', async () => {
  const actual = await vi.importActual<any>('@/lib/api/playbooks');
  return { ...actual, listPlaybooks: (...args: any[]) => mockListPlaybooks(...args) };
});

const mockListOutreachTemplates = vi.fn();
vi.mock('@/lib/api/outreach', async () => {
  const actual = await vi.importActual<any>('@/lib/api/outreach');
  return {
    ...actual,
    listOutreachTemplates: (...args: any[]) => mockListOutreachTemplates(...args),
  };
});

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import AutomationDetailPage from '../[id]/page';

const ownerUser = {
  id: 1,
  email: 'owner@test.com',
  role: 'owner',
  plan: 'business',
  organization_id: 1,
  is_system_admin: false,
};
const memberUser = { ...ownerUser, id: 2, email: 'member@test.com', role: 'member' };

const registry = [
  { key: 're_engagement', label: 'Re-engagement check-in', description: 'x' },
  { key: 'weekly_digest_entry', label: 'Weekly digest entry', description: 'y' },
];

function ruleWith(actions: any[]) {
  return {
    id: 5,
    name: 'Email rule',
    description: null,
    is_active: true,
    mode: 'active' as const,
    trigger_type: 'health_score_threshold' as const,
    trigger_config: { threshold: 30, direction: 'below' },
    actions,
    cooldown_hours: 24,
    execution_count: 0,
    last_executed_at: null,
    is_template: false,
    template_id: null,
    created_at: '2026-05-01T00:00:00Z',
  };
}

describe('AutomationDetailPage — send_customer_email action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListExecutions.mockResolvedValue([]);
    mockListDeliveries.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue([]);
    mockListOutreachTemplates.mockResolvedValue(registry);
  });

  it('pre-populates both selects from the saved config and saves the same two keys', async () => {
    const user = userEvent.setup();
    mockGet.mockResolvedValue(
      ruleWith([
        {
          type: 'send_customer_email',
          config: { template: 'weekly_digest_entry', recipient: 'cs_assignee' },
        },
      ])
    );
    mockUpdate.mockResolvedValue(ruleWith([]));

    render(<AutomationDetailPage />);

    expect(await screen.findByTestId('action-config-template-0')).toHaveTextContent(
      'Weekly digest entry'
    );
    expect(screen.getByTestId('action-config-recipient-0')).toHaveTextContent('CS Assignee');

    await user.click(screen.getByTestId('action-config-recipient-0'));
    await user.click(await screen.findByText('Customer'));
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(
        5,
        expect.objectContaining({
          actions: [
            {
              type: 'send_customer_email',
              config: { template: 'weekly_digest_entry', recipient: 'customer' },
            },
          ],
        })
      );
    });
  });

  it('replaces a stale config when an existing action is switched in', async () => {
    const user = userEvent.setup();
    mockGet.mockResolvedValue(
      ruleWith([
        {
          type: 'send_notification',
          config: { recipients: 'admins', channels: ['dashboard'] },
        },
      ])
    );
    mockUpdate.mockResolvedValue(ruleWith([]));

    render(<AutomationDetailPage />);
    await waitFor(() => expect(mockListOutreachTemplates).toHaveBeenCalled());

    await user.click(await screen.findByTestId('action-type-select-0'));
    await user.click(await screen.findByText('Send Customer Email'));

    expect(await screen.findByTestId('action-config-template-0')).toHaveTextContent(
      'Re-engagement check-in'
    );

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(
        5,
        expect.objectContaining({
          actions: [
            {
              type: 'send_customer_email',
              config: { template: 're_engagement', recipient: 'customer' },
            },
          ],
        })
      );
    });
  });

  it('preserves a valid config across a switch away and back', async () => {
    const user = userEvent.setup();
    mockGet.mockResolvedValue(
      ruleWith([
        {
          type: 'send_customer_email',
          config: { template: 'weekly_digest_entry', recipient: 'cs_assignee' },
        },
      ])
    );

    render(<AutomationDetailPage />);
    await waitFor(() => expect(mockListOutreachTemplates).toHaveBeenCalled());

    await user.click(await screen.findByTestId('action-type-select-0'));
    await user.click(await screen.findByText('Change Status'));

    await user.click(screen.getByTestId('action-type-select-0'));
    await user.click(await screen.findByText('Send Customer Email'));

    expect(await screen.findByTestId('action-config-template-0')).toHaveTextContent(
      'Weekly digest entry'
    );
    expect(screen.getByTestId('action-config-recipient-0')).toHaveTextContent('CS Assignee');
  });

  it('disables the selects for members', async () => {
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockGet.mockResolvedValue(
      ruleWith([
        {
          type: 'send_customer_email',
          config: { template: 're_engagement', recipient: 'customer' },
        },
      ])
    );

    render(<AutomationDetailPage />);

    expect(await screen.findByTestId('action-config-template-0')).toBeDisabled();
    expect(screen.getByTestId('action-config-recipient-0')).toBeDisabled();
  });
});
