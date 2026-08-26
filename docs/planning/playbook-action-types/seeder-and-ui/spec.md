# Aspect — `seeder-and-ui`

**Slice:** M5 + M6 + M7 — the seeder converges the shipped templates, the editor offers the
5 new action types, and execution action logs become visible.

**PRD requirements:** M5, M6, M7, G1, G2.

---

## Problem slice & outcome

Existing installs converge (seeded templates stop carrying dead steps), operators can build
custom playbooks with the new actions, and a run's per-action results — including failures —
are visible in the UI instead of being buried in an unrendered `action_log`.

## In scope

### Backend — seeder (M5)

1. **Retarget New-Customer Save** (`playbook_seeder.py:192-194`): `trigger_automation`
   config `automation_name` → `"At-Risk Customer Outreach"` (a real seeded automation;
   ships in shadow — the step reports the loud `mode=off/shadow — not fired` until an
   operator activates it, per PRD M4).
2. **Update-existing path** in `seed_playbook_templates`:
   - predicate: `organization_id IS NULL AND is_template AND name == seed name` **and**
     stored `action_sequence != seed's` → update `action_sequence` (+ description) to the
     seed
   - **never** touches rows with `source_template_id` set (operator-cloned) or any
     org-owned row
   - idempotent: second run performs no updates
3. Tests in `tests/test_playbook_seeder.py`.

### Frontend — editor + executions (M6, M7)

4. **API client types** (`lib/api/playbooks.ts`): `PlaybookAction.type` union + config
   types gain `notify`, `tag`, `create_task`, `schedule_task`, `trigger_automation`;
   `ACTION_TYPE_LABELS` (:171-177) gains the 5 labels.
5. **Editor config forms** (`components/playbooks/PlaybookEditor.tsx`): per-type config
   editing + defaults, round-tripping the exact config keys the worker reads:
   - `notify`: channel select (slack/discord/dashboard), message input, optional target
     (helper text: target is advisory — the integration's configured channel is used)
   - `tag`: single tag input
   - `create_task`: description, due_in_days, priority (low/medium/high)
   - `schedule_task`: description, due_in_days (no priority)
   - `trigger_automation`: automation picker (list from the existing automations API;
     show mode + trigger type in the option label so shadow/off rules are visible)
6. **Execution surfacing** (`components/playbooks/PlaybookExecutionsList.tsx`): rows gain
   an expandable per-action view rendering `action_log` entries — type, ok/error badges
   (destructive on error, per the automations precedent `automations/[id]/page.tsx:1060-1119`),
   result summary. Status semantics unchanged (M7).

### Docs

7. Close the deferral: `docs/planning/customer-outreach-email-actions/prd.md:247-255` marked
   closed; CHANGELOG entry; `AI-TRACKING.md` + `DEV-TRACKING.md` rows updated.

## Out of scope

- S1 (customer-profile "Playbook tasks" card + read endpoint) — v2.
- Execution status semantics (`partial_failure`, etc.) — PRD N3.
- Provider task creation UI (Jira/Asana/Linear pickers in `create_task`) — v2.
- Editing the 7 seeded templates' content beyond the retarget + convergence.

## Acceptance criteria

- **AC1** — seeder: a pristine seeded row with the old `trigger_automation` config
  converges to the new one on startup; a cloned row (`source_template_id` set) and an
  org-owned row are untouched; a second seeder run is a no-op.
- **AC2** — seeder: New-Customer Save's `trigger_automation` now names
  `At-Risk Customer Outreach`.
- **AC3** — editor: each of the 5 new types is selectable, renders its config form,
  and create → edit → save round-trips the exact config keys the worker handlers read
  (verified against `playbook_engine.py`).
- **AC4** — executions list: rows expose the action log; entries render type + ok/error;
  error entries are visually distinct; result summaries render (e.g. `task_id`, channel).
- **AC5** — `npm run test` + `npm run lint` green in `services/frontend-web`; worker +
  backend suites green.
- **AC6** — docs updated (deferral closed, CHANGELOG, tracking rows).

## Dependencies & sequencing

**Last aspect** — depends on `tag-notify-actions` (labels exist), `playbook-tasks`
(`task_id` in results), `trigger-automation` (automation picker semantics).

## Risks / open questions

- The automations list API shape (`lib/api/automations.ts`) must expose `name`, `mode`,
  `trigger_type` for the picker — confirm; extend the client type if it lacks fields.
- Seeder convergence updates `action_sequence` only — operators who edited a pristine
  template's sequence keep... no: predicate requires stored sequence != seed's, so an
  operator-edited pristine row **is** converged. Flag in docs? The predicate is defined in
  the PRD (M5) and approved — but note it in the seeder docstring so it's not surprising.
- `PlaybookExecutionsList` has no existing test file — first tests land here.