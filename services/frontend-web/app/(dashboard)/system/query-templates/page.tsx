'use client';

import { useState, useEffect, useMemo, Fragment } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  adminQueryTemplatesAPI,
  type QueryTemplate,
  type CopilotStats,
} from '@/lib/api/admin-query-templates';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { Loader2, ChevronDown, ChevronRight, Trash2, ToggleLeft, ToggleRight, BarChart3 } from 'lucide-react';
import { toast } from 'sonner';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

function truncateSql(sql: string, max = 60): string {
  return sql.length > max ? sql.slice(0, max) + '…' : sql;
}

// ─── Stat card ────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  testId,
}: {
  label: string;
  value: string | number;
  testId: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p data-testid={testId} className="text-2xl font-bold mt-1">
          {value}
        </p>
      </CardContent>
    </Card>
  );
}

// ─── Delete confirmation ──────────────────────────────────────────────────────

function DeleteConfirmDialog({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      data-testid="delete-confirm-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onCancel}
    >
      <div
        className="bg-background border border-border rounded-xl shadow-xl p-6 max-w-sm w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-semibold text-lg mb-2">Delete template?</h3>
        <p className="text-sm text-muted-foreground mb-6">
          This will permanently delete the template and all its question pattern mappings.
        </p>
        <div className="flex gap-3 justify-end">
          <Button variant="outline" data-testid="delete-confirm-no" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="destructive" data-testid="delete-confirm-yes" onClick={onConfirm}>
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function QueryTemplatesAdminPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [templates, setTemplates] = useState<QueryTemplate[]>([]);
  const [stats, setStats] = useState<CopilotStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterCreatedBy, setFilterCreatedBy] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  // Access control — admin/owner only (not just system admin, per PRD §8.2)
  const isAdminOrOwner =
    user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    if (user !== null && !isAdminOrOwner) {
      router.push('/dashboard');
      return;
    }
    if (!isAdminOrOwner) return;

    Promise.all([
      adminQueryTemplatesAPI.list(),
      adminQueryTemplatesAPI.getStats(),
    ])
      .then(([listRes, statsRes]) => {
        setTemplates(listRes.items);
        setStats(statsRes);
      })
      .catch(() => toast.error('Failed to load query templates'))
      .finally(() => setLoading(false));
  }, [user, isAdminOrOwner, router]);

  // Client-side filtering
  const filtered = useMemo(() => {
    return templates.filter((t) => {
      if (filterCreatedBy !== 'all' && t.created_by !== filterCreatedBy) return false;
      if (filterStatus === 'active' && !t.is_active) return false;
      if (filterStatus === 'disabled' && t.is_active) return false;
      return true;
    });
  }, [templates, filterCreatedBy, filterStatus]);

  const handleToggleActive = async (t: QueryTemplate) => {
    try {
      const updated = await adminQueryTemplatesAPI.update(t.id, { is_active: !t.is_active });
      setTemplates((prev) => prev.map((x) => (x.id === t.id ? updated : x)));
      toast.success(updated.is_active ? 'Template enabled' : 'Template disabled');
    } catch {
      toast.error('Failed to update template');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await adminQueryTemplatesAPI.delete(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
      toast.success('Template deleted');
    } catch {
      toast.error('Failed to delete template');
    } finally {
      setConfirmDeleteId(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-3 bg-secondary rounded-xl">
          <BarChart3 className="w-8 h-8 text-primary" />
        </div>
        <div>
          <h1 className="text-3xl font-bold text-foreground">Query Templates</h1>
          <p className="text-muted-foreground">
            Auto-saved SQL templates from the AI Copilot. Manage, disable, or delete.
          </p>
        </div>
      </div>

      {/* Stats header */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Total Templates"
            value={stats.total_templates}
            testId="stat-total-templates"
          />
          <StatCard
            label="Template Hit Rate"
            value={`${stats.template_hit_rate_percent}%`}
            testId="stat-hit-rate"
          />
          <StatCard
            label="Queries Today"
            value={stats.queries_today}
            testId="stat-queries-today"
          />
          <StatCard
            label="Avg Latency (ms)"
            value={stats.avg_latency_ms}
            testId="stat-avg-latency"
          />
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          data-testid="filter-created-by"
          value={filterCreatedBy}
          onChange={(e) => setFilterCreatedBy(e.target.value)}
          className="text-sm px-3 py-1.5 rounded-lg border border-border bg-background text-foreground outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="all">All Sources</option>
          <option value="system">system</option>
          <option value="llm">llm</option>
          <option value="admin">admin</option>
        </select>

        <select
          data-testid="filter-status"
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="text-sm px-3 py-1.5 rounded-lg border border-border bg-background text-foreground outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="all">All Statuses</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </select>
      </div>

      {/* Table */}
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Templates ({filtered.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {filtered.length === 0 ? (
            <div data-testid="templates-empty-state" className="py-12 text-center text-muted-foreground">
              <BarChart3 className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p className="font-medium">No query templates yet</p>
              <p className="text-sm mt-1">
                Templates are auto-saved when the AI Copilot generates new SQL queries.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Description</TableHead>
                  <TableHead>SQL Preview</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="text-right">Uses</TableHead>
                  <TableHead>Last Used</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-24">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((t) => (
                  <Fragment key={t.id}>
                    <TableRow
                      className={!t.is_active ? 'opacity-60' : ''}
                    >
                      {/* Expand toggle */}
                      <TableCell>
                        <button
                          data-testid={`expand-btn-${t.id}`}
                          onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                          className="text-muted-foreground hover:text-foreground transition-colors"
                          aria-label={expandedId === t.id ? 'Collapse' : 'Expand'}
                        >
                          {expandedId === t.id ? (
                            <ChevronDown className="w-4 h-4" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                        </button>
                      </TableCell>

                      <TableCell className="font-medium max-w-[200px]">
                        <span className="truncate block">{t.description}</span>
                      </TableCell>

                      <TableCell>
                        <code
                          data-testid={`sql-preview-${t.id}`}
                          className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono block max-w-[240px] truncate"
                          title={t.sql_query}
                        >
                          {truncateSql(t.sql_query)}
                        </code>
                      </TableCell>

                      <TableCell>
                        <Badge
                          variant={
                            t.created_by === 'system'
                              ? 'secondary'
                              : t.created_by === 'llm'
                              ? 'default'
                              : 'outline'
                          }
                          className="text-xs capitalize"
                        >
                          {t.created_by}
                        </Badge>
                      </TableCell>

                      <TableCell className="text-right tabular-nums">
                        {t.usage_count}
                      </TableCell>

                      <TableCell className="text-muted-foreground text-sm">
                        {formatDate(t.last_used_at)}
                      </TableCell>

                      <TableCell>
                        {t.is_active ? (
                          <Badge variant="default" className="text-xs">Active</Badge>
                        ) : (
                          <Badge variant="secondary" className="text-xs">Disabled</Badge>
                        )}
                      </TableCell>

                      <TableCell>
                        <div className="flex items-center gap-1">
                          {/* Toggle active */}
                          <button
                            data-testid={`toggle-active-${t.id}`}
                            onClick={() => handleToggleActive(t)}
                            title={t.is_active ? 'Disable template' : 'Enable template'}
                            className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                          >
                            {t.is_active ? (
                              <ToggleRight className="w-4 h-4 text-primary" />
                            ) : (
                              <ToggleLeft className="w-4 h-4" />
                            )}
                          </button>

                          {/* Delete */}
                          <button
                            data-testid={`delete-btn-${t.id}`}
                            onClick={() => setConfirmDeleteId(t.id)}
                            title="Delete template"
                            className="p-1.5 rounded hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </TableCell>
                    </TableRow>

                    {/* Expanded SQL view */}
                    {expandedId === t.id && (
                      <TableRow>
                        <TableCell colSpan={8} className="bg-muted/30 px-6 py-4">
                          <p className="text-xs text-muted-foreground mb-2 font-medium uppercase tracking-wide">
                            Full SQL Query
                          </p>
                          <pre
                            data-testid={`sql-full-${t.id}`}
                            className="text-xs font-mono bg-background border border-border rounded-lg p-4 overflow-x-auto whitespace-pre-wrap break-words"
                          >
                            {t.sql_query}
                          </pre>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Delete confirmation dialog */}
      {confirmDeleteId !== null && (
        <DeleteConfirmDialog
          onConfirm={() => handleDelete(confirmDeleteId)}
          onCancel={() => setConfirmDeleteId(null)}
        />
      )}
    </div>
  );
}
