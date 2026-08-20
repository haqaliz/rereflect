/**
 * Tests for the Email Deliveries surface on the automation rule detail page
 * (automation-send-customer-email, frontend-editor Phase 4).
 *
 * A `skipped` row is the honest record of a send that did not happen — the
 * reason must always be visible next to it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: '5' }),
  usePathname: () => '/settings/automations/5',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => mockUseAuth() }));

const mockGet = vi.fn();
const mockListExecutions = vi.fn();
const mockListDeliveries = vi.fn();

vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    create: vi.fn(),
    list: vi.fn(),
    get: (...args: any[]) => mockGet(...args),
    update: vi.fn(),
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
  id: 1, email: 'owner@test.com', role: 'owner', plan: 'business',
  organization_id: 1, is_system_admin: false,
};
const memberUser = { ...ownerUser, id: 2, email: 'member@test.com', role: 'member' };

const emailRule = {
  id: 5,
  name: 'Email rule',
  description: null,
  is_active: true,
  mode: 'active' as const,
  trigger_type: 'health_score_threshold' as const,
  trigger_config: { threshold: 30, direction: 'below' },
  actions: [
    { type: 'send_customer_email', config: { template: 're_engagement', recipient: 'customer' } },
  ],
  cooldown_hours: 24,
  execution_count: 3,
  last_executed_at: null,
  is_template: false,
  template_id: null,
  created_at: '2026-05-01T00:00:00Z',
};

function delivery(over: Record<string, any>) {
  return {
    id: 1,
    rule_id: 5,
    customer_email: 'a@b.com',
    to_email: 'a@b.com',
    template_key: 're_engagement',
    subject: 'We would love to hear from you',
    status: 'queued',
    reason: null,
    created_at: '2026-08-01T00:00:00Z',
    ...over,
  };
}

async function openDeliveriesTab(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('tab', { name: /email deliveries/i }));
}

describe('AutomationDetailPage — email deliveries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockGet.mockResolvedValue(emailRule);
    mockListExecutions.mockResolvedValue([]);
    mockListPlaybooks.mockResolvedValue([]);
    mockListOutreachTemplates.mockResolvedValue([
      { key: 're_engagement', label: 'Re-engagement check-in', description: 'x' },
    ]);
  });

  it('renders every status badge and the skip reason', async () => {
    const user = userEvent.setup();
    mockListDeliveries.mockResolvedValue([
      delivery({ id: 1, status: 'queued' }),
      delivery({ id: 2, status: 'sent' }),
      delivery({ id: 3, status: 'skipped', reason: 'opted out' }),
      delivery({ id: 4, status: 'failed', reason: 'email not configured' }),
    ]);

    render(<AutomationDetailPage />);
    await waitFor(() => expect(mockListDeliveries).toHaveBeenCalledWith(5));

    await openDeliveriesTab(user);

    const table = within(await screen.findByRole('table'));
    expect(table.getByText('queued')).toBeInTheDocument();
    expect(table.getByText('sent')).toBeInTheDocument();
    expect(table.getByText('skipped')).toBeInTheDocument();
    expect(table.getByText('failed')).toBeInTheDocument();
    expect(table.getByText('opted out')).toBeInTheDocument();
    expect(table.getByText('email not configured')).toBeInTheDocument();
    expect(table.getAllByText('re_engagement').length).toBe(4);
  });

  it('shows an empty state when there are no deliveries', async () => {
    const user = userEvent.setup();
    mockListDeliveries.mockResolvedValue([]);

    render(<AutomationDetailPage />);
    await waitFor(() => expect(mockListDeliveries).toHaveBeenCalled());

    await openDeliveriesTab(user);

    expect(await screen.findByText(/no email deliveries yet/i)).toBeInTheDocument();
  });

  it('hides the tab from members and never calls the endpoint for them', async () => {
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockListDeliveries.mockResolvedValue([]);

    render(<AutomationDetailPage />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    expect(screen.queryByRole('tab', { name: /email deliveries/i })).not.toBeInTheDocument();
    expect(mockListDeliveries).not.toHaveBeenCalled();
  });
});
