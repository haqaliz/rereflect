'use client';

import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Plus, Trash2 } from 'lucide-react';
import { TeamsIcon } from '@/components/icons/TeamsIcon';
import {
  type Playbook,
  type PlaybookAction,
  ACTION_TYPE_LABELS,
  SEND_EMAIL_RECIPIENTS,
  SEND_EMAIL_RECIPIENT_LABELS,
} from '@/lib/api/playbooks';
import {
  listOutreachTemplates,
  BUILTIN_OUTREACH_TEMPLATES,
  type OutreachTemplateSummary,
} from '@/lib/api/outreach';
import {
  automationsAPI,
  TRIGGER_TYPE_LABELS,
  type AutomationRule,
} from '@/lib/api/automations';

// ─── Constants ────────────────────────────────────────────────────────────────

const NOTIFY_CHANNELS = ['slack', 'discord', 'teams', 'dashboard'] as const;

const NOTIFY_CHANNEL_LABELS: Record<string, string> = {
  slack: 'Slack',
  discord: 'Discord',
  teams: 'Teams',
  dashboard: 'Dashboard',
};

const TASK_PRIORITIES = ['low', 'medium', 'high'] as const;

/**
 * Types whose config is reset to the type defaults on switch. send_email is
 * deliberately excluded — switching away and back preserves its config
 * (pinned behavior). The worker reads type-specific keys, so a stale config
 * from another type must never leak into the save payload.
 */
const RESET_ON_SWITCH_TYPES = new Set([
  'notify',
  'tag',
  'create_task',
  'schedule_task',
  'trigger_automation',
]);

function toStr(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function isNonEmpty(v: unknown): boolean {
  return typeof v === 'string' && v.trim().length > 0;
}

function defaultConfigFor(type: string): Record<string, unknown> | undefined {
  switch (type) {
    case 'send_email':
      return { template: BUILTIN_OUTREACH_TEMPLATES[0].key, recipient: 'customer' };
    case 'notify':
      return { channel: 'slack', message: '' };
    case 'tag':
      return { tag: '' };
    case 'create_task':
      return { description: '', priority: 'medium' };
    case 'schedule_task':
      return { description: '' };
    case 'trigger_automation':
      return { automation_name: '' };
    default:
      return undefined;
  }
}

// ─── ActionCard ───────────────────────────────────────────────────────────────

interface ActionCardProps {
  action: PlaybookAction;
  index: number;
  readOnly: boolean;
  templateOptions: OutreachTemplateSummary[];
  automations: AutomationRule[];
  automationsLoading: boolean;
  error?: string;
  onChange: (index: number, action: PlaybookAction) => void;
  onRemove: (index: number) => void;
}

function ActionCard({
  action,
  index,
  readOnly,
  templateOptions,
  automations,
  automationsLoading,
  error,
  onChange,
  onRemove,
}: ActionCardProps) {
  const actionTypes = Object.keys(ACTION_TYPE_LABELS);
  const isSendEmail = action.type === 'send_email';
  const config = (action.config ?? {}) as Record<string, unknown>;
  const templateKey = isSendEmail && typeof config.template === 'string' ? config.template : '';
  const recipient = isSendEmail && typeof config.recipient === 'string' ? config.recipient : '';
  const templateKnown = templateOptions.some((t) => t.key === templateKey);
  const templateLabel =
    templateOptions.find((t) => t.key === templateKey)?.label ?? templateKey;
  const recipientLabel = SEND_EMAIL_RECIPIENT_LABELS[recipient] ?? recipient;

  const channel = toStr(config.channel);
  const message = toStr(config.message);
  const target = toStr(config.target);
  const tag = toStr(config.tag);
  const description = toStr(config.description);
  const dueInDays =
    config.due_in_days === undefined || config.due_in_days === null
      ? ''
      : String(config.due_in_days);
  const priority = toStr(config.priority);
  const automationName = toStr(config.automation_name);

  const handleTypeChange = (val: string) => {
    if (val === 'send_email' && !action.config) {
      const defaultTemplate =
        templateOptions[0]?.key ?? BUILTIN_OUTREACH_TEMPLATES[0].key;
      onChange(index, {
        ...action,
        type: val,
        config: { template: defaultTemplate, recipient: 'customer' },
      });
    } else if (RESET_ON_SWITCH_TYPES.has(val)) {
      onChange(index, { ...action, type: val, config: defaultConfigFor(val) });
    } else {
      onChange(index, { ...action, type: val });
    }
  };

  const setConfigField = (key: string, value: unknown) => {
    onChange(index, { ...action, config: { ...config, [key]: value } });
  };

  const setDueInDays = (value: string) => {
    const nextConfig: Record<string, unknown> = { ...config };
    if (value === '') {
      delete nextConfig.due_in_days;
    } else {
      nextConfig.due_in_days = Number(value);
    }
    onChange(index, { ...action, config: nextConfig });
  };

  return (
    <div
      data-testid={`action-card-${index}`}
      className="p-3 rounded-lg border border-border bg-muted/30 space-y-2"
    >
      <div className="flex items-center gap-3">
        <span className="text-xs text-muted-foreground w-5 text-center shrink-0">
          {index + 1}
        </span>

        {readOnly ? (
          <span className="flex-1 text-sm">{ACTION_TYPE_LABELS[action.type] ?? action.type}</span>
        ) : (
          <Select value={action.type} onValueChange={handleTypeChange} disabled={readOnly}>
            <SelectTrigger aria-label="Action type" className="flex-1 h-8 text-xs">
              <SelectValue placeholder="Select action type" />
            </SelectTrigger>
            <SelectContent>
              {actionTypes.map((t) => (
                <SelectItem key={t} value={t} className="text-xs">
                  {ACTION_TYPE_LABELS[t]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {!readOnly && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
            onClick={() => onRemove(index)}
            aria-label="Remove action"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
      </div>

      {isSendEmail &&
        (readOnly ? (
          <p className="pl-8 text-xs text-muted-foreground">
            Email template: {templateLabel} → {recipientLabel}
            {!templateKnown && templateKey && ` (unknown template key "${templateKey}")`}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 pl-8">
              <div className="flex items-center gap-2 flex-1 min-w-[220px]">
                <span className="text-xs text-muted-foreground shrink-0">Template</span>
                <Select
                  value={templateKey}
                  onValueChange={(val) => setConfigField('template', val)}
                >
                  <SelectTrigger aria-label="Email template" className="flex-1 h-8 text-xs">
                    <SelectValue placeholder="Select template" />
                  </SelectTrigger>
                  <SelectContent>
                    {templateOptions.map((t) => (
                      <SelectItem key={t.key} value={t.key} className="text-xs">
                        {t.label}
                      </SelectItem>
                    ))}
                    {!templateKnown && templateKey && (
                      <SelectItem value={templateKey} className="text-xs" disabled>
                        {templateKey} (unknown)
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2 flex-1 min-w-[180px]">
                <span className="text-xs text-muted-foreground shrink-0">Recipient</span>
                <Select
                  value={SEND_EMAIL_RECIPIENTS.includes(recipient as (typeof SEND_EMAIL_RECIPIENTS)[number]) ? recipient : ''}
                  onValueChange={(val) => setConfigField('recipient', val)}
                >
                  <SelectTrigger aria-label="Email recipient" className="flex-1 h-8 text-xs">
                    <SelectValue placeholder="Select recipient" />
                  </SelectTrigger>
                  <SelectContent>
                    {SEND_EMAIL_RECIPIENTS.map((r) => (
                      <SelectItem key={r} value={r} className="text-xs">
                        {SEND_EMAIL_RECIPIENT_LABELS[r]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {!templateKnown && templateKey && (
              <p className="pl-8 text-xs text-[var(--chart-2)]" role="alert">
                Template &quot;{templateKey}&quot; is not in the outreach template registry —
                the raw key will be saved.
              </p>
            )}
          </>
        ))}

      {action.type === 'notify' &&
        (readOnly ? (
          <p className="pl-8 text-xs text-muted-foreground">
            Notify via {NOTIFY_CHANNEL_LABELS[channel] ?? channel} → {message}
            {target && ` (target: ${target})`}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 pl-8">
              <div className="flex items-center gap-2 min-w-[180px]">
                <span className="text-xs text-muted-foreground shrink-0">Channel</span>
                <Select
                  value={NOTIFY_CHANNELS.includes(channel as (typeof NOTIFY_CHANNELS)[number]) ? channel : ''}
                  onValueChange={(val) => setConfigField('channel', val)}
                >
                  <SelectTrigger aria-label="Notify channel" className="flex-1 h-8 text-xs">
                    <SelectValue placeholder="Select channel" />
                  </SelectTrigger>
                  <SelectContent>
                    {NOTIFY_CHANNELS.map((c) => (
                      <SelectItem key={c} value={c} className="text-xs">
                        {c === 'teams' ? (
                          <span className="inline-flex items-center gap-1.5">
                            <TeamsIcon className="w-3.5 h-3.5" />
                            {NOTIFY_CHANNEL_LABELS[c]}
                          </span>
                        ) : (
                          NOTIFY_CHANNEL_LABELS[c]
                        )}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2 flex-1 min-w-[240px]">
                <span className="text-xs text-muted-foreground shrink-0">Message</span>
                <Input
                  aria-label="Notify message"
                  value={message}
                  onChange={(e) => setConfigField('message', e.target.value)}
                  placeholder="Message to send"
                />
              </div>

              <div className="flex items-center gap-2 flex-1 min-w-[200px]">
                <span className="text-xs text-muted-foreground shrink-0">Target</span>
                <Input
                  aria-label="Notify target"
                  value={target}
                  onChange={(e) => setConfigField('target', e.target.value)}
                  placeholder="e.g. #sales (optional)"
                />
              </div>
            </div>
            <p className="pl-8 text-xs text-muted-foreground">
              Target is advisory — the integration&apos;s configured channel is used.
            </p>
          </>
        ))}

      {action.type === 'tag' &&
        (readOnly ? (
          <p className="pl-8 text-xs text-muted-foreground">Tag: {tag}</p>
        ) : (
          <div className="flex items-center gap-2 pl-8">
            <span className="text-xs text-muted-foreground shrink-0">Tag</span>
            <Input
              aria-label="Tag"
              value={tag}
              onChange={(e) => setConfigField('tag', e.target.value)}
              placeholder="e.g. at-risk"
              className="max-w-[280px]"
            />
          </div>
        ))}

      {(action.type === 'create_task' || action.type === 'schedule_task') &&
        (readOnly ? (
          <p className="pl-8 text-xs text-muted-foreground">
            {action.type === 'create_task' ? 'Create task' : 'Schedule task'}: {description}
            {dueInDays !== '' && ` (due in ${dueInDays} days`}
            {action.type === 'create_task' && priority && `, ${priority}`}
            {dueInDays !== '' && ')'}
          </p>
        ) : (
          <div className="flex flex-wrap items-center gap-3 pl-8">
            <div className="flex items-center gap-2 flex-1 min-w-[240px]">
              <span className="text-xs text-muted-foreground shrink-0">Description</span>
              <Input
                aria-label="Task description"
                value={description}
                onChange={(e) => setConfigField('description', e.target.value)}
                placeholder="What needs doing?"
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground shrink-0">Due in</span>
              <Input
                aria-label="Due in days"
                type="number"
                min={0}
                value={dueInDays}
                onChange={(e) => setDueInDays(e.target.value)}
                className="w-24"
              />
              <span className="text-xs text-muted-foreground">days</span>
            </div>

            {action.type === 'create_task' && (
              <div className="flex items-center gap-2 min-w-[180px]">
                <span className="text-xs text-muted-foreground shrink-0">Priority</span>
                <Select
                  value={TASK_PRIORITIES.includes(priority as (typeof TASK_PRIORITIES)[number]) ? priority : 'medium'}
                  onValueChange={(val) => setConfigField('priority', val)}
                >
                  <SelectTrigger aria-label="Task priority" className="flex-1 h-8 text-xs">
                    <SelectValue placeholder="Select priority" />
                  </SelectTrigger>
                  <SelectContent>
                    {TASK_PRIORITIES.map((p) => (
                      <SelectItem key={p} value={p} className="text-xs">
                        {p[0].toUpperCase() + p.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        ))}

      {action.type === 'trigger_automation' &&
        (readOnly ? (
          <p className="pl-8 text-xs text-muted-foreground">
            Trigger automation: {automationName}
          </p>
        ) : (
          <div className="flex items-center gap-2 pl-8">
            <span className="text-xs text-muted-foreground shrink-0">Automation</span>
            <Select
              value={automationName}
              onValueChange={(val) => setConfigField('automation_name', val)}
              disabled={automationsLoading || automations.length === 0}
            >
              <SelectTrigger aria-label="Automation" className="flex-1 h-8 text-xs">
                <SelectValue
                  placeholder={
                    automationsLoading
                      ? 'Loading automations…'
                      : automations.length === 0
                        ? 'No automations'
                        : 'Select automation'
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {automations.map((rule) => (
                  <SelectItem key={rule.id} value={rule.name} className="text-xs">
                    {rule.name} ({rule.mode ?? 'off'} ·{' '}
                    {TRIGGER_TYPE_LABELS[rule.trigger_type] ?? rule.trigger_type})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ))}

      {error && (
        <p className="pl-8 text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

// ─── PlaybookEditor ───────────────────────────────────────────────────────────

interface PlaybookEditorProps {
  playbook?: Playbook;
  onSave: (data: Partial<Playbook>) => Promise<unknown> | void;
  onCancel: () => void;
  readOnly?: boolean;
}

export function PlaybookEditor({ playbook, onSave, onCancel, readOnly = false }: PlaybookEditorProps) {
  const [name, setName] = useState(playbook?.name ?? '');
  const [description, setDescription] = useState(playbook?.description ?? '');
  const [probMin, setProbMin] = useState(String(playbook?.probability_min ?? 0.3));
  const [probMax, setProbMax] = useState(String(playbook?.probability_max ?? 0.7));
  const [actions, setActions] = useState<PlaybookAction[]>(() =>
    (playbook?.action_sequence ?? []).map((action) => {
      if (!action.config && defaultConfigFor(action.type)) {
        return { ...action, config: defaultConfigFor(action.type) };
      }
      return action;
    })
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [outreachTemplates, setOutreachTemplates] = useState<OutreachTemplateSummary[] | null>(
    null
  );
  const [automations, setAutomations] = useState<AutomationRule[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    listOutreachTemplates()
      .then((templates) => {
        if (!cancelled) setOutreachTemplates(templates);
      })
      .catch(() => {
        if (cancelled) return;
        setOutreachTemplates(null);
        toast.error('Could not load outreach templates — using built-in options.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    automationsAPI
      .list()
      .then((res) => {
        if (!cancelled) setAutomations(res.rules);
      })
      .catch(() => {
        if (cancelled) return;
        setAutomations([]);
        toast.error('Could not load automations.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const templateOptions = outreachTemplates ?? BUILTIN_OUTREACH_TEMPLATES;

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Name is required';
    if (actions.length === 0) errs.actions = 'At least one action is required';
    const min = parseFloat(probMin);
    const max = parseFloat(probMax);
    if (!isNaN(min) && !isNaN(max) && min >= max) {
      errs.probability = 'Min must be less than max';
    }
    actions.forEach((action, i) => {
      const cfg = (action.config ?? {}) as Record<string, unknown>;
      if (action.type === 'tag' && !isNonEmpty(cfg.tag)) {
        errs[`action-${i}`] = 'Tag is required';
      } else if (action.type === 'notify' && !isNonEmpty(cfg.message)) {
        errs[`action-${i}`] = 'Message is required';
      } else if (
        (action.type === 'create_task' || action.type === 'schedule_task') &&
        !isNonEmpty(cfg.description)
      ) {
        errs[`action-${i}`] = 'Description is required';
      } else if (action.type === 'trigger_automation' && !isNonEmpty(cfg.automation_name)) {
        errs[`action-${i}`] = 'Automation is required';
      }
    });
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        description: description.trim() || null,
        probability_min: parseFloat(probMin),
        probability_max: parseFloat(probMax),
        action_sequence: actions,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleAddAction = () => {
    setActions((prev) => [...prev, { type: 'send_notification' }]);
  };

  const handleRemoveAction = (index: number) => {
    setActions((prev) => prev.filter((_, i) => i !== index));
  };

  const handleChangeAction = (index: number, updated: PlaybookAction) => {
    setActions((prev) => prev.map((a, i) => (i === index ? updated : a)));
  };

  return (
    <div className="space-y-6">
      {/* Name */}
      <div className="space-y-1.5">
        <Label htmlFor="playbook-name">Name</Label>
        <Input
          id="playbook-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={readOnly}
          placeholder="e.g., Critical Save"
        />
        {errors.name && (
          <p className="text-xs text-destructive" role="alert">{errors.name}</p>
        )}
      </div>

      {/* Description */}
      <div className="space-y-1.5">
        <Label htmlFor="playbook-description">Description</Label>
        <Textarea
          id="playbook-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={readOnly}
          placeholder="Describe when to use this playbook..."
          rows={2}
        />
      </div>

      {/* Probability Range */}
      <div className="space-y-2">
        <Label>Probability Range</Label>
        <div className="flex items-center gap-3">
          <div className="flex-1 space-y-1">
            <Label htmlFor="prob-min" className="text-xs text-muted-foreground">Min (%)</Label>
            <Input
              id="prob-min"
              data-testid="prob-min-input"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={probMin}
              onChange={(e) => setProbMin(e.target.value)}
              disabled={readOnly}
              placeholder="0.30"
            />
          </div>
          <span className="text-muted-foreground mt-5">–</span>
          <div className="flex-1 space-y-1">
            <Label htmlFor="prob-max" className="text-xs text-muted-foreground">Max (%)</Label>
            <Input
              id="prob-max"
              data-testid="prob-max-input"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={probMax}
              onChange={(e) => setProbMax(e.target.value)}
              disabled={readOnly}
              placeholder="0.70"
            />
          </div>
        </div>
        {errors.probability && (
          <p className="text-xs text-destructive" role="alert">{errors.probability}</p>
        )}
      </div>

      {/* Action Sequence */}
      <div className="space-y-2">
        <Label>Action Sequence</Label>
        {actions.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-6 text-center text-muted-foreground text-sm">
              No actions yet. Add an action below.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {actions.map((action, i) => (
              <ActionCard
                key={i}
                action={action}
                index={i}
                readOnly={readOnly}
                templateOptions={templateOptions}
                automations={automations ?? []}
                automationsLoading={automations === null}
                error={errors[`action-${i}`]}
                onChange={handleChangeAction}
                onRemove={handleRemoveAction}
              />
            ))}
          </div>
        )}
        {errors.actions && (
          <p className="text-xs text-destructive" role="alert">{errors.actions}</p>
        )}
        {!readOnly && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-1 text-xs"
            onClick={handleAddAction}
          >
            <Plus className="w-3.5 h-3.5 mr-1" />
            Add action
          </Button>
        )}
      </div>

      {/* Footer Buttons */}
      {!readOnly && (
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-border">
          <Button variant="outline" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save playbook'}
          </Button>
        </div>
      )}
    </div>
  );
}