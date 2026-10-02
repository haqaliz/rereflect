# Aspect: sweep-guard (PRD R3)
**Outcome:** a new ungated mutation route cannot be merged unnoticed.
**In scope:** `tests/test_mutation_route_rbac_sweep.py`: AST over `src/api/routes/*.py`; per-route role dep resolved from decorator `dependencies=`, handler argument defaults, and router-level `APIRouter(dependencies=...)`; pinned `ALLOWLIST: {(module, handler): reason}` and `EXCLUDED` (public API, auth/signup, inbound webhooks, usage ingest) with reasons; stale-entry and already-gated-entry checks; self-test of the detector on synthetic source.
**Out of scope:** runtime/app.routes introspection; WebSocket routes.
**Acceptance:** guard green on the post-backend-gating tree; flips RED if a gate is removed from any gated route or an unlisted ungated route is added (proved by mutation on a temp copy / synthetic source).
**Dependencies:** after backend-gating (allowlist must reflect the final state).
**Risk:** `main.py` `include_router(dependencies=...)` — confirm none used (dig found none by grep).
