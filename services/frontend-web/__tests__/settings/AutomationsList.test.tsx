import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/automations',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockList = vi.fn();
const mockToggle = vi.fn();
const mockListTemplates = vi.fn();
const mockEnableTemplate = vi.fn();
const mockDelete = vi.fn();

vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    list: (...args: any[]) => mockList(...args),
    toggle: (...args: any[]) => mockToggle(...args),
    listTemplates: (...args: any[]) => mockListTemplates(...args),
    enableTemplate: (...args: any[]) => mockEnableTemplate(...args),
    delete: (...args: any[]) => mockDelete(...args),
  },
  TRIGGER_TYPE_LABELS: {
    health_score_threshold: 'Health Score Threshold',
    sentiment_pattern: 'Sentiment Pattern',
    churn_risk_level_change: 'Churn Risk Level Change',
    feedback_category_match: 'Category Match',
  },
  ACTION_TYPE_LABELS: {
    auto_assign: 'Auto-Assign',
    change_status: 'Change Status',
    send_notification: 'Send Notification',
    draft_response: 'Draft AI Response',
  },
  PLAN_AUTOMATION_LIMITS: {
    free: 0,
    pro: 5,
    business: 20,
    enterprise: null,
  },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import AutomationsPage from '@/app/(dashboard)/settings/automations/page';

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const proUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const mockRules = [
  {
    id: 1,
    name: 'Churn Prevention',
    description: 'Assign CS when health score drops',
    is_active: true,
    trigger_type: 'health_score_threshold' as const,
    trigger_config: { threshold: 30 },
    actions: [
      { type: 'auto_assign', config: {} },
      { type: 'send_notification', config: {} },
    ],
    cooldown_hours: 24,
    execution_count: 12,
    last_executed_at: '2026-04-10T09:00:00Z',
    is_template: false,
    template_id: null,
    created_at: '2026-03-01T10:00:00Z',
  },
  {
    id: 2,
    name: 'Critical Bug Escalation',
    description: null,
    is_active: false,
    trigger_type: 'sentiment_pattern' as const,
    trigger_config: { count: 3, days: 7 },
    actions: [{ type: 'change_status', config: {} }],
    cooldown_hours: 48,
    execution_count: 5,
    last_executed_at: null,
    is_template: false,
    template_id: null,
    created_at: '2026-03-05T08:00:00Z',
  },
];

const mockTemplates = [
  {
    id: 'churn_prevention',
    name: 'Churn Prevention',
    description: 'Auto-assign CS when health score drops below 30',
    trigger_type: 'health_score_threshold',
    trigger_config: { threshold: 30 },
    actions: [{ type: 'auto_assign', config: {} }],
    cooldown_hours: 24,
  },
];

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('AutomationsList - empty state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockList.mockResolvedValue({ rules: [], count: 0, limit: 5 });
    mockListTemplates.mockResolvedValue([]);
  });

  it('test_renders_empty_state', async () => {
    render(<AutomationsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /add rule/i })).toBeInTheDocument();
  });
});

describe('AutomationsList - rule list', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockList.mockResolvedValue({ rules: mockRules, count: 2, limit: 5 });
    mockListTemplates.mockResolvedValue(mockTemplates);
  });

  it('test_renders_rule_list', async () => {
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Churn Prevention')).toBeInTheDocument();
    });

    expect(screen.getByText('Critical Bug Escalation')).toBeInTheDocument();

    // Trigger type badges
    expect(screen.getByText('Health Score Threshold')).toBeInTheDocument();
    expect(screen.getByText('Sentiment Pattern')).toBeInTheDocument();

    // Execution counts
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });
});

describe('AutomationsList - plan limit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockList.mockResolvedValue({ rules: mockRules, count: 2, limit: 5 });
    mockListTemplates.mockResolvedValue([]);
  });

  it('test_plan_limit_shows_indicator', async () => {
    render(<AutomationsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('plan-limit-indicator')).toBeInTheDocument();
    });
    expect(screen.getByTestId('plan-limit-indicator')).toHaveTextContent('2/5');
  });
});

describe('AutomationsList - add button at limit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Fill pro plan to its limit (5 rules)
    const fiveRules = Array.from({ length: 5 }, (_, i) => ({
      ...mockRules[0],
      id: i + 1,
      name: `Rule ${i + 1}`,
    }));
    mockUseAuth.mockReturnValue({ user: proUser });
    mockList.mockResolvedValue({ rules: fiveRules, count: 5, limit: 5 });
    mockListTemplates.mockResolvedValue([]);
  });

  it('test_add_button_disabled_at_limit', async () => {
    render(<AutomationsPage />);
    await waitFor(() => {
      const addBtn = screen.getByRole('button', { name: /add rule/i });
      expect(addBtn).toBeDisabled();
    });
  });
});

describe('AutomationsList - toggle rule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockList.mockResolvedValue({ rules: mockRules, count: 2, limit: 5 });
    mockListTemplates.mockResolvedValue([]);
    mockToggle.mockResolvedValue({ ...mockRules[0], is_active: false });
  });

  it('test_toggle_rule_active_state', async () => {
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Churn Prevention')).toBeInTheDocument();
    });

    // Find the toggle switch for the first (active) rule
    const switches = screen.getAllByRole('switch');
    expect(switches.length).toBeGreaterThanOrEqual(1);

    fireEvent.click(switches[0]);

    await waitFor(() => {
      expect(mockToggle).toHaveBeenCalledWith(1);
    });
  });
});
