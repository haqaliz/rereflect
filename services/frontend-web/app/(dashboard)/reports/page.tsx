'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  reportsAPI,
  Report,
  REPORT_TYPE_LABELS,
  REPORT_TYPE_COLORS,
  formatDateRangeLabel,
  ReportType,
} from '@/lib/api/reports';
import {
  scheduledReportsAPI,
  ScheduledReport,
  ScheduledReportCreatePayload,
  ReportCadence,
} from '@/lib/api/scheduled-reports';
import { useAuth } from '@/contexts/AuthContext';
import { ReportPreview } from '@/components/copilot/ReportPreview';
import {
  FileBarChart,
  Download,
  Trash2,
  Eye,
  Loader2,
  FileText,
  ArrowRight,
  Plus,
  CalendarClock,
} from 'lucide-react';
import { toast } from 'sonner';

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// ─── Scheduled reports helpers ────────────────────────────────────────────────

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const REPORT_TYPE_OPTIONS = (Object.keys(REPORT_TYPE_LABELS) as ReportType[]).map((t) => ({
  value: t,
  label: REPORT_TYPE_LABELS[t],
}));

const DATE_RANGE_OPTIONS = [7, 30, 90].map((d) => ({
  value: String(d),
  label: formatDateRangeLabel(d),
}));

const CADENCE_OPTIONS = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
];

const DAY_OF_WEEK_OPTIONS = WEEKDAY_LABELS.map((label, index) => ({
  value: String(index),
  label,
}));

const DAY_OF_MONTH_OPTIONS = Array.from({ length: 31 }, (_, i) => ({
  value: String(i + 1),
  label: String(i + 1),
}));

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  value: String(i),
  label: `${String(i).padStart(2, '0')}:00`,
}));

function formatOrdinal(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n}st`;
  if (mod10 === 2 && mod100 !== 12) return `${n}nd`;
  if (mod10 === 3 && mod100 !== 13) return `${n}rd`;
  return `${n}th`;
}

function formatCadenceLabel(s: ScheduledReport): string {
  const time = `${String(s.hour_utc).padStart(2, '0')}:00 UTC`;
  if (s.cadence === 'weekly') {
    return `Weekly · ${WEEKDAY_LABELS[s.day_of_week ?? 0]} ${time}`;
  }
  if (s.cadence === 'monthly') {
    return `Monthly · ${formatOrdinal(s.day_of_month ?? 1)} · ${time}`;
  }
  return `Daily · ${time}`;
}

function parseRecipients(text: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const raw of text.split(/[,\n]+/)) {
    const email = raw.trim();
    if (!email) continue;
    const key = email.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(email);
  }
  return result;
}

// ─── Scheduled reports tab ────────────────────────────────────────────────────

function ScheduledReportsSection() {
  const { user } = useAuth();
  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  const [schedules, setSchedules] = useState<ScheduledReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  const [reportType, setReportType] = useState<ReportType>('executive_summary');
  const [dateRangeDays, setDateRangeDays] = useState<number>(30);
  const [cadence, setCadence] = useState<ReportCadence>('weekly');
  const [hourUtc, setHourUtc] = useState<number>(9);
  const [dayOfWeek, setDayOfWeek] = useState<number>(1);
  const [dayOfMonth, setDayOfMonth] = useState<number>(1);
  const [recipientsText, setRecipientsText] = useState<string>('');

  useEffect(() => {
    const fetchSchedules = async () => {
      try {
        const res = await scheduledReportsAPI.list();
        setSchedules(res);
      } catch {
        toast.error('Failed to load schedules');
      } finally {
        setLoading(false);
      }
    };
    fetchSchedules();
  }, []);

  useEffect(() => {
    if (createOpen) {
      setReportType('executive_summary');
      setDateRangeDays(30);
      setCadence('weekly');
      setHourUtc(9);
      setDayOfWeek(1);
      setDayOfMonth(1);
      setRecipientsText(user?.email ?? '');
    }
  }, [createOpen, user]);

  const handleToggle = async (schedule: ScheduledReport) => {
    setTogglingId(schedule.id);
    setSchedules((prev) =>
      prev.map((s) => (s.id === schedule.id ? { ...s, enabled: !s.enabled } : s))
    );
    try {
      const updated = await scheduledReportsAPI.toggle(schedule.id);
      setSchedules((prev) => prev.map((s) => (s.id === schedule.id ? updated : s)));
      toast.success(updated.enabled ? 'Schedule enabled' : 'Schedule paused');
    } catch {
      setSchedules((prev) => prev.map((s) => (s.id === schedule.id ? schedule : s)));
      toast.error('Failed to toggle schedule');
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    try {
      await scheduledReportsAPI.delete(id);
      setSchedules((prev) => prev.filter((s) => s.id !== id));
      setConfirmDeleteId(null);
      toast.success('Schedule deleted');
    } catch {
      toast.error('Failed to delete schedule');
    } finally {
      setDeletingId(null);
    }
  };

  const handleCreate = async () => {
    const payload: ScheduledReportCreatePayload = {
      report_type: reportType,
      date_range_days: dateRangeDays,
      cadence,
      hour_utc: hourUtc,
      recipients: parseRecipients(recipientsText),
      ...(cadence === 'weekly' ? { day_of_week: dayOfWeek } : {}),
      ...(cadence === 'monthly' ? { day_of_month: dayOfMonth } : {}),
    };
    setCreating(true);
    try {
      const created = await scheduledReportsAPI.create(payload);
      setSchedules((prev) => [created, ...prev]);
      setCreateOpen(false);
      toast.success('Schedule created');
    } catch {
      toast.error('Failed to create schedule');
    } finally {
      setCreating(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Scheduled Reports</CardTitle>
          <CardDescription>
            Deliver AI reports on a fixed cadence.
          </CardDescription>
        </div>
        {isAdminOrOwner && (
          <Button onClick={() => setCreateOpen(true)} className="gap-2" data-testid="new-schedule-button">
            <Plus className="w-4 h-4" />
            New Schedule
          </Button>
        )}
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="text-sm">Loading schedules...</span>
          </div>
        ) : schedules.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center py-16 gap-3 text-center px-4"
            data-testid="empty-state"
          >
            <CalendarClock className="w-10 h-10 text-muted-foreground/40" />
            <div>
              <p className="text-sm font-medium text-foreground">No schedules yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Create a schedule to deliver AI reports on a fixed cadence.
              </p>
            </div>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Report Type</TableHead>
                <TableHead>Schedule</TableHead>
                <TableHead>Recipients</TableHead>
                <TableHead>Last Run</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {schedules.map((schedule) => (
                <TableRow key={schedule.id} data-testid={`schedule-row-${schedule.id}`}>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className={REPORT_TYPE_COLORS[schedule.report_type]}
                      data-testid="schedule-type-badge"
                    >
                      {REPORT_TYPE_LABELS[schedule.report_type]}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {formatCadenceLabel(schedule)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {schedule.recipients.length} recipient
                    {schedule.recipients.length === 1 ? '' : 's'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {schedule.last_run_at ? formatDate(schedule.last_run_at) : '—'}
                  </TableCell>
                  <TableCell>
                    {isAdminOrOwner ? (
                      <Switch
                        checked={schedule.enabled}
                        onCheckedChange={() => handleToggle(schedule)}
                        disabled={togglingId === schedule.id}
                        aria-label={`Toggle schedule ${schedule.id}`}
                        data-testid={`toggle-schedule-${schedule.id}`}
                      />
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        {schedule.enabled ? 'Enabled' : 'Paused'}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {isAdminOrOwner && (
                      <div className="flex items-center justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setConfirmDeleteId(schedule.id)}
                          disabled={deletingId === schedule.id}
                          data-testid={`delete-schedule-${schedule.id}`}
                          className="gap-1.5 text-destructive hover:text-destructive"
                        >
                          {deletingId === schedule.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                          Delete
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {/* Create schedule dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>New Schedule</DialogTitle>
            <DialogDescription>
              Choose a report type and cadence. Reports are generated in-app and emailed
              to the recipients when RESEND_API_KEY is configured.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="report-type">Report type</Label>
              <Select
                value={reportType}
                onValueChange={(v) => setReportType(v as ReportType)}
              >
                <SelectTrigger id="report-type" aria-label="Report type" data-testid="report-type-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {REPORT_TYPE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="date-range">Date range</Label>
                <Select
                  value={String(dateRangeDays)}
                  onValueChange={(v) => setDateRangeDays(Number(v))}
                >
                  <SelectTrigger id="date-range" aria-label="Date range" data-testid="date-range-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DATE_RANGE_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="hour">Hour (UTC)</Label>
                <Select value={String(hourUtc)} onValueChange={(v) => setHourUtc(Number(v))}>
                  <SelectTrigger id="hour" aria-label="Hour (UTC)" data-testid="hour-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {HOUR_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cadence">Cadence</Label>
              <Select
                value={cadence}
                onValueChange={(v) => {
                  setCadence(v as ReportCadence);
                  setDayOfWeek(1);
                  setDayOfMonth(1);
                }}
              >
                <SelectTrigger id="cadence" aria-label="Cadence" data-testid="cadence-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CADENCE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {cadence === 'weekly' && (
              <div className="grid gap-2">
                <Label htmlFor="day-of-week">Day of week</Label>
                <Select value={String(dayOfWeek)} onValueChange={(v) => setDayOfWeek(Number(v))}>
                  <SelectTrigger id="day-of-week" aria-label="Day of week" data-testid="day-of-week-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DAY_OF_WEEK_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {cadence === 'monthly' && (
              <div className="grid gap-2">
                <Label htmlFor="day-of-month">Day of month</Label>
                <Select value={String(dayOfMonth)} onValueChange={(v) => setDayOfMonth(Number(v))}>
                  <SelectTrigger id="day-of-month" aria-label="Day of month" data-testid="day-of-month-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DAY_OF_MONTH_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="grid gap-2">
              <Label htmlFor="recipients">Recipients</Label>
              <Textarea
                id="recipients"
                placeholder="email@example.com, other@example.com"
                value={recipientsText}
                onChange={(e) => setRecipientsText(e.target.value)}
                data-testid="schedule-recipients-input"
              />
              <p className="text-xs text-muted-foreground">
                Comma or newline separated email addresses. Leave empty for in-app only.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={creating}
              data-testid="create-schedule-submit"
            >
              {creating ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Create Schedule
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete schedule confirm dialog */}
      <Dialog open={confirmDeleteId !== null} onOpenChange={() => setConfirmDeleteId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Schedule</DialogTitle>
            <DialogDescription>
              This will stop the schedule and remove it permanently. This action cannot be
              undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDeleteId(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => confirmDeleteId !== null && handleDelete(confirmDeleteId)}
              disabled={deletingId !== null}
              data-testid="confirm-delete-schedule-button"
            >
              {deletingId !== null ? (
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
              ) : null}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ReportsPage() {
  const router = useRouter();

  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [previewReport, setPreviewReport] = useState<Report | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  useEffect(() => {
    const fetchReports = async () => {
      try {
        const res = await reportsAPI.list();
        setReports(res);
      } catch {
        toast.error('Failed to load reports');
      } finally {
        setLoading(false);
      }
    };
    fetchReports();
  }, []);

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    try {
      await reportsAPI.delete(id);
      setReports((prev) => prev.filter((r) => r.id !== id));
      toast.success('Report deleted');
    } catch {
      toast.error('Failed to delete report');
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  };

  const handleViewReport = async (report: Report) => {
    // Use sections from the list item if already present, otherwise fetch the full report
    if (report.sections && report.sections.length > 0) {
      setPreviewReport(report);
      return;
    }
    setPreviewLoading(true);
    try {
      const full = await reportsAPI.get(report.id);
      setPreviewReport(full);
    } catch {
      toast.error('Failed to load report');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleDownloadPDF = async (id: number) => {
    setDownloadingId(id);
    try {
      await reportsAPI.downloadPDF(id);
    } catch {
      toast.error('Failed to download PDF');
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div className="min-h-screen pattern-bg">
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <FileBarChart className="w-6 h-6 text-primary" />
            My Reports
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            AI-generated reports from your feedback data.
          </p>
        </div>
        <Button
          onClick={() => router.push('/conversations?new=true&q=Generate+an+executive+summary+for+the+last+30+days')}
          className="gap-2"
        >
          <FileBarChart className="w-4 h-4" />
          Generate Report
        </Button>
      </div>

      <Tabs defaultValue="reports">
        <TabsList>
          <TabsTrigger value="reports">Reports</TabsTrigger>
          <TabsTrigger value="scheduled">Scheduled</TabsTrigger>
        </TabsList>

        <TabsContent value="reports">
          {/* Report list */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Generated Reports</CardTitle>
              <CardDescription>
                Reports are saved for future access.
              </CardDescription>
            </CardHeader>
              <CardContent className="p-0">
                {loading ? (
                  <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span className="text-sm">Loading reports...</span>
                  </div>
                ) : reports.length === 0 ? (
                  <div
                    className="flex flex-col items-center justify-center py-16 gap-3 text-center px-4"
                    data-testid="empty-state"
                  >
                    <FileText className="w-10 h-10 text-muted-foreground/40" />
                    <div>
                      <p className="text-sm font-medium text-foreground">No reports yet</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Generate your first report using the AI Copilot or the button above.
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-2 mt-1"
                      onClick={() =>
                        router.push(
                          '/conversations?new=true&q=Generate+an+executive+summary+for+the+last+30+days'
                        )
                      }
                    >
                      Generate a Report
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Report Type</TableHead>
                        <TableHead>Title</TableHead>
                        <TableHead>Date Range</TableHead>
                        <TableHead>Generated</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {reports.map((report) => (
                        <TableRow key={report.id} data-testid={`report-row-${report.id}`}>
                          <TableCell>
                            <Badge
                              variant="secondary"
                              className={REPORT_TYPE_COLORS[report.report_type]}
                              data-testid="report-type-badge"
                            >
                              {REPORT_TYPE_LABELS[report.report_type]}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-medium max-w-xs truncate">
                            {report.title}
                          </TableCell>
                          <TableCell className="text-muted-foreground text-sm">
                            {formatDateRangeLabel(report.date_range_days)}
                          </TableCell>
                          <TableCell className="text-muted-foreground text-sm">
                            {formatDate(report.created_at)}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleViewReport(report)}
                                disabled={previewLoading}
                                data-testid={`view-report-${report.id}`}
                                className="gap-1.5"
                              >
                                {previewLoading ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <Eye className="w-3.5 h-3.5" />
                                )}
                                View
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDownloadPDF(report.id)}
                                disabled={downloadingId === report.id}
                                data-testid={`download-report-${report.id}`}
                                className="gap-1.5"
                              >
                                {downloadingId === report.id ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <Download className="w-3.5 h-3.5" />
                                )}
                                PDF
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setConfirmDeleteId(report.id)}
                                disabled={deletingId === report.id}
                                data-testid={`delete-report-${report.id}`}
                                className="gap-1.5 text-destructive hover:text-destructive"
                              >
                                {deletingId === report.id ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <Trash2 className="w-3.5 h-3.5" />
                                )}
                                Delete
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

          {/* Delete confirm dialog */}
          <Dialog open={confirmDeleteId !== null} onOpenChange={() => setConfirmDeleteId(null)}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete Report</DialogTitle>
                <DialogDescription>
                  This will permanently delete the report. This action cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirmDeleteId(null)}>
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => confirmDeleteId !== null && handleDelete(confirmDeleteId)}
                  disabled={deletingId !== null}
                  data-testid="confirm-delete-button"
                >
                  {deletingId !== null ? (
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  ) : null}
                  Delete
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Report preview dialog */}
          <Dialog open={previewReport !== null} onOpenChange={() => setPreviewReport(null)}>
            <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{previewReport?.title}</DialogTitle>
                <DialogDescription>
                  {previewReport && REPORT_TYPE_LABELS[previewReport.report_type]} ·{' '}
                  {previewReport && formatDateRangeLabel(previewReport.date_range_days)}
                </DialogDescription>
              </DialogHeader>
              {previewReport && (
                <ReportPreview
                  sections={previewReport.sections ?? []}
                  title={undefined}
                  isStreaming={false}
                  reportId={previewReport.id}
                  onDownloadPDF={() => handleDownloadPDF(previewReport.id)}
                />
              )}
            </DialogContent>
          </Dialog>
        </TabsContent>

        <TabsContent value="scheduled">
          <ScheduledReportsSection />
        </TabsContent>
      </Tabs>
    </div>
    </div>
  );
}