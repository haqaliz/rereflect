'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { ChevronLeft, Activity, Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import {
  getOrgAccuracyHistory,
  formatMetricPercent,
  type OrgHistoryResponse,
} from '@/lib/api/churn-accuracy';
import { AccuracyTrendChart } from '@/components/analytics/AccuracyTrendChart';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function ChurnAccuracyDrillInPage() {
  const { user } = useAuth();
  const router = useRouter();
  const params = useParams();

  const orgIdRaw = String(params.orgId ?? '');
  const orgId = parseInt(orgIdRaw, 10);

  const [data, setData] = useState<OrgHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Auth guard
  useEffect(() => {
    if (user && !user.is_system_admin) {
      router.push('/dashboard');
    }
  }, [user, router]);

  const fetchData = useCallback(async () => {
    if (!user?.is_system_admin || isNaN(orgId)) return;
    setLoading(true);
    setError(false);
    try {
      const result = await getOrgAccuracyHistory(orgId);
      setData(result);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [user, orgId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (!user?.is_system_admin) return null;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/system/churn-accuracy"
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Back to Churn Accuracy
        </Link>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-muted-foreground">Failed to load organization history.</p>
          </CardContent>
        </Card>
      ) : data ? (
        <>
          <div>
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <Activity className="w-6 h-6 text-[var(--chart-1)]" />
              {data.organization_name}
            </h1>
            <p className="text-muted-foreground mt-1">
              Model accuracy history and backtest trend.
            </p>
          </div>

          {/* Accuracy trend chart */}
          <Card>
            <CardHeader>
              <CardTitle>Accuracy Over Time</CardTitle>
            </CardHeader>
            <CardContent>
              <AccuracyTrendChart runs={data.backtest_runs} />
            </CardContent>
          </Card>

          {/* Model version history table */}
          <Card>
            <CardHeader>
              <CardTitle>Model Version History</CardTitle>
            </CardHeader>
            <CardContent>
              {data.models.length === 0 ? (
                <p className="text-center text-sm text-muted-foreground py-8">
                  No model versions recorded yet.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Status</TableHead>
                      <TableHead>Label Count</TableHead>
                      <TableHead>Precision</TableHead>
                      <TableHead>Recall</TableHead>
                      <TableHead>F1</TableHead>
                      <TableHead>AUC</TableHead>
                      <TableHead>Fit At</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.models.map((model) => (
                      <TableRow key={model.id}>
                        <TableCell>
                          {model.is_active ? (
                            <Badge variant="default">Active</Badge>
                          ) : (
                            <Badge variant="secondary">Archived</Badge>
                          )}
                        </TableCell>
                        <TableCell>{model.label_count.toLocaleString()}</TableCell>
                        <TableCell>{formatMetricPercent(model.precision)}</TableCell>
                        <TableCell>{formatMetricPercent(model.recall)}</TableCell>
                        <TableCell>{formatMetricPercent(model.f1)}</TableCell>
                        <TableCell>{formatMetricPercent(model.auc)}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">
                          {formatDateTime(model.fit_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
