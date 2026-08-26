import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

const REGISTRY = [
  { key: 're_engagement', label: 'Re-engagement check-in', description: 'nudge' },
  { key: 'weekly_digest_entry', label: 'Weekly digest entry', description: 'digest' },
];

const RULES = [
  {
    id: 1,
    name: 'At-Risk Customer Outreach',
    description: null,
    is_active: false,
    mode: 'shadow',
    trigger_type: 'churn_probability_threshold',
    trigger_config: {},
    actions: [],
    cooldown_hours: 24,
    execution_count: 0,
    last_executed_at: null,
    is_template: true,
    template_id: 'at_risk_outreach',
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'Weekly Nudge',
    description: null,
    is_active: true,
    mode: 'active',
    trigger_type: 'churn_probability_threshold',
    trigger_config: {},
    actions: [],
    cooldown_hours: 24,
    execution_count: 3,
    last_executed_at: '2026-02-01T00:00:00Z',
    is_template: false,
    template_id: null,
    created_at: '2026-01-01T00:00:00Z',
  },
];

const mockListOutreachTemplates = vi.fn();
const mockListAutomations = vi.fn();

vi.mock('@/lib/api/outreach', () => ({
  listOutreachTemplates: (...args: unknown[]) => mockListOutreachTemplates(...args),
  BUILTIN_OUTREACH_TEMPLATES: [
    { key: 're_engagement', label: 'Re-engagement check-in', description: 'nudge' },
    { key: 'weekly_digest_entry', label: 'Weekly digest entry', description: 'digest' },
  ],
}));

vi.mock('@/lib/api/playbooks', () => ({
  ACTION_TYPE_LABELS: {
    assign: 'Assign',
    change_status: 'Change Status',
    send_notification: 'Send Notification',
    draft_response: 'Draft AI Response',
    send_email: 'Send Email',
    notify: 'Notify',
    tag: 'Tag',
    create_task: 'Create task',
    schedule_task: 'Schedule task',
    trigger_automation: 'Trigger automation',
  },
  SEND_EMAIL_RECIPIENTS: ['customer', 'cs_assignee'],
  SEND_EMAIL_RECIPIENT_LABELS: { customer: 'Customer', cs_assignee: 'CS Assignee' },
}));

vi.mock('@/lib/api/automations', () => ({
  automationsAPI: {
    list: (...args: unknown[]) => mockListAutomations(...args),
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
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { PlaybookEditor } from '@/components/playbooks/PlaybookEditor';
import type { Playbook } from '@/lib/api/playbooks';

const basePlaybook: Playbook = {
  id: 6,
  organization_id: 1,
  name: 'Outreach',
  description: null,
  probability_min: 0.5,
  probability_max: 0.7,
  action_sequence: [],
  is_template: false,
  is_active: true,
  source_template_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const allTypesPlaybook: Playbook = {
  ...basePlaybook,
  name: 'All types',
  action_sequence: [
    { type: 'notify', config: { channel: 'slack', target: '#ops', message: 'Hi team' } },
    { type: 'tag', config: { tag: 'at-risk' } },
    {
      type: 'create_task',
      config: { description: 'Call customer', due_in_days: 3, priority: 'medium' },
    },
    { type: 'schedule_task', config: { description: 'Follow up' } },
    { type: 'trigger_automation', config: { automation_name: 'At-Risk Customer Outreach' } },
  ],
};

async function switchActionType(cardIndex: number, optionLabel: string) {
  const user = userEvent.setup();
  const cards = screen.getAllByRole('combobox', { name: /action type/i });
  await user.click(cards[cardIndex]);
  await user.click(await screen.findByRole('option', { name: optionLabel }));
}

describe('PlaybookEditor — 5 new action types', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListOutreachTemplates.mockResolvedValue(REGISTRY);
    mockListAutomations.mockResolvedValue({ rules: RULES, count: RULES.length, limit: null });
  });

  it('renders the notify config form hydrated from config (channel, message, target, advisory helper)', async () => {
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [
        { type: 'notify', config: { channel: 'slack', target: '#ops', message: 'Hi team' } },
      ],
    };
    render(<PlaybookEditor playbook={playbook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /notify channel/i })).toHaveTextContent('Slack');
    });
    expect(screen.getByRole('textbox', { name: /notify message/i })).toHaveValue('Hi team');
    expect(screen.getByRole('textbox', { name: /notify target/i })).toHaveValue('#ops');
    expect(screen.getByText(/advisory/i)).toBeInTheDocument();
  });

  it('renders the tag config form hydrated from config', async () => {
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'tag', config: { tag: 'at-risk' } }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /^tag$/i })).toHaveValue('at-risk');
    });
  });

  it('renders create_task fields (description, due in days, priority) hydrated from config', async () => {
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [
        { type: 'create_task', config: { description: 'Call', due_in_days: 3, priority: 'high' } },
      ],
    };
    render(<PlaybookEditor playbook={playbook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /task description/i })).toHaveValue('Call');
    });
    expect(screen.getByRole('spinbutton', { name: /due in days/i })).toHaveValue(3);
    expect(screen.getByRole('combobox', { name: /task priority/i })).toHaveTextContent('High');
  });

  it('renders schedule_task with description + due in days but NO priority select', async () => {
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'schedule_task', config: { description: 'Follow up' } }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /task description/i })).toHaveValue('Follow up');
    });
    expect(screen.getByRole('spinbutton', { name: /due in days/i })).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: /task priority/i })).not.toBeInTheDocument();
  });

  it('seeds defaults on type switch: notify → channel slack; create_task → priority medium, due empty', async () => {
    const user = userEvent.setup();
    render(<PlaybookEditor onSave={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Defaults' } });
    fireEvent.click(screen.getByRole('button', { name: /add action/i }));

    await switchActionType(0, 'Notify');
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /notify channel/i })).toHaveTextContent('Slack');
    });
    expect(screen.getByRole('textbox', { name: /notify message/i })).toHaveValue('');

    await switchActionType(0, 'Create task');
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /task priority/i })).toHaveTextContent('Medium');
    });
    expect(screen.getByRole('spinbutton', { name: /due in days/i })).toHaveValue(null);
    expect(user).toBeDefined();
  });

  it('hydrates load-time defaults for a notify action with no config', async () => {
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'notify' }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /notify channel/i })).toHaveTextContent('Slack');
    });
  });

  it('create → save round-trips the exact config keys for all 5 new types', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<PlaybookEditor onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'My Playbook' } });

    fireEvent.click(screen.getByRole('button', { name: /add action/i }));
    await switchActionType(0, 'Notify');
    await user.type(screen.getByRole('textbox', { name: /notify message/i }), 'Hello');
    await user.type(screen.getByRole('textbox', { name: /notify target/i }), '#sales');

    fireEvent.click(screen.getByRole('button', { name: /add action/i }));
    await switchActionType(1, 'Tag');
    await user.type(screen.getByRole('textbox', { name: /^tag$/i }), 'at-risk');

    fireEvent.click(screen.getByRole('button', { name: /add action/i }));
    await switchActionType(2, 'Create task');
    await user.type(within(screen.getByTestId('action-card-2')).getByRole('textbox', { name: /task description/i }), 'Call');
    await user.type(within(screen.getByTestId('action-card-2')).getByRole('spinbutton', { name: /due in days/i }), '3');

    fireEvent.click(screen.getByRole('button', { name: /add action/i }));
    await switchActionType(3, 'Schedule task');
    await user.type(within(screen.getByTestId('action-card-3')).getByRole('textbox', { name: /task description/i }), 'Follow up');

    fireEvent.click(screen.getByRole('button', { name: /add action/i }));
    await switchActionType(4, 'Trigger automation');
    await user.click(screen.getByRole('combobox', { name: /automation/i }));
    await user.click(await screen.findByRole('option', { name: /At-Risk Customer Outreach/ }));

    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          action_sequence: [
            { type: 'notify', config: { channel: 'slack', message: 'Hello', target: '#sales' } },
            { type: 'tag', config: { tag: 'at-risk' } },
            {
              type: 'create_task',
              config: { description: 'Call', due_in_days: 3, priority: 'medium' },
            },
            { type: 'schedule_task', config: { description: 'Follow up' } },
            { type: 'trigger_automation', config: { automation_name: 'At-Risk Customer Outreach' } },
          ],
        })
      );
    });
  });

  it('edit → save round-trips the exact config keys untouched (AC3)', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<PlaybookEditor playbook={allTypesPlaybook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /notify channel/i })).toHaveTextContent('Slack');
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          action_sequence: [
            { type: 'notify', config: { channel: 'slack', target: '#ops', message: 'Hi team' } },
            { type: 'tag', config: { tag: 'at-risk' } },
            {
              type: 'create_task',
              config: { description: 'Call customer', due_in_days: 3, priority: 'medium' },
            },
            { type: 'schedule_task', config: { description: 'Follow up' } },
            {
              type: 'trigger_automation',
              config: { automation_name: 'At-Risk Customer Outreach' },
            },
          ],
        })
      );
    });
  });

  it('automation picker lists rules with name + mode + trigger type in the option label', async () => {
    const user = userEvent.setup();
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'trigger_automation', config: { automation_name: '' } }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /automation/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('combobox', { name: /automation/i }));

    const shadowOption = await screen.findByRole('option', {
      name: /At-Risk Customer Outreach \(shadow · Churn probability threshold\)/,
    });
    const activeOption = screen.getByRole('option', {
      name: /Weekly Nudge \(active · Churn probability threshold\)/,
    });
    expect(shadowOption).toBeInTheDocument();
    expect(activeOption).toBeInTheDocument();
  });

  it('automation picker is disabled with "No automations" when the org has none', async () => {
    mockListAutomations.mockResolvedValue({ rules: [], count: 0, limit: null });
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'trigger_automation', config: { automation_name: '' } }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /automation/i })).toBeDisabled();
    });
    expect(screen.getByRole('combobox', { name: /automation/i })).toHaveTextContent(
      'No automations'
    );
  });

  it('blocks save when tag is empty', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'tag', config: { tag: '' } }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /^tag$/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(screen.getByText(/tag is required/i)).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it('blocks save when create_task description is empty', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'create_task', config: { description: '', priority: 'medium' } }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /task description/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(screen.getByText(/description is required/i)).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it('blocks save when schedule_task description is empty', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'schedule_task', config: { description: '' } }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /task description/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(screen.getByText(/description is required/i)).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it('blocks save when notify message is empty', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'notify', config: { channel: 'slack', message: '' } }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /notify message/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(screen.getByText(/message is required/i)).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it('blocks save when no automation is selected', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [{ type: 'trigger_automation', config: { automation_name: '' } }],
    };
    render(<PlaybookEditor playbook={playbook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /automation/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(screen.getByText(/automation is required/i)).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it('readOnly renders text summaries, never selects', async () => {
    render(
      <PlaybookEditor playbook={allTypesPlaybook} readOnly onSave={vi.fn()} onCancel={vi.fn()} />
    );

    await waitFor(() => {
      expect(screen.getByText(/notify via slack/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/tag: at-risk/i)).toBeInTheDocument();
    expect(screen.getByText(/create task: call customer/i)).toBeInTheDocument();
    expect(screen.getByText(/schedule task: follow up/i)).toBeInTheDocument();
    expect(screen.getByText(/trigger automation: at-risk customer outreach/i)).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('editing a notify field preserves sibling config keys exactly', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    const playbook: Playbook = {
      ...basePlaybook,
      action_sequence: [
        { type: 'notify', config: { channel: 'discord', target: '#ops', message: 'Hi' } },
      ],
    };
    render(<PlaybookEditor playbook={playbook} onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /notify channel/i })).toHaveTextContent(
        'Discord'
      );
    });
    await user.clear(screen.getByRole('textbox', { name: /notify message/i }));
    await user.type(screen.getByRole('textbox', { name: /notify message/i }), 'Hello team');

    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          action_sequence: [
            {
              type: 'notify',
              config: { channel: 'discord', target: '#ops', message: 'Hello team' },
            },
          ],
        })
      );
    });
  });
});