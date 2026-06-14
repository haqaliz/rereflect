import React from 'react';
import { ArrowDown, Sparkles } from 'lucide-react';

const metrics = [
  {
    before: '10 hrs/week',
    after: '30 min/week',
    label: 'Manual review time saved',
  },
  {
    before: '2+ days',
    after: '< 1 hour',
    label: 'Time to respond to churn signals',
  },
  {
    before: 'Gut feeling',
    after: 'Data-driven',
    label: 'Product roadmap decisions',
  },
];

export default function ImpactMetrics() {
  return (
    <section data-testid="impact-section" className="py-24">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-4">
            <Sparkles className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-primary">Real Impact</span>
          </div>
          <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
            What changes when feedback is organized
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {metrics.map((metric, i) => (
            <div
              key={i}
              data-testid={`metric-card-${i}`}
              className="bg-card rounded-3xl p-8 border-l-4 border-l-primary"
            >
              <p className="text-2xl font-bold text-muted-foreground line-through">
                {metric.before}
              </p>
              <div className="flex justify-center my-3 text-muted-foreground">
                <ArrowDown className="w-5 h-5" />
              </div>
              <p className="text-3xl font-bold text-primary">{metric.after}</p>
              <p className="text-sm text-muted-foreground mt-2">{metric.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
