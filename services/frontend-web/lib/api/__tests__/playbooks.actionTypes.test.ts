import { describe, it, expect } from 'vitest';
import {
  ACTION_TYPE_LABELS,
  type PlaybookAction,
  type NotifyActionConfig,
  type TagActionConfig,
  type TaskActionConfig,
  type TriggerAutomationConfig,
} from '@/lib/api/playbooks';
import type { AutomationRule } from '@/lib/api/automations';

describe('playbook action types — tag / notify / tasks / trigger-automation', () => {
  it('labels the 5 new action types', () => {
    expect(ACTION_TYPE_LABELS.notify).toBe('Notify');
    expect(ACTION_TYPE_LABELS.tag).toBe('Tag');
    expect(ACTION_TYPE_LABELS.create_task).toBe('Create task');
    expect(ACTION_TYPE_LABELS.schedule_task).toBe('Schedule task');
    expect(ACTION_TYPE_LABELS.trigger_automation).toBe('Trigger automation');
  });

  it('type-checks the worker-exact config shapes and labels every fixture action', () => {
    const notifyConfig: NotifyActionConfig = {
      channel: 'slack',
      target: '#ops',
      message: 'High-risk customer detected',
    };
    const teamsNotifyConfig: NotifyActionConfig = {
      channel: 'teams',
      message: 'High-risk customer detected',
    };
    const tagConfig: TagActionConfig = { tag: 'at-risk' };
    const createTaskConfig: TaskActionConfig = {
      description: 'Call the customer',
      due_in_days: 3,
      priority: 'medium',
    };
    const scheduleTaskConfig: TaskActionConfig = {
      description: 'Follow up in a week',
      due_in_days: 7,
    };
    const triggerConfig: TriggerAutomationConfig = {
      automation_name: 'At-Risk Customer Outreach',
    };

    const actions: PlaybookAction[] = [
      { type: 'notify', config: notifyConfig },
      { type: 'notify', config: teamsNotifyConfig },
      { type: 'tag', config: tagConfig },
      { type: 'create_task', config: createTaskConfig },
      { type: 'schedule_task', config: scheduleTaskConfig },
      { type: 'trigger_automation', config: triggerConfig },
    ];

    for (const action of actions) {
      expect(ACTION_TYPE_LABELS[action.type]).toBeDefined();
    }
  });

  it('automations rule type exposes name, mode and trigger_type for the picker', () => {
    const rule: AutomationRule = {
      id: 1,
      name: 'At-Risk Customer Outreach',
      description: null,
      is_active: false,
      mode: 'shadow',
      trigger_type: 'churn_probability_threshold',
      trigger_config: { probability_threshold: 0.7 },
      actions: [{ type: 'send_notification', config: {} }],
      cooldown_hours: 24,
      execution_count: 0,
      last_executed_at: null,
      is_template: false,
      template_id: null,
      created_at: '2026-01-01T00:00:00Z',
    };
    expect(rule.name).toBe('At-Risk Customer Outreach');
    expect(rule.mode).toBe('shadow');
    expect(rule.trigger_type).toBe('churn_probability_threshold');
  });
});