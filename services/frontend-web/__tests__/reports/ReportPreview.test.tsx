import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReportPreview } from '@/components/copilot/ReportPreview';
import { ReportSection } from '@/lib/api/reports';

// ─── Mock Recharts (no-op in jsdom) ──────────────────────────────────────────

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-container">{children}</div>
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-line-chart">{children}</div>
  ),
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-bar-chart">{children}</div>
  ),
  PieChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-pie-chart">{children}</div>
  ),
  Line: () => null,
  Bar: () => null,
  Pie: () => null,
  Cell: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
}));

// ─── Test data ────────────────────────────────────────────────────────────────

const mockSections: ReportSection[] = [
  {
    heading: 'Overview',
    narrative: 'We received 300 feedback items this month. Sentiment was mostly positive.',
  },
  {
    heading: 'Sentiment Analysis',
    narrative: 'Positive sentiment increased by 12% compared to the previous period.',
    data: {
      type: 'table',
      columns: ['Sentiment', 'Count', 'Percentage'],
      rows: [
        ['positive', 120, '40%'],
        ['neutral', 100, '33%'],
        ['negative', 80, '27%'],
      ],
    },
    chart: {
      type: 'line',
      data: [
        { date: '2026-03-01', score: 0.45 },
        { date: '2026-03-15', score: 0.55 },
      ],
    },
  },
];

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ReportPreview', () => {
  it('test_renders_sections', () => {
    render(<ReportPreview sections={mockSections} />);

    // Headings
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Sentiment Analysis')).toBeInTheDocument();

    // Narratives
    expect(
      screen.getByText(/We received 300 feedback items this month/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Positive sentiment increased by 12%/)
    ).toBeInTheDocument();
  });

  it('test_renders_table_when_data_present', () => {
    render(<ReportPreview sections={mockSections} />);

    // Table columns
    expect(screen.getByText('Sentiment')).toBeInTheDocument();
    expect(screen.getByText('Count')).toBeInTheDocument();
    expect(screen.getByText('Percentage')).toBeInTheDocument();

    // Table rows
    expect(screen.getByText('positive')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('40%')).toBeInTheDocument();
  });

  it('test_renders_download_button', () => {
    const onDownload = vi.fn();

    render(
      <ReportPreview
        sections={mockSections}
        isStreaming={false}
        reportId={42}
        onDownloadPDF={onDownload}
      />
    );

    const downloadBtn = screen.getByTestId('download-pdf-button');
    expect(downloadBtn).toBeInTheDocument();
    expect(downloadBtn).toHaveTextContent(/Download PDF/i);

    fireEvent.click(downloadBtn);
    expect(onDownload).toHaveBeenCalledOnce();
  });

  it('test_loading_state', () => {
    render(<ReportPreview sections={[]} isStreaming={true} />);

    expect(screen.getByTestId('report-streaming-indicator')).toBeInTheDocument();
    expect(screen.getByText('Generating report...')).toBeInTheDocument();

    // Download button should NOT be visible while streaming
    expect(screen.queryByTestId('download-pdf-button')).not.toBeInTheDocument();
  });

  it('test_no_download_button_without_handler', () => {
    // isStreaming=false but no onDownloadPDF provided
    render(<ReportPreview sections={mockSections} isStreaming={false} />);

    expect(screen.queryByTestId('download-pdf-button')).not.toBeInTheDocument();
  });

  it('test_renders_title_when_provided', () => {
    render(
      <ReportPreview
        sections={mockSections}
        title="Executive Summary — March 2026"
      />
    );

    expect(screen.getByText('Executive Summary — March 2026')).toBeInTheDocument();
  });
});
