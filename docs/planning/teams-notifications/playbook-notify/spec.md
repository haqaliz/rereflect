# Spec: playbook-notify

## Problem slice

The churn-playbook `notify` action can target a Teams channel — worker engine branch
plus the editor's channel select, matching the existing discord precedent.

## In-scope

- Worker `services/worker-service/src/services/playbook_engine.py` `_handle_notify`
  (:580-722): `channel == "teams"` branch beside discord (:662-691), via the generic
  `_dispatch_external_notify` helper (:725-747) and the worker Teams sender.
- Frontend `services/frontend-web/components/playbooks/PlaybookEditor.tsx`:
  `NOTIFY_CHANNELS` gains `'teams'` (:32) + `NOTIFY_CHANNEL_LABELS` entry (:34-38).
- `services/frontend-web/lib/api/playbooks.ts` channel union gains `'teams'` (:17).
- Playbook `notify` channel is advisory-only for the target text (existing behavior
  unchanged); worker-side send is the real dispatch.

## Out-of-scope

New action types; task/schedule work; P7 refactor.

## Acceptance criteria

- Playbook run with a `notify` step, `channel: "teams"`, active Teams integration →
  one card per org via `_dispatch_external_notify`.
- Editor's notify-channel select offers "Teams" and persists `channel: 'teams'`.
- No Teams integration → step logs a clear skip/error (existing pattern for slack/discord).
- Worker suite + frontend playbook tests green.

## Dependencies / sequencing

Depends on `worker-dispatch` (sender). Frontend half can land with `frontend-ui` work if
scheduled later, but keep the spec self-contained.