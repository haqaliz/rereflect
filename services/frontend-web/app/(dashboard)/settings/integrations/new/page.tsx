'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  integrationsAPI,
  TRIGGER_OPTIONS,
  TemplateVariable,
} from '@/lib/api/integrations';
import {
  Slack,
  ArrowLeft,
  Loader2,
  AlertCircle,
  Info,
  Check,
  Link as LinkIcon,
  Webhook,
  HelpCircle,
} from 'lucide-react';

type ConnectionMethod = 'oauth' | 'webhook';

export default function NewIntegrationPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [templateVariables, setTemplateVariables] = useState<TemplateVariable[]>([]);
  const [defaultTemplate, setDefaultTemplate] = useState('');
  const [copiedVar, setCopiedVar] = useState<string | null>(null);
  const [connectionMethod, setConnectionMethod] = useState<ConnectionMethod>('oauth');
  const [oauthLoading, setOauthLoading] = useState(false);

  const [form, setForm] = useState({
    name: '',
    webhook_url: '',
    triggers: ['urgent'] as string[],
    digest_time: '09:00',
    message_template: '',
  });

  useEffect(() => {
    const loadTemplateVariables = async () => {
      try {
        const data = await integrationsAPI.getTemplateVariables();
        setTemplateVariables(data.variables);
        setDefaultTemplate(data.default_template);
        setForm(prev => ({ ...prev, message_template: data.default_template }));
      } catch (err) {
        console.error('Failed to load template variables:', err);
      }
    };
    loadTemplateVariables();
  }, []);

  const handleOAuthConnect = async () => {
    if (!form.name) {
      setError('Please enter an integration name first');
      return;
    }

    setError(null);
    setOauthLoading(true);

    try {
      const data = await integrationsAPI.getSlackOAuthUrl(form.name);
      // Redirect to Slack OAuth
      window.location.href = data.auth_url;
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to initiate OAuth. Make sure SLACK_CLIENT_ID is configured.');
      setOauthLoading(false);
    }
  };

  const handleWebhookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await integrationsAPI.createSlackWebhook({
        name: form.name,
        webhook_url: form.webhook_url,
        triggers: form.triggers,
        digest_time: form.digest_time,
        message_template: form.message_template || undefined,
      });
      router.push('/settings/integrations');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create integration');
    } finally {
      setLoading(false);
    }
  };

  const toggleTrigger = (trigger: string) => {
    setForm(prev => ({
      ...prev,
      triggers: prev.triggers.includes(trigger)
        ? prev.triggers.filter(t => t !== trigger)
        : [...prev.triggers, trigger],
    }));
  };

  const insertVariable = (varName: string) => {
    const textarea = document.getElementById('message_template') as HTMLTextAreaElement;
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const text = form.message_template;
      const variable = `{{${varName}}}`;
      const newText = text.substring(0, start) + variable + text.substring(end);
      setForm(prev => ({ ...prev, message_template: newText }));
      setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(start + variable.length, start + variable.length);
      }, 0);
    }
  };

  const needsDigestTime = form.triggers.includes('daily_digest') || form.triggers.includes('weekly_digest');

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="animate-fade-in">
          <Link
            href="/settings/integrations"
            className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4"
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back to Integrations
          </Link>
          <div className="flex items-center space-x-3">
            <div className="p-3 bg-secondary rounded-xl">
              <Slack className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-foreground">New Slack Integration</h1>
              <p className="text-muted-foreground">Connect Rereflect to a Slack channel</p>
            </div>
          </div>
        </div>

        {/* Integration Name (always shown) */}
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>Integration Name</CardTitle>
            <CardDescription>Give your integration a descriptive name</CardDescription>
          </CardHeader>
          <CardContent>
            <Input
              id="name"
              placeholder="e.g., #feedback-alerts, Product Team Channel"
              value={form.name}
              onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
              required
            />
          </CardContent>
        </Card>

        {/* Connection Method Selection */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader>
            <CardTitle>Connection Method</CardTitle>
            <CardDescription>Choose how to connect to Slack</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* OAuth Option */}
              <button
                type="button"
                onClick={() => setConnectionMethod('oauth')}
                className={`p-4 rounded-lg border-2 text-left transition-all ${
                  connectionMethod === 'oauth'
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:border-primary/50'
                }`}
              >
                <div className="flex items-center gap-3 mb-2">
                  <div className={`p-2 rounded-lg ${connectionMethod === 'oauth' ? 'bg-primary/10' : 'bg-secondary'}`}>
                    <LinkIcon className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="font-semibold">Connect with Slack</h4>
                    <span className="text-xs text-green-600 dark:text-green-400">Recommended</span>
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">
                  One-click connection via Slack OAuth. No manual setup required.
                </p>
              </button>

              {/* Webhook Option */}
              <button
                type="button"
                onClick={() => setConnectionMethod('webhook')}
                className={`p-4 rounded-lg border-2 text-left transition-all ${
                  connectionMethod === 'webhook'
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:border-primary/50'
                }`}
              >
                <div className="flex items-center gap-3 mb-2">
                  <div className={`p-2 rounded-lg ${connectionMethod === 'webhook' ? 'bg-primary/10' : 'bg-secondary'}`}>
                    <Webhook className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="font-semibold">Webhook URL</h4>
                    <span className="text-xs text-muted-foreground">Manual setup</span>
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">
                  Manually configure an Incoming Webhook from your Slack app.
                </p>
              </button>
            </div>
          </CardContent>
        </Card>

        {/* OAuth Flow */}
        {connectionMethod === 'oauth' && (
          <Card className="animate-slide-up stagger-2">
            <CardHeader>
              <CardTitle>Connect to Slack</CardTitle>
              <CardDescription>
                Click the button below to authorize Rereflect to post messages to your Slack workspace
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-4 bg-muted/50 rounded-lg border border-border">
                <h4 className="font-medium mb-2">What happens next:</h4>
                <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside">
                  <li>You&apos;ll be redirected to Slack to authorize access</li>
                  <li>Select the channel where you want to receive alerts</li>
                  <li>You&apos;ll be redirected back to configure alert settings</li>
                </ol>
              </div>

              <Button
                onClick={handleOAuthConnect}
                disabled={oauthLoading || !form.name}
                className="w-full"
                size="lg"
              >
                {oauthLoading ? (
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                ) : (
                  <Slack className="w-5 h-5 mr-2" />
                )}
                Connect to Slack
              </Button>

              {!form.name && (
                <p className="text-sm text-muted-foreground text-center">
                  Enter an integration name above to continue
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Webhook Flow */}
        {connectionMethod === 'webhook' && (
          <form onSubmit={handleWebhookSubmit} className="space-y-6">
            {/* Webhook URL */}
            <Card className="animate-slide-up stagger-2">
              <CardHeader>
                <CardTitle>Webhook Configuration</CardTitle>
                <CardDescription>Enter your Slack Incoming Webhook URL</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="webhook_url">Webhook URL</Label>
                  <Input
                    id="webhook_url"
                    type="url"
                    placeholder="https://hooks.slack.com/services/..."
                    value={form.webhook_url}
                    onChange={e => setForm(prev => ({ ...prev, webhook_url: e.target.value }))}
                    required
                  />
                  <p className="text-xs text-muted-foreground">
                    Get this from Slack: App Settings → Incoming Webhooks → Add New Webhook
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Triggers */}
            <Card className="animate-slide-up stagger-3">
              <CardHeader>
                <CardTitle>Alert Triggers</CardTitle>
                <CardDescription>Choose when to send alerts to this channel</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {TRIGGER_OPTIONS.map(opt => (
                  <div key={opt.value} className="flex items-start space-x-3">
                    <Checkbox
                      id={`trigger-${opt.value}`}
                      checked={form.triggers.includes(opt.value)}
                      onCheckedChange={() => toggleTrigger(opt.value)}
                    />
                    <div className="grid gap-0.5">
                      <Label htmlFor={`trigger-${opt.value}`} className="font-medium cursor-pointer">
                        {opt.label}
                      </Label>
                      <p className="text-xs text-muted-foreground">{opt.description}</p>
                    </div>
                  </div>
                ))}

                {needsDigestTime && (
                  <div className="mt-4 pt-4 border-t border-border">
                    <Label htmlFor="digest_time">Digest Time (UTC)</Label>
                    <Input
                      id="digest_time"
                      type="time"
                      value={form.digest_time}
                      onChange={e => setForm(prev => ({ ...prev, digest_time: e.target.value }))}
                      className="w-32 mt-2"
                    />
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Message Template */}
            <Card className="animate-slide-up stagger-4">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  Message Template
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <Info className="w-4 h-4 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-sm">
                        <p>Customize the message format using variables. Click a variable below to insert it.</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </CardTitle>
                <CardDescription>Customize the message sent to Slack</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Variable Pills */}
                <div>
                  <Label className="text-xs text-muted-foreground uppercase tracking-wider">
                    Available Variables (click to insert)
                  </Label>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {templateVariables.map(v => (
                      <TooltipProvider key={v.name}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              onClick={() => insertVariable(v.name)}
                              className="inline-flex items-center gap-1 px-2 py-1 text-xs font-mono bg-secondary hover:bg-secondary/80 rounded-md transition-colors"
                            >
                              {`{{${v.name}}}`}
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="bottom" className="max-w-xs">
                            <p className="font-medium">{v.description}</p>
                            <p className="text-xs text-muted-foreground mt-1">Example: {v.example}</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    ))}
                  </div>
                </div>

                {/* Conditional Blocks Help */}
                <div className="p-3 bg-muted/50 rounded-lg border border-border">
                  <div className="flex items-start gap-2">
                    <HelpCircle className="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                    <div className="text-xs text-muted-foreground space-y-1">
                      <p className="font-medium text-foreground">Conditional Blocks</p>
                      <p>
                        Use <code className="bg-secondary px-1 rounded">{`{{#variable}}`}</code>...<code className="bg-secondary px-1 rounded">{`{{/variable}}`}</code> to show content only when a variable has a value.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Template Editor */}
                <div className="space-y-2">
                  <Label htmlFor="message_template">Message Template</Label>
                  <Textarea
                    id="message_template"
                    value={form.message_template}
                    onChange={e => setForm(prev => ({ ...prev, message_template: e.target.value }))}
                    placeholder="Enter your custom message template..."
                    className="font-mono text-sm min-h-[200px]"
                  />
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-muted-foreground">
                      Slack mrkdwn: *bold*, _italic_, `code`, &gt; quote
                    </p>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setForm(prev => ({ ...prev, message_template: defaultTemplate }))}
                    >
                      Reset to Default
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3">
              <Link href="/settings/integrations">
                <Button type="button" variant="outline">Cancel</Button>
              </Link>
              <Button type="submit" disabled={loading || !form.name || !form.webhook_url}>
                {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                Create Integration
              </Button>
            </div>
          </form>
        )}

        {/* Error */}
        {error && (
          <div className="p-4 bg-destructive/10 text-destructive rounded-lg flex items-center gap-2">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            {error}
          </div>
        )}
      </main>
    </div>
  );
}
