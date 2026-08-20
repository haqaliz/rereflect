/**
 * Tests for the `send_customer_email` action editor on the "New Automation
 * Rule" page (automation-send-customer-email, frontend-editor Phase 2).
 *
 * The save payload must carry EXACTLY { template, recipient } — the backend
 * config model is `extra="forbid"`, so any stray key 422s the save.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/automations/new',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockCreate = vi.fn();
vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    create: (...args: any[]) => mockCreate(...args),
    list: vi.fn().mockResolvedValue({ rules: [], count: 0, limit: 5 }),
    get: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    toggle: vi.fn(),
    listExecutions: vi.fn().mockResolvedValue([]),
    listDeliveries: vi.fn().mockResolvedValue([]),
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
  PLAN_AUTOMATION_LIMITS: { free: 0, pro: 5, business: 20, enterprise: null },
}));

const mockListPlaybooks = vi.fn();
vi.mock('@/lib/api/playbooks', async () => {
  const actual = await vi.importActual<any>('@/lib/api/playbooks');
  return {
    ...actual,
    listPlaybooks: (...args: any[]) => mockListPlaybooks(...args),
  };
});

const mockListOutreachTemplates = vi.fn();
vi.mock('@/lib/api/outreach', async () => {
  const actual = await vi.importActual<any>('@/lib/api/outreach');
  return {
    ...actual,
    listOutreachTemplates: (...args: any[]) => mockListOutreachTemplates(...args),
  };
});

const mockToastError = vi.fn();
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: (...a: any[]) => mockToastError(...a) },
}));

import NewAutomationPage from '../new/page';

const ownerUser = {
  id: 1,
  email: 'owner@test.com',
  role: 'owner',
  plan: 'business',
  organization_id: 1,
  is_system_admin: false,
};

const registry = [
  { key: 're_engagement', label: 'Re-engagement check-in', description: 'x' },
  { key: 'weekly_digest_entry', label: 'Weekly digest entry', description: 'y' },
];

async function pickSendCustomerEmail(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /add action/i }));
  await user.click(screen.getByTestId('action-type-select-0'));
  await user.click(await screen.findByText('Send Customer Email'));
}

describe('NewAutomationPage — send_customer_email action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
    mockListOutreachTemplates.mockResolvedValue(registry);
  });

  it('seeds the first registry template and the customer recipient on switch-in', async () => {
    const user = userEvent.setup();
    render(<NewAutomationPage />);
    await waitFor(() => expect(mockListOutreachTemplates).toHaveBeenCalled());

    await pickSendCustomerEmail(user);

    expect(await screen.findByTestId('action-config-template-0')).toHaveTextContent(
      'Re-engagement check-in'
    );
    expect(screen.getByTestId('action-config-recipient-0')).toHaveTextContent('Customer');
  });

  it('submits exactly { template, recipient }', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 42, name: 'x' });
    render(<NewAutomationPage />);
    await waitFor(() => expect(mockListOutreachTemplates).toHaveBeenCalled());

    await user.type(screen.getByTestId('rule-name-input'), 'At-risk outreach');
    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Health Score Threshold'));

    await pickSendCustomerEmail(user);

    await user.click(screen.getByTestId('action-config-template-0'));
    await user.click(await screen.findByText('Weekly digest entry'));

    await user.click(screen.getByTestId('action-config-recipient-0'));
    await user.click(await screen.findByText('CS Assignee'));

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          actions: [
            {
              type: 'send_customer_email',
              config: { template: 'weekly_digest_entry', recipient: 'cs_assignee' },
            },
          ],
        })
      );
    });
  });

  it('falls back to the built-in registry when the fetch fails', async () => {
    const user = userEvent.setup();
    mockListOutreachTemplates.mockRejectedValue(new Error('boom'));
    render(<NewAutomationPage />);
    await waitFor(() => expect(mockToastError).toHaveBeenCalled());

    await pickSendCustomerEmail(user);

    expect(await screen.findByTestId('action-config-template-0')).toHaveTextContent(
      'Re-engagement check-in'
    );
  });
});
