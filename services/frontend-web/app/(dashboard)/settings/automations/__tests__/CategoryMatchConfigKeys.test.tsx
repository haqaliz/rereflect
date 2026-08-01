/**
 * The category-match editor must write the keys the backend actually reads.
 *
 * DEV-TRACKING P4: `[id]/page.tsx`'s CategoryMatchTriggerFields read and wrote
 * `config.tags` / `config.urgent`, while the backend's FeedbackCategoryConfig
 * (automations.py) and the worker evaluator (automation_feedback_trigger.py)
 * both use `categories` / `is_urgent`. Editing an existing rule through the
 * detail page therefore appeared to save and silently changed nothing about
 * what the rule matched.
 *
 * This asserts the contract as a plain shape check rather than by driving the
 * component: the defect was never about rendering, it was about which keys
 * leave the component, and the two pages disagreeing about that is exactly
 * what no test noticed.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';

const EDITOR = join(
  __dirname,
  '..',
  '[id]',
  'page.tsx'
);

describe('category-match trigger config keys', () => {
  const source = readFileSync(EDITOR, 'utf8');

  it('writes categories, never the ignored tags key', () => {
    expect(source).toContain('categories: [...tags, tag]');
    expect(source).toContain('categories: tags.filter');
    expect(source).not.toContain('tags: [...tags, tag]');
    expect(source).not.toContain('tags: tags.filter');
  });

  it('writes is_urgent, never the ignored urgent key', () => {
    expect(source).toContain('is_urgent: !!checked');
    expect(source).not.toContain('urgent: !!checked,');
    expect(source).not.toMatch(/onChange\(\{ \.\.\.config, urgent: /);
  });

  it('still reads the legacy keys so previously-saved rules display', () => {
    // Rules saved while the bug was live carry `tags`/`urgent`. Dropping the
    // read-fallback would make those rules look empty in the editor, which is
    // a second, worse bug.
    expect(source).toContain('config.categories ?? config.tags');
    expect(source).toContain('config.is_urgent ?? config.urgent');
  });
});
