# Card — feat/oidc-sso (freeform, no GitHub issue)

**Type:** feat
**Slug:** oidc-sso
**Branch:** feat/oidc-sso
**Source:** `rereflect-next` handoff (2026-07-16). No GitHub issue — freeform
(`gh issue list --repo haqaliz/rereflect --state all --search "sso OR oidc OR saml"` → No Issues).

## Brief (from rereflect-next handoff)

Add OIDC single sign-on for self-hosted deployments. Scope slice 1 to **OIDC only** — Okta, Azure AD,
Google Workspace, and Keycloak all speak it. SAML is a separate, heavier slice, explicitly out of scope.

Reuse the proven seam in `services/backend-api/src/api/routes/auth.py:179-278` (Google OAuth: verify
external identity → map to `User` → issue the internal JWT). Keep password login (`auth.py:61`) and
Google login (`auth.py:239`) working untouched — **additive only**.

## Why this, why now (moat grounding)

- **Genuinely unbuilt, and unwritten.** `DEV-TRACKING.md:168` lists "SSO/SAML (Okta, Azure AD, Google
  Workspace)" unchecked. A grep for `SSO|SAML|OIDC|single sign|SCIM` across all 17 root `PRD-*.md`
  and all 25 `docs/planning/*/prd.md` returns **zero hits** — this is an unwritten gap, not a deferred
  item, so there is no prior scoping to inherit.
- **The only existing reference is stale.** `src/config/plans.py:203` (`"sso_saml"`) and
  `src/api/routes/billing.py` are pre-pivot billing artifacts. CLAUDE.md's Enterprise-tier framing for
  SSO is stale for the same reason.
- **No plan gate applies.** `AI-TRACKING.md:250-256` (M4.2): "Plan gate: removed — all features
  unlocked in the open-source self-hosted edition." SSO was the Enterprise gate that no longer exists;
  shipping it unlocked is the "no SSO tax" posture and on-brand for MIT self-hosted.
- **The role model it maps onto is locked.** `PRD-OSS-SELF-HOSTED-PIVOT.md:43` (D6) — "Keep RBAC
  (owner/admin/member) and `organization_id`". Multi-tenancy is explicitly preserved.
- **Deepens the self-host story** (a named moat pillar) — the standard adoption blocker for a
  team-scoped self-hosted tool with RBAC and team invites.
- **Unblocked**, unlike M5.3 (per-org churn ML), which is hard-gated on ~500 labels/org in six files.

## Known caveats carried in from the handoff

1. **No OIDC library is installed.** `services/backend-api/requirements.txt` has
   `python-jose[cryptography]==3.3.0` and `passlib[bcrypt]==1.7.4` only — **no `authlib`**. Decide
   explicitly in the PRD: add `authlib`, or hand-roll the auth-code exchange and verify the ID token
   via python-jose against the provider's JWKS.
2. **Org mapping for a first-time SSO user is an open product decision**, not a coding one.
   Auto-provision vs invite-only vs email-domain match — and at what default role, given
   owner/admin/member. **Settle before coding.**
3. **Auth is the riskiest surface in the app.** Strictly additive: password login (`auth.py:61`) and
   Google OAuth (`auth.py:239`) must keep working untouched.
4. **SAML ≠ OIDC.** Slice 1 is OIDC only; SAML is a much heavier lift.
5. **Testing** wants a local Keycloak (docker-compose) as the IdP under test.

## Out of scope (slice 1)

- SAML (separate, later slice)
- SCIM / directory provisioning + deprovisioning
- Changing or removing password login or Google OAuth
- Any plan gating (all features unlocked post-pivot)

## Open questions for the dig / PRD

- Which org does a first-time SSO user land in, and at what default role?
- Is SSO config per-org (DB row) or per-deployment (env)? Single-tenant self-host suggests env may
  suffice — but multi-tenancy is explicitly preserved (`PRD-OSS-SELF-HOSTED-PIVOT.md:43`).
- Can an operator *require* SSO (disable password login) for their deployment? Tension with caveat 3
  unless opt-in.
- How does SSO interact with the existing team-invite flow (`src/api/routes/team.py`)?
- Where do client secrets live? Is there an existing reversible-secret pattern to reuse (CRM/LLM BYOK
  keys already store provider secrets)?
- Does the existing Google OAuth path get refactored to sit on the generic OIDC seam, or stay separate?
  (Additive-only says: stay separate for now.)
