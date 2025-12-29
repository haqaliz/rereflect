'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { feedbackAPI, FeedbackItem } from '@/lib/api/feedback';
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
  Megaphone
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

export default function FeedbackDetailPage() {
  const router = useRouter();
  const params = useParams();
  const feedbackId = Number(params.id);

  const [feedback, setFeedback] = useState<FeedbackItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (feedbackId) {
      fetchFeedback();
    }
  }, [feedbackId]);

  const fetchFeedback = async () => {
    try {
      setLoading(true);
      const data = await feedbackAPI.get(feedbackId);
      setFeedback(data);
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

  const handleAnalyze = async () => {
    if (!feedback) return;
    try {
      setAnalyzing(true);
      await feedbackAPI.analyze([feedback.id]);
      await fetchFeedback();
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
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Back button and actions */}
        <div className="flex items-center justify-between animate-fade-in">
          <Button
            onClick={() => router.back()}
            variant="ghost"
            className="flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </Button>
          <div className="flex items-center gap-2">
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
                        <Globe className="w-3.5 h-3.5" />
                        {feedback.source}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <p className="text-lg leading-relaxed">{feedback.text}</p>
          </CardContent>
        </Card>

        {/* Analysis Results Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Sentiment Analysis */}
          <Card className="animate-slide-up stagger-1">
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
          <Card className="animate-slide-up stagger-2">
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
          <Card className="animate-slide-up stagger-3">
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
          <Card className="animate-slide-up stagger-4">
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
        </div>

        {/* Categorization Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Pain Point Categorization */}
          <Card className="animate-slide-up stagger-5">
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
          <Card className="animate-slide-up stagger-6">
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
          <Card className="animate-slide-up stagger-7">
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
        </div>
      </main>
    </div>
  );
}
