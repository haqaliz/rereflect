'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Lightbulb, ArrowRight, ChevronDown, ChevronUp, HeartPulse } from 'lucide-react';
import { CustomerHealthSummary } from '@/lib/api/dashboard';

interface AtRiskCustomersWidgetProps {
  customers: CustomerHealthSummary[];
}

export function AtRiskCustomersWidget({ customers }: AtRiskCustomersWidgetProps) {
  const router = useRouter();
  const [expandedCustomer, setExpandedCustomer] = useState<string | null>(null);

  if (customers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <HeartPulse className="w-12 h-12 mb-3 opacity-20" />
        <p className="text-sm">No at-risk customers detected</p>
        <p className="text-xs opacity-60 mt-1">All customers are in good health</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
          {customers.map((customer) => {
            const healthColor =
              customer.health_score >= 70 ? 'var(--chart-5)' :
              customer.health_score >= 50 ? 'var(--chart-2)' :
              customer.health_score >= 30 ? 'var(--chart-1)' :
              'var(--destructive)';
            const isExpanded = expandedCustomer === customer.customer_email;

            return (
              <div
                key={customer.customer_email}
                className="rounded-xl border transition-all duration-200"
                style={{
                  backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                  borderColor: isExpanded ? healthColor : 'var(--border)',
                }}
              >
                <div
                  className="flex items-center justify-between p-4 cursor-pointer hover:scale-[1.01] transition-transform"
                  onClick={() => setExpandedCustomer(isExpanded ? null : customer.customer_email)}
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <span
                      className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold font-mono flex-shrink-0"
                      style={{
                        backgroundColor: `color-mix(in oklch, ${healthColor} 20%, transparent)`,
                        color: healthColor,
                      }}
                    >
                      {customer.health_score}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">
                        {customer.customer_name || customer.customer_email}
                      </p>
                      {customer.customer_name && (
                        <p className="text-xs text-muted-foreground truncate">{customer.customer_email}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0 ml-3">
                    <span
                      className="px-2 py-0.5 text-xs font-semibold rounded-md capitalize"
                      style={{
                        backgroundColor: `color-mix(in oklch, ${healthColor} 15%, transparent)`,
                        color: healthColor,
                      }}
                    >
                      {customer.risk_level.replace('_', ' ')}
                    </span>
                    <span className="text-xs text-muted-foreground font-mono">
                      {customer.feedback_count} feedback{customer.feedback_count !== 1 ? 's' : ''}
                    </span>
                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    )}
                  </div>
                </div>

                {isExpanded && (
                  <div className="px-4 pb-4 border-t" style={{ borderColor: 'var(--border)' }}>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
                      <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--muted) 70%, transparent)' }}>
                        <p className="text-xs text-muted-foreground">Churn Risk</p>
                        <p className="text-sm font-bold font-mono text-foreground">{customer.churn_risk_component}</p>
                      </div>
                      <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--muted) 70%, transparent)' }}>
                        <p className="text-xs text-muted-foreground">Sentiment</p>
                        <p className="text-sm font-bold font-mono text-foreground">{customer.sentiment_component}</p>
                      </div>
                      <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--muted) 70%, transparent)' }}>
                        <p className="text-xs text-muted-foreground">Resolution</p>
                        <p className="text-sm font-bold font-mono text-foreground">{customer.resolution_component}</p>
                      </div>
                      <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--muted) 70%, transparent)' }}>
                        <p className="text-xs text-muted-foreground">Frequency</p>
                        <p className="text-sm font-bold font-mono text-foreground">{customer.frequency_component}</p>
                      </div>
                    </div>
                    {customer.llm_analysis && (
                      <div className="mt-3 p-3 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--chart-4) 10%, transparent)' }}>
                        <p className="text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1.5">
                          <Lightbulb className="w-3.5 h-3.5" style={{ color: 'var(--chart-4)' }} />
                          AI Analysis
                        </p>
                        <p className="text-sm text-foreground leading-relaxed">{customer.llm_analysis}</p>
                      </div>
                    )}
                    <button
                      className="mt-3 text-sm font-medium flex items-center gap-1.5 transition-colors"
                      style={{ color: 'var(--primary)' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        router.push(`/feedbacks?search=${encodeURIComponent(customer.customer_email)}`);
                      }}
                    >
                      View feedback
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
    </div>
  );
}
