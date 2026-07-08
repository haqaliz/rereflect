'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Brain, Loader2, ExternalLink, CircleAlert, CheckCircle2, Clock, TrendingUp, Eye, Square, CheckSquare, X, Flag, UserX } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/contexts/AuthContext';
import { customersAPI, CustomerProfileData, ActionItem } from '@/lib/api/customers';
import { aiCorrectionsAPI } from '@/lib/api/ai-corrections';
import { MarkAsChurnedDialog } from '@/components/customers/MarkAsChurnedDialog';
import { PotentialWinbackBanner } from '@/components/customers/PotentialWinbackBanner';
import { RunPlaybookDropdown } from '@/components/customers/RunPlaybookDropdown';
import { HealthScoreCircle } from '@/components/customers/HealthScoreCircle';
import { ChurnProbabilityBadge } from '@/components/customers/ChurnProbabilityBadge';
import { ChurnTimelineBadge } from '@/components/customers/ChurnTimelineBadge';
import { SegmentBadge } from '@/components/customers/SegmentBadge';
import { ComponentProgressBars } from '@/components/customers/ComponentProgressBars';
import { HealthTimeline } from '@/components/customers/HealthTimeline';
import { UsageTimeline } from '@/components/customers/UsageTimeline';
import { ActivityTimeline } from '@/components/customers/ActivityTimeline';
import { CustomerTimeline } from '@/components/customers/CustomerTimeline';
import { CustomerFeedbackList } from '@/components/customers/CustomerFeedbackList';
import { ChurnRiskDrivers } from '@/components/customers/ChurnRiskDrivers';
import { ModelAccuracyCard } from '@/components/dashboard/widgets/ModelAccuracyCard';
import { CrmCompanyCard } from '@/components/customers/CrmCompanyCard';
import { ConfidenceBadge } from '@/components/feedbacks/ConfidenceBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

function getRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function getRiskBadgeColor(riskLevel: string): string {
  switch (riskLevel) {
    case 'healthy': return 'var(--chart-5)';
    case 'moderate': return 'var(--chart-2)';
    case 'at_risk': return 'var(--chart-1)';
    case 'critical': return 'var(--destructive)';
    default: return 'var(--muted-foreground)';
  }
}

function getRiskLabel(riskLevel: string): string {
  switch (riskLevel) {
    case 'healthy': return 'Healthy';
    case 'moderate': return 'Moderate';
    case 'at_risk': return 'At Risk';
    case 'critical': return 'Critical';
    default: return riskLevel;
  }
}

// Legacy parser fallback (for records without llm_analysis_data)
function parseAnalysisLegacy(raw: string) {
  const parts = raw.split(' | ');
  const analysis = parts[0] || '';
  let actions: string[] = [];
  let urgency = '';
  for (let i = 1; i < parts.length; i++) {
    const part = parts[i];
    if (part.startsWith('Actions: ')) {
      actions = part.replace('Actions: ', '').split('; ').filter(Boolean);
    } else if (part.startsWith('Urgency: ')) {
      urgency = part.replace('Urgency: ', '');
    }
  }
  return { analysis, actions, urgency };
}

function getUrgencyStyle(urgency: string) {
  switch (urgency) {
    case 'immediate':
      return { color: 'var(--destructive)', label: 'Immediate', icon: CircleAlert };
    case 'this_week':
      return { color: 'var(--chart-1)', label: 'This Week', icon: Clock };
    case 'this_month':
      return { color: 'var(--chart-2)', label: 'This Month', icon: Clock };
    default:
      return { color: 'var(--muted-foreground)', label: urgency, icon: Clock };
  }
}

function getAnalysisTypeStyle(analysisType: string | null) {
  switch (analysisType) {
    case 'churn_risk':
      return {
        icon: AlertTriangle,
        label: 'Churn Analysis',
        tint: 'var(--destructive)',
        bgTint: 'color-mix(in oklch, var(--destructive) 5%, transparent)',
        borderTint: 'color-mix(in oklch, var(--destructive) 15%, transparent)',
      };
    case 'retention':
      return {
        icon: Eye,
        label: 'Watch List',
        tint: 'var(--chart-2)',
        bgTint: 'color-mix(in oklch, var(--chart-2) 5%, transparent)',
        borderTint: 'color-mix(in oklch, var(--chart-2) 15%, transparent)',
      };
    case 'growth_opportunity':
      return {
        icon: TrendingUp,
        label: 'Growth Opportunities',
        tint: 'var(--chart-5)',
        bgTint: 'color-mix(in oklch, var(--chart-5) 5%, transparent)',
        borderTint: 'color-mix(in oklch, var(--chart-5) 15%, transparent)',
      };
    default:
      return {
        icon: Brain,
        label: 'AI Analysis',
        tint: 'var(--chart-5)',
        bgTint: 'transparent',
        borderTint: 'transparent',
      };
  }
}

interface ActionChecklistProps {
  actions: ActionItem[];
  email: string;
  readonly: boolean;
  onActionUpdated: () => void;
}

function ActionChecklist({ actions, email, readonly, onActionUpdated }: ActionChecklistProps) {
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  const handleToggle = async (action: ActionItem, newStatus: 'completed' | 'dismissed') => {
    if (readonly) return;
    setUpdatingId(action.id);
    try {
      await customersAPI.updateAction(email, action.id, newStatus);
      onActionUpdated();
    } catch {
      // swallow
    } finally {
      setUpdatingId(null);
    }
  };

  if (actions.length === 0) return null;

  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
        Action Items
      </p>
      <ul className="space-y-2">
        {actions.map((action) => {
          const isCompleted = action.status === 'completed';
          const isDismissed = action.status === 'dismissed';
          const isUpdating = updatingId === action.id;

          return (
            <li key={action.id} className="flex items-start gap-2 text-sm group">
              {isUpdating ? (
                <Loader2 className="w-4 h-4 mt-0.5 shrink-0 animate-spin text-muted-foreground" />
              ) : readonly ? (
                isCompleted ? (
                  <CheckSquare className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--chart-5)' }} />
                ) : isDismissed ? (
                  <X className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />
                ) : (
                  <Square className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />
                )
              ) : (
                <button
                  onClick={() => handleToggle(action, isCompleted ? 'dismissed' : 'completed')}
                  className="mt-0.5 shrink-0 hover:opacity-80 transition-opacity"
                >
                  {isCompleted ? (
                    <CheckSquare className="w-4 h-4" style={{ color: 'var(--chart-5)' }} />
                  ) : isDismissed ? (
                    <X className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <Square className="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
                  )}
                </button>
              )}
              <span className={isCompleted ? 'line-through text-muted-foreground' : isDismissed ? 'line-through text-muted-foreground opacity-50' : ''}>
                {action.action_text}
              </span>
              {!readonly && !isCompleted && !isDismissed && (
                <button
                  onClick={() => handleToggle(action, 'dismissed')}
                  className="ml-auto opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground transition-opacity"
                  title="Dismiss"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

interface LLMSectionProps {
  profile: CustomerProfileData;
  email: string;
  hasLLMFeature: boolean;
  hasActionsFeature: boolean;
  onAnalysisRequested: () => void;
}

function LLMSection({ profile, email, hasLLMFeature, hasActionsFeature, onAnalysisRequested }: LLMSectionProps) {
  const [requesting, setRequesting] = useState(false);
  const queryClient = useQueryClient();

  const handleGenerate = async () => {
    setRequesting(true);
    try {
      await customersAPI.requestAnalysis(email);
      onAnalysisRequested();
    } catch {
      // swallow
    } finally {
      setRequesting(false);
    }
  };

  const handleActionUpdated = () => {
    queryClient.invalidateQueries({ queryKey: ['customer-profile', email] });
  };

  // Determine analysis data — prefer structured, fall back to legacy
  const hasStructured = !!profile.llm_analysis_summary;
  const hasLegacy = !!profile.llm_analysis;
  const hasAnalysis = hasStructured || hasLegacy;

  let summary: string | null = null;
  let recommendedActions: string[] = [];
  let riskDrivers: string[] = [];
  let urgency: string | null = null;
  let analysisType: string | null = null;

  if (hasStructured) {
    summary = profile.llm_analysis_summary;
    recommendedActions = profile.llm_recommended_actions || [];
    riskDrivers = profile.llm_risk_drivers || [];
    urgency = profile.llm_urgency;
    analysisType = profile.llm_analysis_type;
  } else if (hasLegacy && profile.llm_analysis) {
    const parsed = parseAnalysisLegacy(profile.llm_analysis);
    summary = parsed.analysis;
    recommendedActions = parsed.actions;
    urgency = parsed.urgency || null;
    analysisType = 'churn_risk';
  }

  const typeStyle = getAnalysisTypeStyle(analysisType);
  const TypeIcon = typeStyle.icon;
  const urgencyStyle = urgency ? getUrgencyStyle(urgency) : null;
  const UrgencyIcon = urgencyStyle?.icon;

  if (!hasAnalysis) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Brain className="w-4 h-4 text-[var(--chart-5)]" />
            AI Analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-2">
            <p className="text-sm text-muted-foreground mb-3">
              No analysis generated yet.
            </p>
            <Button
              size="sm"
              onClick={handleGenerate}
              disabled={requesting}
            >
              {requesting && <Loader2 className="w-3 h-3 mr-2 animate-spin" />}
              Generate Analysis
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card style={{ backgroundColor: typeStyle.bgTint, borderColor: typeStyle.borderTint }}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <TypeIcon className="w-4 h-4" style={{ color: typeStyle.tint }} />
            {typeStyle.label}
          </CardTitle>
          {hasActionsFeature && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleGenerate}
              disabled={requesting}
              className="text-xs h-7"
            >
              {requesting ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null}
              Re-analyze
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm leading-relaxed">{summary}</p>

        {riskDrivers.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {riskDrivers.map((driver, i) => (
              <Badge
                key={i}
                variant="outline"
                className="text-xs"
                style={{
                  color: typeStyle.tint,
                  borderColor: `color-mix(in oklch, ${typeStyle.tint} 30%, transparent)`,
                  backgroundColor: `color-mix(in oklch, ${typeStyle.tint} 8%, transparent)`,
                }}
              >
                {driver}
              </Badge>
            ))}
          </div>
        )}

        {/* Interactive action items (Business+) or read-only list (Pro) */}
        {profile.llm_actions && profile.llm_actions.length > 0 ? (
          <ActionChecklist
            actions={profile.llm_actions}
            email={email}
            readonly={!hasActionsFeature}
            onActionUpdated={handleActionUpdated}
          />
        ) : recommendedActions.length > 0 ? (
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Recommended Actions
            </p>
            <ul className="space-y-1.5">
              {recommendedActions.map((action, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <CheckCircle2
                    className="w-3.5 h-3.5 mt-0.5 shrink-0"
                    style={{ color: 'var(--chart-5)' }}
                  />
                  {action}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="flex items-center justify-between pt-1">
          {urgencyStyle && UrgencyIcon && (
            <Badge
              variant="outline"
              style={{
                backgroundColor: `color-mix(in oklch, ${urgencyStyle.color} 15%, transparent)`,
                color: urgencyStyle.color,
                borderColor: `color-mix(in oklch, ${urgencyStyle.color} 30%, transparent)`,
              }}
            >
              <UrgencyIcon className="w-3 h-3 mr-1" />
              {urgencyStyle.label}
            </Badge>
          )}
          <p className="text-xs text-muted-foreground">
            Last analyzed: {getRelativeTime(profile.llm_analyzed_at)}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

interface FlagDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  healthScore: number | null;
}

function FlagDialog({ open, onOpenChange, healthScore }: FlagDialogProps) {
  const [feedbackText, setFeedbackText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await aiCorrectionsAPI.submit({
        correction_type: 'churn_risk',
        entity_type: 'customer_health',
        entity_id: null,
        signal: 'thumbs_down',
        original_value: healthScore !== null ? String(healthScore) : undefined,
        feedback_text: feedbackText.trim() || null,
      });
      toast.success('Thank you! Your feedback helps improve AI accuracy.');
      setFeedbackText('');
      onOpenChange(false);
    } catch {
      toast.error('Failed to submit feedback. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Flag Health Score as Inaccurate</DialogTitle>
          <DialogDescription>
            Help us improve by explaining why this health score seems wrong.
          </DialogDescription>
        </DialogHeader>
        <div className="py-2">
          <Textarea
            placeholder="e.g., This customer is churning but shows a healthy score..."
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            rows={4}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting && <Loader2 className="w-3 h-3 mr-2 animate-spin" />}
            Submit
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Usage Activity Card ────────────────────────────────────────────────────

function UsageActivityCard({ email }: { email: string }) {
  const [days, setDays] = useState(30);

  const { data, isLoading } = useQuery({
    queryKey: ['customer-usage', email, days],
    queryFn: () => customersAPI.getUsage(email, days),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  function relativeTime(dateStr: string | null): string {
    if (!dateStr) return 'Never';
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  const rollup = data?.rollup;
  const hasUsage = rollup && ((rollup.login_count_30d ?? 0) > 0 || (rollup.active_days_30d ?? 0) > 0);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Usage Activity</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="space-y-2">
            <div className="h-4 w-1/3 bg-muted rounded animate-pulse" />
            <div className="h-4 w-1/2 bg-muted rounded animate-pulse" />
          </div>
        ) : !hasUsage ? (
          <p className="text-sm text-muted-foreground">
            No product-usage events recorded yet. Send events via{' '}
            <code className="text-xs bg-muted px-1 py-0.5 rounded">
              POST /api/v1/webhooks/usage
            </code>{' '}
            to start tracking engagement.
          </p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-xs text-muted-foreground">Last Active</p>
              <p className="font-medium">{relativeTime(rollup?.last_active_at ?? null)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Logins (30d)</p>
              <p className="font-mono font-medium">{rollup?.login_count_30d ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Active Days (30d)</p>
              <p className="font-mono font-medium">{rollup?.active_days_30d ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Features Used</p>
              <p className="font-mono font-medium">{rollup?.distinct_feature_count ?? 0}</p>
            </div>
          </div>
        )}
        <UsageTimeline email={email} />
      </CardContent>
    </Card>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function CustomerProfilePage() {
  const router = useRouter();
  const params = useParams();
  const { user } = useAuth();

  // Decode the email from URL params
  const emailParam = decodeURIComponent(String(params.email));

  // Free plan redirect
  useEffect(() => {
    if (user && user.plan === 'free') {
      router.push('/customers');
    }
  }, [user, router]);

  const [analysisRefetchToken, setAnalysisRefetchToken] = useState(0);
  const [flagDialogOpen, setFlagDialogOpen] = useState(false);
  const [markChurnedOpen, setMarkChurnedOpen] = useState(false);

  const { data: profile, isLoading, error } = useQuery({
    queryKey: ['customer-profile', emailParam, analysisRefetchToken],
    queryFn: () => customersAPI.getByEmail(emailParam),
    staleTime: 5 * 60 * 1000,
    enabled: !!emailParam && user?.plan !== 'free',
  });

  if (user?.plan === 'free') {
    return null;
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <Card className="p-8 text-center">
          <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-destructive opacity-50" />
          <h2 className="text-xl font-semibold mb-2">Customer not found</h2>
          <p className="text-muted-foreground mb-4">
            The customer profile you&apos;re looking for doesn&apos;t exist.
          </p>
          <Button variant="outline" asChild>
            <Link href="/customers">Back to Customers</Link>
          </Button>
        </Card>
      </div>
    );
  }

  const riskColor = getRiskBadgeColor(profile.risk_level);
  const hasLLMFeature = user?.plan === 'pro' || user?.plan === 'business' || user?.plan === 'enterprise';
  const hasActionsFeature = user?.plan === 'business' || user?.plan === 'enterprise';
  const showConfidenceBadge = profile.confidence_level === 'low' || profile.confidence_level === 'medium';

  return (
    <TooltipProvider>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Link href="/customers" className="hover:text-foreground transition-colors">
            Customers
          </Link>
          <span>/</span>
          <span className="text-foreground truncate max-w-xs">{profile.customer_email}</span>
        </nav>

        {/* Profile Header */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-start gap-4">
              <div className="relative">
                <HealthScoreCircle score={profile.health_score} size="lg" />
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => setFlagDialogOpen(true)}
                      className="absolute -top-1 -left-1 p-1 rounded-full bg-background border border-border text-muted-foreground hover:text-destructive hover:border-destructive/50 transition-colors shadow-sm"
                    >
                      <Flag className="w-3 h-3" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>Flag score as inaccurate</p>
                  </TooltipContent>
                </Tooltip>
              </div>

              <div className="flex-1 min-w-0">
                <h1 className="text-lg font-bold text-foreground truncate">
                  {profile.customer_email}
                </h1>
                {profile.customer_name ? (
                  <p className="text-sm text-muted-foreground">{profile.customer_name}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">—</p>
                )}

                <div className="flex flex-wrap items-center gap-2 mt-2 text-sm text-muted-foreground">
                  {profile.churn_probability !== null && profile.churn_probability !== undefined ? (
                    <ChurnProbabilityBadge
                      probability={profile.churn_probability}
                      probabilityLow={profile.churn_probability_low ?? undefined}
                      probabilityHigh={profile.churn_probability_high ?? undefined}
                    />
                  ) : (
                    <Badge
                      variant="outline"
                      style={{
                        color: riskColor,
                        borderColor: `color-mix(in oklch, ${riskColor} 30%, transparent)`,
                        backgroundColor: `color-mix(in oklch, ${riskColor} 10%, transparent)`,
                      }}
                    >
                      {getRiskLabel(profile.risk_level)}
                    </Badge>
                  )}
                  <ChurnTimelineBadge bucket={profile.time_to_churn_bucket ?? null} />
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="cursor-help">
                        <SegmentBadge segment={profile.segment} size="sm" />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="text-xs max-w-xs">
                        Rule-based segment computed from usage and feedback signals — not a
                        guarantee.
                      </p>
                    </TooltipContent>
                  </Tooltip>
                  <span>{profile.feedback_count} feedbacks</span>
                  {profile.last_feedback_at && (
                    <span>Last active {getRelativeTime(profile.last_feedback_at)}</span>
                  )}
                </div>

                {showConfidenceBadge && (
                  <div className="mt-2">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="flex items-center gap-1.5 w-fit cursor-help">
                          <AlertTriangle className="w-3.5 h-3.5 text-[var(--chart-2)]" />
                          <span className="text-xs text-[var(--chart-2)] font-medium capitalize">
                            {profile.confidence_level} confidence
                          </span>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="text-xs max-w-xs">
                          Score based on only {profile.feedback_count} feedback
                          {profile.feedback_count === 1 ? '' : 's'}. More feedback improves accuracy.
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                )}
                {profile.confidence_score !== null && profile.confidence_score !== undefined && (
                  <div className="mt-2">
                    <ConfidenceBadge
                      confidenceScore={profile.confidence_score}
                      feedbackCount={profile.feedback_count}
                      lastFeedbackDaysAgo={
                        profile.last_feedback_at
                          ? Math.floor((Date.now() - new Date(profile.last_feedback_at).getTime()) / 86400000)
                          : 0
                      }
                      uniqueCategories={0}
                    />
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2">
                <RunPlaybookDropdown
                  customerEmail={profile.customer_email}
                  churnProbability={profile.churn_probability ?? null}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setMarkChurnedOpen(true)}
                >
                  <UserX className="w-3.5 h-3.5 mr-2" />
                  Mark as churned
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <Link href={`/feedbacks?customer_email=${encodeURIComponent(profile.customer_email)}`}>
                    <ExternalLink className="w-3.5 h-3.5 mr-2" />
                    View All Feedbacks
                  </Link>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Potential winback banner */}
        <PotentialWinbackBanner
          has_potential_winback={(profile as CustomerProfileData & { has_potential_winback?: boolean }).has_potential_winback ?? false}
          customerEmail={profile.customer_email}
          onRecovered={() => setAnalysisRefetchToken((t) => t + 1)}
        />

        {/* Tabs */}
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="feedbacks">Feedbacks</TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6 mt-4">
            {/* CRM / Company — shows HubSpot- or Salesforce-synced data when available (see profile.crm_provider) */}
            <CrmCompanyCard crm={profile} />

            {/* Health Score Components */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Health Score Components</CardTitle>
              </CardHeader>
              <CardContent>
                <ComponentProgressBars
                  churn_risk_component={profile.churn_risk_component}
                  sentiment_component={profile.sentiment_component}
                  resolution_component={profile.resolution_component}
                  frequency_component={profile.frequency_component}
                  usage_component={profile.usage_component}
                />
              </CardContent>
            </Card>

            {/* Health Timeline */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Health Score History</CardTitle>
              </CardHeader>
              <CardContent>
                <HealthTimeline email={profile.customer_email} />
              </CardContent>
            </Card>

            {/* Usage Activity */}
            <UsageActivityCard email={profile.customer_email} />

            {/* LLM Analysis */}
            <LLMSection
              profile={profile}
              email={profile.customer_email}
              hasLLMFeature={hasLLMFeature}
              hasActionsFeature={hasActionsFeature}
              onAnalysisRequested={() => setAnalysisRefetchToken((t) => t + 1)}
            />

            {/* Churn Risk Drivers */}
            {hasLLMFeature && (
              <ChurnRiskDrivers email={profile.customer_email} />
            )}

            {/* Model Accuracy Card (Business+ only) */}
            {hasActionsFeature && (
              <ModelAccuracyCard />
            )}

            {/* Recent Activity */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Recent Activity</CardTitle>
              </CardHeader>
              <CardContent>
                <ActivityTimeline email={profile.customer_email} />
              </CardContent>
            </Card>

            {/* Full paginated timeline (usage + churn + feedback interleaved) */}
            <CustomerTimeline email={profile.customer_email} />
          </TabsContent>

          {/* Feedbacks Tab */}
          <TabsContent value="feedbacks" className="mt-4">
            <CustomerFeedbackList email={profile.customer_email} />
          </TabsContent>
        </Tabs>

        <FlagDialog
          open={flagDialogOpen}
          onOpenChange={setFlagDialogOpen}
          healthScore={profile.health_score}
        />

        <MarkAsChurnedDialog
          open={markChurnedOpen}
          onOpenChange={setMarkChurnedOpen}
          customerEmail={profile.customer_email}
          onSuccess={() => setAnalysisRefetchToken((t) => t + 1)}
        />
      </div>
    </TooltipProvider>
  );
}
