import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

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
  },
  PLAN_AUTOMATION_LIMITS: {
    free: 0,
    pro: 5,
    business: 20,
    enterprise: null,
  },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import NewAutomationPage from '@/app/(dashboard)/settings/automations/new/page';

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const proUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('AutomationForm - trigger type select', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
  });

  it('test_renders_trigger_type_select', async () => {
    render(<NewAutomationPage />);

    // Name input should be present
    expect(screen.getByTestId('rule-name-input')).toBeInTheDocument();

    // Trigger type select should be rendered
    expect(screen.getByTestId('trigger-type-select')).toBeInTheDocument();
  });
});

describe('AutomationForm - dynamic config health_score', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
  });

  it('test_dynamic_config_for_health_score', async () => {
    render(<NewAutomationPage />);

    // Open trigger type dropdown and select health_score_threshold
    const triggerSelect = screen.getByTestId('trigger-type-select');
    fireEvent.click(triggerSelect);

    await waitFor(() => {
      expect(screen.getByText('Health Score Threshold')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Health Score Threshold'));

    await waitFor(() => {
      expect(screen.getByTestId('trigger-config-threshold')).toBeInTheDocument();
    });
  });
});

describe('AutomationForm - dynamic config sentiment_pattern', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
  });

  it('test_dynamic_config_for_sentiment_pattern', async () => {
    render(<NewAutomationPage />);

    // Open trigger type dropdown and select sentiment_pattern
    const triggerSelect = screen.getByTestId('trigger-type-select');
    fireEvent.click(triggerSelect);

    await waitFor(() => {
      expect(screen.getByText('Sentiment Pattern')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Sentiment Pattern'));

    await waitFor(() => {
      expect(screen.getByTestId('trigger-config-count')).toBeInTheDocument();
      expect(screen.getByTestId('trigger-config-days')).toBeInTheDocument();
    });
  });
});

describe('AutomationForm - add action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
  });

  it('test_add_action_button', async () => {
    render(<NewAutomationPage />);

    const addActionBtn = screen.getByRole('button', { name: /add action/i });
    expect(addActionBtn).toBeInTheDocument();

    fireEvent.click(addActionBtn);

    await waitFor(() => {
      // An action row should now be visible with a type selector
      expect(screen.getByTestId('action-type-select-0')).toBeInTheDocument();
    });
  });
});

describe('AutomationForm - submit creates rule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockCreate.mockResolvedValue({
      id: 99,
      name: 'New Rule',
      description: null,
      is_active: true,
      trigger_type: 'health_score_threshold',
      trigger_config: { threshold: 30 },
      actions: [],
      cooldown_hours: 24,
      execution_count: 0,
      last_executed_at: null,
      is_template: false,
      template_id: null,
      created_at: '2026-04-13T00:00:00Z',
    });
  });

  it('test_submit_creates_rule', async () => {
    render(<NewAutomationPage />);

    // Fill in rule name
    const nameInput = screen.getByTestId('rule-name-input');
    fireEvent.change(nameInput, { target: { value: 'New Rule' } });

    // Select a trigger type
    const triggerSelect = screen.getByTestId('trigger-type-select');
    fireEvent.click(triggerSelect);

    await waitFor(() => {
      expect(screen.getByText('Health Score Threshold')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Health Score Threshold'));

    await waitFor(() => {
      expect(screen.getByTestId('trigger-config-threshold')).toBeInTheDocument();
    });

    // Click save
    const saveBtn = screen.getByRole('button', { name: /save rule/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'New Rule',
          trigger_type: 'health_score_threshold',
        })
      );
    });

    // Should redirect to the new rule's detail page
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/settings/automations/99');
    });
  });
});
