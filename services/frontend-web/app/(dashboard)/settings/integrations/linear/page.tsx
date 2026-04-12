'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle,
  HelpCircle,
  Info,
  Loader2,
  Send,
  Trash2,
  XCircle,
} from 'lucide-react';
import {
  linearAPI,
  LinearConnectionStatus,
  LinearTeam,
  LinearTeamMapping,
  LinearStatusMapping,
  LinearTemplateVariable,
  REREFLECT_CATEGORIES,
  LINEAR_STATUS_TYPES,
  REREFLECT_STATUSES,
} from '@/lib/api/linear';
import { LinearIcon } from '@/components/icons/LinearIcon';
import { useAuth } from '@/contexts/AuthContext';

export default function LinearSettingsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [status, setStatus] = useState<LinearConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [teams, setTeams] = useState<LinearTeam[]>([]);
  const [teamMappings, setTeamMappings] = useState<LinearTeamMapping[]>([]);
  const [statusMappings, setStatusMappings] = useState<LinearStatusMapping[]>([]);

  // Template state
  const [titleTemplate, setTitleTemplate] = useState('');
  const [descriptionTemplate, setDescriptionTemplate] = useState('');
  const [defaultTitleTemplate, setDefaultTitleTemplate] = useState('');
  const [defaultDescriptionTemplate, setDefaultDescriptionTemplate] = useState('');
  const [templateVariables, setTemplateVariables] = useState<LinearTemplateVariable[]>([]);

  // Form state for toggle
  const [isActive, setIsActive] = useState(true);
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);
  const [confirmMessage, setConfirmMessage] = useState('');

  const requestConfirm = (message: string, action: () => void) => {
    setConfirmMessage(message);
    setConfirmAction(() => action);
  };

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    if (user && user.role !== 'owner' && user.role !== 'admin') {
      router.replace('/settings/preferences');
    }
  }, [user, router]);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await linearAPI.getStatus();
      setStatus(s);
      setIsActive(s.is_active);
      return s;
    } catch {
      // ignore
    }
  }, []);

  const fetchMappings = useCallback(async () => {
    try {
      const [tm, sm] = await Promise.all([
        linearAPI.getTeamMappings(),
        linearAPI.getStatusMappings(),
      ]);
      setTeamMappings(tm);
      setStatusMappings(sm);
    } catch {
      // ignore
    }
  }, []);

  const fetchTeams = useCallback(async () => {
    try {
      const t = await linearAPI.getTeams();
      setTeams(t);
    } catch {
      // ignore
    }
  }, []);

  const fetchTemplates = useCallback(async () => {
    try {
      const [config, vars] = await Promise.all([
        linearAPI.getConfig(),
        linearAPI.getTemplateVariables(),
      ]);
      setTitleTemplate(config.issue_title_template || vars.default_title_template);
      setDescriptionTemplate(config.issue_description_template || vars.default_description_template);
      setDefaultTitleTemplate(vars.default_title_template);
      setDefaultDescriptionTemplate(vars.default_description_template);
      setTemplateVariables(vars.variables);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    async function init() {
      setLoading(true);
      const s = await fetchStatus();
      if (s?.connected && s?.is_active) {
        await Promise.all([fetchTeams(), fetchMappings(), fetchTemplates()]);
      }
      setLoading(false);
    }
    init();
  }, [fetchStatus, fetchTeams, fetchMappings, fetchTemplates]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await linearAPI.testConnection();
      setTestResult(result);
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
      'Disconnect Linear? Existing issue links will be preserved.',
      async () => {
        try {
          await linearAPI.disconnect();
          router.push('/settings/integrations');
        } catch (err) {
          console.error('Failed to disconnect Linear:', err);
        }
      }
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      // Save all settings in parallel
      await Promise.all([
        linearAPI.updateTeamMappings({
          mappings: teamMappings.map(m => ({
            rereflect_category: m.rereflect_category,
            linear_team_id: m.linear_team_id,
            linear_team_name: m.linear_team_name,
            linear_project_id: m.linear_project_id ?? undefined,
            linear_project_name: m.linear_project_name ?? undefined,
            priority: m.priority,
          })),
        }),
        linearAPI.updateStatusMappings({
          mappings: statusMappings.map(m => ({
            linear_status_name: m.linear_status_name,
            linear_status_type: m.linear_status_type,
            rereflect_status: m.rereflect_status,
          })),
        }),
        linearAPI.updateConfig({
          issue_title_template: titleTemplate,
          issue_description_template: descriptionTemplate,
        }),
      ]);
      setTestResult({ success: true, message: 'Changes saved successfully!' });
      setTimeout(() => setTestResult(null), 3000);
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.response?.data?.detail || 'Failed to save changes',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleTeamMappingChange = (category: string, teamId: string) => {
    const team = teams.find(t => t.id === teamId);
    if (!team) return;
    setTeamMappings(prev => {
      const existing = prev.find(m => m.rereflect_category === category);
      if (existing) {
        return prev.map(m =>
          m.rereflect_category === category
            ? { ...m, linear_team_id: teamId, linear_team_name: team.name }
            : m
        );
      }
      return [
        ...prev,
        {
          id: Date.now(),
          rereflect_category: category,
          linear_team_id: teamId,
          linear_team_name: team.name,
          linear_project_id: null,
          linear_project_name: null,
          priority: 1,
        },
      ];
    });
  };

  const handleStatusMappingChange = (statusType: string, rereflectStatus: string) => {
    setStatusMappings(prev => {
      const existing = prev.find(m => m.linear_status_type === statusType);
      const typeDef = LINEAR_STATUS_TYPES.find(t => t.value === statusType);
      if (existing) {
        return prev.map(m =>
          m.linear_status_type === statusType
            ? { ...m, rereflect_status: rereflectStatus }
            : m
        );
      }
      return [
        ...prev,
        {
          id: Date.now(),
          linear_status_name: typeDef?.label ?? statusType,
          linear_status_type: statusType,
          rereflect_status: rereflectStatus,
        },
      ];
    });
  };

  const insertVariable = (field: 'title' | 'description', varName: string) => {
    const textareaId = field === 'title' ? 'title_template' : 'description_template';
    const textarea = document.getElementById(textareaId) as HTMLTextAreaElement;
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const currentValue = field === 'title' ? titleTemplate : descriptionTemplate;
      const variable = `{{${varName}}}`;
      const newValue = currentValue.substring(0, start) + variable + currentValue.substring(end);
      if (field === 'title') setTitleTemplate(newValue);
      else setDescriptionTemplate(newValue);
      setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(start + variable.length, start + variable.length);
      }, 0);
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

  const isConnected = status?.connected ?? false;

  // Not connected — show connect CTA
  if (!isConnected) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
          <div className="animate-fade-in">
            <Link
              href="/settings/integrations"
              className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4"
            >
              <ArrowLeft className="w-4 h-4 mr-1" />
              Back to Integrations
            </Link>
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-[#5E6AD2]/10 rounded-xl">
                <LinearIcon className="w-8 h-8 text-[#5E6AD2]" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-foreground">Linear</h1>
                <p className="text-muted-foreground">Create issues directly from feedback</p>
              </div>
            </div>
          </div>
          <Card className="animate-slide-up">
            <CardContent className="text-center py-12">
              <LinearIcon className="w-16 h-16 mx-auto text-[#5E6AD2]/50 mb-4" />
              <h3 className="text-lg font-semibold text-foreground mb-2">Connect your Linear workspace</h3>
              <p className="text-muted-foreground mb-6 max-w-md mx-auto">
                Create Linear issues directly from customer feedback. Map categories to teams and sync issue statuses automatically.
              </p>
              {isAdminOrOwner && (
                <Button onClick={async () => {
                  try {
                    const { auth_url } = await linearAPI.getConnectUrl();
                    window.location.href = auth_url;
                  } catch {
                    // ignore
                  }
                }}>
                  Connect Linear
                </Button>
              )}
            </CardContent>
          </Card>
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
              <div className="p-3 bg-[#5E6AD2]/10 rounded-xl">
                <LinearIcon className="w-8 h-8 text-[#5E6AD2]" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-3xl font-bold text-foreground">Linear</h1>
                  {isActive ? (
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
                  Configure your Linear integration
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={handleTest}
                disabled={testing}
              >
                {testing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
                Test
              </Button>
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
                  {isActive
                    ? `Connected to ${status?.org_name}`
                    : 'Integration is paused'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-muted-foreground">
                  {isActive ? 'Enabled' : 'Disabled'}
                </span>
                <Switch
                  checked={isActive}
                  onCheckedChange={(checked) => setIsActive(checked)}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Mapping Configuration */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader>
            <CardTitle>Mapping Configuration</CardTitle>
            <CardDescription>Configure how Rereflect maps to Linear</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Tabs defaultValue="team-mapping">
              <TabsList className="mb-4">
                <TabsTrigger value="team-mapping">Team Mapping</TabsTrigger>
                <TabsTrigger value="status-mapping">Status Mapping</TabsTrigger>
              </TabsList>

              {/* Team Mapping Tab */}
              <TabsContent value="team-mapping" className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  Map Rereflect categories to Linear teams. When creating an issue, the matching team will be pre-selected.
                </p>
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium text-muted-foreground">Category</th>
                        <th className="text-left px-4 py-3 font-medium text-muted-foreground">Linear Team</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {REREFLECT_CATEGORIES.map(cat => {
                        const mapping = teamMappings.find(m => m.rereflect_category === cat.value);
                        return (
                          <tr key={cat.value}>
                            <td className="px-4 py-3 font-medium">{cat.label}</td>
                            <td className="px-4 py-3">
                              <Select
                                value={mapping?.linear_team_id ?? ''}
                                onValueChange={val => handleTeamMappingChange(cat.value, val)}
                                disabled={!isAdminOrOwner}
                              >
                                <SelectTrigger className="w-48">
                                  <SelectValue placeholder="Select team..." />
                                </SelectTrigger>
                                <SelectContent>
                                  {teams.map(team => (
                                    <SelectItem key={team.id} value={team.id}>
                                      {team.name}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </TabsContent>

              {/* Status Mapping Tab */}
              <TabsContent value="status-mapping" className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  Map Linear status types to Rereflect workflow statuses. Status changes in Linear will update feedback automatically.
                </p>
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium text-muted-foreground">Linear Status Type</th>
                        <th className="text-left px-4 py-3 font-medium text-muted-foreground">Rereflect Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {LINEAR_STATUS_TYPES.map(statusType => {
                        const mapping = statusMappings.find(m => m.linear_status_type === statusType.value);
                        return (
                          <tr key={statusType.value}>
                            <td className="px-4 py-3 font-medium">{statusType.label}</td>
                            <td className="px-4 py-3">
                              <Select
                                value={mapping?.rereflect_status ?? ''}
                                onValueChange={val => handleStatusMappingChange(statusType.value, val)}
                                disabled={!isAdminOrOwner}
                              >
                                <SelectTrigger className="w-40">
                                  <SelectValue placeholder="Select status..." />
                                </SelectTrigger>
                                <SelectContent>
                                  {REREFLECT_STATUSES.map(s => (
                                    <SelectItem key={s.value} value={s.value}>
                                      {s.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        {/* Issue Template */}
        <Card className="animate-slide-up stagger-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Issue Template
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
            <CardDescription>Customize the default issue format using variables</CardDescription>
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
                          onClick={() => {
                            const active = document.activeElement;
                            const field = active?.id === 'title_template' ? 'title' : 'description';
                            insertVariable(field, v.name);
                          }}
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

            {/* Title Template */}
            <div className="space-y-2">
              <Label htmlFor="title_template">Issue Title Template</Label>
              <Textarea
                id="title_template"
                value={titleTemplate}
                onChange={e => setTitleTemplate(e.target.value)}
                className="font-mono text-sm min-h-[60px]"
                rows={2}
              />
            </div>

            {/* Description Template */}
            <div className="space-y-2">
              <Label htmlFor="description_template">Issue Description Template</Label>
              <Textarea
                id="description_template"
                value={descriptionTemplate}
                onChange={e => setDescriptionTemplate(e.target.value)}
                className="font-mono text-sm min-h-[200px]"
              />
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Supports Markdown: **bold**, _italic_, `code`, &gt; quote
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setTitleTemplate(defaultTitleTemplate);
                    setDescriptionTemplate(defaultDescriptionTemplate);
                  }}
                >
                  Reset to Default
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Save Button — sticky bar matching Slack */}
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
