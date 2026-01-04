// Category utility functions for styling and display
// Theme-aligned with Sunset Horizon color palette

// Pain Point Categories with theme-aligned colors
export const PAIN_POINT_CATEGORIES = {
  security_breach: { label: 'Security Breach', severity: 'critical', color: 'var(--destructive)' },
  data_loss: { label: 'Data Loss', severity: 'critical', color: 'var(--destructive)' },
  payment_issue: { label: 'Payment Issue', severity: 'critical', color: 'var(--destructive)' },
  system_crash: { label: 'System Crash', severity: 'major', color: 'var(--chart-1)' },
  authentication: { label: 'Authentication', severity: 'major', color: 'var(--chart-1)' },
  functionality_broken: { label: 'Functionality Broken', severity: 'major', color: 'var(--chart-5)' },
  performance: { label: 'Performance', severity: 'moderate', color: 'var(--chart-4)' },
  usability: { label: 'Usability', severity: 'moderate', color: 'var(--chart-2)' },
  compatibility: { label: 'Compatibility', severity: 'moderate', color: 'var(--chart-4)' },
  missing_feature: { label: 'Missing Feature', severity: 'minor', color: 'var(--accent)' },
  documentation: { label: 'Documentation', severity: 'minor', color: 'var(--chart-3)' },
  cosmetic: { label: 'Cosmetic', severity: 'trivial', color: 'var(--muted-foreground)' },
} as const;

// Feature Request Categories with theme-aligned colors
export const FEATURE_REQUEST_CATEGORIES = {
  core_functionality: { label: 'Core Functionality', priority: 'high', color: 'var(--chart-2)' },
  automation: { label: 'Automation', priority: 'high', color: 'var(--accent)' },
  integration: { label: 'Integration', priority: 'high', color: 'var(--chart-4)' },
  reporting: { label: 'Reporting', priority: 'medium', color: 'var(--chart-1)' },
  customization: { label: 'Customization', priority: 'medium', color: 'var(--primary)' },
  collaboration: { label: 'Collaboration', priority: 'medium', color: 'var(--chart-5)' },
  export_import: { label: 'Export/Import', priority: 'medium', color: 'var(--chart-3)' },
  mobile: { label: 'Mobile', priority: 'medium', color: 'var(--chart-2)' },
  notifications: { label: 'Notifications', priority: 'low', color: 'var(--chart-4)' },
  ui_enhancement: { label: 'UI Enhancement', priority: 'low', color: 'var(--accent)' },
} as const;

// Urgent Categories with theme-aligned colors
export const URGENT_CATEGORIES = {
  service_outage: { label: 'Service Outage', responseTime: 'immediate', color: 'var(--destructive)' },
  data_breach: { label: 'Data Breach', responseTime: 'immediate', color: 'var(--destructive)' },
  payment_failure: { label: 'Payment Failure', responseTime: 'immediate', color: 'var(--destructive)' },
  data_corruption: { label: 'Data Corruption', responseTime: 'immediate', color: 'var(--destructive)' },
  account_locked: { label: 'Account Locked', responseTime: '1_hour', color: 'var(--chart-1)' },
  critical_bug: { label: 'Critical Bug', responseTime: '1_hour', color: 'var(--chart-5)' },
  billing_dispute: { label: 'Billing Dispute', responseTime: '4_hours', color: 'var(--chart-4)' },
  churn_risk: { label: 'Churn Risk', responseTime: '4_hours', color: 'var(--chart-2)' },
  compliance: { label: 'Compliance', responseTime: '4_hours', color: 'var(--accent)' },
  reputation_risk: { label: 'Reputation Risk', responseTime: '24_hours', color: 'var(--chart-3)' },
} as const;

// Severity styles using theme variables
export const SEVERITY_STYLES = {
  critical: {
    bg: 'bg-destructive/20',
    text: 'text-destructive',
    border: 'border-destructive/30',
  },
  major: {
    bg: 'bg-primary/20',
    text: 'text-primary',
    border: 'border-primary/30',
  },
  moderate: {
    bg: 'bg-accent/20',
    text: 'text-accent-foreground',
    border: 'border-accent/30',
  },
  minor: {
    bg: 'bg-secondary',
    text: 'text-secondary-foreground',
    border: 'border-secondary',
  },
  trivial: {
    bg: 'bg-muted',
    text: 'text-muted-foreground',
    border: 'border-muted',
  },
} as const;

// Priority styles using theme variables
export const PRIORITY_STYLES = {
  high: {
    bg: 'bg-accent/20',
    text: 'text-accent-foreground',
    border: 'border-accent/30',
  },
  medium: {
    bg: 'bg-primary/20',
    text: 'text-primary',
    border: 'border-primary/30',
  },
  low: {
    bg: 'bg-secondary',
    text: 'text-secondary-foreground',
    border: 'border-secondary',
  },
} as const;

// Response time styles using theme variables
export const RESPONSE_TIME_STYLES = {
  immediate: {
    bg: 'bg-destructive/20',
    text: 'text-destructive',
    border: 'border-destructive/30',
    label: 'Immediate',
  },
  '1_hour': {
    bg: 'bg-primary/20',
    text: 'text-primary',
    border: 'border-primary/30',
    label: '1 Hour',
  },
  '4_hours': {
    bg: 'bg-accent/20',
    text: 'text-accent-foreground',
    border: 'border-accent/30',
    label: '4 Hours',
  },
  '24_hours': {
    bg: 'bg-secondary',
    text: 'text-secondary-foreground',
    border: 'border-secondary',
    label: '24 Hours',
  },
} as const;

// Helper functions
export function getPainPointLabel(category: string): string {
  return PAIN_POINT_CATEGORIES[category as keyof typeof PAIN_POINT_CATEGORIES]?.label || category;
}

export function getFeatureRequestLabel(category: string): string {
  return FEATURE_REQUEST_CATEGORIES[category as keyof typeof FEATURE_REQUEST_CATEGORIES]?.label || category;
}

export function getUrgentLabel(category: string): string {
  return URGENT_CATEGORIES[category as keyof typeof URGENT_CATEGORIES]?.label || category;
}

export function getSeverityStyles(severity: string) {
  return SEVERITY_STYLES[severity as keyof typeof SEVERITY_STYLES] || SEVERITY_STYLES.moderate;
}

export function getPriorityStyles(priority: string) {
  return PRIORITY_STYLES[priority as keyof typeof PRIORITY_STYLES] || PRIORITY_STYLES.medium;
}

export function getResponseTimeStyles(responseTime: string) {
  return RESPONSE_TIME_STYLES[responseTime as keyof typeof RESPONSE_TIME_STYLES] || RESPONSE_TIME_STYLES['4_hours'];
}

export function getResponseTimeLabel(responseTime: string): string {
  return RESPONSE_TIME_STYLES[responseTime as keyof typeof RESPONSE_TIME_STYLES]?.label || responseTime;
}

// Get category color for inline styles (matching tag style)
export function getPainPointColor(category: string): string {
  return PAIN_POINT_CATEGORIES[category as keyof typeof PAIN_POINT_CATEGORIES]?.color || 'var(--chart-1)';
}

export function getFeatureRequestColor(category: string): string {
  return FEATURE_REQUEST_CATEGORIES[category as keyof typeof FEATURE_REQUEST_CATEGORIES]?.color || 'var(--accent)';
}

export function getUrgentColor(category: string): string {
  return URGENT_CATEGORIES[category as keyof typeof URGENT_CATEGORIES]?.color || 'var(--destructive)';
}

// Get inline style object for category badges (same as tags)
export function getCategoryBadgeStyle(color: string) {
  return {
    backgroundColor: `color-mix(in oklch, ${color} 15%, transparent)`,
    color: color,
    borderColor: `color-mix(in oklch, ${color} 30%, transparent)`
  };
}

// Tag styles using theme colors - maps tag names to chart colors
export const TAG_STYLES: Record<string, { color: string; displayName: string }> = {
  'bug': { color: 'var(--destructive)', displayName: 'Bug' },
  'performance': { color: 'var(--chart-1)', displayName: 'Performance' },
  'ui-ux': { color: 'var(--chart-5)', displayName: 'UI/UX' },
  'feature-request': { color: 'var(--chart-2)', displayName: 'Feature Request' },
  'mobile': { color: 'var(--chart-6)', displayName: 'Mobile' },
  'web': { color: 'var(--chart-7)', displayName: 'Web' },
  'security': { color: 'var(--chart-4)', displayName: 'Security' },
  'pricing': { color: 'var(--chart-8)', displayName: 'Pricing' },
  'support': { color: 'var(--chart-9)', displayName: 'Support' },
  'documentation': { color: 'var(--chart-3)', displayName: 'Documentation' },
  'integration': { color: 'var(--accent)', displayName: 'Integration' },
  'data': { color: 'var(--chart-10)', displayName: 'Data' },
  'notification': { color: 'var(--chart-4)', displayName: 'Notification' },
  'search': { color: 'var(--chart-6)', displayName: 'Search' },
  'accessibility': { color: 'var(--chart-7)', displayName: 'Accessibility' },
};

export function getTagStyles(tag: string): { color: string; displayName: string } {
  return TAG_STYLES[tag] || { color: 'var(--muted-foreground)', displayName: tag };
}
