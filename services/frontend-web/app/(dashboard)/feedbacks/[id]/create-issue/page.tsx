'use client';

import { Suspense, useState, useEffect, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  ArrowLeft,
  GitBranch,
  Settings,
  CheckCircle,
  ChevronRight,
  ExternalLink,
  AlertCircle,
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
import { feedbackAPI, FeedbackItem } from '@/lib/api/feedback';
import { useAuth } from '@/contexts/AuthContext';

type Step = 'select-integration' | 'configure' | 'done';

const STEPS: { key: Step; label: string }[] = [
  { key: 'select-integration', label: 'Integration' },
  { key: 'configure', label: 'Configure' },
  { key: 'done', label: 'Done' },
];

export default function CreateIssuePage() {
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
      <CreateIssueContent />
    </Suspense>
  );
}

interface FormState {
  title: string;
  description: string;
  teamId: string;
  projectId: string;
  priority: string;
  labelIds: string[];
}

function CreateIssueContent() {
  const router = useRouter();
  const params = useParams();
  const { user } = useAuth();
  const feedbackId = Number(params.id);

  const [currentStep, setCurrentStep] = useState<Step>('select-integration');
  const [feedback, setFeedback] = useState<FeedbackItem | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<LinearConnectionStatus | null>(null);
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [teams, setTeams] = useState<LinearTeam[]>([]);
  const [projects, setProjects] = useState<LinearProject[]>([]);
  const [labels, setLabels] = useState<LinearLabel[]>([]);
  const [existingIssues, setExistingIssues] = useState<LinearIssue[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [createdIssue, setCreatedIssue] = useState<LinearIssue | null>(null);
  const [createdUrl, setCreatedUrl] = useState('');
  const [createError, setCreateError] = useState('');
  const [form, setForm] = useState<FormState>({
    title: '',
    description: '',
    teamId: '',
    projectId: '',
    priority: '3',
    labelIds: [],
  });

  const isConnected = connectionStatus?.connected && connectionStatus?.is_active;

  useEffect(() => {
    feedbackAPI.get(feedbackId)
      .then((fb) => {
        setFeedback(fb);
        setForm(prev => ({
          ...prev,
          title: fb.extracted_issue || '',
          description: fb.text || '',
        }));
      })
      .catch(() => {});
  }, [feedbackId]);

  useEffect(() => {
    linearAPI.getStatus()
      .then(setConnectionStatus)
      .catch(() => {})
      .finally(() => setStatusLoaded(true));
  }, []);

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
    if (currentStep === 'configure' && isConnected) {
      loadFormData();
    }
  }, [currentStep, isConnected, loadFormData]);

  useEffect(() => {
    if (!form.teamId) {
      setProjects([]);
      return;
    }
    linearAPI.getProjects(form.teamId)
      .then(setProjects)
      .catch(() => {});
  }, [form.teamId]);

  const handleSelectLinear = () => {
    setCurrentStep('configure');
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setCreateError('');
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
      // Backend returns flat issue object; frontend type wraps it in { issue, linear_url }
      const issue = response.issue ?? (response as any);
      setCreatedIssue(issue);
      setCreatedUrl(response.linear_url ?? issue.linear_issue_url ?? '');
      setCurrentStep('done');
    } catch (err: any) {
      setCreateError(err?.response?.data?.detail || 'Failed to create issue. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const stepIndex = STEPS.findIndex(s => s.key === currentStep);

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4 animate-fade-in">
          <div className="p-3 rounded-xl bg-primary/10">
            <GitBranch className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Create Issue</h1>
            <p className="text-sm text-muted-foreground">Link feedback to your project tracker</p>
          </div>
        </div>

        {/* Step indicator — matching feedback source style */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {STEPS.map((step, index) => {
            const isActive = index === stepIndex;
            const isDone = index < stepIndex;
            return (
              <div key={step.key} className="flex items-center">
                <div className="flex items-center gap-2">
                  <div
                    className={[
                      'flex items-center justify-center w-6 h-6 rounded-full transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground ring-2 ring-primary/30'
                        : isDone
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted',
                    ].join(' ')}
                  >
                    {isDone ? (
                      <CheckCircle className="w-3.5 h-3.5" />
                    ) : isActive ? (
                      <span className="w-2 h-2 rounded-full bg-primary-foreground" />
                    ) : (
                      <span className="w-2 h-2 rounded-full bg-muted-foreground/40" />
                    )}
                  </div>
                  <span
                    className={[
                      'text-sm font-medium hidden sm:inline',
                      isActive || isDone ? 'text-foreground' : 'text-muted-foreground',
                    ].join(' ')}
                  >
                    {step.label}
                  </span>
                </div>
                {index < STEPS.length - 1 && (
                  <ChevronRight className="w-4 h-4 text-muted-foreground mx-2" />
                )}
              </div>
            );
          })}
        </div>

        {/* Step 1: Select Integration */}
        {currentStep === 'select-integration' && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle>Select Integration</CardTitle>
              <CardDescription>Choose where to create the issue</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {!statusLoaded && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              )}

              {statusLoaded && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Linear */}
                  {isConnected ? (
                    <button
                      onClick={handleSelectLinear}
                      className="p-4 rounded-lg border-2 border-border hover:border-primary/50 text-left transition-all"
                    >
                      <div className="flex items-start gap-3">
                        <div className="p-2 bg-secondary rounded-lg">
                          <GitBranch className="w-6 h-6 text-[#5E6AD2]" />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground">Linear</span>
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">Connected to {connectionStatus?.org_name}</p>
                        </div>
                      </div>
                    </button>
                  ) : (
                    <div className="p-4 rounded-lg border-2 border-border bg-muted/30 opacity-60 cursor-not-allowed">
                      <div className="flex items-start gap-3">
                        <div className="p-2 bg-secondary rounded-lg">
                          <GitBranch className="w-6 h-6 text-[#5E6AD2]" />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground">Linear</span>
                            <Badge variant="secondary" className="text-xs">Not connected</Badge>
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">Connect in Settings &rarr; Integrations</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* JIRA */}
                  <div className="p-4 rounded-lg border-2 border-border bg-muted/30 opacity-60 cursor-not-allowed">
                    <div className="flex items-start gap-3">
                      <div className="p-2 bg-secondary rounded-lg">
                        <ExternalLink className="w-6 h-6 text-blue-500" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground">JIRA</span>
                          <Badge variant="secondary" className="text-xs">Coming soon</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">Atlassian JIRA integration</p>
                      </div>
                    </div>
                  </div>

                  {/* Asana */}
                  <div className="p-4 rounded-lg border-2 border-border bg-muted/30 opacity-60 cursor-not-allowed">
                    <div className="flex items-start gap-3">
                      <div className="p-2 bg-secondary rounded-lg">
                        <ExternalLink className="w-6 h-6 text-pink-500" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground">Asana</span>
                          <Badge variant="secondary" className="text-xs">Coming soon</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">Asana project management</p>
                      </div>
                    </div>
                  </div>

                  {/* GitHub Issues */}
                  <div className="p-4 rounded-lg border-2 border-border bg-muted/30 opacity-60 cursor-not-allowed">
                    <div className="flex items-start gap-3">
                      <div className="p-2 bg-secondary rounded-lg">
                        <ExternalLink className="w-6 h-6 text-gray-500" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground">GitHub Issues</span>
                          <Badge variant="secondary" className="text-xs">Coming soon</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">GitHub issue tracking</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Navigation */}
              <div className="flex justify-between pt-4 border-t border-border">
                <Button
                  variant="outline"
                  onClick={() => router.push(`/feedbacks/${feedbackId}`)}
                >
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Back
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 2: Configure (Linear form) */}
        {currentStep === 'configure' && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle>Configure Linear Issue</CardTitle>
              <CardDescription>Fill in the issue details to create in Linear</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
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
              <div className="space-y-2">
                <label className="text-sm font-medium">Title</label>
                <Input
                  value={form.title}
                  onChange={e => setForm(prev => ({ ...prev, title: e.target.value }))}
                  placeholder="Issue title"
                />
              </div>

              {/* Description */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Description</label>
                <Textarea
                  value={form.description}
                  onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Issue description (markdown supported)"
                  rows={5}
                />
              </div>

              {/* Team + Priority row */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Team</label>
                  <Select
                    value={form.teamId}
                    onValueChange={val => setForm(prev => ({ ...prev, teamId: val, projectId: '' }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select team..." />
                    </SelectTrigger>
                    <SelectContent>
                      {teams.map(t => (
                        <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
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
                <div className="space-y-2">
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

              {/* Error */}
              {createError && (
                <div className="p-4 bg-destructive/10 text-destructive rounded-lg flex items-center gap-2">
                  <AlertCircle className="w-5 h-5 flex-shrink-0" />
                  {createError}
                </div>
              )}

              {/* Navigation */}
              <div className="flex justify-between pt-4 border-t border-border">
                <Button variant="outline" onClick={() => setCurrentStep('select-integration')}>
                  Back
                </Button>
                <Button onClick={handleSubmit} disabled={submitting || !form.title || !form.teamId}>
                  {submitting ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Creating...</>
                  ) : (
                    'Create Issue'
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 3: Done */}
        {currentStep === 'done' && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle>Issue Created</CardTitle>
              <CardDescription>Your issue has been created and linked to this feedback</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {createdIssue ? (
                <>
                  <div className="flex items-center gap-3 p-4 bg-green-50 dark:bg-green-950 rounded-lg border border-green-200 dark:border-green-800">
                    <div className="p-2 bg-green-100 dark:bg-green-950 rounded-full">
                      <CheckCircle className="w-6 h-6 text-green-600" />
                    </div>
                    <div>
                      <p className="font-semibold text-green-800 dark:text-green-200">
                        {createdIssue.linear_issue_identifier}
                      </p>
                      <p className="text-sm text-muted-foreground">{createdIssue.linear_issue_title}</p>
                    </div>
                  </div>

                  <div className="p-4 bg-muted/50 rounded-lg space-y-3">
                    <div className="text-sm">
                      <span className="text-muted-foreground">Identifier:</span>
                      <span className="text-foreground font-mono ml-2">{createdIssue.linear_issue_identifier}</span>
                    </div>
                    <div className="text-sm">
                      <span className="text-muted-foreground">Title:</span>
                      <span className="text-foreground ml-2">{createdIssue.linear_issue_title}</span>
                    </div>
                    {createdUrl && (
                      <div className="text-sm">
                        <span className="text-muted-foreground">Link:</span>
                        <a
                          href={createdUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline ml-2 inline-flex items-center gap-1"
                        >
                          Open in Linear
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              )}

              {/* Navigation */}
              <div className="flex justify-between pt-4 border-t border-border">
                <div />
                <Button onClick={() => router.push(`/feedbacks/${feedbackId}`)}>
                  Done
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
