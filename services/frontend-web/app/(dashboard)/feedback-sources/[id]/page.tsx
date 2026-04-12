'use client';

import { useState, useEffect, Suspense, use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  feedbackSourcesAPI,
  FeedbackSource,
  FeedbackSourceEvent,
  TRIGGER_OPTIONS,
  UpdateFeedbackSourceRequest,
} from '@/lib/api/feedback-sources';
import {
  Webhook,
  MessageCircle,
  Mail,
  ArrowLeft,
  Loader2,
  Save,
  Clock,
  Activity,
  AlertCircle,
  CheckCircle,
  XCircle,
  Copy,
  Check,
  Trash2,
  RefreshCw,
  Info,
} from 'lucide-react';
import { SlackIcon } from '@/components/icons/SlackIcon';
import { IntercomIcon } from '@/components/icons/IntercomIcon';
import { LinearIcon } from '@/components/icons/LinearIcon';

// Source type icon mapping
const SOURCE_ICONS: Record<string, React.ElementType> = {
  slack: SlackIcon,
  intercom: IntercomIcon,
  webhook: Webhook,
  discord: MessageCircle,
  email: Mail,
  linear: LinearIcon,
};

// Source type colors
const SOURCE_COLORS: Record<string, string> = {
  slack: 'text-[#4A154B]',
  intercom: 'text-[#1F8DED]',
  webhook: 'text-blue-600',
  discord: 'text-[#5865F2]',
  email: 'text-amber-600',
  linear: 'text-[#5E6AD2]',
};

function SourceDetailContent({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const resolvedParams = use(params);
  const sourceId = parseInt(resolvedParams.id);

  const [source, setSource] = useState<FeedbackSource | null>(null);
  const [events, setEvents] = useState<FeedbackSourceEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);
  const [confirmMessage, setConfirmMessage] = useState('');

  const requestConfirm = (message: string, action: () => void) => {
    setConfirmMessage(message);
    setConfirmAction(() => action);
  };

  // Form state
  const [form, setForm] = useState<{
    name: string;
    triggers: any;
    field_mapping: any;
    auto_import: boolean;
    is_active: boolean;
  }>({
    name: '',
    triggers: {},
    field_mapping: {},
    auto_import: true,
    is_active: true,
  });

  // Trigger value inputs
  const [reactionInput, setReactionInput] = useState('');
  const [keywordInput, setKeywordInput] = useState('');

  useEffect(() => {
    fetchSource();
  }, [sourceId]);

  const fetchSource = async () => {
    try {
      setLoading(true);
      const [sourceData, eventsData] = await Promise.all([
        feedbackSourcesAPI.get(sourceId),
        feedbackSourcesAPI.getEvents(sourceId, 1, 10),
      ]);
      setSource(sourceData);
      setEvents(eventsData);
      setForm({
        name: sourceData.name || '',
        triggers: { ...sourceData.triggers },
        field_mapping: { ...sourceData.field_mapping },
        auto_import: sourceData.auto_import,
        is_active: sourceData.is_active,
      });
    } catch (err) {
      console.error('Failed to load source:', err);
      setError('Failed to load feedback source');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);

      const updates: UpdateFeedbackSourceRequest = {
        name: form.name || undefined,
        triggers: form.triggers,
        field_mapping: form.field_mapping,
        auto_import: form.auto_import,
        is_active: form.is_active,
      };

      await feedbackSourcesAPI.update(sourceId, updates);
      setSuccess('Settings saved successfully');
      await fetchSource();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = () => {
    requestConfirm(
      'Delete this feedback source? This cannot be undone.',
      async () => {
        try {
          await feedbackSourcesAPI.delete(sourceId);
          router.push('/feedback-sources');
        } catch (err: any) {
          setError(err.response?.data?.detail || 'Failed to delete source');
        }
      }
    );
  };

  const copyWebhookUrl = () => {
    if (source?.webhook_url) {
      navigator.clipboard.writeText(source.webhook_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const copyInboundAddress = () => {
    const address = source?.provider_config?.inbound_address;
    if (address) {
      navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const toggleTrigger = (key: string) => {
    setForm(prev => {
      const triggers = { ...prev.triggers };
      if (key === 'all_messages') {
        triggers.all_messages = !triggers.all_messages;
      } else if (key === 'mentions.bot') {
        triggers.mentions = {
          ...triggers.mentions,
          bot: !triggers.mentions?.bot,
        };
      }
      return { ...prev, triggers };
    });
  };

  const addReaction = () => {
    if (!reactionInput.trim()) return;
    const emoji = reactionInput.trim().replace(/:/g, '');
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        reactions: [...(prev.triggers.reactions || []), emoji],
      },
    }));
    setReactionInput('');
  };

  const removeReaction = (emoji: string) => {
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        reactions: (prev.triggers.reactions || []).filter((r: string) => r !== emoji),
      },
    }));
  };

  const addKeyword = () => {
    if (!keywordInput.trim()) return;
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        keywords: [...(prev.triggers.keywords || []), keywordInput.trim()],
      },
    }));
    setKeywordInput('');
  };

  const removeKeyword = (keyword: string) => {
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        keywords: (prev.triggers.keywords || []).filter((k: string) => k !== keyword),
      },
    }));
  };

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const getEventStatusIcon = (status: string) => {
    switch (status) {
      case 'processed':
        return <CheckCircle className="w-4 h-4 text-green-600" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-destructive" />;
      case 'ignored':
        return <XCircle className="w-4 h-4 text-muted-foreground" />;
      default:
        return <Clock className="w-4 h-4 text-amber-600" />;
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    );
  }

  if (!source) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-16">
            <AlertCircle className="w-16 h-16 mx-auto text-muted-foreground/50 mb-4" />
            <h2 className="text-xl font-semibold">Source not found</h2>
            <Link href="/feedback-sources">
              <Button className="mt-4">Back to Sources</Button>
            </Link>
          </div>
        </main>
      </div>
    );
  }

  const Icon = SOURCE_ICONS[source.source_type] || Webhook;
  const iconColor = SOURCE_COLORS[source.source_type] || 'text-muted-foreground';

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="animate-fade-in">
          <Link
            href="/feedback-sources"
            className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4"
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back to Feedback Sources
          </Link>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <Icon className={`w-8 h-8 ${iconColor}`} />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-foreground">
                  {source.name || `${source.source_type.charAt(0).toUpperCase() + source.source_type.slice(1)} Source`}
                </h1>
                <div className="flex items-center gap-2 mt-1">
                  {source.is_active ? (
                    <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950">
                      Active
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      Paused
                    </Badge>
                  )}
                  <Badge variant="secondary" className="capitalize">{source.source_type}</Badge>
                </div>
              </div>
            </div>
            <Button
              variant="outline"
              onClick={handleDelete}
              className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete
            </Button>
          </div>
        </div>

        {/* Success/Error messages */}
        {success && (
          <div className="p-4 bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300 rounded-lg flex items-center gap-2">
            <CheckCircle className="w-5 h-5" />
            {success}
          </div>
        )}
        {error && (
          <div className="p-4 bg-destructive/10 text-destructive rounded-lg flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            {error}
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 animate-slide-up">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-muted-foreground" />
                <div>
                  <div className="text-2xl font-bold">{source.events_processed}</div>
                  <div className="text-sm text-muted-foreground">Events Processed</div>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2">
                <Clock className="w-5 h-5 text-muted-foreground" />
                <div>
                  <div className="text-lg font-semibold truncate">
                    {source.last_event_at
                      ? new Date(source.last_event_at).toLocaleDateString()
                      : 'Never'}
                  </div>
                  <div className="text-sm text-muted-foreground">Last Event</div>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2">
                <AlertCircle className={`w-5 h-5 ${source.error_count > 0 ? 'text-destructive' : 'text-muted-foreground'}`} />
                <div>
                  <div className="text-2xl font-bold">{source.error_count}</div>
                  <div className="text-sm text-muted-foreground">Errors</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Webhook URL (for webhook sources) */}
        {source.source_type === 'webhook' && source.webhook_url && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle>Webhook URL</CardTitle>
              <CardDescription>Send POST requests to this URL to create feedback</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={source.webhook_url}
                  className="font-mono text-sm"
                />
                <Button variant="outline" onClick={copyWebhookUrl}>
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>

              {/* Example code snippets */}
              <div className="pt-2">
                <p className="text-sm font-medium text-muted-foreground mb-3">Example requests:</p>
                <Tabs defaultValue="curl" className="w-full">
                  <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="curl">cURL</TabsTrigger>
                    <TabsTrigger value="nodejs">Node.js</TabsTrigger>
                    <TabsTrigger value="python">Python</TabsTrigger>
                  </TabsList>
                  <TabsContent value="curl">
                    <SyntaxHighlighter
                      language="bash"
                      style={oneDark}
                      customStyle={{ borderRadius: '0.5rem', fontSize: '0.75rem', margin: 0 }}
                    >
{`curl -X POST "${source.webhook_url}" \\
  -H "Content-Type: application/json" \\
  -d '{"text": "Your feedback message here"}'`}
                    </SyntaxHighlighter>
                  </TabsContent>
                  <TabsContent value="nodejs">
                    <SyntaxHighlighter
                      language="javascript"
                      style={oneDark}
                      customStyle={{ borderRadius: '0.5rem', fontSize: '0.75rem', margin: 0 }}
                    >
{`fetch("${source.webhook_url}", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text: "Your feedback message here" })
});`}
                    </SyntaxHighlighter>
                  </TabsContent>
                  <TabsContent value="python">
                    <SyntaxHighlighter
                      language="python"
                      style={oneDark}
                      customStyle={{ borderRadius: '0.5rem', fontSize: '0.75rem', margin: 0 }}
                    >
{`import requests

requests.post(
    "${source.webhook_url}",
    json={"text": "Your feedback message here"}
)`}
                    </SyntaxHighlighter>
                  </TabsContent>
                </Tabs>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Email Inbound Address (for email sources) */}
        {source.source_type === 'email' && source.provider_config?.inbound_address && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle>Forwarding Address</CardTitle>
              <CardDescription>Forward emails to this address to create feedback items</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={source.provider_config.inbound_address}
                  className="font-mono text-sm"
                />
                <Button variant="outline" onClick={copyInboundAddress}>
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>

              <div className="p-4 bg-muted/50 rounded-lg space-y-3">
                <h4 className="font-semibold text-foreground text-sm">Setup instructions</h4>
                <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                  <li>Open your email client (Gmail, Outlook, etc.)</li>
                  <li>Create a forwarding rule for your support inbox</li>
                  <li>Set the destination to the address above</li>
                  <li>Emails forwarded will appear as feedback items</li>
                </ol>
              </div>

              <div className="p-3 bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 rounded-lg flex items-start gap-2 text-sm">
                <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>
                  Only the email body content is captured. Sender information is not stored for privacy.
                </span>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Settings */}
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="name">Source Name</Label>
              <Input
                id="name"
                value={form.name}
                onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="Enter a name for this source"
              />
            </div>

            {/* Active toggle */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Active</Label>
                <p className="text-xs text-muted-foreground">Receive events from this source</p>
              </div>
              <Switch
                checked={form.is_active}
                onCheckedChange={checked => setForm(prev => ({ ...prev, is_active: checked }))}
              />
            </div>

            {/* Auto-import toggle */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Auto-import</Label>
                <p className="text-xs text-muted-foreground">
                  {form.auto_import
                    ? 'Feedback is created automatically'
                    : 'Feedback goes to pending queue for review'}
                </p>
              </div>
              <Switch
                checked={form.auto_import}
                onCheckedChange={checked => setForm(prev => ({ ...prev, auto_import: checked }))}
              />
            </div>
          </CardContent>
        </Card>

        {/* Triggers */}
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>Triggers</CardTitle>
            <CardDescription>Configure when messages should be captured</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {TRIGGER_OPTIONS[source.source_type]?.map(trigger => {
              const isEnabled = trigger.key === 'all_messages'
                ? form.triggers.all_messages
                : trigger.key === 'mentions.bot'
                ? form.triggers.mentions?.bot
                : false;

              return (
                <div key={trigger.key} className="space-y-2">
                  <div className="flex items-start space-x-3">
                    {!trigger.hasValues && (
                      <Checkbox
                        id={`trigger-${trigger.key}`}
                        checked={isEnabled}
                        onCheckedChange={() => toggleTrigger(trigger.key)}
                      />
                    )}
                    <div className="flex-1">
                      <Label
                        htmlFor={`trigger-${trigger.key}`}
                        className={`font-medium ${trigger.hasValues ? '' : 'cursor-pointer'}`}
                      >
                        {trigger.label}
                      </Label>
                      <p className="text-xs text-muted-foreground">{trigger.description}</p>

                      {/* Reactions input */}
                      {trigger.key === 'reactions' && (
                        <div className="mt-2 space-y-2">
                          <div className="flex gap-2">
                            <Input
                              placeholder="e.g., memo, feedback"
                              value={reactionInput}
                              onChange={e => setReactionInput(e.target.value)}
                              onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addReaction())}
                              className="flex-1"
                            />
                            <Button type="button" onClick={addReaction} size="sm">
                              Add
                            </Button>
                          </div>
                          {form.triggers.reactions?.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                              {form.triggers.reactions.map((emoji: string) => (
                                <Badge
                                  key={emoji}
                                  variant="secondary"
                                  className="cursor-pointer"
                                  onClick={() => removeReaction(emoji)}
                                >
                                  :{emoji}: ×
                                </Badge>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Keywords input */}
                      {trigger.key === 'keywords' && (
                        <div className="mt-2 space-y-2">
                          <div className="flex gap-2">
                            <Input
                              placeholder="e.g., bug, feedback"
                              value={keywordInput}
                              onChange={e => setKeywordInput(e.target.value)}
                              onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addKeyword())}
                              className="flex-1"
                            />
                            <Button type="button" onClick={addKeyword} size="sm">
                              Add
                            </Button>
                          </div>
                          {form.triggers.keywords?.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                              {form.triggers.keywords.map((keyword: string) => (
                                <Badge
                                  key={keyword}
                                  variant="secondary"
                                  className="cursor-pointer"
                                  onClick={() => removeKeyword(keyword)}
                                >
                                  {keyword} ×
                                </Badge>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        {/* Field Mapping */}
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>Field Mapping</CardTitle>
            <CardDescription>Configure how messages are converted to feedback</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Text Source</Label>
              <Select
                value={form.field_mapping.text_source || 'message'}
                onValueChange={value =>
                  setForm(prev => ({
                    ...prev,
                    field_mapping: { ...prev.field_mapping, text_source: value },
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="message">Message only</SelectItem>
                  <SelectItem value="thread">Message + thread context</SelectItem>
                  <SelectItem value="full">Full thread</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center justify-between">
              <Label>Include Author Info</Label>
              <Switch
                checked={form.field_mapping.include_author ?? true}
                onCheckedChange={checked =>
                  setForm(prev => ({
                    ...prev,
                    field_mapping: { ...prev.field_mapping, include_author: checked },
                  }))
                }
              />
            </div>

            <div className="flex items-center justify-between">
              <Label>Include Source Name</Label>
              <Switch
                checked={form.field_mapping.include_source_name ?? true}
                onCheckedChange={checked =>
                  setForm(prev => ({
                    ...prev,
                    field_mapping: { ...prev.field_mapping, include_source_name: checked },
                  }))
                }
              />
            </div>
          </CardContent>
        </Card>

        {/* Recent Events */}
        <Card className="animate-slide-up">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Recent Events</CardTitle>
              <CardDescription>Last 10 events received</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={fetchSource}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </Button>
          </CardHeader>
          <CardContent>
            {events.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No events received yet
              </div>
            ) : (
              <div className="space-y-2">
                {events.map(event => (
                  <div
                    key={event.id}
                    className="flex items-center justify-between p-3 bg-muted/30 rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      {getEventStatusIcon(event.status)}
                      <div>
                        <div className="text-sm font-medium">
                          {event.event_type}
                          {event.trigger_matched && (
                            <Badge variant="secondary" className="ml-2 text-xs">
                              {event.trigger_matched}
                            </Badge>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {formatTime(event.received_at)}
                        </div>
                      </div>
                    </div>
                    <Badge
                      variant={
                        event.status === 'processed'
                          ? 'default'
                          : event.status === 'failed'
                          ? 'destructive'
                          : 'secondary'
                      }
                      className={event.status === 'processed' ? 'bg-green-600' : ''}
                    >
                      {event.status}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

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

        {/* Save Button */}
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Save className="w-4 h-4 mr-2" />
            )}
            Save Changes
          </Button>
        </div>
      </main>
    </div>
  );
}

export default function SourceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={
      <div className="min-h-screen pattern-bg">
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    }>
      <SourceDetailContent params={params} />
    </Suspense>
  );
}
