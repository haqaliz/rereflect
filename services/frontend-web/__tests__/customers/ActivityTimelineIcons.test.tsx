import { describe, it, expect } from 'vitest';

// Import the eventIconMap directly — it is the pure data structure we want to test.
// We import the module after it has been patched by vi.mock if needed; here we need
// the real implementation so we import it directly.
import { eventIconMap } from '../../components/customers/ActivityTimeline';

describe('eventIconMap — new usage/churn event types', () => {
  const newTypes = [
    'churned',
    'churn_recovered',
    'usage_first_seen',
    'usage_feature_adopted',
    'usage_reactivated',
  ] as const;

  it.each(newTypes)('%s has an icon defined (not undefined)', (type) => {
    expect(eventIconMap[type]).toBeDefined();
    expect(eventIconMap[type].icon).toBeDefined();
  });

  it.each(newTypes)('%s has a CSS-var color (not a hardcoded hex/rgb)', (type) => {
    const config = eventIconMap[type];
    expect(config.color).toMatch(/^var\(--/);
  });

  it.each(newTypes)('%s has a CSS-var bg via color-mix', (type) => {
    const config = eventIconMap[type];
    expect(config.bg).toMatch(/color-mix/);
  });

  it('all 10 event types are represented in the map', () => {
    const allTypes = [
      'feedback_created',
      'status_changed',
      'health_score_changed',
      'llm_analysis_generated',
      'action_completed',
      'churned',
      'churn_recovered',
      'usage_first_seen',
      'usage_feature_adopted',
      'usage_reactivated',
    ] as const;
    for (const type of allTypes) {
      expect(eventIconMap[type], `Missing icon config for: ${type}`).toBeDefined();
    }
  });
});
