'use client';

import { useState, useCallback, useMemo } from 'react';
import {
  ResponsiveGridLayout,
  useContainerWidth,
  verticalCompactor,
} from 'react-grid-layout';
import type { Layout, LayoutItem, ResponsiveLayouts } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';

import { Button } from '@/components/ui/button';
import { Settings2, RotateCcw, Plus, LayoutGrid } from 'lucide-react';
import {
  MessageSquare,
  Smile,
  Meh,
  Frown,
} from 'lucide-react';

import { WidgetWrapper } from './WidgetWrapper';
import { WidgetCatalog } from './WidgetCatalog';
import { useDashboardLayout } from './hooks/useDashboardLayout';
import {
  useDashboardStats,
  useComparison,
  useTrends,
  useActivityFeed,
  useTeamActivity,
  useAnomalies,
  useWeeklyInsights,
} from './hooks/useDashboardData';
import { widgetRegistryMap } from './constants/widget-registry';
import { gridBreakpoints, gridCols } from './constants/default-layouts';

// Widget components
import { StatCardWidget } from './widgets/StatCardWidget';
import { NpsScoreWidget } from './widgets/NpsScoreWidget';
import { SentimentDonutWidget } from './widgets/SentimentDonutWidget';
import { PainPointsBarWidget } from './widgets/PainPointsBarWidget';
import { PainPointsListWidget } from './widgets/PainPointsListWidget';
import { FeatureRequestsWidget } from './widgets/FeatureRequestsWidget';
import { UrgentFeedbackWidget } from './widgets/UrgentFeedbackWidget';
import { TopCategoriesWidget } from './widgets/TopCategoriesWidget';
import { ChurnRiskWidget } from './widgets/ChurnRiskWidget';
import { AtRiskCustomersWidget } from './widgets/AtRiskCustomersWidget';
import { AiInsightsWidget } from './widgets/AiInsightsWidget';
import { AnomalyAlertsWidget } from './widgets/AnomalyAlertsWidget';
import { TrendLineWidget } from './widgets/TrendLineWidget';
import { ActivityFeedWidget } from './widgets/ActivityFeedWidget';
import { TeamActivityWidget } from './widgets/TeamActivityWidget';

function WidgetPlaceholder({ name }: { name: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
      <LayoutGrid className="w-8 h-8 mb-2 opacity-30" />
      <p className="text-xs">{name}</p>
      <p className="text-[10px] opacity-60 mt-0.5">Coming soon</p>
    </div>
  );
}

interface DashboardGridProps {
  days: number;
}

export function DashboardGrid({ days }: DashboardGridProps) {
  const [isEditMode, setIsEditMode] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const { layouts, saveLayout, flushSave, resetLayout, addWidget, removeWidget } =
    useDashboardLayout();

  const { width, containerRef, mounted } = useContainerWidth({
    initialWidth: 1280,
  });

  // Fetch all dashboard data
  const { data: dashboardData, isLoading: statsLoading } = useDashboardStats(days);
  const { data: comparison } = useComparison(days);
  const { data: volumeTrends } = useTrends('volume', days);
  const { data: sentimentTrends } = useTrends('sentiment', days);
  const { data: churnTrends } = useTrends('churn_risk', days);
  // ActivityFeedWidget handles its own data fetching
  useActivityFeed(); // Warm up the cache
  const { data: teamMembers } = useTeamActivity();
  const { data: anomalyData } = useAnomalies();
  const { data: weeklyInsight } = useWeeklyInsights();

  const activeWidgetIds = useMemo(() => {
    const lgLayout = (layouts.lg || []) as readonly LayoutItem[];
    return lgLayout.map((item) => item.i);
  }, [layouts]);

  const handleLayoutChange = useCallback(
    (_currentLayout: Layout, allLayouts: ResponsiveLayouts) => {
      if (!isEditMode) return;
      saveLayout(allLayouts);
    },
    [isEditMode, saveLayout]
  );

  const handleReset = useCallback(() => {
    resetLayout();
    setIsEditMode(false);
  }, [resetLayout]);

  const totalFeedback = dashboardData
    ? dashboardData.sentiment.positive_count +
      dashboardData.sentiment.neutral_count +
      dashboardData.sentiment.negative_count
    : 0;

  // Compute NPS from sentiment data
  const npsScore = dashboardData && totalFeedback > 0
    ? Math.round(
        ((dashboardData.sentiment.positive_count - dashboardData.sentiment.negative_count) /
          totalFeedback) *
          100
      )
    : 0;

  function renderWidgetContent(widgetId: string) {
    if (statsLoading || !dashboardData) {
      return null; // WidgetWrapper handles loading state
    }

    switch (widgetId) {
      case 'stat-total-feedback':
        return (
          <StatCardWidget
            title="Total Feedback"
            value={dashboardData.total_feedback}
            icon={MessageSquare}
            color="blue"
            href="/feedbacks"
            deltaPct={comparison?.total_feedback_delta_pct}
            subtitle="All feedback received"
          />
        );
      case 'stat-positive':
        return (
          <StatCardWidget
            title="Positive Feedback"
            value={dashboardData.sentiment.positive_count}
            icon={Smile}
            color="green"
            href="/feedbacks?sentiment=positive"
            deltaPct={comparison?.positive_delta_pct}
            subtitle="Satisfied customers"
          />
        );
      case 'stat-neutral':
        return (
          <StatCardWidget
            title="Neutral Feedback"
            value={dashboardData.sentiment.neutral_count}
            icon={Meh}
            color="yellow"
            href="/feedbacks?sentiment=neutral"
            deltaPct={comparison?.neutral_delta_pct}
            subtitle="Mixed sentiment"
          />
        );
      case 'stat-negative':
        return (
          <StatCardWidget
            title="Negative Feedback"
            value={dashboardData.sentiment.negative_count}
            icon={Frown}
            color="red"
            href="/feedbacks?sentiment=negative"
            deltaPct={comparison?.negative_delta_pct}
            invertDelta
            subtitle="Needs attention"
          />
        );
      case 'nps-score':
        return (
          <NpsScoreWidget
            score={npsScore}
            label=""
          />
        );
      case 'sentiment-donut':
        return (
          <SentimentDonutWidget
            sentimentData={dashboardData.sentiment}
            totalFeedback={totalFeedback}
          />
        );
      case 'pain-points-bar':
        return (
          <PainPointsBarWidget
            categories={dashboardData.pain_point_categories || []}
          />
        );
      case 'pain-points-list':
        return (
          <PainPointsListWidget
            categories={dashboardData.pain_point_categories || []}
          />
        );
      case 'feature-requests-list':
        return (
          <FeatureRequestsWidget
            categories={dashboardData.feature_request_categories || []}
          />
        );
      case 'urgent-feedback':
        return (
          <UrgentFeedbackWidget
            categories={dashboardData.urgent_categories || []}
          />
        );
      case 'top-categories':
        return (
          <TopCategoriesWidget
            categories={dashboardData.top_categories || []}
          />
        );
      case 'churn-risk-summary':
        return (
          <ChurnRiskWidget
            summary={dashboardData.churn_risk_summary}
            topRisks={dashboardData.top_churn_risks || []}
          />
        );
      case 'at-risk-customers':
        return (
          <AtRiskCustomersWidget
            customers={dashboardData.at_risk_customers || []}
          />
        );
      case 'ai-insights':
        return (
          <AiInsightsWidget
            insights={weeklyInsight ?? null}
          />
        );
      case 'anomaly-alerts':
        return (
          <AnomalyAlertsWidget
            anomalies={anomalyData?.items || []}
          />
        );
      case 'trend-volume':
        return (
          <TrendLineWidget
            metric="volume"
            data={volumeTrends?.data || []}
            granularity={volumeTrends?.granularity || 'daily'}
          />
        );
      case 'trend-sentiment':
        return (
          <TrendLineWidget
            metric="sentiment"
            data={sentimentTrends?.data || []}
            granularity={sentimentTrends?.granularity || 'daily'}
          />
        );
      case 'trend-churn':
        return (
          <TrendLineWidget
            metric="churn_risk"
            data={churnTrends?.data || []}
            granularity={churnTrends?.granularity || 'daily'}
          />
        );
      case 'activity-feed':
        return <ActivityFeedWidget />;
      case 'team-activity':
        return (
          <TeamActivityWidget
            members={teamMembers || []}
          />
        );
      default: {
        const def = widgetRegistryMap.get(widgetId);
        return <WidgetPlaceholder name={def?.name || widgetId} />;
      }
    }
  }

  return (
    <div ref={containerRef} className={isEditMode ? '' : 'overflow-hidden'}>
      {/* Toolbar */}
      <div className="flex items-center justify-end gap-2 mb-4">
        {isEditMode && (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCatalogOpen(true)}
            >
              <Plus className="w-4 h-4 mr-1.5" />
              Add Widget
            </Button>
            <Button variant="outline" size="sm" onClick={handleReset}>
              <RotateCcw className="w-4 h-4 mr-1.5" />
              Reset Layout
            </Button>
          </>
        )}
        <Button
          variant={isEditMode ? 'default' : 'outline'}
          size="sm"
          onClick={() => {
            setIsEditMode((prev) => {
              if (prev) flushSave(); // Flush pending save when exiting edit mode
              return !prev;
            });
          }}
        >
          <Settings2 className="w-4 h-4 mr-1.5" />
          {isEditMode ? 'Done' : 'Customize'}
        </Button>
      </div>

      {/* Grid */}
      {mounted && (
        <div
          className={
            isEditMode
              ? 'rounded-xl border-2 border-dashed border-border/50 bg-muted/20 transition-all'
              : 'transition-all'
          }
        >
          <ResponsiveGridLayout
            width={width}
            layouts={layouts}
            breakpoints={gridBreakpoints}
            cols={gridCols}
            rowHeight={80}
            margin={[16, 16] as const}
            containerPadding={[0, 0] as const}
            compactor={verticalCompactor}
            dragConfig={{
              enabled: isEditMode,
              handle: '.drag-handle',
            }}
            resizeConfig={{
              enabled: isEditMode,
            }}
            onLayoutChange={handleLayoutChange}
          >
            {activeWidgetIds.map((widgetId) => {
              const definition = widgetRegistryMap.get(widgetId);
              if (!definition) return null;

              const isStatCard = widgetId.startsWith('stat-');

              return (
                <div key={widgetId}>
                  <WidgetWrapper
                    widgetId={widgetId}
                    title={definition.name}
                    subtitle={definition.description}
                    icon={definition.icon}
                    isEditMode={isEditMode}
                    onRemove={() => removeWidget(widgetId)}
                    isLoading={statsLoading}
                    planGated={false}
                    hideHeader={isStatCard}
                  >
                    {renderWidgetContent(widgetId)}
                  </WidgetWrapper>
                </div>
              );
            })}
          </ResponsiveGridLayout>
        </div>
      )}

      {/* Widget Catalog */}
      <WidgetCatalog
        open={catalogOpen}
        onOpenChange={setCatalogOpen}
        activeWidgetIds={activeWidgetIds}
        onAddWidget={addWidget}
      />
    </div>
  );
}
