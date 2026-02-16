import type { LayoutItem, ResponsiveLayouts } from 'react-grid-layout';

// 12-column grid, 80px row height
export const defaultLayout: LayoutItem[] = [
  // Row 1: 4 stat cards (3x2 each)
  { i: 'stat-total-feedback', x: 0, y: 0, w: 3, h: 2, minW: 2, minH: 2 },
  { i: 'stat-positive', x: 3, y: 0, w: 3, h: 2, minW: 2, minH: 2 },
  { i: 'stat-neutral', x: 6, y: 0, w: 3, h: 2, minW: 2, minH: 2 },
  { i: 'stat-negative', x: 9, y: 0, w: 3, h: 2, minW: 2, minH: 2 },

  // Row 2: nps-score (4x5) + sentiment-donut (4x5) + activity-feed (4x6, spans rows 2-3)
  { i: 'nps-score', x: 0, y: 2, w: 4, h: 5, minW: 3, minH: 4 },
  { i: 'sentiment-donut', x: 4, y: 2, w: 4, h: 5, minW: 3, minH: 4 },
  { i: 'activity-feed', x: 8, y: 2, w: 4, h: 6, minW: 3, minH: 4 },

  // Row 3: trend-sentiment (8x4)
  { i: 'trend-sentiment', x: 0, y: 7, w: 8, h: 4, minW: 3, minH: 3 },

  // Row 4: pain-points-bar (6x6) + feature-requests-list (6x6)
  { i: 'pain-points-bar', x: 0, y: 9, w: 6, h: 6, minW: 3, minH: 3 },
  { i: 'feature-requests-list', x: 6, y: 9, w: 6, h: 6, minW: 3, minH: 3 },

  // Row 5: churn-risk-summary (6x8) + urgent-feedback (6x6)
  { i: 'churn-risk-summary', x: 0, y: 15, w: 6, h: 8, minW: 3, minH: 3 },
  { i: 'urgent-feedback', x: 6, y: 15, w: 6, h: 6, minW: 3, minH: 3 },

  // Row 6: at-risk-customers (6x4) + ai-insights (6x8)
  { i: 'at-risk-customers', x: 0, y: 23, w: 6, h: 4, minW: 3, minH: 3 },
  { i: 'ai-insights', x: 6, y: 21, w: 6, h: 8, minW: 3, minH: 3 },

  // Row 7: top-categories (12x5)
  { i: 'top-categories', x: 0, y: 29, w: 12, h: 5, minW: 3, minH: 2 },

  // Row 8: team-activity (6x4) + anomaly-alerts (6x4)
  { i: 'team-activity', x: 0, y: 32, w: 6, h: 4, minW: 3, minH: 3 },
  { i: 'anomaly-alerts', x: 6, y: 32, w: 6, h: 4, minW: 3, minH: 2 },
];

// pain-points-list is not in the default layout but available in the catalog

// Tablet (6-col)
const tabletLayout: LayoutItem[] = [
  { i: 'stat-total-feedback', x: 0, y: 0, w: 3, h: 2, minW: 2, minH: 2 },
  { i: 'stat-positive', x: 3, y: 0, w: 3, h: 2, minW: 2, minH: 2 },
  { i: 'stat-neutral', x: 0, y: 2, w: 3, h: 2, minW: 2, minH: 2 },
  { i: 'stat-negative', x: 3, y: 2, w: 3, h: 2, minW: 2, minH: 2 },

  { i: 'nps-score', x: 0, y: 4, w: 3, h: 5, minW: 3, minH: 4 },
  { i: 'sentiment-donut', x: 3, y: 4, w: 3, h: 5, minW: 3, minH: 4 },

  { i: 'activity-feed', x: 0, y: 9, w: 6, h: 5, minW: 3, minH: 4 },
  { i: 'trend-sentiment', x: 0, y: 12, w: 6, h: 4, minW: 3, minH: 3 },

  { i: 'pain-points-bar', x: 0, y: 16, w: 6, h: 6, minW: 3, minH: 3 },
  { i: 'feature-requests-list', x: 0, y: 22, w: 6, h: 6, minW: 3, minH: 3 },

  { i: 'churn-risk-summary', x: 0, y: 28, w: 6, h: 8, minW: 3, minH: 3 },
  { i: 'urgent-feedback', x: 0, y: 36, w: 6, h: 6, minW: 3, minH: 3 },

  { i: 'at-risk-customers', x: 0, y: 42, w: 6, h: 4, minW: 3, minH: 3 },
  { i: 'ai-insights', x: 0, y: 46, w: 6, h: 8, minW: 3, minH: 3 },
  { i: 'top-categories', x: 0, y: 54, w: 6, h: 5, minW: 3, minH: 2 },


  { i: 'team-activity', x: 0, y: 57, w: 6, h: 4, minW: 3, minH: 3 },
  { i: 'anomaly-alerts', x: 0, y: 61, w: 6, h: 4, minW: 3, minH: 2 },
];

// Mobile (1-col)
const mobileLayout: LayoutItem[] = [
  { i: 'stat-total-feedback', x: 0, y: 0, w: 1, h: 2, minW: 1, minH: 2 },
  { i: 'stat-positive', x: 0, y: 2, w: 1, h: 2, minW: 1, minH: 2 },
  { i: 'stat-neutral', x: 0, y: 4, w: 1, h: 2, minW: 1, minH: 2 },
  { i: 'stat-negative', x: 0, y: 6, w: 1, h: 2, minW: 1, minH: 2 },

  { i: 'nps-score', x: 0, y: 8, w: 1, h: 5, minW: 1, minH: 4 },
  { i: 'sentiment-donut', x: 0, y: 13, w: 1, h: 5, minW: 1, minH: 4 },
  { i: 'activity-feed', x: 0, y: 18, w: 1, h: 5, minW: 1, minH: 4 },
  { i: 'trend-sentiment', x: 0, y: 19, w: 1, h: 4, minW: 1, minH: 3 },

  { i: 'pain-points-bar', x: 0, y: 23, w: 1, h: 6, minW: 1, minH: 3 },
  { i: 'feature-requests-list', x: 0, y: 29, w: 1, h: 6, minW: 1, minH: 3 },

  { i: 'churn-risk-summary', x: 0, y: 35, w: 1, h: 8, minW: 1, minH: 3 },
  { i: 'urgent-feedback', x: 0, y: 43, w: 1, h: 6, minW: 1, minH: 3 },

  { i: 'at-risk-customers', x: 0, y: 49, w: 1, h: 4, minW: 1, minH: 3 },
  { i: 'ai-insights', x: 0, y: 53, w: 1, h: 8, minW: 1, minH: 3 },
  { i: 'top-categories', x: 0, y: 61, w: 1, h: 5, minW: 1, minH: 2 },

  { i: 'team-activity', x: 0, y: 64, w: 1, h: 4, minW: 1, minH: 3 },
  { i: 'anomaly-alerts', x: 0, y: 68, w: 1, h: 4, minW: 1, minH: 2 },
];

export const responsiveLayouts: ResponsiveLayouts = {
  lg: defaultLayout,
  md: tabletLayout,
  sm: mobileLayout,
};

export const gridBreakpoints = { lg: 1280, md: 768, sm: 0 };
export const gridCols = { lg: 12, md: 6, sm: 1 };
