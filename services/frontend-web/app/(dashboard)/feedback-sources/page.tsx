'use client';

import { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  feedbackSourcesAPI,
  FeedbackSource,
  SourceTypeInfo,
} from '@/lib/api/feedback-sources';
import {
  Slack,
  Webhook,
  MessageCircle,
  MessageSquare,
  Mail,
  Plus,
  Trash2,
  Settings2,
  Clock,
  ArrowLeft,
  ChevronRight,
  Loader2,
  AlertCircle,
  CheckCircle,
  Inbox,
  Activity,
  Pause,
  Play,
} from 'lucide-react';

// Source type icon mapping
const SOURCE_ICONS: Record<string, React.ElementType> = {
  slack: Slack,
  intercom: MessageSquare,
  webhook: Webhook,
  discord: MessageCircle,
  email: Mail,
};

// Source type colors
const SOURCE_COLORS: Record<string, string> = {
  slack: 'text-[#4A154B]',
  intercom: 'text-[#1F8DED]',
  webhook: 'text-blue-600',
  discord: 'text-[#5865F2]',
  email: 'text-amber-600',
};

function FeedbackSourcesContent() {
  const [sources, setSources] = useState<FeedbackSource[]>([]);
  const [sourceTypes, setSourceTypes] = useState<SourceTypeInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [sourcesResponse, typesResponse] = await Promise.all([
        feedbackSourcesAPI.list(),
        feedbackSourcesAPI.getTypes(),
      ]);
      setSources(sourcesResponse.sources);
      setSourceTypes(typesResponse);
    } catch (err) {
      console.error('Failed to load feedback sources:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (source: FeedbackSource) => {
    const name = source.name || `${source.source_type} source`;
    if (!confirm(`Delete "${name}"? This will stop receiving feedback from this source and cannot be undone.`)) return;

    try {
      setDeletingId(source.id);
      await feedbackSourcesAPI.delete(source.id);
      await fetchData();
    } catch (err) {
      console.error('Failed to delete source:', err);
    } finally {
      setDeletingId(null);
    }
  };

  const handleToggleActive = async (source: FeedbackSource) => {
    try {
      setTogglingId(source.id);
      await feedbackSourcesAPI.update(source.id, { is_active: !source.is_active });
      await fetchData();
    } catch (err) {
      console.error('Failed to toggle source:', err);
    } finally {
      setTogglingId(null);
    }
  };

  const getSourceIcon = (sourceType: string) => {
    return SOURCE_ICONS[sourceType] || Webhook;
  };

  const formatLastEvent = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="animate-fade-in">
          <Link
            href="/feedbacks"
            className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4"
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back to Feedbacks
          </Link>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <Inbox className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-foreground">Feedback Sources</h1>
                <p className="text-muted-foreground">Receive feedback from Slack, webhooks, and other sources</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Link href="/feedback-sources/pending">
                <Button variant="outline" className="flex items-center gap-2">
                  <Inbox className="w-4 h-4" />
                  Pending Queue
                </Button>
              </Link>
              <Link href="/feedback-sources/new">
                <Button className="flex items-center gap-2">
                  <Plus className="w-4 h-4" />
                  Add Source
                </Button>
              </Link>
            </div>
          </div>
        </div>

        {/* Sources List */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center justify-between">
              <span>Active Sources</span>
              <Badge variant="secondary">{sources.length} source{sources.length !== 1 ? 's' : ''}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            {sources.length === 0 ? (
              <div className="text-center py-12">
                <Inbox className="w-16 h-16 mx-auto text-muted-foreground/50 mb-4" />
                <h3 className="text-lg font-semibold text-foreground mb-2">No feedback sources yet</h3>
                <p className="text-muted-foreground mb-6">
                  Connect a source to start receiving feedback automatically
                </p>
                <Link href="/feedback-sources/new">
                  <Button>
                    <Plus className="w-4 h-4 mr-2" />
                    Add Your First Source
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="space-y-4">
                {sources.map(source => {
                  const Icon = getSourceIcon(source.source_type);
                  const iconColor = SOURCE_COLORS[source.source_type] || 'text-muted-foreground';

                  return (
                    <div
                      key={source.id}
                      className="p-4 border border-border rounded-xl bg-card/50 hover:bg-card/80 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <Link
                          href={`/feedback-sources/${source.id}`}
                          className="flex items-center gap-3 flex-1 group"
                        >
                          <div className="p-2 bg-secondary rounded-lg">
                            <Icon className={`w-6 h-6 ${iconColor}`} />
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-foreground group-hover:text-primary transition-colors">
                                {source.name || `${source.source_type.charAt(0).toUpperCase() + source.source_type.slice(1)} Source`}
                              </span>
                              {source.is_active ? (
                                <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950">
                                  Active
                                </Badge>
                              ) : (
                                <Badge variant="outline" className="text-muted-foreground">
                                  Paused
                                </Badge>
                              )}
                              <Badge variant="secondary" className="text-xs capitalize">
                                {source.source_type}
                              </Badge>
                              {source.auto_import ? (
                                <Badge variant="secondary" className="text-xs">
                                  Auto-import
                                </Badge>
                              ) : (
                                <Badge variant="outline" className="text-xs text-amber-600 border-amber-600/30">
                                  Review mode
                                </Badge>
                              )}
                              <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                            </div>

                            {/* Source-specific info */}
                            <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
                              {source.source_type === 'slack' && source.provider_config?.channel_name && (
                                <span>#{source.provider_config.channel_name}</span>
                              )}
                              {source.source_type === 'intercom' && source.provider_config?.workspace_name && (
                                <span>{source.provider_config.workspace_name}</span>
                              )}
                              {source.source_type === 'webhook' && source.webhook_url && (
                                <span className="font-mono text-xs truncate max-w-[300px]">
                                  {source.webhook_url}
                                </span>
                              )}
                            </div>

                            {/* Trigger summary */}
                            <div className="flex flex-wrap gap-1.5 mt-2">
                              {source.triggers.all_messages && (
                                <Badge variant="secondary" className="text-xs">All messages</Badge>
                              )}
                              {source.triggers.mentions?.bot && (
                                <Badge variant="secondary" className="text-xs">Bot mentions</Badge>
                              )}
                              {source.triggers.reactions && source.triggers.reactions.length > 0 && (
                                <Badge variant="secondary" className="text-xs">
                                  Reactions: {source.triggers.reactions.slice(0, 3).join(', ')}
                                  {source.triggers.reactions.length > 3 && ` +${source.triggers.reactions.length - 3}`}
                                </Badge>
                              )}
                              {source.triggers.keywords && source.triggers.keywords.length > 0 && (
                                <Badge variant="secondary" className="text-xs">
                                  Keywords: {source.triggers.keywords.slice(0, 2).join(', ')}
                                  {source.triggers.keywords.length > 2 && ` +${source.triggers.keywords.length - 2}`}
                                </Badge>
                              )}
                            </div>
                          </div>
                        </Link>

                        <div className="flex items-center gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.preventDefault();
                              handleToggleActive(source);
                            }}
                            disabled={togglingId === source.id}
                            title={source.is_active ? 'Pause source' : 'Activate source'}
                          >
                            {togglingId === source.id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : source.is_active ? (
                              <Pause className="w-4 h-4" />
                            ) : (
                              <Play className="w-4 h-4" />
                            )}
                          </Button>
                          <Link href={`/feedback-sources/${source.id}`}>
                            <Button variant="outline" size="sm" title="Configure">
                              <Settings2 className="w-4 h-4" />
                            </Button>
                          </Link>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.preventDefault();
                              handleDelete(source);
                            }}
                            disabled={deletingId === source.id}
                            className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                            title="Delete"
                          >
                            {deletingId === source.id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </Button>
                        </div>
                      </div>

                      {/* Stats row */}
                      <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground ml-11">
                        <span className="flex items-center gap-1">
                          <Activity className="w-3 h-3" />
                          {source.events_processed} processed
                        </span>
                        {source.last_event_at && (
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            Last event: {formatLastEvent(source.last_event_at)}
                          </span>
                        )}
                        {source.error_count > 0 && (
                          <span className="flex items-center gap-1 text-destructive">
                            <AlertCircle className="w-3 h-3" />
                            {source.error_count} error{source.error_count !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>

                      {/* Last error display */}
                      {source.last_error && (
                        <div className="mt-3 p-3 rounded-lg bg-destructive/10 text-destructive text-sm flex items-center gap-2 ml-11">
                          <AlertCircle className="w-4 h-4 flex-shrink-0" />
                          <span className="truncate">{source.last_error}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Available Source Types */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border">
            <CardTitle>Available Source Types</CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {sourceTypes.map(type => {
                const Icon = SOURCE_ICONS[type.type] || Webhook;
                const iconColor = SOURCE_COLORS[type.type] || 'text-muted-foreground';

                return (
                  <div
                    key={type.type}
                    className={`p-4 border border-border rounded-xl ${
                      type.available
                        ? 'bg-card/50 hover:bg-card/80 cursor-pointer'
                        : 'bg-muted/30 opacity-60'
                    } transition-colors`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="p-2 bg-secondary rounded-lg">
                        <Icon className={`w-6 h-6 ${iconColor}`} />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground">{type.name}</span>
                          {!type.available && (
                            <Badge variant="outline" className="text-xs">Coming Soon</Badge>
                          )}
                          {type.requires_integration && type.available && (
                            <Badge variant="secondary" className="text-xs">Requires OAuth</Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">{type.description}</p>
                      </div>
                      {type.available && (
                        <Link href={`/feedback-sources/new?type=${type.type}`}>
                          <Button size="sm" variant="outline">
                            <Plus className="w-4 h-4" />
                          </Button>
                        </Link>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

export default function FeedbackSourcesPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen pattern-bg">
        <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    }>
      <FeedbackSourcesContent />
    </Suspense>
  );
}
