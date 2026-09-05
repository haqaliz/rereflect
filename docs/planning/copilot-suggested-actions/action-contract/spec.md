# Spec: action-contract

## Problem slice

Both ends of this feature must agree on one JSON shape that neither can see the other define.
`MessageBubble.tsx:269-282` **silently skips** any unrecognised `data_type`, so a backend that
emits actions against a frontend that cannot render them has zero visible symptom. This repo
has shipped that exact failure four times (`DEV-TRACKING.md:433`). This aspect writes the
contract and the fixture that pins it, **before** either side is built.

**User outcome:** none directly. This is the guard that stops the feature shipping dead.

## In-scope

- **The item envelope.** Matches what `format_table`/`format_chart` already produce
  (`response_formatter.py:58-61`, `:171-174`): a required `data_type` discriminator plus a
  free-form `data`, with extra top-level sibling keys permitted (`chart_type` is the
  precedent).

  ```json
  {
    "data_type": "actions",
    "data": {
      "proposal_id": "<stable opaque id>",
      "actions": [
        {
          "action": "tag_customers",
          "label": "Tag these 3 customers…",
          "params": { "emails": ["a@x.com", "b@y.com", "c@z.com"] },
          "requires_input": ["tag"]
        }
      ]
    }
  }
  ```

- **`proposal_id`** — stable and deterministic for a given message + proposal, since M9's
  one-shot guard keys off it.
- **`requires_input`** — names the params the *user* must supply (the tag value). The server
  never authors these; the client collects them and sends them at execute time.
- **The golden fixture** — one committed JSON file holding a representative `actions` item,
  read by both suites. Place it where the frontend can also read it; the Intercom precedent
  (`services/worker-service/tests/fixtures/intercom_webhook_envelope.json`) puts the fixture
  in the consuming service and has the producing service read across.
- **A backend test** asserting the proposer's output equals the fixture ("this is what I
  emit").
- **A frontend test** asserting the renderer, given the fixture, produces one button per
  action with the right labels ("given this, I render N buttons").

## Out-of-scope

- The proposer logic (→ `deterministic-proposer`), the registry and execute route (→
  `action-registry`), the dialog and execute call (→ `frontend-actions-ui`).
- Typing the whole `structured_data` payload. It is raw dicts end-to-end today
  (`-> dict`, `Column(JSON)`, `Record<string, unknown>`); introducing a Pydantic model for the
  entire payload is a refactor this slice does not need. A typed model for the **actions item
  alone** is acceptable if it does not change what goes on the wire.

## Acceptance criteria

- The fixture file exists and is valid JSON matching the envelope above.
- Backend test: the proposer's emitted item, serialised, equals the fixture.
- Frontend test: rendering the fixture yields exactly one button per `actions[]` entry, with
  `label` as the accessible name.
- **Negative test (the load-bearing one):** rendering an item whose `data_type` is unknown
  produces no button and no throw — pinning the silent-skip behaviour as *deliberate* rather
  than accidental, so a future rename of `"actions"` fails loudly on the fixture test instead
  of silently in production.
- Both tests fail (RED) before the other aspects are implemented.

## Dependencies and sequencing

**First.** Everything else depends on this shape. No dependencies of its own.

## Open questions / risks

- Fixture location: mirror the Intercom precedent (fixture lives with one suite, read across)
  or duplicate it? Duplication defeats the purpose — prefer one file, one path, read twice.
- `proposal_id` derivation: message id + a hash of the action set is sufficient and needs no
  new storage. Must be stable across a re-read of the same persisted message.
