'use client';

import { useQuery } from '@tanstack/react-query';
import { dashboardAPI, type DashboardData } from '@/lib/api/dashboard';
import { anomaliesAPI, type AnomalyListResponse } from '@/lib/api/anomalies';
import { insightsAPI, type WeeklyInsight } from '@/lib/api/insights';
import {
  dashboardV2API,
  type TrendResponse,
  type ComparisonData,
  type ActivityFeedResponse,
  type TeamMember,
} from '@/lib/api/dashboard-v2';

const STALE_TIME = 5 * 60 * 1000;
const GC_TIME = 30 * 60 * 1000;

export function useDashboardStats(days: number) {
  return useQuery<DashboardData>({
    queryKey: ['dashboard', days],
    queryFn: () => dashboardAPI.get(days),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
  });
}

export function useComparison(days: number) {
  return useQuery<ComparisonData>({
    queryKey: ['dashboard-comparison', days],
    queryFn: () => dashboardV2API.getComparison(days),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
  });
}

export function useTrends(metric: 'volume' | 'sentiment' | 'churn_risk', days: number) {
  return useQuery<TrendResponse>({
    queryKey: ['dashboard-trends', metric, days],
    queryFn: () => dashboardV2API.getTrends(metric, days),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
  });
}

export function useActivityFeed() {
  return useQuery<ActivityFeedResponse>({
    queryKey: ['activity-feed'],
    queryFn: () => dashboardV2API.getActivityFeed(),
    staleTime: 30 * 1000,
    gcTime: GC_TIME,
  });
}

export function useTeamActivity() {
  return useQuery<TeamMember[]>({
    queryKey: ['team-activity'],
    queryFn: () => dashboardV2API.getTeamActivity(),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
  });
}

export function useAnomalies() {
  return useQuery<AnomalyListResponse>({
    queryKey: ['anomalies', false],
    queryFn: () => anomaliesAPI.list(false).catch(() => ({ items: [], total: 0 })),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
  });
}

export function useWeeklyInsights() {
  return useQuery<WeeklyInsight | null>({
    queryKey: ['insights', 'weekly'],
    queryFn: () => insightsAPI.getLatest().catch(() => null),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
  });
}
