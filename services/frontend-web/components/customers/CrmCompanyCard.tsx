'use client';

import { useQuery } from '@tanstack/react-query';
import { customersAPI } from '@/lib/api/customers';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface CrmCompanyCardProps {
  email: string;
}

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val);
}

function formatDate(val: string | null | undefined): string {
  if (!val) return '—';
  return new Date(val).toLocaleDateString();
}

function isWithin30Days(dateStr: string | null | undefined): boolean {
  if (!dateStr) return false;
  const diff = new Date(dateStr).getTime() - Date.now();
  return diff >= 0 && diff <= 30 * 24 * 60 * 60 * 1000;
}

export function CrmCompanyCard({ email }: CrmCompanyCardProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['customer-crm', email],
    queryFn: () => customersAPI.getByEmail(email),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const hasCrm = !!(
    data?.crm_company_name ||
    data?.crm_deal_name ||
    data?.crm_lifecycle_stage
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">CRM / Company</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <div className="h-4 w-1/3 bg-muted rounded animate-pulse" />
            <div className="h-4 w-1/2 bg-muted rounded animate-pulse" />
          </div>
        ) : !hasCrm ? (
          <p className="text-sm text-muted-foreground">
            No CRM data available. Connect HubSpot in Settings to sync company and deal information.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Company</p>
                <p className="font-medium">{data.crm_company_name ?? '—'}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Lifecycle Stage</p>
                <p className="font-medium">{data.crm_lifecycle_stage ?? '—'}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">ARR</p>
                <p className="font-medium font-mono">{formatCurrency(data.crm_arr)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Renewal Date</p>
                <p
                  className="font-medium"
                  style={isWithin30Days(data.crm_renewal_date) ? { color: 'var(--chart-1)' } : undefined}
                >
                  {formatDate(data.crm_renewal_date)}
                </p>
              </div>
            </div>
            {(data.crm_deal_name || data.crm_deal_stage || data.crm_deal_amount != null) && (
              <div className="border-t border-border pt-3">
                <p className="text-xs text-muted-foreground mb-1">Open Deal</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  {data.crm_deal_name && <span className="font-medium">{data.crm_deal_name}</span>}
                  {data.crm_deal_stage && (
                    <span className="text-muted-foreground">{data.crm_deal_stage}</span>
                  )}
                  {data.crm_deal_amount != null && (
                    <span className="font-mono">{formatCurrency(data.crm_deal_amount)}</span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
