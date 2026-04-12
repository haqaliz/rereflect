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
} from '@/lib/api/automations';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
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
  return <Badge variant="destructive">failed</Badge>;
}

// ─── Trigger Config Fields ────────────────────────────────────────────────────

interface TriggerConfigProps {
  triggerType: TriggerType;
  config: Record<string, any>;
  onChange: (config: Record<string, any>) => void;
  disabled?: boolean;
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
    const tags: string[] = config.tags ?? [];
    const [tagInput, setTagInput] = useState('');

    const addTag = () => {
      const tag = tagInput.trim().toLowerCase();
      if (tag && !tags.includes(tag)) {
        onChange({ ...config, tags: [...tags, tag] });
        setTagInput('');
      }
    };

    const removeTag = (tag: string) => {
      onChange({ ...config, tags: tags.filter(t => t !== tag) });
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
            checked={config.urgent ?? false}
            onCheckedChange={checked => !disabled && onChange({ ...config, urgent: !!checked })}
            disabled={disabled}
          />
          <label htmlFor="trigger-urgent" className="text-sm cursor-pointer">
            Only when feedback is urgent
          </label>
        </div>
      </div>
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
];

interface ActionRowProps {
  index: number;
  action: AutomationAction;
  onChange: (action: AutomationAction) => void;
  onRemove: () => void;
  disabled?: boolean;
}

function ActionRow({ index, action, onChange, onRemove, disabled }: ActionRowProps) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/20">
      <div className="flex-1 space-y-3">
        <Select
          value={action.type}
          onValueChange={val => onChange({ ...action, type: val as ActionType })}
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

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AutomationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();

  const ruleId = Number(params?.id);

  const [loading, setLoading] = useState(true);
  const [rule, setRule] = useState<AutomationRule | null>(null);
  const [executions, setExecutions] = useState<AutomationExecution[]>([]);

  // Config form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [triggerType, setTriggerType] = useState<TriggerType | ''>('');
  const [triggerConfig, setTriggerConfig] = useState<Record<string, any>>({});
  const [actions, setActions] = useState<AutomationAction[]>([]);
  const [cooldownHours, setCooldownHours] = useState(24);
  const [isActive, setIsActive] = useState(true);
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
        const [r, execs] = await Promise.all([
          automationsAPI.get(ruleId),
          automationsAPI.listExecutions(ruleId),
        ]);
        setRule(r);
        setExecutions(execs);

        // Populate form
        setName(r.name);
        setDescription(r.description ?? '');
        setTriggerType(r.trigger_type || r.trigger?.type || '');
        setTriggerConfig(r.trigger_config || r.trigger?.config || {});
        setActions(r.actions);
        setCooldownHours(r.cooldown_hours);
        setIsActive(r.is_active);
      } catch {
        toast.error('Failed to load automation rule');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [ruleId]);

  const handleSave = useCallback(async () => {
    if (!rule) return;
    setSaving(true);
    try {
      const updated = await automationsAPI.update(rule.id, {
        name,
        description: description.trim() || null,
        trigger: { type: triggerType as TriggerType, config: triggerConfig },
        actions: actions.map(a => ({ type: a.type, config: a.config })),
        cooldown_hours: cooldownHours,
        is_active: isActive,
      });
      setRule(updated);
      toast.success('Rule saved');
    } catch {
      toast.error('Failed to save rule');
    } finally {
      setSaving(false);
    }
  }, [rule, name, description, triggerType, triggerConfig, actions, cooldownHours, isActive]);

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
                <div className="flex items-center gap-2">
                  <Switch
                    id="is-active"
                    checked={isActive}
                    onCheckedChange={setIsActive}
                    disabled={!isAdminOrOwner}
                  />
                  <label htmlFor="is-active" className="text-sm font-medium cursor-pointer">
                    Active
                  </label>
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
                      setTriggerConfig({});
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
                  <span className="text-sm text-muted-foreground">Don't re-trigger within</span>
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
                    No executions yet. This rule hasn't fired.
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
