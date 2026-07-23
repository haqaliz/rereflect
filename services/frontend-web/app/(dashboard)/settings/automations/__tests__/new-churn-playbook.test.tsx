/**
 * Tests for the churn-triggered-playbooks additions to the "New Automation
 * Rule" page: the `churn_probability_threshold` trigger config, the
 * `run_playbook` action config (playbook picker sourced from
 * `listPlaybooks()`), and the off|shadow|active rule `mode` selector.
 *
 * Mirrors the mock/import pattern used by
 * app/(dashboard)/settings/sso/__tests__/page.test.tsx and
 * __tests__/settings/AutomationForm.test.tsx.
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

const playbookFixtures = [
  { id: 1, organization_id: null, name: 'Template Playbook', description: null, probability_min: 0.5, probability_max: 1, action_sequence: [], is_template: true, is_active: true, source_template_id: null, created_at: '', updated_at: '' },
  { id: 2, organization_id: 1, name: 'Inactive Playbook', description: null, probability_min: 0.5, probability_max: 1, action_sequence: [], is_template: false, is_active: false, source_template_id: null, created_at: '', updated_at: '' },
  { id: 3, organization_id: 1, name: 'Win-back offer', description: null, probability_min: 0.5, probability_max: 1, action_sequence: [], is_template: false, is_active: true, source_template_id: null, created_at: '', updated_at: '' },
];

describe('NewAutomationPage — churn_probability_threshold trigger', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue(playbookFixtures);
  });

  it('renders the threshold input when the trigger is selected, and includes the entered value + direction:above on save', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 42, name: 'x' });

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Win-back at risk');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Churn probability threshold'));

    const thresholdInput = await screen.findByTestId('trigger-config-churn-threshold');
    expect(thresholdInput).toBeInTheDocument();

    await user.clear(thresholdInput);
    await user.type(thresholdInput, '0.85');

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          trigger: {
            type: 'churn_probability_threshold',
            config: expect.objectContaining({ threshold: 0.85, direction: 'above' }),
          },
        })
      );
    });
  });
});

describe('NewAutomationPage — run_playbook action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue(playbookFixtures);
  });

  it('renders a playbook picker filtered to active, non-template playbooks and sends the chosen playbook_id on save', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 42, name: 'x' });

    render(<NewAutomationPage />);

    await user.type(screen.getByTestId('rule-name-input'), 'Run playbook rule');

    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Health Score Threshold'));

    await waitFor(() => expect(mockListPlaybooks).toHaveBeenCalled());

    await user.click(screen.getByRole('button', { name: /add action/i }));
    await user.click(screen.getByTestId('action-type-select-0'));
    await user.click(await screen.findByText('Run churn playbook'));

    const playbookSelect = await screen.findByTestId('action-config-playbook');
    await user.click(playbookSelect);

    expect(await screen.findByText('Win-back offer')).toBeInTheDocument();
    expect(screen.queryByText('Template Playbook')).not.toBeInTheDocument();
    expect(screen.queryByText('Inactive Playbook')).not.toBeInTheDocument();

    await user.click(screen.getByText('Win-back offer'));

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          actions: [
            expect.objectContaining({
              type: 'run_playbook',
              config: expect.objectContaining({ playbook_id: 3 }),
            }),
          ],
        })
      );
    });
  });

  it('shows an empty-state message when there are no active, non-template playbooks', async () => {
    const user = userEvent.setup();
    mockListPlaybooks.mockResolvedValue([playbookFixtures[0], playbookFixtures[1]]); // template + inactive only

    render(<NewAutomationPage />);

    await waitFor(() => expect(mockListPlaybooks).toHaveBeenCalled());

    await user.click(screen.getByRole('button', { name: /add action/i }));
    await user.click(screen.getByTestId('action-type-select-0'));
    await user.click(await screen.findByText('Run churn playbook'));

    expect(await screen.findByText(/no active playbooks.*create one first/i)).toBeInTheDocument();
    expect(screen.queryByTestId('action-config-playbook')).not.toBeInTheDocument();
  });
});

describe('NewAutomationPage — rule mode selector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockListPlaybooks.mockResolvedValue(playbookFixtures);
  });

  it('defaults to active and sends the selected mode on save', async () => {
    const user = userEvent.setup();
    mockCreate.mockResolvedValue({ id: 42, name: 'x' });

    render(<NewAutomationPage />);

    const modeSelect = screen.getByTestId('rule-mode-select');
    expect(modeSelect).toHaveTextContent(/active/i);

    await user.type(screen.getByTestId('rule-name-input'), 'Shadow test rule');
    await user.click(screen.getByTestId('trigger-type-select'));
    await user.click(await screen.findByText('Health Score Threshold'));

    await user.click(modeSelect);
    await user.click(await screen.findByText('Shadow'));

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({ mode: 'shadow' })
      );
    });
  });
});
