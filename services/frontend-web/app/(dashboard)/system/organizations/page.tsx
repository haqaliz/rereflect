'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  adminOrgsAPI,
  type AdminOrg,
  type AdminOrgDetail,
} from '@/lib/api/admin-orgs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Building2,
  Loader2,
  Eye,
  Search,
  ChevronLeft,
  ChevronRight,
  Users,
  Shield,
  ExternalLink,
} from 'lucide-react';
import { toast } from 'sonner';
import Link from 'next/link';

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

const PLAN_COLORS: Record<string, 'default' | 'secondary' | 'success' | 'destructive'> = {
  free: 'secondary',
  pro: 'success',
  business: 'default',
  enterprise: 'destructive',
};

export default function AdminOrganizationsPage() {
  const { user } = useAuth();
  const router = useRouter();

  // List state
  const [orgs, setOrgs] = useState<AdminOrg[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);

  // Detail dialog
  const [detailOrg, setDetailOrg] = useState<AdminOrgDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const PAGE_SIZE = 50;

  // Auth guard
  useEffect(() => {
    if (user && !user.is_system_admin) {
      router.push('/dashboard');
    }
  }, [user, router]);

  // Debounced search
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Fetch orgs
  const fetchOrgs = useCallback(async () => {
    try {
      setIsLoading(true);
      const params: Record<string, unknown> = { page, page_size: PAGE_SIZE };
      if (search) params.search = search;
      const data = await adminOrgsAPI.list(params as Parameters<typeof adminOrgsAPI.list>[0]);
      setOrgs(data.organizations);
      setTotal(data.total);
    } catch {
      toast.error('Failed to load organizations');
    } finally {
      setIsLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    if (user?.is_system_admin) {
      fetchOrgs();
    }
  }, [user, fetchOrgs]);

  const handleViewDetail = async (org: AdminOrg) => {
    setIsLoadingDetail(true);
    setDetailOrg(null);
    try {
      const detail = await adminOrgsAPI.get(org.id);
      setDetailOrg(detail);
    } catch {
      toast.error('Failed to load organization details');
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  if (!user?.is_system_admin) return null;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Organizations</h1>
        <p className="text-muted-foreground">View all organizations and their members. {total} total.</p>
      </div>

      {/* Search */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by name..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="w-5 h-5" />
            All Organizations
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : orgs.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              No organizations found.
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Plan</TableHead>
                    <TableHead>Users</TableHead>
                    <TableHead>Promo</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orgs.map(org => (
                    <TableRow key={org.id}>
                      <TableCell className="font-medium">{org.name}</TableCell>
                      <TableCell>
                        <Badge variant={PLAN_COLORS[org.plan] || 'secondary'} className="capitalize">
                          {org.plan}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <Users className="w-3.5 h-3.5 text-muted-foreground" />
                          {org.user_count}
                        </div>
                      </TableCell>
                      <TableCell>
                        {org.promo_code_used ? (
                          <Badge variant="outline" className="font-mono text-xs">
                            {org.promo_code_used}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {formatDate(org.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleViewDetail(org)}
                            title="View details"
                          >
                            <Eye className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            asChild
                            title="View users in this org"
                          >
                            <Link href={`/system/users?org=${org.id}`}>
                              <ExternalLink className="w-4 h-4" />
                            </Link>
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4">
                  <span className="text-sm text-muted-foreground">
                    Page {page} of {totalPages}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page <= 1}
                      onClick={() => setPage(p => p - 1)}
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage(p => p + 1)}
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={isLoadingDetail || !!detailOrg} onOpenChange={(open) => {
        if (!open) {
          setDetailOrg(null);
          setIsLoadingDetail(false);
        }
      }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Organization Details</DialogTitle>
          </DialogHeader>
          {isLoadingDetail ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : detailOrg && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-muted-foreground">Name</span>
                  <p className="font-medium">{detailOrg.name}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Plan</span>
                  <p>
                    <Badge variant={PLAN_COLORS[detailOrg.plan] || 'secondary'} className="capitalize">
                      {detailOrg.plan}
                    </Badge>
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Users</span>
                  <p>{detailOrg.user_count} / {detailOrg.max_seats ?? 'Unlimited'}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Created</span>
                  <p>{formatDate(detailOrg.created_at)}</p>
                </div>
                {detailOrg.promo_code_used && (
                  <div>
                    <span className="text-muted-foreground">Promo Code</span>
                    <p className="font-mono">{detailOrg.promo_code_used}</p>
                  </div>
                )}
                {detailOrg.stripe_customer_id && (
                  <div>
                    <span className="text-muted-foreground">Stripe Customer</span>
                    <p className="font-mono text-xs">{detailOrg.stripe_customer_id}</p>
                  </div>
                )}
              </div>

              {/* Users List */}
              {detailOrg.users.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium mb-2">Members ({detailOrg.users.length})</h3>
                  <div className="border rounded-md divide-y">
                    {detailOrg.users.map(u => (
                      <div key={u.id} className="px-3 py-2 text-sm flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span>{u.email}</span>
                          {u.is_system_admin && (
                            <Shield className="w-3 h-3 text-primary" />
                          )}
                        </div>
                        <Badge variant="outline" className="capitalize text-xs">
                          {u.role}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetailOrg(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
