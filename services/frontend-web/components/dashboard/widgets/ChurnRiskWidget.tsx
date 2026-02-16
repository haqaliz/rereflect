'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { UserX, Lightbulb, ArrowRight } from 'lucide-react';
import { ChurnRiskSummary, ChurnRiskItem } from '@/lib/api/dashboard';

interface ChurnRiskWidgetProps {
  summary: ChurnRiskSummary;
  topRisks: ChurnRiskItem[];
}

export function ChurnRiskWidget({ summary, topRisks }: ChurnRiskWidgetProps) {
  const router = useRouter();

  const hasData = summary.high_count > 0 || summary.medium_count > 0;

  return (
    <div className="h-full flex flex-col">
      {summary.total_at_risk > 0 && (
        <div className="flex justify-end mb-2">
          <Link
            href="/churn-risks"
            className="flex items-center space-x-1 text-sm text-primary hover:text-primary/80 font-medium transition-colors group"
          >
            <span>View All</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>
      )}
      {hasData ? (
          <div className="space-y-6">
            {/* Risk Level Counts */}
            <div className="grid grid-cols-3 gap-4">
              <div
                className="rounded-xl p-5 text-center border-2"
                style={{
                  backgroundColor: 'color-mix(in oklch, var(--destructive) 10%, transparent)',
                  borderColor: 'color-mix(in oklch, var(--destructive) 25%, transparent)',
                }}
              >
                <p className="text-3xl font-bold font-mono text-destructive">{summary.high_count}</p>
                <p className="text-sm text-muted-foreground mt-2 font-semibold uppercase tracking-wide">High Risk</p>
              </div>
              <div
                className="rounded-xl p-5 text-center border-2"
                style={{
                  backgroundColor: 'color-mix(in oklch, var(--chart-2) 10%, transparent)',
                  borderColor: 'color-mix(in oklch, var(--chart-2) 25%, transparent)',
                }}
              >
                <p className="text-3xl font-bold font-mono" style={{ color: 'var(--chart-2)' }}>{summary.medium_count}</p>
                <p className="text-sm text-muted-foreground mt-2 font-semibold uppercase tracking-wide">Medium Risk</p>
              </div>
              <div
                className="rounded-xl p-5 text-center border-2"
                style={{
                  backgroundColor: 'color-mix(in oklch, var(--chart-5) 10%, transparent)',
                  borderColor: 'color-mix(in oklch, var(--chart-5) 25%, transparent)',
                }}
              >
                <p className="text-3xl font-bold font-mono" style={{ color: 'var(--chart-5)' }}>{summary.low_count}</p>
                <p className="text-sm text-muted-foreground mt-2 font-semibold uppercase tracking-wide">Low Risk</p>
              </div>
            </div>

            {/* Top Churn Risks */}
            {topRisks.length > 0 && (
              <ul className="space-y-3">
                {topRisks.map((item) => {
                  const riskColor =
                    item.churn_risk_score > 70 ? 'var(--destructive)' :
                    item.churn_risk_score >= 40 ? 'var(--chart-2)' :
                    'var(--chart-5)';

                  return (
                    <li
                      key={item.id}
                      className="group flex justify-between items-start p-4 rounded-xl transition-all duration-200 cursor-pointer border hover:scale-[1.01] hover:shadow-md"
                      style={{
                        backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                        borderColor: 'var(--border)',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = `color-mix(in oklch, ${riskColor} 10%, var(--muted))`;
                        e.currentTarget.style.borderColor = riskColor;
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'color-mix(in oklch, var(--muted) 50%, transparent)';
                        e.currentTarget.style.borderColor = 'var(--border)';
                      }}
                      onClick={() => router.push(`/feedbacks/${item.id}`)}
                    >
                      <div className="flex-1 min-w-0 mr-4">
                        <p className="text-sm text-foreground line-clamp-2 leading-relaxed">{item.text}</p>
                        {item.suggested_action && (
                          <p className="text-xs text-muted-foreground mt-1.5 flex items-start gap-1.5">
                            <Lightbulb className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" style={{ color: 'var(--chart-2)' }} />
                            <span className="line-clamp-1">{item.suggested_action}</span>
                          </p>
                        )}
                      </div>
                      <span
                        className="px-3 py-1.5 text-sm font-bold rounded-lg font-mono flex-shrink-0"
                        style={{
                          backgroundColor: `color-mix(in oklch, ${riskColor} 20%, transparent)`,
                          color: riskColor,
                        }}
                      >
                        {item.churn_risk_score}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ) : (
          <div className="text-center py-12 text-muted-foreground">
            <UserX className="w-12 h-12 mx-auto mb-3 opacity-20" />
            <p className="text-sm">No churn risk data available yet</p>
            <p className="text-xs mt-1">Churn risk scores are generated during feedback analysis</p>
          </div>
      )}
    </div>
  );
}
