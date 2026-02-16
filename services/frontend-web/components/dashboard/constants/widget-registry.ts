import type { LucideIcon } from 'lucide-react';
import {
  MessageSquare,
  Smile,
  Meh,
  Frown,
  Gauge,
  PieChart,
  AlertTriangle,
  TrendingUp,
  LineChart,
  UserX,
  Lightbulb,
  CircleAlert,
  Tag,
  ShieldAlert,
  HeartPulse,
  Activity,
  Users,
  Sparkles,
  Bell,
  BarChart3,
} from 'lucide-react';

export type WidgetCategory =
  | 'Overview'
  | 'Charts'
  | 'Lists'
  | 'Risk'
  | 'Activity'
  | 'Intelligence';

export interface WidgetDefinition {
  id: string;
  name: string;
  description: string;
  category: WidgetCategory;
  icon: LucideIcon;
  minW: number;
  minH: number;
  defaultW: number;
  defaultH: number;
  maxW: number;
  maxH: number;
  planGate: string | null;
}

export const widgetRegistry: WidgetDefinition[] = [
  // Overview
  {
    id: 'stat-total-feedback',
    name: 'Total Feedback',
    description: 'Total number of feedback items received',
    category: 'Overview',
    icon: MessageSquare,
    minW: 2, minH: 2, defaultW: 3, defaultH: 2, maxW: 6, maxH: 3,
    planGate: null,
  },
  {
    id: 'stat-positive',
    name: 'Positive Feedback',
    description: 'Count of positive sentiment feedback',
    category: 'Overview',
    icon: Smile,
    minW: 2, minH: 2, defaultW: 3, defaultH: 2, maxW: 6, maxH: 3,
    planGate: null,
  },
  {
    id: 'stat-neutral',
    name: 'Neutral Feedback',
    description: 'Count of neutral sentiment feedback',
    category: 'Overview',
    icon: Meh,
    minW: 2, minH: 2, defaultW: 3, defaultH: 2, maxW: 6, maxH: 3,
    planGate: null,
  },
  {
    id: 'stat-negative',
    name: 'Negative Feedback',
    description: 'Count of negative sentiment feedback',
    category: 'Overview',
    icon: Frown,
    minW: 2, minH: 2, defaultW: 3, defaultH: 2, maxW: 6, maxH: 3,
    planGate: null,
  },
  {
    id: 'nps-score',
    name: 'Net Promoter Score',
    description: 'NPS gauge with trend',
    category: 'Overview',
    icon: Gauge,
    minW: 3, minH: 3, defaultW: 4, defaultH: 3, maxW: 6, maxH: 5,
    planGate: null,
  },

  // Charts
  {
    id: 'sentiment-donut',
    name: 'Sentiment Distribution',
    description: 'Donut chart of positive/neutral/negative breakdown',
    category: 'Charts',
    icon: PieChart,
    minW: 3, minH: 3, defaultW: 4, defaultH: 3, maxW: 8, maxH: 5,
    planGate: null,
  },
  {
    id: 'pain-points-bar',
    name: 'Pain Points Chart',
    description: 'Bar chart of top pain point categories',
    category: 'Charts',
    icon: BarChart3,
    minW: 3, minH: 3, defaultW: 6, defaultH: 4, maxW: 12, maxH: 6,
    planGate: null,
  },
  {
    id: 'trend-volume',
    name: 'Volume Trend',
    description: 'Line chart of feedback volume over time',
    category: 'Charts',
    icon: TrendingUp,
    minW: 3, minH: 3, defaultW: 8, defaultH: 4, maxW: 12, maxH: 6,
    planGate: 'trends_analytics',
  },
  {
    id: 'trend-sentiment',
    name: 'Sentiment Trend',
    description: 'Line chart of sentiment scores over time',
    category: 'Charts',
    icon: LineChart,
    minW: 3, minH: 3, defaultW: 8, defaultH: 4, maxW: 12, maxH: 6,
    planGate: 'trends_analytics',
  },
  {
    id: 'trend-churn',
    name: 'Churn Trend',
    description: 'Line chart of churn risk trend over time',
    category: 'Charts',
    icon: UserX,
    minW: 3, minH: 3, defaultW: 8, defaultH: 4, maxW: 12, maxH: 6,
    planGate: 'trends_analytics',
  },

  // Lists
  {
    id: 'pain-points-list',
    name: 'Pain Points List',
    description: 'Top pain points with severity and count',
    category: 'Lists',
    icon: AlertTriangle,
    minW: 3, minH: 3, defaultW: 6, defaultH: 4, maxW: 12, maxH: 8,
    planGate: null,
  },
  {
    id: 'feature-requests-list',
    name: 'Feature Requests',
    description: 'Top feature requests with priority and votes',
    category: 'Lists',
    icon: Lightbulb,
    minW: 3, minH: 3, defaultW: 6, defaultH: 4, maxW: 12, maxH: 8,
    planGate: null,
  },
  {
    id: 'urgent-feedback',
    name: 'Urgent Feedback',
    description: 'Feedback items flagged as urgent',
    category: 'Lists',
    icon: CircleAlert,
    minW: 3, minH: 3, defaultW: 6, defaultH: 4, maxW: 12, maxH: 8,
    planGate: null,
  },
  {
    id: 'top-categories',
    name: 'Top Categories',
    description: 'Most common feedback tags and categories',
    category: 'Lists',
    icon: Tag,
    minW: 3, minH: 2, defaultW: 12, defaultH: 3, maxW: 12, maxH: 5,
    planGate: null,
  },

  // Risk
  {
    id: 'churn-risk-summary',
    name: 'Churn Risk Summary',
    description: 'Overview of churn risk levels across customers',
    category: 'Risk',
    icon: ShieldAlert,
    minW: 3, minH: 3, defaultW: 6, defaultH: 4, maxW: 12, maxH: 6,
    planGate: 'enhanced_churn_prediction',
  },
  {
    id: 'at-risk-customers',
    name: 'At-Risk Customers',
    description: 'Customers with lowest health scores',
    category: 'Risk',
    icon: HeartPulse,
    minW: 3, minH: 3, defaultW: 6, defaultH: 4, maxW: 12, maxH: 8,
    planGate: 'customer_health_scores',
  },

  // Activity
  {
    id: 'activity-feed',
    name: 'Activity Feed',
    description: 'Real-time feed of latest feedback activity',
    category: 'Activity',
    icon: Activity,
    minW: 3, minH: 4, defaultW: 4, defaultH: 6, maxW: 6, maxH: 10,
    planGate: null,
  },
  {
    id: 'team-activity',
    name: 'Team Activity',
    description: 'Team member actions and response times',
    category: 'Activity',
    icon: Users,
    minW: 3, minH: 3, defaultW: 6, defaultH: 4, maxW: 12, maxH: 6,
    planGate: 'team_activity',
  },

  // Intelligence
  {
    id: 'ai-insights',
    name: 'AI Insights',
    description: 'AI-generated patterns and recommendations',
    category: 'Intelligence',
    icon: Sparkles,
    minW: 3, minH: 3, defaultW: 6, defaultH: 5, maxW: 12, maxH: 8,
    planGate: null,
  },
  {
    id: 'anomaly-alerts',
    name: 'Anomaly Alerts',
    description: 'Detected sentiment spikes and unusual patterns',
    category: 'Intelligence',
    icon: Bell,
    minW: 3, minH: 2, defaultW: 6, defaultH: 2, maxW: 12, maxH: 4,
    planGate: null,
  },
];

export const widgetRegistryMap = new Map(
  widgetRegistry.map((w) => [w.id, w])
);

export const widgetCategories: WidgetCategory[] = [
  'Overview',
  'Charts',
  'Lists',
  'Risk',
  'Activity',
  'Intelligence',
];
