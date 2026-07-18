'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  automationsAPI,
  TRIGGER_TYPE_LABELS,
  ACTION_TYPE_LABELS,
  PLAN_AUTOMATION_LIMITS,
  type AutomationRule,
  type AutomationTemplate,
} from '@/lib/api/automations';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Zap,
  Plus,
  LayoutTemplate,
  UserCheck,
  RefreshCcw,
  Bell,
  Bot,
  Loader2,
} from 'lucide-react';
import { toast } from 'sonner';
import Link from 'next/link';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ACTION_ICONS: Record<string, React.ReactNode> = {
  auto_assign: <UserCheck className="w-3.5 h-3.5" />,
  change_status: <RefreshCcw className="w-3.5 h-3.5" />,
  send_notification: <Bell className="w-3.5 h-3.5" />,
  draft_response: <Bot className="w-3.5 h-3.5" />,
};

function TriggerBadge({ type }: { type: string }) {
  const label = TRIGGER_TYPE_LABELS[type as keyof typeof TRIGGER_TYPE_LABELS] ?? type;
  return (
    <Badge variant="secondary" className="text-xs font-normal">
      {label}
    </Badge>
  );
}

function ActionChips({ actions }: { actions: { type: string; config: Record<string, any> }[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {actions.map((a, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground"
          title={ACTION_TYPE_LABELS[a.type as keyof typeof ACTION_TYPE_LABELS] ?? a.type}
        >
          {ACTION_ICONS[a.type] ?? <Zap className="w-3.5 h-3.5" />}
          <span>{ACTION_TYPE_LABELS[a.type as keyof typeof ACTION_TYPE_LABELS] ?? a.type}</span>
        </span>
      ))}
    </div>
  );
}

function formatTs(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// ─── Template Picker Dialog ───────────────────────────────────────────────────

interface TemplatePickerProps {
  open: boolean;
  onClose: () => void;
  templates: AutomationTemplate[];
  onEnable: (templateId: string) => Promise<void>;
  enabling: string | null;
}

function TemplatePicker({ open, onClose, templates, onEnable, enabling }: TemplatePickerProps) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Browse Automation Templates</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          {templates.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No templates available.</p>
          ) : (
            templates.map(tpl => (
              <div
                key={tpl.id}
                className="flex items-start justify-between gap-4 p-4 rounded-lg border border-border hover:border-primary/50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-sm">{tpl.name}</h3>
                  <p className="text-sm text-muted-foreground mt-0.5">{tpl.description}</p>
                  <div className="flex flex-wrap items-center gap-2 mt-2">
                    <TriggerBadge type={(tpl as any).trigger?.type || tpl.trigger_type} />
                    <ActionChips actions={tpl.actions} />
                  </div>
                </div>
                <Button
                  size="sm"
                  onClick={() => onEnable(tpl.id)}
                  disabled={enabling === tpl.id}
                >
                  {enabling === tpl.id ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    'Enable'
                  )}
                </Button>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AutomationsPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [templates, setTemplates] = useState<AutomationTemplate[]>([]);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false);
  const [enablingTemplate, setEnablingTemplate] = useState<string | null>(null);

  const plan = user?.plan ?? 'free';
  const planLimit = PLAN_AUTOMATION_LIMITS[plan];
  const atLimit = planLimit !== null && rules.length >= planLimit;

  useEffect(() => {
    async function load() {
      try {
        const [listResult, tplResult] = await Promise.all([
          automationsAPI.list(),
          automationsAPI.listTemplates(),
        ]);
        setRules(listResult.rules);
        setTemplates(tplResult);
      } catch {
        toast.error('Failed to load automations');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleToggle = useCallback(async (rule: AutomationRule) => {
    setTogglingId(rule.id);
    try {
      const updated = await automationsAPI.toggle(rule.id);
      setRules(prev => prev.map(r => r.id === rule.id ? updated : r));
      toast.success(updated.is_active ? 'Rule activated' : 'Rule paused');
    } catch {
      toast.error('Failed to toggle rule');
    } finally {
      setTogglingId(null);
    }
  }, []);

  const handleEnableTemplate = useCallback(async (templateId: string) => {
    setEnablingTemplate(templateId);
    try {
      const newRule = await automationsAPI.enableTemplate(templateId);
      setTemplateDialogOpen(false);
      toast.success('Template enabled');
      router.push(`/settings/automations/${newRule.id}`);
    } catch {
      toast.error('Failed to enable template');
    } finally {
      setEnablingTemplate(null);
    }
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full" />
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
          <p className="text-muted-foreground font-medium">Loading automations...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

        {/* Page Header */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <Zap className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-foreground">Automations</h1>
                <p className="text-muted-foreground text-sm">
                  Automate actions when feedback conditions are met
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Plan limit indicator */}
              <span
                className="text-sm text-muted-foreground"
                data-testid="plan-limit-indicator"
              >
                {rules.length}/{planLimit ?? '∞'} rules used
              </span>

              <Button
                variant="outline"
                onClick={() => setTemplateDialogOpen(true)}
                className="flex items-center gap-2"
              >
                <LayoutTemplate className="w-4 h-4" />
                Browse Templates
              </Button>

              <Button
                onClick={() => !atLimit && router.push('/settings/automations/new')}
                disabled={atLimit}
                title={atLimit ? `Plan limit reached (${planLimit} rules). Upgrade to add more.` : undefined}
                className="flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                Add Rule
              </Button>
            </div>
          </div>
        </div>

        {/* Rules Table */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border">
            <CardTitle>Automation Rules ({rules.length})</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {rules.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground" data-testid="empty-state">
                <Zap className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="font-medium">No automation rules configured</p>
                <p className="text-sm mt-1">
                  Add a rule or use a template to automate actions on feedback events.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-left">
                      <th className="pb-2 font-medium">Name</th>
                      <th className="pb-2 font-medium">Trigger</th>
                      <th className="pb-2 font-medium">Actions</th>
                      <th className="pb-2 font-medium text-center">Executions</th>
                      <th className="pb-2 font-medium">Last Fired</th>
                      <th className="pb-2 font-medium text-center">Active</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {rules.map(rule => (
                      <tr key={rule.id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 font-medium">
                          <Link
                            href={`/settings/automations/${rule.id}`}
                            className="hover:underline text-foreground"
                          >
                            {rule.name}
                          </Link>
                          {rule.mode === 'shadow' && (
                            <Badge
                              variant="outline"
                              className="ml-2 text-xs font-normal align-middle"
                              data-testid={`shadow-badge-${rule.id}`}
                            >
                              Shadow
                            </Badge>
                          )}
                          {rule.description && (
                            <p className="text-xs text-muted-foreground mt-0.5 font-normal">
                              {rule.description}
                            </p>
                          )}
                        </td>
                        <td className="py-3">
                          <TriggerBadge type={rule.trigger_type || (rule as any).trigger?.type} />
                        </td>
                        <td className="py-3">
                          <ActionChips actions={rule.actions} />
                        </td>
                        <td className="py-3 text-center text-muted-foreground">
                          {rule.execution_count}
                        </td>
                        <td className="py-3 text-xs text-muted-foreground">
                          {formatTs(rule.last_executed_at)}
                        </td>
                        <td className="py-3 text-center">
                          <Switch
                            checked={rule.is_active}
                            onCheckedChange={() => handleToggle(rule)}
                            disabled={togglingId === rule.id}
                            aria-label={rule.is_active ? 'Pause rule' : 'Activate rule'}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

      </main>

      <TemplatePicker
        open={templateDialogOpen}
        onClose={() => setTemplateDialogOpen(false)}
        templates={templates}
        onEnable={handleEnableTemplate}
        enabling={enablingTemplate}
      />
    </div>
  );
}
