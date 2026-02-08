'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  sharedLinksAPI,
  type SharedLink,
  type PaginatedSharedLinks,
  type SharedLinksFilter,
} from '@/lib/api/analytics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Copy,
  Check,
  Eye,
  Trash2,
  Link as LinkIcon,
  Search,
  ChevronLeft,
  ChevronRight,
  Shield,
  Clock,
  XCircle,
  ExternalLink,
} from 'lucide-react';

export default function SharedLinksPage() {
  const [data, setData] = useState<PaginatedSharedLinks | null>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<SharedLinksFilter>({ page: 1, page_size: 20 });
  const [searchInput, setSearchInput] = useState('');
  const [copiedId, setCopiedId] = useState<number | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await sharedLinksAPI.listAll(filters);
      setData(result);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSearch = () => {
    setFilters(prev => ({ ...prev, page: 1, search: searchInput || undefined }));
  };

  const handleStatusFilter = (value: string) => {
    setFilters(prev => ({
      ...prev,
      page: 1,
      status: value === 'all' ? undefined : value as SharedLinksFilter['status'],
    }));
  };

  const handleDateFrom = (value: string) => {
    setFilters(prev => ({ ...prev, page: 1, date_from: value || undefined }));
  };

  const handleDateTo = (value: string) => {
    setFilters(prev => ({ ...prev, page: 1, date_to: value || undefined }));
  };

  const handleDeactivate = async (id: number) => {
    try {
      await sharedLinksAPI.deactivate(id);
      fetchData();
    } catch {
      // handle error
    }
  };

  const handleCopy = async (link: SharedLink) => {
    const url = `${window.location.origin}/shared/${link.token}`;
    await navigator.clipboard.writeText(url);
    setCopiedId(link.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  const getLinkStatus = (link: SharedLink): { label: string; variant: 'default' | 'secondary' | 'destructive' } => {
    if (!link.is_active) return { label: 'Deactivated', variant: 'secondary' };
    if (link.expires_at && new Date(link.expires_at) < new Date()) return { label: 'Expired', variant: 'destructive' };
    return { label: 'Active', variant: 'default' };
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Shared Links</h1>
        {data && (
          <span className="text-sm text-muted-foreground">{data.total} total links</span>
        )}
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-end gap-3 flex-wrap">
            <div className="flex-1 min-w-[200px]">
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Search</label>
              <div className="flex gap-2">
                <Input
                  placeholder="Search by token..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="h-9"
                />
                <Button variant="outline" size="sm" onClick={handleSearch} className="h-9 px-3">
                  <Search className="w-4 h-4" />
                </Button>
              </div>
            </div>

            <div className="w-[150px]">
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Status</label>
              <Select value={filters.status || 'all'} onValueChange={handleStatusFilter}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="expired">Expired</SelectItem>
                  <SelectItem value="deactivated">Deactivated</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="w-[160px]">
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Created from</label>
              <Input
                type="date"
                value={filters.date_from || ''}
                onChange={(e) => handleDateFrom(e.target.value)}
                className="h-9"
              />
            </div>

            <div className="w-[160px]">
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Created to</label>
              <Input
                type="date"
                value={filters.date_to || ''}
                onChange={(e) => handleDateTo(e.target.value)}
                className="h-9"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Links list */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[72px]" />
          ))}
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-16 h-16 mb-4 rounded-full bg-muted flex items-center justify-center">
            <LinkIcon className="w-8 h-8 text-muted-foreground" />
          </div>
          <h2 className="text-lg font-semibold mb-1">No shared links</h2>
          <p className="text-sm text-muted-foreground max-w-md">
            Create shared links from the Analytics page to share your dashboard with others.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {data?.items.map((link) => {
            const status = getLinkStatus(link);
            return (
              <Card key={link.id}>
                <CardContent className="py-4 px-5">
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-4 min-w-0 flex-1">
                      <div className="flex items-center gap-2 min-w-0">
                        <LinkIcon className="w-4 h-4 text-muted-foreground shrink-0" />
                        <span className="font-mono text-sm truncate max-w-[240px]">
                          ...{link.token.slice(-12)}
                        </span>
                      </div>

                      <Badge variant={status.variant} className="text-xs shrink-0">
                        {status.label}
                      </Badge>

                      {link.has_password && (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground shrink-0">
                          <Shield className="w-3 h-3" /> Protected
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-4 shrink-0">
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Eye className="w-3 h-3" /> {link.view_count}
                      </span>

                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="w-3 h-3" />
                        {link.expires_at
                          ? new Date(link.expires_at).toLocaleDateString()
                          : 'Never'}
                      </span>

                      <span className="text-xs text-muted-foreground">
                        {new Date(link.created_at).toLocaleDateString()}
                      </span>

                      <div className="flex items-center gap-1">
                        {status.label === 'Active' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0"
                            onClick={() => window.open(`/shared/${link.token}`, '_blank')}
                            title="Open link"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0"
                          onClick={() => handleCopy(link)}
                          title="Copy link"
                        >
                          {copiedId === link.id ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                        </Button>
                        {link.is_active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                            onClick={() => handleDeactivate(link.id)}
                            title="Deactivate link"
                          >
                            <XCircle className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {data && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Page {data.page} of {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={data.page <= 1}
              onClick={() => setFilters(prev => ({ ...prev, page: (prev.page || 1) - 1 }))}
            >
              <ChevronLeft className="w-4 h-4 mr-1" /> Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={data.page >= totalPages}
              onClick={() => setFilters(prev => ({ ...prev, page: (prev.page || 1) + 1 }))}
            >
              Next <ChevronRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
