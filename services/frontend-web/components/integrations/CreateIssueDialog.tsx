'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertCircle,
  CheckCircle,
  ExternalLink,
  GitBranch,
  Loader2,
} from 'lucide-react';
import {
  linearAPI,
  LinearConnectionStatus,
  LinearTeam,
  LinearProject,
  LinearLabel,
  LinearIssue,
  LINEAR_PRIORITY_LABELS,
} from '@/lib/api/linear';
import { useAuth } from '@/contexts/AuthContext';

interface CreateIssueDialogProps {
  feedbackId: number;
  aiTitle?: string;
  aiDescription?: string;
  /** Called after issue is successfully created */
  onCreated?: (issue: LinearIssue) => void;
}

type Step = 'select-integration' | 'linear-form' | 'success';

interface FormState {
  title: string;
  description: string;
  teamId: string;
  projectId: string;
  priority: string;
  labelIds: string[];
}

export function CreateIssueDialog({
  feedbackId,
  aiTitle = '',
  aiDescription = '',
  onCreated,
}: CreateIssueDialogProps) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>('select-integration');
  const [connectionStatus, setConnectionStatus] = useState<LinearConnectionStatus | null>(null);
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [teams, setTeams] = useState<LinearTeam[]>([]);
  const [projects, setProjects] = useState<LinearProject[]>([]);
  const [labels, setLabels] = useState<LinearLabel[]>([]);
  const [existingIssues, setExistingIssues] = useState<LinearIssue[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [createdIssue, setCreatedIssue] = useState<LinearIssue | null>(null);
  const [createdUrl, setCreatedUrl] = useState<string>('');
  const [form, setForm] = useState<FormState>({
    title: aiTitle,
    description: aiDescription,
    teamId: '',
    projectId: '',
    priority: '3',
    labelIds: [],
  });

  const isFree = user?.plan === 'free';
  const isConnected = connectionStatus?.connected && connectionStatus?.is_active;

  // Load connection status on mount
  useEffect(() => {
    linearAPI.getStatus()
      .then(s => setConnectionStatus(s))
      .catch(() => {})
      .finally(() => setStatusLoaded(true));
  }, []);

  // Load teams/labels when dialog opens
  const loadFormData = useCallback(async () => {
    try {
      const [t, l, linked] = await Promise.all([
        linearAPI.getTeams(),
        linearAPI.getLabels(),
        linearAPI.getLinkedIssues(feedbackId),
      ]);
      setTeams(t);
      setLabels(l);
      setExistingIssues(linked);
    } catch {
      // ignore
    }
  }, [feedbackId]);

  useEffect(() => {
    if (open && isConnected) {
      loadFormData();
    }
  }, [open, isConnected, loadFormData]);

  // Load projects when team changes
  useEffect(() => {
    if (!form.teamId) {
      setProjects([]);
      return;
    }
    linearAPI.getProjects(form.teamId)
      .then(p => setProjects(p))
      .catch(() => {});
  }, [form.teamId]);

  const handleOpen = () => {
    setStep('select-integration');
    setForm({ title: aiTitle, description: aiDescription, teamId: '', projectId: '', priority: '3', labelIds: [] });
    setCreatedIssue(null);
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };

  const handleSelectLinear = () => {
    setStep('linear-form');
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const response = await linearAPI.createIssue({
        feedback_id: feedbackId,
        team_id: form.teamId,
        project_id: form.projectId || undefined,
        title: form.title,
        description: form.description,
        priority: parseInt(form.priority, 10),
        label_ids: form.labelIds.length > 0 ? form.labelIds : undefined,
      });
      setCreatedIssue(response.issue);
      setCreatedUrl(response.linear_url);
      setStep('success');
      onCreated?.(response.issue);
    } catch {
      // ignore — in production we'd show an error
    } finally {
      setSubmitting(false);
    }
  };

  // Don't render button if status not loaded or not connected
  if (!statusLoaded) return null;
  if (!isConnected) return null;

  return (
    <>
      <Button
        onClick={handleOpen}
        disabled={isFree}
        variant="outline"
        size="sm"
        className="flex items-center gap-2"
        title={isFree ? 'Upgrade to Pro to create Linear issues' : 'Create Linear issue'}
      >
        <GitBranch className="w-4 h-4" />
        Create Issue
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {step === 'select-integration' && 'Create Issue'}
              {step === 'linear-form' && 'New Linear Issue'}
              {step === 'success' && 'Issue Created'}
            </DialogTitle>
          </DialogHeader>

          {/* Step 1: Select integration */}
          {step === 'select-integration' && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">Select where to create the issue:</p>

              {/* Linear — available */}
              <button
                onClick={handleSelectLinear}
                aria-label={`Linear - Connected to ${connectionStatus?.org_name}`}
                className="w-full flex items-center gap-3 p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-secondary/30 transition-all text-left"
              >
                <div className="p-2 bg-primary/10 rounded-lg">
                  <GitBranch className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <p className="font-semibold">Linear</p>
                  <p className="text-sm text-muted-foreground">Connected to {connectionStatus?.org_name}</p>
                </div>
              </button>

              {/* JIRA — coming soon */}
              <div className="w-full flex items-center gap-3 p-4 border border-border rounded-xl bg-muted/30 opacity-60 cursor-not-allowed">
                <div className="p-2 bg-blue-500/10 rounded-lg">
                  <ExternalLink className="w-5 h-5 text-blue-500" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-semibold">JIRA</p>
                    <Badge variant="secondary" className="text-xs">Coming soon</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">Atlassian JIRA integration</p>
                </div>
              </div>

              {/* Asana — coming soon */}
              <div className="w-full flex items-center gap-3 p-4 border border-border rounded-xl bg-muted/30 opacity-60 cursor-not-allowed">
                <div className="p-2 bg-pink-500/10 rounded-lg">
                  <ExternalLink className="w-5 h-5 text-pink-500" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-semibold">Asana</p>
                    <Badge variant="secondary" className="text-xs">Coming soon</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">Asana project management</p>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button variant="ghost" onClick={handleClose}>Cancel</Button>
              </div>
            </div>
          )}

          {/* Step 2: Linear form */}
          {step === 'linear-form' && (
            <div className="space-y-4">
              {/* Duplicate warning */}
              {existingIssues.length > 0 && (
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    This feedback is already linked to{' '}
                    {existingIssues.map(issue => (
                      <a
                        key={issue.id}
                        href={issue.linear_issue_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono font-semibold text-primary hover:underline"
                      >
                        {issue.linear_issue_identifier}
                      </a>
                    ))}.
                    {' '}Creating another issue will link it too.
                  </AlertDescription>
                </Alert>
              )}

              {/* Title */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Title</label>
                <Input
                  value={form.title}
                  onChange={e => setForm(prev => ({ ...prev, title: e.target.value }))}
                  placeholder="Issue title"
                />
              </div>

              {/* Description */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Description</label>
                <Textarea
                  value={form.description}
                  onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Issue description (markdown supported)"
                  rows={5}
                />
              </div>

              {/* Team + Priority row */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Team</label>
                  <Select
                    value={form.teamId}
                    onValueChange={val => setForm(prev => ({ ...prev, teamId: val, projectId: '' }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select team…" />
                    </SelectTrigger>
                    <SelectContent>
                      {teams.map(t => (
                        <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Priority</label>
                  <Select
                    value={form.priority}
                    onValueChange={val => setForm(prev => ({ ...prev, priority: val }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(LINEAR_PRIORITY_LABELS).map(([val, label]) => (
                        <SelectItem key={val} value={val}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Project (optional) */}
              {projects.length > 0 && (
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Project (optional)</label>
                  <Select
                    value={form.projectId}
                    onValueChange={val => setForm(prev => ({ ...prev, projectId: val }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="No project" />
                    </SelectTrigger>
                    <SelectContent>
                      {projects.map(p => (
                        <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" onClick={handleClose}>Cancel</Button>
                <Button onClick={handleSubmit} disabled={submitting}>
                  {submitting ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Creating…</>
                  ) : (
                    'Create'
                  )}
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Success */}
          {step === 'success' && createdIssue && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 p-4 bg-green-50 dark:bg-green-950 rounded-xl border border-green-200 dark:border-green-800">
                <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-green-800 dark:text-green-200">
                    Issue created successfully
                  </p>
                  <a
                    href={createdUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-sm text-primary hover:underline flex items-center gap-1 mt-0.5"
                  >
                    {createdIssue.linear_issue_identifier}
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
              <p className="text-sm text-muted-foreground">{createdIssue.linear_issue_title}</p>
              <div className="flex justify-end">
                <Button onClick={handleClose}>Done</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
