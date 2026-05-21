'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Activity, Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import {
  getSystemAccuracy,
  formatMetricPercent,
  type OrgAccuracyRow,
  type SystemAccuracyResponse,
} from '@/lib/api/churn-accuracy';
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

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function StatCard({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold mt-1">{value}</p>
      </CardContent>
    </Card>
  );
}

function OrgTableRow({ org }: { org: OrgAccuracyRow }) {
  return (
    <TableRow>
      <TableCell className="font-medium">
        <Link
          href={`/system/churn-accuracy/${org.organization_id}`}
          className="hover:underline text-primary"
        >
          {org.organization_name}
        </Link>
      </TableCell>
      <TableCell>{org.label_count.toLocaleString()}</TableCell>
      <TableCell>{formatMetricPercent(org.f1)}</TableCell>
      <TableCell className="text-muted-foreground text-sm">
        {formatDate(org.last_refit_at)}
      </TableCell>
      <TableCell>
        {org.is_using_global_fallback ? (
          <Badge variant="secondary">Global</Badge>
        ) : (
          <Badge variant="outline">Dedicated</Badge>
        )}
      </TableCell>
      <TableCell>
        <Link
          href={`/system/churn-accuracy/${org.organization_id}`}
          className="text-sm text-primary hover:underline"
        >
          View history
        </Link>
      </TableCell>
    </TableRow>
  );
}

export default function ChurnAccuracyPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [data, setData] = useState<SystemAccuracyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Auth guard
  useEffect(() => {
    if (user && !user.is_system_admin) {
      router.push('/dashboard');
    }
  }, [user, router]);

  const fetchData = useCallback(async () => {
    if (!user?.is_system_admin) return;
    setLoading(true);
    setError(false);
    try {
      const result = await getSystemAccuracy();
      setData(result);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (!user?.is_system_admin) return null;

  // Sort orgs by label_count descending
  const sortedOrgs = data
    ? [...data.orgs].sort((a, b) => b.label_count - a.label_count)
    : [];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Activity className="w-6 h-6 text-[var(--chart-1)]" />
          Churn Accuracy
        </h1>
        <p className="text-muted-foreground mt-1">
          Cross-organization model accuracy and label volume overview.
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-muted-foreground">Failed to load accuracy data.</p>
          </CardContent>
        </Card>
      ) : data ? (
        <>
          {/* Summary stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <StatCard
              label="Global Model F1"
              value={formatMetricPercent(data.global_f1)}
            />
            <StatCard
              label="Global Label Count"
              value={data.global_label_count.toLocaleString()}
            />
            <StatCard
              label="Orgs Using Global"
              value={data.total_orgs_using_global}
            />
            <StatCard
              label="Orgs with Dedicated Model"
              value={data.total_orgs_with_dedicated_model}
            />
          </div>

          {/* Org table */}
          <Card>
            <CardHeader>
              <CardTitle>Organizations</CardTitle>
            </CardHeader>
            <CardContent>
              {sortedOrgs.length === 0 ? (
                <p className="text-center text-sm text-muted-foreground py-8">
                  No organizations have labeled data yet.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Organization</TableHead>
                      <TableHead>Label Count</TableHead>
                      <TableHead>F1 Score</TableHead>
                      <TableHead>Last Refit</TableHead>
                      <TableHead>Model</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedOrgs.map((org) => (
                      <OrgTableRow key={org.organization_id} org={org} />
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
