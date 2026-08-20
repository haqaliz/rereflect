/**
 * Tests for the `batch_sentiment_threshold` trigger additions to the "New
 * Automation Rule" page: the trigger type option, the config fields
 * (sentiment / window_hours / mode / threshold / min_total) with THE
 * CONTRACT defaults, and the per-trigger `mode` default (shadow), asserted
 * against a non-batch-sentiment negative case.
 *
 * Mirrors the mock/import pattern used by new-usage-trend-trigger.test.tsx.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// ─── mocks ──────────────────────────────────────────────────────────────────

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
    batch_sentiment_threshold: 'Batch Sentiment Threshold',
  },
  ACTION_TYPE_LABELS: {
    auto_assign: 'Auto-Assign',
    change_status: 'Change Status',
    send_notification: 'Send Notification',
    draft_response: 'Draft AI Response',
    run_playbook: 'Run churn playbook',
    send_customer_email: 'Send Customer Email',
  },
  PLAN_AUTOMATION_LIMITS: {
    free: 0,
    pro: 5,
    business: 20,
    enterprise: null,
  },
}));

const mockListPlaybooks = vi.fn();
vi.mock('@/lib/api/playbooks', () => ({
  listPlaybooks: (...args: any[]) => mockListPlaybooks(...args),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── import after mocks ───────────────────────────────────────────────────

import NewAutomationPage from '../new/page';

// ─── fixtures ─────────────────────────────────────────────────────────────

const ownerUser = {
  id: 1,
  email: 'owner@test.com',
  role: 'owner',
  plan: 'business',
  organization_id: 1,
  is_system_admin: false,
};

describe('NewAutomationPage — batch_sentiment_threshold trigger type selection (AC1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('appears in the trigger type selector with its label', async () => {
    const user = userEvent.setup();
    render(<NewAutomationPage />);

    await user.click(screen.getByTestId('trigger-type-select'));
    expect(await screen.findByText('Batch Sentiment Threshold')).toBeInTheDocument();
  });
});

describe('NewAutomationPage — batch_sentiment_threshold config fields (AC2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('renders THE CONTRACT defaults and submits them unchanged', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 77, name: 'x' });

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Negative sentiment spike');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Batch Sentiment Threshold'));

    expect(await screen.findByTestId('trigger-config-sentiment')).toHaveTextContent('Negative');
    expect(screen.getByTestId('trigger-config-window-hours')).toHaveValue(24);
    expect(screen.getByTestId('trigger-config-mode')).toHaveTextContent(/percentage/i);
    expect(screen.getByTestId('trigger-config-batch-threshold')).toHaveValue(0.5);
    expect(screen.getByTestId('trigger-config-min-total')).toHaveValue(5);

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          trigger: {
            type: 'batch_sentiment_threshold',
            config: {
              sentiment: 'negative',
              window_hours: 24,
              mode: 'percentage',
              threshold: 0.5,
              min_total: 5,
            },
          },
        })
      );
    });
  });

  it('switching threshold type to count updates the config payload', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 78, name: 'x' });

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Count mode rule');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Batch Sentiment Threshold'));

    await user.click(await screen.findByTestId('trigger-config-mode'));
    await user.click(await screen.findByText('Absolute count'));

    const thresholdInput = screen.getByTestId('trigger-config-batch-threshold');
    await user.clear(thresholdInput);
    await user.type(thresholdInput, '3');

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          trigger: {
            type: 'batch_sentiment_threshold',
            config: {
              sentiment: 'negative',
              window_hours: 24,
              mode: 'count',
              threshold: 3,
              min_total: 5,
            },
          },
        })
      );
    });
  });
});

describe('NewAutomationPage — batch_sentiment_threshold defaults mode to shadow (AC3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('submits mode: "shadow" for a new batch_sentiment_threshold rule without touching the mode selector', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 79, name: 'x' });

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Shadow by default');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Batch Sentiment Threshold'));

    expect(screen.getByTestId('rule-mode-select')).toHaveTextContent(/shadow/i);

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(expect.objectContaining({ mode: 'shadow' }));
    });
  });
});

describe('NewAutomationPage — other trigger types still default to active (AC3 negative case)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue([]);
  });

  it('submits mode: "active" for a non-batch-sentiment rule — the shadow default must not leak', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 80, name: 'x' });

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Still active by default');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Health Score Threshold'));

    expect(screen.getByTestId('rule-mode-select')).toHaveTextContent(/active/i);

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(expect.objectContaining({ mode: 'active' }));
    });
  });
});
