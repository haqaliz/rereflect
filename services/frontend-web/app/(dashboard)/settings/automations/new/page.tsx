'use client';

import { useState, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  automationsAPI,
  TRIGGER_TYPE_LABELS,
  ACTION_TYPE_LABELS,
  type TriggerType,
  type ActionType,
  type AutomationAction,
} from '@/lib/api/automations';
import { listPlaybooks, type Playbook } from '@/lib/api/playbooks';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ArrowLeft, Plus, Trash2, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

// ─── Trigger Config Components ────────────────────────────────────────────────

interface TriggerConfigProps {
  triggerType: TriggerType;
  config: Record<string, any>;
  onChange: (config: Record<string, any>) => void;
}

function CategoryMatchConfig({ config, onChange }: { config: Record<string, any>; onChange: (c: Record<string, any>) => void }) {
  const [tagInput, setTagInput] = useState('');
  const tags: string[] = config.categories ?? config.tags ?? [];

  const addTag = () => {
    const tag = tagInput.trim().toLowerCase();
    if (tag && !tags.includes(tag)) {
      onChange({ ...config, categories: [...tags, tag] });
      setTagInput('');
    }
  };

  const removeTag = (tag: string) => {
    onChange({ ...config, categories: tags.filter(t => t !== tag) });
  };

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <label className="text-sm font-medium">Category tags</label>
        <div className="flex gap-2">
          <Input
            data-testid="trigger-config-tags"
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            placeholder="e.g. billing, authentication"
            onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addTag())}
            className="flex-1"
          />
          <Button variant="outline" size="sm" type="button" onClick={addTag}>
            Add
          </Button>
        </div>
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {tags.map(tag => (
              <Badge
                key={tag}
                variant="secondary"
                className="cursor-pointer"
                onClick={() => removeTag(tag)}
              >
                {tag} &times;
              </Badge>
            ))}
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Checkbox
          data-testid="trigger-config-urgent"
          checked={config.is_urgent ?? false}
          onCheckedChange={checked => onChange({ ...config, is_urgent: !!checked })}
        />
        <label className="text-sm">Only urgent feedback</label>
      </div>
    </div>
  );
}

const USAGE_TREND_STATES: { value: string; label: string }[] = [
  { value: 'declining', label: 'Declining' },
  { value: 'sharp_decline', label: 'Sharp decline' },
];

function UsageTrendConfig({ config, onChange }: { config: Record<string, any>; onChange: (c: Record<string, any>) => void }) {
  const states: string[] = config.states ?? [];

  const toggleState = (state: string) => {
    const next = states.includes(state)
      ? states.filter(s => s !== state)
      : [...states, state];
    onChange({ ...config, states: next });
  };

  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">Fires when usage trend becomes</label>
      <div className="space-y-2">
        {USAGE_TREND_STATES.map(({ value, label }) => (
          <div key={value} className="flex items-center gap-2">
            <Checkbox
              data-testid={`trigger-config-state-${value}`}
              checked={states.includes(value)}
              onCheckedChange={() => toggleState(value)}
            />
            <label className="text-sm">{label}</label>
          </div>
        ))}
      </div>
      {states.length === 0 && (
        <p className="text-xs text-destructive">Select at least one state.</p>
      )}
    </div>
  );
}

function TriggerConfigFields({ triggerType, config, onChange }: TriggerConfigProps) {
  if (triggerType === 'health_score_threshold') {
    return (
      <div className="space-y-1.5">
        <label className="text-sm font-medium">
          When score drops below
        </label>
        <Input
          data-testid="trigger-config-threshold"
          type="number"
          min={1}
          max={100}
          value={config.threshold ?? 30}
          onChange={e => onChange({ ...config, threshold: Number(e.target.value) })}
          className="w-32"
        />
      </div>
    );
  }

  if (triggerType === 'sentiment_pattern') {
    return (
      <div className="flex items-end gap-3">
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Negative feedback count</label>
          <Input
            data-testid="trigger-config-count"
            type="number"
            min={1}
            value={config.count ?? 3}
            onChange={e => onChange({ ...config, count: Number(e.target.value) })}
            className="w-24"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Within days</label>
          <Input
            data-testid="trigger-config-days"
            type="number"
            min={1}
            value={config.days ?? 7}
            onChange={e => onChange({ ...config, days: Number(e.target.value) })}
            className="w-24"
          />
        </div>
      </div>
    );
  }

  if (triggerType === 'churn_risk_level_change') {
    return (
      <div className="space-y-1.5">
        <label className="text-sm font-medium">When risk level becomes</label>
        <Select
          value={config.target_level ?? 'at_risk'}
          onValueChange={val => onChange({ ...config, target_level: val })}
        >
          <SelectTrigger className="w-48" data-testid="trigger-config-target-level">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="at_risk">At Risk</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
          </SelectContent>
        </Select>
      </div>
    );
  }

  if (triggerType === 'feedback_category_match') {
    return <CategoryMatchConfig config={config} onChange={onChange} />;
  }

  if (triggerType === 'usage_trend') {
    return <UsageTrendConfig config={config} onChange={onChange} />;
  }

  if (triggerType === 'churn_probability_threshold') {
    return (
      <div className="space-y-1.5">
        <label className="text-sm font-medium">
          Fires when churn probability &ge; threshold
        </label>
        <Input
          data-testid="trigger-config-churn-threshold"
          type="number"
          min={0}
          max={1}
          step={0.05}
          value={config.threshold ?? 0.7}
          onChange={e =>
            onChange({ ...config, threshold: Number(e.target.value), direction: 'above' })
          }
          className="w-32"
        />
      </div>
    );
  }

  return null;
}

// ─── Action Config Components ─────────────────────────────────────────────────

interface ActionRowProps {
  index: number;
  action: AutomationAction;
  onChange: (action: AutomationAction) => void;
  onRemove: () => void;
  playbooks: Playbook[];
}

const ACTION_TYPES: ActionType[] = [
  'auto_assign',
  'change_status',
  'send_notification',
  'draft_response',
  'run_playbook',
];

function ActionRow({ index, action, onChange, onRemove, playbooks }: ActionRowProps) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/20">
      <div className="flex-1 space-y-3">
        <Select
          value={action.type}
          onValueChange={val => {
            const defaults: Record<string, Record<string, any>> = {
              auto_assign: { assign_to: 'round_robin' },
              change_status: { status: 'in_review' },
              send_notification: { recipients: 'admins', channels: ['dashboard'] },
              draft_response: { tone: 'professional' },
              run_playbook: {},
            };
            onChange({ type: val as ActionType, config: defaults[val] || {} });
          }}
        >
          <SelectTrigger data-testid={`action-type-select-${index}`}>
            <SelectValue placeholder="Select action type" />
          </SelectTrigger>
          <SelectContent>
            {ACTION_TYPES.map(t => (
              <SelectItem key={t} value={t}>
                {ACTION_TYPE_LABELS[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Inline config for change_status */}
        {action.type === 'change_status' && (
          <Select
            value={action.config.status ?? 'in_progress'}
            onValueChange={val => onChange({ ...action, config: { ...action.config, status: val } })}
          >
            <SelectTrigger data-testid={`action-config-status-${index}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="open">Open</SelectItem>
              <SelectItem value="in_progress">In Progress</SelectItem>
              <SelectItem value="resolved">Resolved</SelectItem>
              <SelectItem value="closed">Closed</SelectItem>
            </SelectContent>
          </Select>
        )}

        {/* Inline config for run_playbook */}
        {action.type === 'run_playbook' && (
          playbooks.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">
              No active playbooks — create one first.
            </p>
          ) : (
            <Select
              value={action.config.playbook_id != null ? String(action.config.playbook_id) : ''}
              onValueChange={val => onChange({ ...action, config: { ...action.config, playbook_id: Number(val) } })}
            >
              <SelectTrigger data-testid="action-config-playbook">
                <SelectValue placeholder="Select a playbook..." />
              </SelectTrigger>
              <SelectContent>
                {playbooks.map(p => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )
        )}
      </div>

      <Button
        variant="ghost"
        size="icon"
        type="button"
        onClick={onRemove}
        className="text-destructive hover:text-destructive mt-0.5"
        aria-label="Remove action"
      >
        <Trash2 className="w-4 h-4" />
      </Button>
    </div>
  );
}

const MODE_LABELS: Record<'off' | 'shadow' | 'active', string> = {
  off: 'Off',
  shadow: 'Shadow',
  active: 'Active',
};

// Per-trigger-type default rule mode. usage_trend defaults to shadow so an
// operator watches the execution log before it can take real actions; every
// other trigger type keeps the global 'active' default.
const TRIGGER_DEFAULT_MODE: Partial<Record<TriggerType, 'off' | 'shadow' | 'active'>> = {
  usage_trend: 'shadow',
};

function defaultModeForTrigger(triggerType: string): 'off' | 'shadow' | 'active' {
  return TRIGGER_DEFAULT_MODE[triggerType as TriggerType] ?? 'active';
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function NewAutomationPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [triggerType, setTriggerType] = useState<TriggerType | ''>('');
  const [triggerConfig, setTriggerConfig] = useState<Record<string, any>>({});
  const [actions, setActions] = useState<AutomationAction[]>([]);
  const [cooldownHours, setCooldownHours] = useState(24);
  const [mode, setMode] = useState<'off' | 'shadow' | 'active'>('active');
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listPlaybooks()
      .then(all => setPlaybooks(all.filter(p => !p.is_template && p.is_active)))
      .catch(() => setPlaybooks([]));
  }, []);

  const addAction = () => {
    setActions(prev => [...prev, { type: 'send_notification', config: { recipients: 'admins', channels: ['dashboard'] } }]);
  };

  const updateAction = (index: number, updated: AutomationAction) => {
    setActions(prev => prev.map((a, i) => i === index ? updated : a));
  };

  const removeAction = (index: number) => {
    setActions(prev => prev.filter((_, i) => i !== index));
  };

  const handleTriggerTypeChange = (val: string) => {
    setTriggerType(val as TriggerType);
    const triggerDefaults: Record<string, Record<string, any>> = {
      health_score_threshold: { threshold: 30, direction: 'below' },
      sentiment_pattern: { count: 3, days: 7, sentiment: 'negative' },
      churn_risk_level_change: { target_level: 'at_risk' },
      feedback_category_match: { categories: [], is_urgent: false },
      churn_probability_threshold: { threshold: 0.7, direction: 'above' },
      usage_trend: { states: ['declining', 'sharp_decline'] },
    };
    setTriggerConfig(triggerDefaults[val] || {});
    setMode(defaultModeForTrigger(val));
  };

  const handleSubmit = useCallback(async () => {
    if (!name.trim()) {
      toast.error('Rule name is required');
      return;
    }
    if (!triggerType) {
      toast.error('Trigger type is required');
      return;
    }
    if (triggerType === 'usage_trend' && (!triggerConfig.states || triggerConfig.states.length === 0)) {
      toast.error('Select at least one usage trend state');
      return;
    }

    setSubmitting(true);
    try {
      const created = await automationsAPI.create({
        name: name.trim(),
        description: description.trim() || null,
        trigger: { type: triggerType, config: triggerConfig },
        actions: actions.map(a => ({ type: a.type as ActionType, config: a.config })),
        cooldown_hours: cooldownHours,
        mode,
      });
      toast.success('Automation rule created');
      router.push(`/settings/automations/${created.id}`);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: any) => d.msg).join(', ') : 'Failed to create rule';
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }, [name, description, triggerType, triggerConfig, actions, cooldownHours, mode, router]);

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

        {/* Back nav */}
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => router.push('/settings/automations')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <h1 className="text-xl font-semibold">New Automation Rule</h1>
        </div>

        {/* Rule Basics */}
        <Card>
          <CardHeader>
            <CardTitle>Rule Details</CardTitle>
            <CardDescription>Give your automation rule a descriptive name</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Name <span className="text-destructive">*</span></label>
              <Input
                data-testid="rule-name-input"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g., Churn Prevention"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Description <span className="text-muted-foreground text-xs">(optional)</span></label>
              <textarea
                data-testid="rule-description-input"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="What does this automation do?"
                rows={2}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none"
              />
            </div>
            <div className="flex items-center justify-between gap-4">
              <div>
                <label className="text-sm font-medium">Mode</label>
                <p className="text-xs text-muted-foreground">
                  Shadow logs what would run without executing.
                </p>
              </div>
              <Select value={mode} onValueChange={val => setMode(val as 'off' | 'shadow' | 'active')}>
                <SelectTrigger
                  aria-label="Rule mode"
                  data-testid="rule-mode-select"
                  className="w-32 shrink-0"
                >
                  <SelectValue>{MODE_LABELS[mode]}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="off">Off</SelectItem>
                  <SelectItem value="shadow">Shadow</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Trigger */}
        <Card>
          <CardHeader>
            <CardTitle>Trigger</CardTitle>
            <CardDescription>Define when this rule fires</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Trigger Type <span className="text-destructive">*</span></label>
              <Select value={triggerType} onValueChange={handleTriggerTypeChange}>
                <SelectTrigger data-testid="trigger-type-select">
                  <SelectValue placeholder="Select a trigger..." />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(TRIGGER_TYPE_LABELS) as TriggerType[]).map(t => (
                    <SelectItem key={t} value={t}>
                      {TRIGGER_TYPE_LABELS[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {triggerType && (
              <TriggerConfigFields
                triggerType={triggerType}
                config={triggerConfig}
                onChange={setTriggerConfig}
              />
            )}
          </CardContent>
        </Card>

        {/* Actions */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Actions</CardTitle>
                <CardDescription className="mt-1">What to do when the trigger fires</CardDescription>
              </div>
              <Button variant="outline" size="sm" type="button" onClick={addAction}>
                <Plus className="w-4 h-4 mr-1" />
                Add Action
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {actions.length === 0 ? (
              <p className="text-sm text-muted-foreground italic">
                No actions added yet. Click "Add Action" to add one.
              </p>
            ) : (
              actions.map((action, i) => (
                <ActionRow
                  key={i}
                  index={i}
                  action={action}
                  onChange={updated => updateAction(i, updated)}
                  onRemove={() => removeAction(i)}
                  playbooks={playbooks}
                />
              ))
            )}
          </CardContent>
        </Card>

        {/* Cooldown */}
        <Card>
          <CardHeader>
            <CardTitle>Cooldown</CardTitle>
            <CardDescription>Prevent re-triggering for the same customer too frequently</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">Don't re-trigger within</span>
              <Input
                data-testid="cooldown-hours-input"
                type="number"
                min={1}
                max={168}
                value={cooldownHours}
                onChange={e => setCooldownHours(Number(e.target.value))}
                className="w-24"
              />
              <span className="text-sm text-muted-foreground">hours</span>
            </div>
          </CardContent>
        </Card>

        {/* Submit */}
        <div className="flex justify-end gap-3 pb-8">
          <Button variant="outline" onClick={() => router.push('/settings/automations')}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={submitting || !name.trim() || !triggerType}
          >
            {submitting ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving...</>
            ) : (
              'Save Rule'
            )}
          </Button>
        </div>

      </main>
    </div>
  );
}
