'use client';

import { Loader2, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { ReportSection } from '@/lib/api/reports';

// ─── Chart palette (Sunset Horizon) ─────────────────────────────────────────

const CHART_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
];

// ─── Section chart renderer ───────────────────────────────────────────────────

function SectionChart({ chart }: { chart: NonNullable<ReportSection['chart']> }) {
  if (chart.type === 'line') {
    const keys = chart.data.length > 0
      ? Object.keys(chart.data[0]).filter((k) => k !== 'date' && k !== 'name')
      : [];
    return (
      <div className="h-48 w-full mt-3" data-testid="report-chart-line">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chart.data}>
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            {keys.map((key, i) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={CHART_COLORS[i % CHART_COLORS.length]}
                dot={false}
                strokeWidth={2}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (chart.type === 'bar') {
    const keys = chart.data.length > 0
      ? Object.keys(chart.data[0]).filter((k) => k !== 'name')
      : [];
    return (
      <div className="h-48 w-full mt-3" data-testid="report-chart-bar">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chart.data}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            {keys.map((key, i) => (
              <Bar
                key={key}
                dataKey={key}
                fill={CHART_COLORS[i % CHART_COLORS.length]}
                radius={[3, 3, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (chart.type === 'pie') {
    return (
      <div className="h-48 w-full mt-3" data-testid="report-chart-pie">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chart.data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={70}
            >
              {chart.data.map((_: any, index: number) => (
                <Cell
                  key={`cell-${index}`}
                  fill={CHART_COLORS[index % CHART_COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return null;
}

// ─── Section renderer ─────────────────────────────────────────────────────────

function ReportSectionView({ section }: { section: ReportSection }) {
  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold text-foreground">{section.heading}</h3>
      <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">
        {section.narrative}
      </div>

      {section.data && section.data.type === 'table' && (
        <div className="rounded-lg border border-border overflow-hidden mt-3">
          <Table>
            <TableHeader>
              <TableRow>
                {section.data.columns.map((col) => (
                  <TableHead key={col} className="text-xs">
                    {col}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {section.data.rows.map((row, rowIndex) => (
                <TableRow key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <TableCell key={cellIndex} className="text-xs">
                      {String(cell)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {section.chart && <SectionChart chart={section.chart} />}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface ReportPreviewProps {
  sections: ReportSection[];
  title?: string;
  isStreaming?: boolean;
  reportId?: number;
  onDownloadPDF?: () => void;
}

export function ReportPreview({
  sections,
  title,
  isStreaming = false,
  reportId,
  onDownloadPDF,
}: ReportPreviewProps) {
  return (
    <div className="space-y-6" data-testid="report-preview">
      {title && (
        <h2 className="text-lg font-bold text-foreground">{title}</h2>
      )}

      {sections.map((section, index) => (
        <div key={index}>
          <ReportSectionView section={section} />
          {index < sections.length - 1 && (
            <hr className="mt-6 border-border" />
          )}
        </div>
      ))}

      {isStreaming && (
        <div
          className="flex items-center gap-2 text-sm text-muted-foreground"
          data-testid="report-streaming-indicator"
        >
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Generating report...</span>
        </div>
      )}

      {!isStreaming && onDownloadPDF && (
        <div className="pt-2 border-t border-border">
          <Button
            variant="outline"
            size="sm"
            onClick={onDownloadPDF}
            data-testid="download-pdf-button"
            className="gap-2"
          >
            <Download className="w-4 h-4" />
            Download PDF
          </Button>
        </div>
      )}
    </div>
  );
}
