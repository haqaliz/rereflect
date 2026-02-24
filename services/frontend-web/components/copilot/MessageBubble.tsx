'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { useRouter } from 'next/navigation';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { MessageActions } from './MessageActions';
import type { ChatMessage } from './ChatArea';

// Chart colors — use CSS variables to match dashboard theme
const CHART_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)'];

// Structured table renderer
function StructuredTable({ messageId, columns, rows }: {
  messageId: number | string;
  columns: string[];
  rows: (string | number)[][];
}) {
  return (
    <div data-testid={`structured-table-${messageId}`} className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted/50 border-b border-border">
            {columns.map((col) => (
              <th key={col} className="px-3 py-2 text-left font-medium text-muted-foreground whitespace-nowrap">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2 text-foreground">{String(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Theme-aware chart tooltip (matches dashboard widgets)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs shadow-xl"
      style={{
        backgroundColor: 'var(--background)',
        borderColor: 'var(--border)',
      }}
    >
      {label != null && (
        <p className="font-medium text-foreground mb-1">{String(label)}</p>
      )}
      {payload.map((entry: any) => (
        <div key={entry.dataKey} className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: entry.color || entry.fill }}
          />
          <span className="text-muted-foreground">{entry.name ?? entry.dataKey}:</span>
          <span className="font-medium text-foreground">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

// Truncate long axis labels
const MAX_LABEL_CHARS = 18;
function truncateLabel(value: unknown): string {
  const str = String(value);
  return str.length > MAX_LABEL_CHARS ? str.slice(0, MAX_LABEL_CHARS) + '…' : str;
}

// X-axis display mode based on data point count
// ≤6  → show all labels normally
// 7-15 → show every Nth label, angled
// 16+ → hide labels entirely, show hover hint
const LABEL_THRESHOLD_ANGLE = 6;
const LABEL_THRESHOLD_HIDE = 15;

function getXAxisProps(count: number, categoryKey: string) {
  if (count > LABEL_THRESHOLD_HIDE) {
    // Too many — hide labels entirely
    return {
      dataKey: categoryKey,
      tick: false as const,
      tickLine: false,
      axisLine: false,
      height: 8,
    };
  }
  if (count > LABEL_THRESHOLD_ANGLE) {
    // Moderate — show every Nth, angled
    const interval = Math.max(1, Math.floor(count / 6)) - 1;
    return {
      dataKey: categoryKey,
      tickFormatter: truncateLabel,
      angle: -45,
      textAnchor: 'end' as const,
      height: 70,
      interval,
      tickLine: false,
      axisLine: false,
      tick: { fontSize: 10 },
    };
  }
  // Few — show all labels straight
  return {
    dataKey: categoryKey,
    tickFormatter: truncateLabel,
    interval: 0,
    tickLine: false,
    axisLine: false,
    tick: { fontSize: 11 },
  };
}

// Structured chart renderer (new format: data_type="chart", chart_type="bar"|"line"|"pie")
function StructuredChart({ messageId, chartType, data, title }: {
  messageId: number | string;
  chartType: string;
  data: Record<string, unknown>[];
  title?: string;
}) {
  if (!data || data.length === 0) return null;

  // Detect keys from first data point
  const keys = Object.keys(data[0]);
  const categoryKey = keys[0] ?? 'name';
  const valueKey = keys[1] ?? 'value';

  const hideLabels = data.length > LABEL_THRESHOLD_HIDE;
  const xAxisProps = getXAxisProps(data.length, categoryKey);

  return (
    <div data-testid={`structured-chart-${messageId}`} className="space-y-2">
      {title && <p className="text-sm font-medium text-foreground">{title}</p>}
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          {chartType === 'line' ? (
            <LineChart data={data}>
              <XAxis {...xAxisProps} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--muted)', opacity: 0.3 }} />
              <Line type="monotone" dataKey={valueKey} stroke={CHART_COLORS[0]} dot={false} />
            </LineChart>
          ) : chartType === 'pie' ? (
            <PieChart>
              <Pie data={data} dataKey={valueKey} nameKey={categoryKey} cx="50%" cy="50%" outerRadius={70}>
                {data.map((_, index) => (
                  <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--muted)', opacity: 0.3 }} />
            </PieChart>
          ) : (
            <BarChart data={data}>
              <XAxis {...xAxisProps} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--muted)', opacity: 0.3 }} />
              <Bar dataKey={valueKey} fill={CHART_COLORS[0]} radius={[8, 8, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
      {hideLabels && (
        <p className="text-xs text-muted-foreground text-center">
          Hover over bars for details
        </p>
      )}
    </div>
  );
}

// Markdown link + code components
function makeMarkdownComponents(messageId: number | string, onLinkClick: (href: string) => void) {
  return {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    code({ inline, className, children, ...props }: any) {
      const match = /language-(\w+)/.exec(className ?? '');
      const lang = match ? match[1] : '';
      if (!inline) {
        return (
          <div data-testid={`code-block-${messageId}`}>
            <SyntaxHighlighter style={oneDark} language={lang || undefined} PreTag="div"
              className="rounded-lg text-xs !mt-2 !mb-2" {...props}>
              {String(children).replace(/\n$/, '')}
            </SyntaxHighlighter>
          </div>
        );
      }
      return (
        <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono" {...props}>
          {children}
        </code>
      );
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    a({ href, children, ...props }: any) {
      const isInternal = href && !href.startsWith('http');
      if (isInternal) {
        return (
          <a href={href} onClick={(e) => { e.preventDefault(); onLinkClick(href); }}
            className="text-primary underline hover:opacity-80 cursor-pointer" {...props}>
            {children}
          </a>
        );
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer"
          className="text-primary underline hover:opacity-80" {...props}>
          {children}
        </a>
      );
    },
  };
}

// Main component
interface MessageBubbleProps {
  message: ChatMessage;
  onRegenerate?: (messageId: number | string) => void;
}

export function MessageBubble({ message, onRegenerate }: MessageBubbleProps) {
  const router = useRouter();
  const isUser = message.role === 'user';

  const handleLinkClick = (href: string) => { router.push(href); };

  // Parse structured data — supports both new pipeline format and legacy format
  // New format: { text, structured_data: [{data_type: "table", data: {...}}, {data_type: "chart", ...}] }
  // Legacy format: { kind: "table", columns: [...], rows: [...] }
  const raw = message.structured_data as Record<string, unknown> | Record<string, unknown>[] | null;

  let tableItem: { columns: string[]; rows: (string | number)[][] } | null = null;
  let chartItem: { chartType: string; data: Record<string, unknown>[]; title?: string } | null = null;

  if (raw) {
    // New pipeline format: structured_data is array or has .structured_data array
    const items = Array.isArray(raw)
      ? raw
      : Array.isArray(raw.structured_data)
        ? (raw.structured_data as Record<string, unknown>[])
        : null;

    if (items) {
      for (const item of items) {
        if (item.data_type === 'table' && item.data) {
          const d = item.data as Record<string, unknown>;
          tableItem = {
            columns: d.columns as string[],
            rows: d.rows as (string | number)[][],
          };
        } else if (item.data_type === 'chart' && item.data) {
          chartItem = {
            chartType: (item.chart_type as string) ?? 'bar',
            data: item.data as Record<string, unknown>[],
          };
        }
      }
    } else if (!Array.isArray(raw)) {
      // Legacy format: { kind: "table"|"bar_chart"|... }
      const kind = (raw.kind as string) ?? '';
      if (kind === 'table' && raw.columns && raw.rows) {
        tableItem = {
          columns: raw.columns as string[],
          rows: raw.rows as (string | number)[][],
        };
      } else if (kind.endsWith('_chart') && raw.data) {
        const legacyType = kind.replace('_chart', '');
        chartItem = {
          chartType: legacyType,
          data: raw.data as Record<string, unknown>[],
          title: raw.title as string | undefined,
        };
      }
    }
  }

  return (
    <div
      data-testid={`message-bubble-${message.id}`}
      data-role={message.role}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}
    >
      <div className={`max-w-[75%] ${
        isUser
          ? 'bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-3'
          : 'bg-muted/50 text-foreground rounded-2xl rounded-tl-sm px-4 py-3 w-full'
      }`}>
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="space-y-4">
            <div className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={makeMarkdownComponents(message.id, handleLinkClick)}>
                {message.content}
              </ReactMarkdown>
            </div>
            {tableItem && (
              <StructuredTable
                messageId={message.id}
                columns={tableItem.columns}
                rows={tableItem.rows}
              />
            )}
            {chartItem && (
              <StructuredChart
                messageId={message.id}
                chartType={chartItem.chartType}
                data={chartItem.data}
                title={chartItem.title}
              />
            )}
            <MessageActions messageId={message.id} content={message.content} onRegenerate={onRegenerate} />
          </div>
        )}
      </div>
    </div>
  );
}
