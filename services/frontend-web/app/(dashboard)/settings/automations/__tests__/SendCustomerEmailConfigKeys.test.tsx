/**
 * The send_customer_email editor must write EXACTLY the two keys the backend
 * accepts.
 *
 * `SendCustomerEmailConfig` (backend `automations.py`) is `extra="forbid"`, so
 * a config carrying another action type's leftovers (`recipients`, `channels`,
 * `status`, `tone`) does not "mostly work" — the whole save 422s. The `[id]`
 * page preserves config across an action-type switch for every other type,
 * which is exactly how such a config would be produced.
 *
 * Asserted as a plain source shape check (the CategoryMatchConfigKeys pattern):
 * the risk is about which keys leave the component, not about rendering, and a
 * render test would pass against a mock that never sees the real payload.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';

const NEW_PAGE = join(__dirname, '..', 'new', 'page.tsx');
const ID_PAGE = join(__dirname, '..', '[id]', 'page.tsx');

const newSource = readFileSync(NEW_PAGE, 'utf8');
const idSource = readFileSync(ID_PAGE, 'utf8');

describe.each([
  ['new/page.tsx', newSource],
  ['[id]/page.tsx', idSource],
])('send_customer_email config keys — %s', (_name, source) => {
  it('seeds the config through the single seeding helper', () => {
    expect(source).toContain('seedSendCustomerEmailConfig');
    expect(source).toContain("recipient: 'customer',");
    expect(source).toContain(
      "template: templateOptions[0]?.key ?? BUILTIN_OUTREACH_TEMPLATES[0].key,"
    );
  });

  it('reads only template and recipient off the action config', () => {
    expect(source).toContain('action.config?.template');
    expect(source).toContain('action.config?.recipient');
  });

  it('writes only template and recipient from the editor branch', () => {
    const writes = [...source.matchAll(/config: \{ \.\.\.action\.config, (\w+):/g)].map(
      m => m[1]
    );
    // Other action types write status / playbook_id from their own branches;
    // what matters is that no OTHER key is written in this file than the ones
    // those branches own plus ours.
    expect(writes).toContain('template');
    expect(writes).toContain('recipient');
    for (const key of ['recipients', 'channels', 'tone', 'assign_to']) {
      expect(writes).not.toContain(key);
    }
  });

  it('guards the recipient union when deciding a config is reusable', () => {
    expect(source).toMatch(
      /\(recipient === 'customer' \|\| recipient === 'cs_assignee'\)/
    );
  });
});

describe('send_customer_email stale-config replacement', () => {
  it('the [id] page seeds on switch-in instead of preserving the old config', () => {
    // Without this branch, switching a send_notification action to
    // send_customer_email would carry `recipients`/`channels` into a save the
    // backend rejects with a 422.
    expect(idSource).toContain("if (val === 'send_customer_email') {");
    expect(idSource).toContain(
      'config: seedSendCustomerEmailConfig(action.config, templateOptions),'
    );
  });
});
