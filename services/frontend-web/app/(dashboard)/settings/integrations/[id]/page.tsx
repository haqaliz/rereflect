'use client';

import { useState, useEffect, use, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  integrationsAPI,
  Integration,
  AlertLog,
  TRIGGER_OPTIONS,
  TemplateVariable,
} from '@/lib/api/integrations';
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  Info,
  Send,
  CheckCircle,
  XCircle,
  Trash2,
  Clock,
  History,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
} from 'lucide-react';
import { SlackIcon } from '@/components/icons/SlackIcon';
import { IntercomIcon } from '@/components/icons/IntercomIcon';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export default function IntegrationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [integration, setIntegration] = useState<Integration | null>(null);
  const [logs, setLogs] = useState<AlertLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [templateVariables, setTemplateVariables] = useState<TemplateVariable[]>([]);
  const [defaultTemplate, setDefaultTemplate] = useState('');
  const [logsPage, setLogsPage] = useState(0);
  const logsPerPage = 10;
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);
  const [confirmMessage, setConfirmMessage] = useState('');

  const requestConfirm = (message: string, action: () => void) => {
    setConfirmMessage(message);
    setConfirmAction(() => action);
  };

  const [form, setForm] = useState({
    name: '',
    triggers: [] as string[],
    digest_time: '09:00',
    message_template: '',
    is_active: true,
  });

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const [integrationData, logsData, templateData] = await Promise.all([
          integrationsAPI.get(parseInt(id)),
          integrationsAPI.getLogs(parseInt(id), 100), // Fetch more for pagination
          integrationsAPI.getTemplateVariables(),
        ]);

        setIntegration(integrationData);
        setLogs(logsData);
        setTemplateVariables(templateData.variables);
        setDefaultTemplate(templateData.default_template);

        setForm({
          name: integrationData.name || '',
          triggers: integrationData.triggers || ['urgent'],
          digest_time: integrationData.digest_time || '09:00',
          message_template: integrationData.message_template || templateData.default_template,
          is_active: integrationData.is_active,
        });
      } catch (err) {
        console.error('Failed to load integration:', err);
        setError('Failed to load integration');
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [id]);

  const handleSave = async () => {
    setError(null);
    setSaving(true);

    try {
      const updated = await integrationsAPI.update(parseInt(id), {
        name: form.name,
        triggers: form.triggers,
        digest_time: form.digest_time,
        message_template: form.message_template,
        is_active: form.is_active,
      });
      setIntegration(updated);
      setTestResult({ success: true, message: 'Changes saved successfully!' });
      setTimeout(() => setTestResult(null), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await integrationsAPI.testSlack(parseInt(id));
      setTestResult(result);
      // Refresh logs
      const newLogs = await integrationsAPI.getLogs(parseInt(id), 100);
      setLogs(newLogs);
      setLogsPage(0); // Reset to first page
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.response?.data?.detail || 'Test failed',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleDelete = () => {
    requestConfirm(
      'Delete this integration? This cannot be undone.',
      async () => {
        try {
          await integrationsAPI.delete(parseInt(id));
          router.push('/settings/integrations');
        } catch (err) {
          console.error('Failed to delete integration:', err);
        }
      }
    );
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

  // Pagination for logs
  const totalPages = Math.ceil(logs.length / logsPerPage);
  const paginatedLogs = useMemo(() => {
    const start = logsPage * logsPerPage;
    return logs.slice(start, start + logsPerPage);
  }, [logs, logsPage, logsPerPage]);

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

  if (!integration) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-16">
            <AlertCircle className="w-12 h-12 mx-auto text-destructive mb-4" />
            <h2 className="text-xl font-semibold">Integration not found</h2>
            <Link href="/settings/integrations" className="text-primary hover:underline mt-2 inline-block">
              Back to Integrations
            </Link>
          </div>
        </main>
      </div>
    );
  }

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
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className={`p-3 rounded-xl ${integration.type === 'intercom' ? 'bg-[#1F8DED]/10' : 'bg-secondary'}`}>
                {integration.type === 'intercom' ? (
                  <IntercomIcon className="w-8 h-8" />
                ) : (
                  <SlackIcon className="w-8 h-8" />
                )}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-3xl font-bold text-foreground">{integration.name}</h1>
                  {form.is_active ? (
                    <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950">
                      Active
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      Disabled
                    </Badge>
                  )}
                </div>
                <p className="text-muted-foreground">
                  {integration.type === 'intercom' ? 'Configure your Intercom integration' : 'Configure your Slack integration'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {integration.type !== 'intercom' && (
                <Button
                  variant="outline"
                  onClick={handleTest}
                  disabled={testing}
                >
                  {testing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
                  Test
                </Button>
              )}
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
        </div>

        {/* Test Result */}
        {testResult && (
          <div
            className={`p-4 rounded-lg flex items-center gap-2 animate-fade-in ${
              testResult.success
                ? 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300'
                : 'bg-destructive/10 text-destructive'
            }`}
          >
            {testResult.success ? (
              <CheckCircle className="w-5 h-5 flex-shrink-0" />
            ) : (
              <XCircle className="w-5 h-5 flex-shrink-0" />
            )}
            {testResult.message}
          </div>
        )}

        {/* Status Toggle */}
        <Card className="animate-slide-up">
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold">Integration Status</h3>
                <p className="text-sm text-muted-foreground">
                  {form.is_active
                    ? `Integration is active${integration?.type === 'intercom' ? '' : ' and sending alerts to Slack'}`
                    : 'Integration is paused'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-muted-foreground">
                  {form.is_active ? 'Enabled' : 'Disabled'}
                </span>
                <Switch
                  checked={form.is_active}
                  onCheckedChange={(checked) => setForm(prev => ({ ...prev, is_active: checked }))}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Basic Settings */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader>
            <CardTitle>Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Integration Name</Label>
              <Input
                id="name"
                value={form.name}
                onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
              />
            </div>
          </CardContent>
        </Card>

        {/* Triggers */}
        <Card className="animate-slide-up stagger-2">
          <CardHeader>
            <CardTitle>Alert Triggers</CardTitle>
            <CardDescription>Choose when to send alerts</CardDescription>
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
        <Card className="animate-slide-up stagger-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Message Template
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="w-4 h-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-sm">
                    <p>Click a variable to insert it at your cursor position in the template.</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </CardTitle>
            <CardDescription>Customize the message format using variables</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Variable Pills */}
            <div>
              <Label className="text-xs text-muted-foreground uppercase tracking-wider">Available Variables</Label>
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
                  <p className="text-muted-foreground/80">
                    Example: <code className="bg-secondary px-1 rounded">{`{{#pain_point_category}}Pain: {{pain_point_category}}{{/pain_point_category}}`}</code>
                  </p>
                </div>
              </div>
            </div>

            {/* Template Editor */}
            <div className="space-y-2">
              <Label htmlFor="message_template">Template</Label>
              <Textarea
                id="message_template"
                value={form.message_template}
                onChange={e => setForm(prev => ({ ...prev, message_template: e.target.value }))}
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

        {/* Alert History */}
        <Card className="animate-slide-up stagger-4">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <History className="w-5 h-5" />
                Recent Alerts
              </CardTitle>
              {logs.length > 0 && (
                <span className="text-sm text-muted-foreground">
                  {logs.length} total
                </span>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {logs.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">No alerts sent yet</p>
            ) : (
              <div className="space-y-4">
                <div className="rounded-md border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50">
                        <TableHead className="w-[100px]">Status</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Feedback</TableHead>
                        <TableHead className="text-right">Sent At</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedLogs.map(log => (
                        <TableRow key={log.id}>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              {log.status === 'sent' ? (
                                <>
                                  <CheckCircle className="w-4 h-4 text-green-500" />
                                  <span className="text-green-600 dark:text-green-400 text-sm">Sent</span>
                                </>
                              ) : (
                                <>
                                  <XCircle className="w-4 h-4 text-destructive" />
                                  <span className="text-destructive text-sm">Failed</span>
                                </>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="capitalize">
                              {log.alert_type}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {log.feedback_id ? (
                              <Link
                                href={`/feedbacks/${log.feedback_id}`}
                                className="hover:text-primary hover:underline"
                              >
                                #{log.feedback_id}
                              </Link>
                            ) : (
                              <span className="text-muted-foreground/50">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right text-muted-foreground">
                            <div className="flex items-center justify-end gap-2">
                              <Clock className="w-3 h-3" />
                              {new Date(log.sent_at).toLocaleString()}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between px-2">
                    <div className="text-sm text-muted-foreground">
                      Showing {logsPage * logsPerPage + 1}-{Math.min((logsPage + 1) * logsPerPage, logs.length)} of {logs.length}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setLogsPage(p => Math.max(0, p - 1))}
                        disabled={logsPage === 0}
                      >
                        <ChevronLeft className="w-4 h-4 mr-1" />
                        Previous
                      </Button>
                      <span className="text-sm text-muted-foreground px-2">
                        Page {logsPage + 1} of {totalPages}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setLogsPage(p => Math.min(totalPages - 1, p + 1))}
                        disabled={logsPage >= totalPages - 1}
                      >
                        Next
                        <ChevronRight className="w-4 h-4 ml-1" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Error */}
        {error && (
          <div className="p-4 bg-destructive/10 text-destructive rounded-lg flex items-center gap-2">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Save Button */}
        <div className="flex items-center justify-end gap-3 sticky bottom-4 bg-background/80 backdrop-blur-sm p-4 -mx-4 rounded-lg border border-border">
          <Link href="/settings/integrations">
            <Button type="button" variant="outline">Cancel</Button>
          </Link>
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Save Changes
          </Button>
        </div>
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
