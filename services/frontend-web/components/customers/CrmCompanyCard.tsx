'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface CrmData {
  crm_company_name?: string | null;
  crm_lifecycle_stage?: string | null;
  crm_arr?: number | null;
  crm_renewal_date?: string | null;
  crm_deal_name?: string | null;
  crm_deal_stage?: string | null;
  crm_deal_amount?: number | null;
}

interface CrmCompanyCardProps {
  crm: CrmData;
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

export function CrmCompanyCard({ crm }: CrmCompanyCardProps) {
  const hasCrm = !!(
    crm.crm_company_name ||
    crm.crm_deal_name ||
    crm.crm_lifecycle_stage
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">CRM / Company</CardTitle>
      </CardHeader>
      <CardContent>
        {!hasCrm ? (
          <p className="text-sm text-muted-foreground">
            No CRM data available. Connect HubSpot in Settings to sync company and deal information.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Company</p>
                <p className="font-medium">{crm.crm_company_name ?? '—'}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Lifecycle Stage</p>
                <p className="font-medium">{crm.crm_lifecycle_stage ?? '—'}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">ARR</p>
                <p className="font-medium font-mono">{formatCurrency(crm.crm_arr)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Renewal Date</p>
                <p
                  className="font-medium"
                  style={isWithin30Days(crm.crm_renewal_date) ? { color: 'var(--chart-1)' } : undefined}
                >
                  {formatDate(crm.crm_renewal_date)}
                </p>
              </div>
            </div>
            {(crm.crm_deal_name || crm.crm_deal_stage || crm.crm_deal_amount != null) && (
              <div className="border-t border-border pt-3">
                <p className="text-xs text-muted-foreground mb-1">Open Deal</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  {crm.crm_deal_name && <span className="font-medium">{crm.crm_deal_name}</span>}
                  {crm.crm_deal_stage && (
                    <span className="text-muted-foreground">{crm.crm_deal_stage}</span>
                  )}
                  {crm.crm_deal_amount != null && (
                    <span className="font-mono">{formatCurrency(crm.crm_deal_amount)}</span>
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
