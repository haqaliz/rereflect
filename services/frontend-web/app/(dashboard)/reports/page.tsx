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
import {
  reportsAPI,
  Report,
  REPORT_TYPE_LABELS,
  REPORT_TYPE_COLORS,
  formatDateRangeLabel,
} from '@/lib/api/reports';
import { useAuth } from '@/contexts/AuthContext';
import { ReportPreview } from '@/components/copilot/ReportPreview';
import { UpgradeCTA } from '@/components/copilot/UpgradeCTA';
import {
  FileBarChart,
  Download,
  Trash2,
  Eye,
  Loader2,
  FileText,
  ArrowRight,
} from 'lucide-react';
import { toast } from 'sonner';

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function ReportsPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [previewReport, setPreviewReport] = useState<Report | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  // Plan gate: Business+ only
  const isBusinessOrEnterprise =
    user?.plan === 'business' || user?.plan === 'enterprise';

  useEffect(() => {
    if (!isBusinessOrEnterprise) return;
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
  }, [isBusinessOrEnterprise]);

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

      {/* Plan gate */}
      {!isBusinessOrEnterprise && (
        <Card data-testid="upgrade-cta-card">
          <CardContent className="py-12 flex flex-col items-center gap-4 text-center">
            <div className="p-4 bg-primary/10 rounded-full">
              <FileBarChart className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h3 className="text-lg font-semibold">Business Plan Required</h3>
              <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                Report generation is available on the Business plan. Upgrade to generate
                comprehensive PDF reports from your feedback data.
              </p>
            </div>
            <UpgradeCTA
              message="Upgrade to Business to unlock AI Reports"
              variant="inline"
            />
          </CardContent>
        </Card>
      )}

      {/* Report list */}
      {isBusinessOrEnterprise && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Generated Reports</CardTitle>
            <CardDescription>
              Reports are saved for future access. Business plan includes up to 20 saved reports.
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
      )}

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
    </div>
    </div>
  );
}
