'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  automationsAPI,
  TRIGGER_TYPE_LABELS,
  ACTION_TYPE_LABELS,
  type AutomationRule,
  type AutomationExecution,
  type TriggerType,
  type ActionType,
  type AutomationAction,
  type AutomationEmailDelivery,
  type SendCustomerEmailConfig,
} from '@/lib/api/automations';
import {
  listPlaybooks,
  SEND_EMAIL_RECIPIENTS,
  SEND_EMAIL_RECIPIENT_LABELS,
  type Playbook,
} from '@/lib/api/playbooks';
import {
  BUILTIN_OUTREACH_TEMPLATES,
  listOutreachTemplates,
  type OutreachTemplateSummary,
} from '@/lib/api/outreach';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  ArrowLeft,
  Trash2,
  Save,
  Loader2,
  Plus,
} from 'lucide-react';
import { toast } from 'sonner';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const DELIVERY_STATUS_VARIANTS: Record<string, 'outline' | 'secondary' | 'destructive'> = {
  queued: 'outline',
  sent: 'secondary',
  skipped: 'secondary',
  failed: 'destructive',
};

function formatTs(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function StatusBadge({ status }: { status: AutomationExecution['status'] }) {
  if (status === 'success') {
    return <Badge className="bg-green-500 text-white hover:bg-green-600">success</Badge>;
  }
  if (status === 'partial_failure') {
    return <Badge className="bg-yellow-500 text-white hover:bg-yellow-600">partial</Badge>;
  }
  if (status === 'shadow') {
    return <Badge className="bg-blue-500 text-white hover:bg-blue-600">shadow</Badge>;
  }
  return <Badge variant="destructive">failed</Badge>;
}

// ─── Trigger Config Fields ────────────────────────────────────────────────────

interface TriggerConfigProps {
  triggerType: TriggerType;
  config: Record<string, any>;
  onChange: (config: Record<string, any>) => void;
  disabled?: boolean;
}

/**
 * The category-match branch owns a text input, so it needs local state. It used
 * to call useState() inline inside TriggerConfigFields' if-chain, which changed
 * the hook order whenever the user switched trigger types — a
 * react-hooks/rules-of-hooks violation that React only tolerates by accident.
 * Extracting it into its own component makes the hook unconditional.
 */
function CategoryMatchTriggerFields({
  config,
  onChange,
  disabled,
}: {
  config: Record<string, any>;
  onChange: (config: Record<string, any>) => void;
  disabled?: boolean;
}) {
  // Read `categories` (what the backend's FeedbackCategoryConfig and the
  // worker evaluator actually use), falling back to the legacy `tags` key so
  // rules previously saved through this page -- which wrote keys the backend
  // ignored -- still display their values instead of appearing empty.
  const tags: string[] = config.categories ?? config.tags ?? [];
  const [tagInput, setTagInput] = useState('');

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
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            placeholder="e.g. billing, authentication"
            onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addTag())}
            disabled={disabled}
            className="flex-1"
          />
          <Button variant="outline" size="sm" type="button" onClick={addTag} disabled={disabled}>
            Add
          </Button>
        </div>
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {tags.map(tag => (
              <Badge
                key={tag}
                variant="secondary"
                className={disabled ? '' : 'cursor-pointer'}
                onClick={() => !disabled && removeTag(tag)}
              >
                {tag} {!disabled && <>×</>}
              </Badge>
            ))}
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Checkbox
          id="trigger-urgent"
          checked={config.is_urgent ?? config.urgent ?? false}
          onCheckedChange={checked => !disabled && onChange({ ...config, is_urgent: !!checked })}
          disabled={disabled}
        />
        <label htmlFor="trigger-urgent" className="text-sm cursor-pointer">
          Only when feedback is urgent
        </label>
      </div>
    </div>
  );
}

const BATCH_SENTIMENT_OPTIONS: { value: string; label: string }[] = [
  { value: 'negative', label: 'Negative' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'positive', label: 'Positive' },
];

/**
 * Stateless — every field reads/writes directly through `config`/`onChange`,
 * so unlike CategoryMatchTriggerFields this does not need local useState and
 * can stay inline in the TriggerConfigFields if-chain.
 */
function BatchSentimentThresholdConfig({
  config,
  onChange,
  disabled,
}: {
  config: Record<string, any>;
  onChange: (config: Record<string, any>) => void;
  disabled?: boolean;
}) {
  const thresholdMode: 'percentage' | 'count' = config.mode ?? 'percentage';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Sentiment</label>
          <Select
            value={config.sentiment ?? 'negative'}
            onValueChange={val => onChange({ ...config, sentiment: val })}
            disabled={disabled}
          >
            <SelectTrigger data-testid="trigger-config-sentiment" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {BATCH_SENTIMENT_OPTIONS.map(({ value, label }) => (
                <SelectItem key={value} value={value}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Window (hours)</label>
          <Input
            data-testid="trigger-config-window-hours"
            type="number"
            min={1}
            max={168}
            value={config.window_hours ?? 24}
            onChange={e => onChange({ ...config, window_hours: Number(e.target.value) })}
            disabled={disabled}
            className="w-28"
          />
        </div>
      </div>
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Threshold type</label>
          <Select
            value={thresholdMode}
            onValueChange={val => onChange({ ...config, mode: val })}
            disabled={disabled}
          >
            <SelectTrigger data-testid="trigger-config-mode" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="percentage">Percentage of feedback</SelectItem>
              <SelectItem value="count">Absolute count</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">
            {thresholdMode === 'percentage' ? 'Threshold (share, 0–1)' : 'Threshold (count)'}
          </label>
          <Input
            data-testid="trigger-config-batch-threshold"
            type="number"
            min={thresholdMode === 'percentage' ? 0.01 : 1}
            max={thresholdMode === 'percentage' ? 1 : undefined}
            step={thresholdMode === 'percentage' ? 0.05 : 1}
            value={config.threshold ?? 0.5}
            onChange={e => onChange({ ...config, threshold: Number(e.target.value) })}
            disabled={disabled}
            className="w-28"
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <label className="text-sm font-medium">Minimum feedback in window</label>
        <Input
          data-testid="trigger-config-min-total"
          type="number"
          min={1}
          value={config.min_total ?? 5}
          onChange={e => onChange({ ...config, min_total: Number(e.target.value) })}
          disabled={disabled}
          className="w-28"
        />
        <p className="text-xs text-muted-foreground">
          Sample floor — the rule won&rsquo;t fire until at least this many feedback items land in the window.
        </p>
      </div>
    </div>
  );
}

function TriggerConfigFields({ triggerType, config, onChange, disabled }: TriggerConfigProps) {
  if (triggerType === 'health_score_threshold') {
    return (
      <div className="space-y-1.5">
        <label className="text-sm font-medium">When score drops below</label>
        <Input
          data-testid="trigger-config-threshold"
          type="number"
          min={1}
          max={100}
          value={config.threshold ?? 30}
          onChange={e => onChange({ ...config, threshold: Number(e.target.value) })}
          disabled={disabled}
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
            disabled={disabled}
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
            disabled={disabled}
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
          disabled={disabled}
        >
          <SelectTrigger className="w-48">
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
    return (
      <CategoryMatchTriggerFields
        config={config}
        onChange={onChange}
        disabled={disabled}
      />
    );
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
          disabled={disabled}
          className="w-32"
        />
      </div>
    );
  }

  if (triggerType === 'usage_trend') {
    const states: string[] = config.states ?? [];
    const usageTrendStates: { value: string; label: string }[] = [
      { value: 'declining', label: 'Declining' },
      { value: 'sharp_decline', label: 'Sharp decline' },
    ];

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
          {usageTrendStates.map(({ value, label }) => (
            <div key={value} className="flex items-center gap-2">
              <Checkbox
                data-testid={`trigger-config-state-${value}`}
                checked={states.includes(value)}
                onCheckedChange={() => !disabled && toggleState(value)}
                disabled={disabled}
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

  if (triggerType === 'batch_sentiment_threshold') {
    return (
      <BatchSentimentThresholdConfig
        config={config}
        onChange={onChange}
        disabled={disabled}
      />
    );
  }

  return null;
}

// ─── Action Row ───────────────────────────────────────────────────────────────

const ACTION_TYPES: ActionType[] = [
  'auto_assign',
  'change_status',
  'send_notification',
  'draft_response',
  'run_playbook',
  'send_customer_email',
];

interface ActionRowProps {
  index: number;
  action: AutomationAction;
  onChange: (action: AutomationAction) => void;
  onRemove: () => void;
  disabled?: boolean;
  playbooks: Playbook[];
  templateOptions: OutreachTemplateSummary[];
}

/**
 * Seed a `send_customer_email` config, replacing anything stale.
 *
 * This page preserves config across an action-type switch, which is fine for
 * every other type — but the backend `send_customer_email` config model is
 * `extra="forbid"`, so a leftover `recipients`/`status`/`tone` key would 422
 * the save. A config survives only when it is exactly { template, recipient }
 * with a known recipient.
 */
function seedSendCustomerEmailConfig(
  config: Record<string, any> | undefined,
  templateOptions: OutreachTemplateSummary[]
): SendCustomerEmailConfig {
  const template = config?.template;
  const recipient = config?.recipient;
  const onlyKnownKeys = Object.keys(config ?? {}).every(
    k => k === 'template' || k === 'recipient'
  );
  const valid =
    typeof template === 'string' &&
    (recipient === 'customer' || recipient === 'cs_assignee') &&
    onlyKnownKeys;

  return valid
    ? { template, recipient }
    : {
        template: templateOptions[0]?.key ?? BUILTIN_OUTREACH_TEMPLATES[0].key,
        recipient: 'customer',
      };
}

function ActionRow({ index, action, onChange, onRemove, disabled, playbooks, templateOptions }: ActionRowProps) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/20">
      <div className="flex-1 space-y-3">
        <Select
          value={action.type}
          onValueChange={val => {
            if (val === 'send_customer_email') {
              onChange({
                ...action,
                type: val,
                config: seedSendCustomerEmailConfig(action.config, templateOptions),
              });
            } else {
              onChange({ ...action, type: val as ActionType });
            }
          }}
          disabled={disabled}
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

        {action.type === 'change_status' && (
          <Select
            value={action.config.status ?? 'in_progress'}
            onValueChange={val => onChange({ ...action, config: { ...action.config, status: val } })}
            disabled={disabled}
          >
            <SelectTrigger>
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

        {action.type === 'run_playbook' && (
          playbooks.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">
              No active playbooks — create one first.
            </p>
          ) : (
            <Select
              value={action.config.playbook_id != null ? String(action.config.playbook_id) : ''}
              onValueChange={val => onChange({ ...action, config: { ...action.config, playbook_id: Number(val) } })}
              disabled={disabled}
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

        {action.type === 'send_customer_email' && (
          <div className="space-y-3">
            <Select
              value={typeof action.config?.template === 'string' ? action.config.template : ''}
              onValueChange={val => onChange({ ...action, config: { ...action.config, template: val } })}
              disabled={disabled}
            >
              <SelectTrigger data-testid={`action-config-template-${index}`}>
                <SelectValue placeholder="Select template..." />
              </SelectTrigger>
              <SelectContent>
                {templateOptions.map(t => (
                  <SelectItem key={t.key} value={t.key}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={
                SEND_EMAIL_RECIPIENTS.includes(action.config?.recipient)
                  ? action.config.recipient
                  : ''
              }
              onValueChange={val => onChange({ ...action, config: { ...action.config, recipient: val } })}
              disabled={disabled}
            >
              <SelectTrigger data-testid={`action-config-recipient-${index}`}>
                <SelectValue placeholder="Select recipient..." />
              </SelectTrigger>
              <SelectContent>
                {SEND_EMAIL_RECIPIENTS.map(r => (
                  <SelectItem key={r} value={r}>
                    {SEND_EMAIL_RECIPIENT_LABELS[r]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Sent through the shared outreach path: opted-out customers are never
              emailed, the same per-recipient cooldown as bulk outreach applies, and
              with no email key configured the send is recorded as skipped. A rule in
              shadow mode never sends.
            </p>
          </div>
        )}
      </div>

      {!disabled && (
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
      )}
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
// other trigger type keeps the global 'active' default. Mirrors new/page.tsx.
const TRIGGER_DEFAULT_MODE: Partial<Record<TriggerType, 'off' | 'shadow' | 'active'>> = {
  usage_trend: 'shadow',
  batch_sentiment_threshold: 'shadow',
};

function defaultModeForTrigger(triggerType: string): 'off' | 'shadow' | 'active' {
  return TRIGGER_DEFAULT_MODE[triggerType as TriggerType] ?? 'active';
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AutomationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();

  const ruleId = Number(params?.id);

  const [loading, setLoading] = useState(true);
  const [rule, setRule] = useState<AutomationRule | null>(null);
  const [executions, setExecutions] = useState<AutomationExecution[]>([]);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);

  // Config form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [triggerType, setTriggerType] = useState<TriggerType | ''>('');
  const [triggerConfig, setTriggerConfig] = useState<Record<string, any>>({});
  const [actions, setActions] = useState<AutomationAction[]>([]);
  const [cooldownHours, setCooldownHours] = useState(24);
  const [mode, setMode] = useState<'off' | 'shadow' | 'active'>('active');
  const [deliveries, setDeliveries] = useState<AutomationEmailDelivery[]>([]);
  const [outreachTemplates, setOutreachTemplates] = useState<OutreachTemplateSummary[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);
  const [confirmMessage, setConfirmMessage] = useState('');

  const requestConfirm = (message: string, action: () => void) => {
    setConfirmMessage(message);
    setConfirmAction(() => action);
  };

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    if (!ruleId || isNaN(ruleId)) return;

    async function load() {
      try {
        const [r, execs, allPlaybooks, dels] = await Promise.all([
          automationsAPI.get(ruleId),
          automationsAPI.listExecutions(ruleId),
          listPlaybooks().catch(() => []),
          // Members are not allowed to read deliveries (the endpoint 403s) —
          // don't ask.
          isAdminOrOwner
            ? automationsAPI.listDeliveries(ruleId).catch(() => [])
            : Promise.resolve([]),
        ]);
        setRule(r);
        setExecutions(execs);
        setDeliveries(dels);
        setPlaybooks(allPlaybooks.filter(p => !p.is_template && p.is_active));

        // Populate form
        setName(r.name);
        setDescription(r.description ?? '');
        setTriggerType(r.trigger_type || r.trigger?.type || '');
        setTriggerConfig(r.trigger_config || r.trigger?.config || {});
        setActions(r.actions);
        setCooldownHours(r.cooldown_hours);
        setMode(r.mode ?? 'active');
      } catch {
        toast.error('Failed to load automation rule');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [ruleId, isAdminOrOwner]);

  useEffect(() => {
    listOutreachTemplates()
      .then(setOutreachTemplates)
      .catch(() => {
        setOutreachTemplates(null);
        toast.error('Could not load outreach templates — using built-in options.');
      });
  }, []);

  const templateOptions = outreachTemplates ?? BUILTIN_OUTREACH_TEMPLATES;

  const handleSave = useCallback(async () => {
    if (!rule) return;
    if (triggerType === 'usage_trend' && (!triggerConfig.states || triggerConfig.states.length === 0)) {
      toast.error('Select at least one usage trend state');
      return;
    }
    setSaving(true);
    try {
      const updated = await automationsAPI.update(rule.id, {
        name,
        description: description.trim() || null,
        trigger: { type: triggerType as TriggerType, config: triggerConfig },
        actions: actions.map(a => ({ type: a.type as ActionType, config: a.config })),
        cooldown_hours: cooldownHours,
        mode,
      });
      setRule(updated);
      toast.success('Rule saved');
    } catch {
      toast.error('Failed to save rule');
    } finally {
      setSaving(false);
    }
  }, [rule, name, description, triggerType, triggerConfig, actions, cooldownHours, mode]);

  const handleDelete = useCallback(() => {
    if (!rule) return;
    requestConfirm(
      `Delete "${rule.name}"? This cannot be undone.`,
      async () => {
        setDeleting(true);
        try {
          await automationsAPI.delete(rule.id);
          toast.success('Rule deleted');
          router.push('/settings/automations');
        } catch {
          toast.error('Failed to delete rule');
          setDeleting(false);
        }
      }
    );
  }, [rule, router]);

  const addAction = () => {
    setActions(prev => [...prev, { type: 'send_notification', config: {} }]);
  };

  const updateAction = (index: number, updated: AutomationAction) => {
    setActions(prev => prev.map((a, i) => i === index ? updated : a));
  };

  const removeAction = (index: number) => {
    setActions(prev => prev.filter((_, i) => i !== index));
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full" />
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
          <p className="text-muted-foreground font-medium">Loading rule...</p>
        </div>
      </div>
    );
  }

  if (!rule) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground">Automation rule not found.</p>
          <Button asChild variant="ghost" className="mt-4">
            <Link href="/settings/automations">Back to Automations</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

        {/* Back nav + header */}
        <div className="animate-fade-in">
          <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2 text-muted-foreground">
            <Link href="/settings/automations">
              <ArrowLeft className="w-4 h-4 mr-1" />
              Back to Automations
            </Link>
          </Button>

          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-foreground">{rule.name}</h1>
              {rule.description && (
                <p className="text-muted-foreground text-sm mt-1">{rule.description}</p>
              )}
              <div className="flex items-center gap-2 mt-2">
                <Badge variant="secondary">
                  {TRIGGER_TYPE_LABELS[(rule.trigger_type || rule.trigger?.type) as keyof typeof TRIGGER_TYPE_LABELS] ?? rule.trigger_type ?? rule.trigger?.type}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {rule.execution_count} executions
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              {isAdminOrOwner && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="text-destructive hover:text-destructive border-destructive/30 hover:border-destructive"
                >
                  {deleting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4" />
                  )}
                  <span className="ml-1.5">Delete</span>
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="configuration" className="animate-slide-up">
          <TabsList>
            <TabsTrigger value="configuration">Configuration</TabsTrigger>
            <TabsTrigger value="execution-log">Execution Log</TabsTrigger>
            {isAdminOrOwner && (
              <TabsTrigger value="email-deliveries">Email Deliveries</TabsTrigger>
            )}
          </TabsList>

          {/* ── Configuration Tab ──────────────────────────────────── */}
          <TabsContent value="configuration" className="mt-4 space-y-6">

            <Card>
              <CardHeader className="border-b border-border">
                <CardTitle>Rule Details</CardTitle>
              </CardHeader>
              <CardContent className="pt-5 space-y-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Name</label>
                  <Input
                    data-testid="rule-name-input"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    disabled={!isAdminOrOwner}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Description</label>
                  <textarea
                    data-testid="rule-description-input"
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                    rows={2}
                    disabled={!isAdminOrOwner}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                </div>
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <label className="text-sm font-medium">Mode</label>
                    <p className="text-xs text-muted-foreground">
                      Shadow logs what would run without executing.
                    </p>
                  </div>
                  <Select
                    value={mode}
                    onValueChange={val => setMode(val as 'off' | 'shadow' | 'active')}
                    disabled={!isAdminOrOwner}
                  >
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

            <Card>
              <CardHeader className="border-b border-border">
                <CardTitle>Trigger</CardTitle>
              </CardHeader>
              <CardContent className="pt-5 space-y-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Trigger Type</label>
                  <Select
                    value={triggerType}
                    onValueChange={val => {
                      setTriggerType(val as TriggerType);
                      const triggerDefaults: Record<string, Record<string, any>> = {
                        health_score_threshold: { threshold: 30, direction: 'below' },
                        sentiment_pattern: { count: 3, days: 7, sentiment: 'negative' },
                        churn_risk_level_change: { target_level: 'at_risk' },
                        feedback_category_match: { categories: [], is_urgent: false },
                        churn_probability_threshold: { threshold: 0.7, direction: 'above' },
                        usage_trend: { states: ['declining', 'sharp_decline'] },
                        batch_sentiment_threshold: {
                          sentiment: 'negative',
                          window_hours: 24,
                          mode: 'percentage',
                          threshold: 0.5,
                          min_total: 5,
                        },
                      };
                      setTriggerConfig(triggerDefaults[val] || {});
                      setMode(defaultModeForTrigger(val));
                    }}
                    disabled={!isAdminOrOwner}
                  >
                    <SelectTrigger data-testid="trigger-type-select">
                      <SelectValue />
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
                    disabled={!isAdminOrOwner}
                  />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="border-b border-border">
                <div className="flex items-center justify-between">
                  <CardTitle>Actions</CardTitle>
                  {isAdminOrOwner && (
                    <Button variant="outline" size="sm" type="button" onClick={addAction}>
                      <Plus className="w-4 h-4 mr-1" />
                      Add Action
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent className="pt-4 space-y-3">
                {actions.length === 0 ? (
                  <p className="text-sm text-muted-foreground italic">No actions configured.</p>
                ) : (
                  actions.map((action, i) => (
                    <ActionRow
                      key={i}
                      index={i}
                      action={action}
                      onChange={updated => updateAction(i, updated)}
                      onRemove={() => removeAction(i)}
                      disabled={!isAdminOrOwner}
                      playbooks={playbooks}
                      templateOptions={templateOptions}
                    />
                  ))
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="border-b border-border">
                <CardTitle>Cooldown</CardTitle>
              </CardHeader>
              <CardContent className="pt-5">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-muted-foreground">Don&rsquo;t re-trigger within</span>
                  <Input
                    data-testid="cooldown-hours-input"
                    type="number"
                    min={1}
                    max={168}
                    value={cooldownHours}
                    onChange={e => setCooldownHours(Number(e.target.value))}
                    disabled={!isAdminOrOwner}
                    className="w-24"
                  />
                  <span className="text-sm text-muted-foreground">hours</span>
                </div>
              </CardContent>
            </Card>

            {isAdminOrOwner && (
              <div className="flex justify-end">
                <Button onClick={handleSave} disabled={saving}>
                  {saving ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving…</>
                  ) : (
                    <><Save className="w-4 h-4 mr-2" />Save Changes</>
                  )}
                </Button>
              </div>
            )}

          </TabsContent>

          {/* ── Execution Log Tab ───────────────────────────────────── */}
          <TabsContent value="execution-log" className="mt-4">
            <Card>
              <CardHeader className="border-b border-border">
                <CardTitle>Execution Log (last 50)</CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                {executions.length === 0 ? (
                  <p className="text-center py-8 text-muted-foreground text-sm">
                    No executions yet. This rule hasn&rsquo;t fired.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-muted-foreground text-left">
                          <th className="pb-2 font-medium">Timestamp</th>
                          <th className="pb-2 font-medium">Customer</th>
                          <th className="pb-2 font-medium">Feedback #</th>
                          <th className="pb-2 font-medium">Actions Taken</th>
                          <th className="pb-2 font-medium">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {executions.map(exec => (
                          <tr key={exec.id} className="hover:bg-muted/30 transition-colors">
                            <td className="py-2.5 text-muted-foreground text-xs">
                              {formatTs(exec.executed_at)}
                            </td>
                            <td className="py-2.5 text-xs">
                              {exec.customer_email ?? '—'}
                            </td>
                            <td className="py-2.5 text-xs text-muted-foreground">
                              {exec.feedback_id != null ? `#${exec.feedback_id}` : '—'}
                            </td>
                            <td className="py-2.5">
                              <div className="flex flex-wrap gap-1">
                                {exec.actions_executed.map((a, i) => (
                                  <Badge
                                    key={i}
                                    variant={a.error ? 'destructive' : 'secondary'}
                                    className="text-xs"
                                    title={a.error ?? a.result}
                                  >
                                    {ACTION_TYPE_LABELS[a.type as keyof typeof ACTION_TYPE_LABELS] ?? a.type}
                                  </Badge>
                                ))}
                              </div>
                            </td>
                            <td className="py-2.5">
                              <StatusBadge status={exec.status} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── Email Deliveries Tab ────────────────────────────────── */}
          {isAdminOrOwner && (
            <TabsContent value="email-deliveries" className="mt-4">
              <Card>
                <CardHeader className="border-b border-border">
                  <CardTitle>Email Deliveries</CardTitle>
                  <CardDescription>
                    One row per <code>Send Customer Email</code> action. A
                    <strong> skipped</strong> row is the honest record of a send that
                    did not happen — the reason says why.
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-4">
                  {deliveries.length === 0 ? (
                    <p className="text-center py-8 text-muted-foreground text-sm">
                      No email deliveries yet.
                    </p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border text-muted-foreground text-left">
                            <th className="pb-2 font-medium">Timestamp</th>
                            <th className="pb-2 font-medium">Recipient</th>
                            <th className="pb-2 font-medium">Template</th>
                            <th className="pb-2 font-medium">Subject</th>
                            <th className="pb-2 font-medium">Status</th>
                            <th className="pb-2 font-medium">Reason</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {deliveries.map(d => (
                            <tr key={d.id} className="hover:bg-muted/30 transition-colors">
                              <td className="py-2.5 text-muted-foreground text-xs">
                                {formatTs(d.created_at)}
                              </td>
                              <td className="py-2.5 text-xs">
                                {d.to_email ?? d.customer_email ?? '—'}
                              </td>
                              <td className="py-2.5 text-xs text-muted-foreground">
                                {d.template_key}
                              </td>
                              <td className="py-2.5 text-xs">{d.subject ?? '—'}</td>
                              <td className="py-2.5">
                                <Badge
                                  variant={DELIVERY_STATUS_VARIANTS[d.status] ?? 'secondary'}
                                  className={
                                    d.status === 'sent' ? 'bg-green-500 text-white text-xs' : 'text-xs'
                                  }
                                >
                                  {d.status}
                                </Badge>
                              </td>
                              <td className="py-2.5 text-xs text-muted-foreground">
                                {d.reason ?? '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          )}
        </Tabs>
      </main>

      {/* Confirm Dialog */}
      <Dialog open={!!confirmAction} onOpenChange={(open) => { if (!open) setConfirmAction(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Confirm Action</DialogTitle>
            <DialogDescription>{confirmMessage}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => { confirmAction?.(); setConfirmAction(null); }}>Confirm</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
