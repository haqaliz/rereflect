'use client';

import { useEffect, useState, useCallback, Suspense } from 'react';
import { useRouter, useParams, useSearchParams } from 'next/navigation';
import { feedbackAPI, FeedbackItem } from '@/lib/api/feedback';
import { customerHealthAPI, CustomerHealthData } from '@/lib/api/customer-health';
import { analytics } from '@/lib/analytics';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  ArrowLeft,
  MessageSquare,
  Calendar,
  Globe,
  AlertTriangle,
  Lightbulb,
  CircleAlert,
  Smile,
  Meh,
  Frown,
  Tag,
  Brain,
  Clock,
  RefreshCw,
  Trash2,
  ShieldAlert,
  DatabaseZap,
  CreditCard,
  ServerCrash,
  KeyRound,
  CircleX,
  Gauge,
  MousePointerClick,
  Laptop,
  PackageX,
  FileQuestion,
  Paintbrush,
  Boxes,
  Workflow,
  Plug,
  BarChart3,
  Settings2,
  Users,
  ArrowUpDown,
  Smartphone,
  Bell,
  Palette,
  ServerOff,
  ShieldOff,
  HardDrive,
  Lock,
  Bug,
  Receipt,
  UserMinus,
  Scale,
  Megaphone,
  Hash,
  Upload,
  Webhook,
  PenLine,
  User,
  ExternalLink,
  HeartPulse
} from 'lucide-react';
import Link from 'next/link';
import {
  getPainPointLabel,
  getFeatureRequestLabel,
  getUrgentLabel,
  getPainPointColor,
  getFeatureRequestColor,
  getUrgentColor,
  getCategoryBadgeStyle,
  getResponseTimeLabel,
  getTagStyles
} from '@/lib/category-utils';
import { WorkflowSection } from '@/components/workflow/WorkflowSection';
import { FeedbackTimeline } from '@/components/workflow/FeedbackTimeline';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from '@/contexts/AuthContext';
import { ChurnFactorBreakdown } from '@/components/feedbacks/ChurnFactorBreakdown';
import { ConfidenceBadge } from '@/components/feedbacks/ConfidenceBadge';

export default function FeedbackDetailPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-muted-foreground font-medium">Loading feedback...</p>
        </div>
      </div>
    }>
      <FeedbackDetailContent />
    </Suspense>
  );
}

function FeedbackDetailContent() {
  const router = useRouter();
  const { user } = useAuth();
  const params = useParams();
  const searchParams = useSearchParams();
  const feedbackId = Number(params.id);

  const validTabs = ['overview', 'analysis', 'timeline'] as const;
  const tabParam = searchParams.get('tab');
  const initialTab = validTabs.includes(tabParam as any) ? tabParam! : 'overview';
  const [activeTab, setActiveTab] = useState(initialTab);

  // Sync tab to URL on mount (so ?tab=overview appears immediately)
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get('tab') !== activeTab) {
      url.searchParams.set('tab', activeTab);
      window.history.replaceState(null, '', url.toString());
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleTabChange = useCallback((value: string) => {
    setActiveTab(value);
    const url = new URL(window.location.href);
    url.searchParams.set('tab', value);
    window.history.replaceState(null, '', url.toString());
  }, []);

  const [feedback, setFeedback] = useState<FeedbackItem | null>(null);
  const [customerHealth, setCustomerHealth] = useState<CustomerHealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (feedbackId) {
      fetchFeedback();
    }
  }, [feedbackId]);

  // Fetch customer health when feedback has customer_email
  useEffect(() => {
    if (!feedback?.customer_email) {
      setCustomerHealth(null);
      return;
    }
    customerHealthAPI.getByEmail(feedback.customer_email)
      .then(setCustomerHealth)
      .catch(() => setCustomerHealth(null)); // 404 or 403 = silently skip
  }, [feedback?.customer_email]);

  const fetchFeedback = async () => {
    try {
      setLoading(true);
      const data = await feedbackAPI.get(feedbackId);
      setFeedback(data);
      analytics.feedbackViewed(data.id, data.sentiment_label || 'unknown');
    } catch (err: any) {
      if (err.response?.status === 401) {
        router.push('/login');
      } else if (err.response?.status === 404) {
        setError('Feedback not found');
      } else {
        setError('Failed to load feedback');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      const data = await feedbackAPI.get(feedbackId);
      setFeedback(data);
    } catch (err) {
      console.error('Refresh failed:', err);
    } finally {
      setRefreshing(false);
    }
  };

  const handleAnalyze = async () => {
    if (!feedback) return;
    try {
      setAnalyzing(true);
      await feedbackAPI.analyze([feedback.id], true);
    } catch (err) {
      console.error('Analysis failed:', err);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleDelete = async () => {
    if (!feedback || !confirm('Are you sure you want to delete this feedback?')) return;
    try {
      setDeleting(true);
      await feedbackAPI.delete(feedback.id);
      router.push('/feedbacks');
    } catch (err) {
      console.error('Delete failed:', err);
    } finally {
      setDeleting(false);
    }
  };


  const getPainPointIcon = (category: string) => {
    const iconMap: Record<string, React.ReactNode> = {
      'security_breach': <ShieldAlert className="w-4 h-4" />,
      'data_loss': <DatabaseZap className="w-4 h-4" />,
      'payment_issue': <CreditCard className="w-4 h-4" />,
      'system_crash': <ServerCrash className="w-4 h-4" />,
      'authentication': <KeyRound className="w-4 h-4" />,
      'functionality_broken': <CircleX className="w-4 h-4" />,
      'performance': <Gauge className="w-4 h-4" />,
      'usability': <MousePointerClick className="w-4 h-4" />,
      'compatibility': <Laptop className="w-4 h-4" />,
      'missing_feature': <PackageX className="w-4 h-4" />,
      'documentation': <FileQuestion className="w-4 h-4" />,
      'cosmetic': <Paintbrush className="w-4 h-4" />,
    };
    return iconMap[category] || <AlertTriangle className="w-4 h-4" />;
  };

  const getFeatureRequestIcon = (category: string) => {
    const iconMap: Record<string, React.ReactNode> = {
      'core_functionality': <Boxes className="w-4 h-4" />,
      'automation': <Workflow className="w-4 h-4" />,
      'integration': <Plug className="w-4 h-4" />,
      'reporting': <BarChart3 className="w-4 h-4" />,
      'customization': <Settings2 className="w-4 h-4" />,
      'collaboration': <Users className="w-4 h-4" />,
      'export_import': <ArrowUpDown className="w-4 h-4" />,
      'mobile': <Smartphone className="w-4 h-4" />,
      'notifications': <Bell className="w-4 h-4" />,
      'ui_enhancement': <Palette className="w-4 h-4" />,
    };
    return iconMap[category] || <Lightbulb className="w-4 h-4" />;
  };

  const getUrgentIcon = (category: string) => {
    const iconMap: Record<string, React.ReactNode> = {
      'service_outage': <ServerOff className="w-4 h-4" />,
      'data_breach': <ShieldOff className="w-4 h-4" />,
      'payment_failure': <CreditCard className="w-4 h-4" />,
      'data_corruption': <HardDrive className="w-4 h-4" />,
      'account_locked': <Lock className="w-4 h-4" />,
      'critical_bug': <Bug className="w-4 h-4" />,
      'billing_dispute': <Receipt className="w-4 h-4" />,
      'churn_risk': <UserMinus className="w-4 h-4" />,
      'compliance': <Scale className="w-4 h-4" />,
      'reputation_risk': <Megaphone className="w-4 h-4" />,
    };
    return iconMap[category] || <CircleAlert className="w-4 h-4" />;
  };

  const getSentimentIcon = (sentiment: string | null) => {
    switch (sentiment) {
      case 'positive':
        return <Smile className="w-5 h-5 text-[var(--chart-2)]" />;
      case 'negative':
        return <Frown className="w-5 h-5 text-destructive" />;
      default:
        return <Meh className="w-5 h-5 text-[var(--chart-3)]" />;
    }
  };

  const getSentimentColor = (sentiment: string | null) => {
    switch (sentiment) {
      case 'positive':
        return 'var(--chart-2)';
      case 'negative':
        return 'var(--destructive)';
      default:
        return 'var(--chart-3)';
    }
  };

  const getSourceIcon = (source: string | null) => {
    switch (source) {
      case 'slack':
        return <Hash className="w-4 h-4" />;
      case 'webhook':
        return <Webhook className="w-4 h-4" />;
      case 'csv_import':
        return <Upload className="w-4 h-4" />;
      case 'manual':
        return <PenLine className="w-4 h-4" />;
      default:
        return <Globe className="w-4 h-4" />;
    }
  };

  const getSourceLabel = (source: string | null) => {
    switch (source) {
      case 'slack':
        return 'Slack';
      case 'webhook':
        return 'Webhook';
      case 'csv_import':
        return 'CSV Import';
      case 'manual':
        return 'Manual Entry';
      default:
        return source || 'Unknown';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-muted-foreground font-medium">Loading feedback...</p>
        </div>
      </div>
    );
  }

  if (error || !feedback) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Card className="p-8 text-center">
            <AlertTriangle className="w-16 h-16 mx-auto mb-4 text-destructive opacity-50" />
            <h2 className="text-xl font-semibold mb-2">{error || 'Feedback not found'}</h2>
            <p className="text-muted-foreground mb-6">The feedback you're looking for doesn't exist or has been deleted.</p>
            <Button onClick={() => router.push('/feedbacks')} variant="outline">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Feedbacks
            </Button>
          </Card>
        </main>
      </div>
    );
  }

  const sentimentColor = getSentimentColor(feedback.sentiment_label);

  return (
    <div className="min-h-screen pattern-bg">
      <Tabs value={activeTab} onValueChange={handleTabChange}>
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Back button, tabs, and actions */}
        <div className="flex items-center justify-between animate-fade-in">
          <Button
            onClick={() => router.back()}
            variant="ghost"
            className="flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </Button>
          <div className="flex items-center gap-3">
            <TabsList className="h-8">
              <TabsTrigger value="overview" className="text-xs px-2 h-6">Overview</TabsTrigger>
              <TabsTrigger value="analysis" className="text-xs px-2 h-6">Analysis</TabsTrigger>
              <TabsTrigger value="timeline" className="text-xs px-2 h-6">Timeline</TabsTrigger>
            </TabsList>
            <Button
              onClick={handleRefresh}
              disabled={refreshing}
              variant="ghost"
              size="icon"
              className="h-8 w-8"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
            <Button
              onClick={handleAnalyze}
              disabled={analyzing}
              variant="outline"
              className="flex items-center gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${analyzing ? 'animate-spin' : ''}`} />
              {analyzing ? 'Analyzing...' : 'Re-analyze'}
            </Button>
            <Button
              onClick={handleDelete}
              disabled={deleting}
              variant="destructive"
              className="flex items-center gap-2"
            >
              <Trash2 className="w-4 h-4" />
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
          </div>
        </div>

        {/* Main feedback card */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div
                  className="p-3 rounded-xl"
                  style={{
                    backgroundColor: `${sentimentColor}15`,
                    borderColor: `${sentimentColor}30`
                  }}
                >
                  <MessageSquare className="w-6 h-6" style={{ color: sentimentColor }} />
                </div>
                <div>
                  <CardTitle className="flex items-center gap-2">
                    Feedback #{feedback.id}
                    {feedback.is_urgent && (
                      <Badge variant="destructive">URGENT</Badge>
                    )}
                  </CardTitle>
                  <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5" />
                      {new Date(feedback.created_at).toLocaleDateString()} at {new Date(feedback.created_at).toLocaleTimeString()}
                    </span>
                    {feedback.source && (
                      <span className="flex items-center gap-1">
                        {getSourceIcon(feedback.source)}
                        {getSourceLabel(feedback.source)}
                        {feedback.source_name && (
                          <span className="text-foreground font-medium">• {feedback.source_name}</span>
                        )}
                      </span>
                    )}
                  </div>
                  {customerHealth && (() => {
                    const score = customerHealth.health_score;
                    const getHealthColor = (s: number) => {
                      if (s >= 70) return 'var(--chart-2)';
                      if (s >= 50) return 'var(--chart-3)';
                      if (s >= 30) return 'var(--chart-1)';
                      return 'var(--destructive)';
                    };
                    const getRiskLabel = (level: string) => {
                      switch (level) {
                        case 'healthy': return 'Healthy';
                        case 'moderate': return 'Moderate';
                        case 'at_risk': return 'At Risk';
                        case 'critical': return 'Critical';
                        default: return level;
                      }
                    };
                    const healthColor = getHealthColor(score);
                    return (
                      <div className="flex items-center gap-2 mt-1.5">
                        <HeartPulse className="w-3.5 h-3.5" style={{ color: healthColor }} />
                        <Badge
                          variant="outline"
                          style={getCategoryBadgeStyle(healthColor)}
                        >
                          {score} · {getRiskLabel(customerHealth.risk_level)}
                        </Badge>
                        {user?.plan !== 'free' ? (
                          <Link
                            href={`/customers/${encodeURIComponent(feedback.customer_email!)}`}
                            className="text-xs text-primary hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {feedback.customer_email}
                          </Link>
                        ) : (
                          <span className="text-xs text-muted-foreground">{feedback.customer_email}</span>
                        )}
                      </div>
                    );
                  })()}
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <p className="text-lg leading-relaxed">{feedback.text}</p>
          </CardContent>
        </Card>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6 mt-6">
            <WorkflowSection
              feedbackId={feedback.id}
              workflowStatus={feedback.workflow_status}
              assignedTo={feedback.assigned_to}
              assignedToEmail={feedback.assigned_to_email}
              onStatusChange={(status) => setFeedback(prev => prev ? { ...prev, workflow_status: status } : null)}
              onAssigneeChange={(userId) => setFeedback(prev => prev ? { ...prev, assigned_to: userId } : null)}
              currentUserId={user?.id ?? 0}
            />
          </TabsContent>

          {/* Analysis Tab */}
          <TabsContent value="analysis" className="space-y-6 mt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Sentiment Analysis */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    {getSentimentIcon(feedback.sentiment_label)}
                    Sentiment Analysis
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {feedback.sentiment_label ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Sentiment</span>
                        <Badge
                          variant="outline"
                          className="capitalize transition-all"
                          style={getCategoryBadgeStyle(sentimentColor)}
                        >
                          {feedback.sentiment_label}
                        </Badge>
                      </div>
                      {feedback.sentiment_score !== null && (
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Score</span>
                          <span className="font-mono font-semibold" style={{ color: sentimentColor }}>
                            {feedback.sentiment_score.toFixed(3)}
                          </span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-muted-foreground italic text-sm">Not analyzed yet</p>
                  )}
                </CardContent>
              </Card>

              {/* Extracted Issue */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Brain className="w-5 h-5 text-[var(--chart-5)]" />
                    Extracted Issue
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {feedback.extracted_issue ? (
                    <p className="text-sm">{feedback.extracted_issue}</p>
                  ) : (
                    <p className="text-muted-foreground italic text-sm">No issue extracted</p>
                  )}
                </CardContent>
              </Card>

              {/* Tags */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Tag className="w-5 h-5 text-[var(--chart-7)]" />
                    Tags
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {feedback.tags && feedback.tags.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {feedback.tags.map((tag) => {
                        const tagStyle = getTagStyles(tag);
                        const badgeStyle = getCategoryBadgeStyle(tagStyle.color);
                        return (
                          <Link key={tag} href={`/categories/${tag}`}>
                            <Badge
                              variant="outline"
                              className="transition-all hover:scale-105 cursor-pointer"
                              style={badgeStyle}
                            >
                              {tagStyle.displayName}
                            </Badge>
                          </Link>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-muted-foreground italic text-sm">No tags</p>
                  )}
                </CardContent>
              </Card>

              {/* Confidence Score */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Gauge className="w-5 h-5 text-[var(--chart-4)]" />
                    Categorization Confidence
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {feedback.categorization_confidence !== null ? (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Confidence</span>
                        <span className="font-mono font-semibold text-[var(--chart-4)]">
                          {(feedback.categorization_confidence * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${feedback.categorization_confidence * 100}%`,
                            backgroundColor: 'var(--chart-4)'
                          }}
                        />
                      </div>
                    </div>
                  ) : (
                    <p className="text-muted-foreground italic text-sm">Not calculated</p>
                  )}
                </CardContent>
              </Card>

              {/* Churn Risk */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <UserMinus className="w-5 h-5 text-destructive" />
                    Churn Risk
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {feedback.churn_risk_score !== null && feedback.churn_risk_score !== undefined ? (
                    <div className="space-y-3">
                      {(() => {
                        const score = feedback.churn_risk_score!;
                        const getRiskLevel = (s: number) => {
                          if (s > 70) return { label: 'High', color: 'var(--destructive)' };
                          if (s >= 40) return { label: 'Medium', color: 'var(--chart-2)' };
                          return { label: 'Low', color: 'var(--chart-5)' };
                        };
                        const risk = getRiskLevel(score);
                        return (
                          <>
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Risk Level</span>
                              <Badge
                                variant="outline"
                                style={getCategoryBadgeStyle(risk.color)}
                              >
                                {risk.label}
                              </Badge>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Score</span>
                              <span className="font-mono font-semibold" style={{ color: risk.color }}>
                                {score}%
                              </span>
                            </div>
                            <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all"
                                style={{
                                  width: `${score}%`,
                                  backgroundColor: risk.color
                                }}
                              />
                            </div>
                            {feedback.customer_confidence_score !== null && feedback.customer_confidence_score !== undefined && (
                              <ConfidenceBadge
                                confidenceScore={feedback.customer_confidence_score}
                                feedbackCount={customerHealth?.feedback_count ?? 0}
                                lastFeedbackDaysAgo={
                                  customerHealth?.last_feedback_at
                                    ? Math.floor((Date.now() - new Date(customerHealth.last_feedback_at).getTime()) / 86400000)
                                    : 0
                                }
                                uniqueCategories={0}
                              />
                            )}
                          </>
                        );
                      })()}
                    </div>
                  ) : (
                    <p className="text-muted-foreground italic text-sm">Not calculated</p>
                  )}
                  <ChurnFactorBreakdown churnRiskFactors={feedback.churn_risk_factors ?? null} />
                </CardContent>
              </Card>

              {/* Pain Point Categorization */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-[var(--chart-1)]" />
                    Pain Point
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {feedback.pain_point_category ? (
                    <div className="space-y-3">
                      {(() => {
                        const color = getPainPointColor(feedback.pain_point_category);
                        return (
                          <>
                            <Badge
                              variant="outline"
                              className="flex items-center gap-1.5 w-fit transition-all"
                              style={getCategoryBadgeStyle(color)}
                            >
                              {getPainPointIcon(feedback.pain_point_category)}
                              {getPainPointLabel(feedback.pain_point_category)}
                            </Badge>
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-muted-foreground">Severity</span>
                              <span className="capitalize font-medium" style={{ color }}>
                                {feedback.pain_point_severity}
                              </span>
                            </div>
                            {feedback.pain_point_text && (
                              <div className="pt-2 border-t border-border">
                                <p className="text-sm text-muted-foreground">{feedback.pain_point_text}</p>
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  ) : (
                    <p className="text-muted-foreground italic text-sm">Not categorized as pain point</p>
                  )}
                </CardContent>
              </Card>

              {/* Feature Request Categorization */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Lightbulb className="w-5 h-5 text-[var(--chart-2)]" />
                    Feature Request
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {feedback.feature_request_category ? (
                    <div className="space-y-3">
                      {(() => {
                        const color = getFeatureRequestColor(feedback.feature_request_category);
                        return (
                          <>
                            <Badge
                              variant="outline"
                              className="flex items-center gap-1.5 w-fit transition-all"
                              style={getCategoryBadgeStyle(color)}
                            >
                              {getFeatureRequestIcon(feedback.feature_request_category)}
                              {getFeatureRequestLabel(feedback.feature_request_category)}
                            </Badge>
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-muted-foreground">Priority</span>
                              <span className="capitalize font-medium" style={{ color }}>
                                {feedback.feature_request_priority}
                              </span>
                            </div>
                            {feedback.feature_request_text && (
                              <div className="pt-2 border-t border-border">
                                <p className="text-sm text-muted-foreground">{feedback.feature_request_text}</p>
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  ) : (
                    <p className="text-muted-foreground italic text-sm">Not categorized as feature request</p>
                  )}
                </CardContent>
              </Card>

              {/* Urgent Categorization */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <CircleAlert className="w-5 h-5 text-destructive" />
                    Urgent Status
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {feedback.is_urgent && feedback.urgent_category ? (
                    <div className="space-y-3">
                      {(() => {
                        const color = getUrgentColor(feedback.urgent_category);
                        return (
                          <>
                            <Badge
                              variant="outline"
                              className="flex items-center gap-1.5 w-fit transition-all"
                              style={getCategoryBadgeStyle(color)}
                            >
                              {getUrgentIcon(feedback.urgent_category)}
                              {getUrgentLabel(feedback.urgent_category)}
                            </Badge>
                            {feedback.urgent_response_time && (
                              <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground flex items-center gap-1">
                                  <Clock className="w-3.5 h-3.5" />
                                  Response Time
                                </span>
                                <span className="font-medium" style={{ color }}>
                                  {getResponseTimeLabel(feedback.urgent_response_time)}
                                </span>
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  ) : feedback.is_urgent ? (
                    <div className="space-y-2">
                      <Badge variant="destructive">URGENT</Badge>
                      <p className="text-muted-foreground italic text-sm">Category not determined</p>
                    </div>
                  ) : (
                    <p className="text-muted-foreground italic text-sm">Not marked as urgent</p>
                  )}
                </CardContent>
              </Card>

              {/* Suggested Action */}
              {feedback.suggested_action && (
                <Card className="md:col-span-2">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Lightbulb className="w-5 h-5 text-[var(--chart-2)]" />
                      AI Suggested Action
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-relaxed">{feedback.suggested_action}</p>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Source Details */}
            {(feedback.source_metadata || feedback.source_name) && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    {getSourceIcon(feedback.source)}
                    Source Details
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                    {feedback.source_name && (
                      <div className="flex flex-col">
                        <span className="text-xs text-muted-foreground uppercase tracking-wide">Source Name</span>
                        <span className="font-medium">{feedback.source_name}</span>
                      </div>
                    )}
                    {feedback.source_metadata?.channel_name && (
                      <div className="flex flex-col">
                        <span className="text-xs text-muted-foreground uppercase tracking-wide">Channel</span>
                        <span className="font-medium flex items-center gap-1">
                          <Hash className="w-3.5 h-3.5" />
                          {feedback.source_metadata.channel_name}
                        </span>
                      </div>
                    )}
                    {feedback.source_metadata?.author_name && (
                      <div className="flex flex-col">
                        <span className="text-xs text-muted-foreground uppercase tracking-wide">Author</span>
                        <span className="font-medium flex items-center gap-1">
                          <User className="w-3.5 h-3.5" />
                          {feedback.source_metadata.author_name}
                        </span>
                      </div>
                    )}
                    {feedback.source_metadata?.url && (
                      <div className="flex flex-col sm:col-span-2">
                        <span className="text-xs text-muted-foreground uppercase tracking-wide">Original Link</span>
                        <a
                          href={feedback.source_metadata.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-primary hover:underline flex items-center gap-1"
                        >
                          View in {getSourceLabel(feedback.source)}
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* Timeline Tab */}
          <TabsContent value="timeline" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Activity Log</CardTitle>
              </CardHeader>
              <CardContent>
                <FeedbackTimeline feedbackId={feedback.id} />
              </CardContent>
            </Card>
          </TabsContent>
      </main>
      </Tabs>
    </div>
  );
}
