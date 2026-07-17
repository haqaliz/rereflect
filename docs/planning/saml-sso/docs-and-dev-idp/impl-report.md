# Implementation Report — `docs-and-dev-idp` aspect

**Date:** 2026-07-18
**Aspect:** 6 of 6 (last) — docs + tracking only, no source changes.

## Summary

Documented the SAML 2.0 SSO slice that shipped across the five functional aspects
(`deps-and-docker`, `config-model-and-crud`, `provider-and-replay-store`,
`login-routes-and-identity`, `frontend-saml-ui`). All claims below were verified against
the shipped code before being written, per the aspect's honesty requirement.

## Files changed

| File | Change |
|---|---|
| `docs/SELF_HOSTING.md` | New `## Single Sign-On (SAML 2.0)` section (mirrors the OIDC section's structure) + a macOS dev-note subsection for building `xmlsec`/`lxml` locally. Added to the doc's TOC. |
| `services/backend-api/.env.example` | **No change** — the ACS-URL note under `BACKEND_URL` was already added by the `deps-and-docker` aspect (verified present at L28-30); nothing to add. |
| `docker-compose.yml` | One-comment-block change on the `keycloak` service: notes it can also host a SAML realm, with a one-line pointer to the ACS URL and the docs section. Comment-only; `docker compose --profile dev-idp config -q` still parses. |
| `DEV-TRACKING.md` | L168-169 Security & Compliance summary line updated (OIDC-only → OIDC+SAML, ticked). M3.6 block (L233-238) header + SAML line rewritten to accurate slice-1 scope and ticked. |
| `AI-TRACKING.md` | Added one new row to the "Current AI Capabilities (Built)" table — there was no pre-existing SSO/OIDC/SAML row to tick (verified via `grep -niE "sso|oidc|saml" AI-TRACKING.md` returning nothing before this edit). |
| `CHANGELOG.md` | New `### Added — Single sign-on (SAML 2.0)` block under `## Unreleased`, directly after the OIDC block. Fixed the OIDC block's stale closing line (previously claimed "SAML ... not yet supported"). |
| `services/landing-web/components/landing/FAQ.tsx` | Fixed the SSO FAQ answer's stale closing sentence ("SAML is not supported yet" → now describes SP-initiated SAML support and names what's still missing: IdP-initiated, SLO, SCIM). No test asserts the old string (checked `services/landing-web/__tests__/landing/FAQ.test.tsx` — no match). |

## Shipped facts verified by grep/read (ground truth used for all docs)

- **Routes** (`services/backend-api/src/api/routes/auth.py`, router prefix `/api/v1/auth`):
  `GET /saml/status` (L347), `GET /saml/login` (L626), `POST /saml/callback` (L683, the ACS).
  Config CRUD lives in `services/backend-api/src/api/routes/saml_config.py`, prefix
  `/api/v1/settings/saml`, verbs `GET`/`PUT`/`DELETE`, all `require_admin_or_owner`.
- **ACS path constant:** `SAML_ACS_PATH = "/api/v1/auth/saml/callback"` (`saml_provider.py:51`) —
  matches the route.
- **SP Entity ID:** derived as `f"{backend_url}{SAML_METADATA_PATH}"` where
  `SAML_METADATA_PATH = "/api/v1/auth/saml/metadata"` (`saml_provider.py:52,163-164`). **No route is
  registered for that path** (confirmed: it does not appear among `auth.py`'s `@router.*` decorators) —
  it is used purely as an identifier string, not a served metadata document. Documented this
  explicitly so operators don't try to fetch it.
- **Config fields** (`services/backend-api/src/models/saml_config.py` +
  `SamlConfigUpdateRequest`/`SamlConfigResponse` in `saml_config.py`): `idp_entity_id`, `idp_sso_url`,
  `idp_x509_cert` (write-only — response returns `cert_fingerprint`, a SHA-256 hex fingerprint, never
  the PEM), `email_attribute` (optional), `allowed_email_domains` (empty = deny-all, normalized
  lowercase), `button_label`, `enabled`. The cert is stored **plaintext** (not Fernet-encrypted) —
  confirmed by the model's docstring and the route module's docstring, since it's public material.
- **`sso_error` codes actually emitted for SAML** — ground truth is
  `SAML_SSO_ERROR_CODES` in `auth.py` (L609-623), the single source of truth per its own comment:
  `disabled, config, state, signature, assertion, audience, recipient, expired, replay, unsolicited,
  unverified, domain, token` (13 codes).
  **Important correction vs. the plan/spec:** both assumed the set included `denied` and omitted
  `state`/`token`. Live grep shows `"denied"` is emitted **only** by the OIDC callback (`auth.py:474`,
  "user declined consent at the IdP") — SAML has no equivalent concept and never emits `denied`. The
  actual SAML set replaces it with `state` (bad/missing RelayState HMAC) and `token` (null/empty
  NameID — the account-takeover guard). Documented the **real** 13-code set, not the plan's assumed
  one.
  Cross-checked the frontend: `services/frontend-web/lib/samlErrors.ts` maps 12 of these codes
  directly (all but `state`/`token`); `app/login/page.tsx` merges the SAML map with
  `lib/oidcErrors.ts`'s map (which *does* cover `state` and `token`), so every SAML-emitted code
  resolves to a sensible message — no dead/unmapped code in practice, so no frontend fix was needed
  (out of scope for this docs-only aspect regardless).
- **SP-metadata endpoint:** did **not** ship (see above) — documented nothing about a fetchable
  metadata document, only that the SP Entity ID *value* is metadata-derived-looking but not fetchable.
- **NameID / email extraction chain** (`saml_provider.py:_extract_email`, L338-352): (1) NameID if its
  Format ends in `emailAddress` and contains `@`; (2) the configured `email_attribute` override if
  present in the assertion's attributes; (3) a default chain — `email`, the LDAP `mail` OID
  (`urn:oid:0.9.2342.19200300.100.1.3`), then the WS-Federation `emailaddress` claim URI.
- **Assertion-signature requirement:** `wantAssertionsSigned: True` in the OneLogin settings dict
  (`saml_provider.py:_build_settings`); an unsigned or response-only-signed assertion is rejected
  (mapped to `signature` or `assertion` depending on the library's error string via
  `_map_error_reason`).
- **Clock skew (verified precisely, not assumed):** the code comment
  (`saml_provider.py:29-36,293-301`) states python3-saml 1.16.0's *native* tolerance is 300s on
  `Conditions`, which is looser than the spec's ±60s — so a supplemental `_enforce_skew_tolerance`
  re-check *tightens* `Conditions` `NotBefore`/`NotOnOrAfter` down to ±60s after the library's own
  (looser) pass succeeds. `SubjectConfirmationData`'s bearer `NotOnOrAfter` gets **no** such
  supplemental re-check — confirmed by the fixture/test comment in
  `services/backend-api/tests/saml_fixtures.py:99` ("SubjectConfirmationData NotOnOrAfter is a *strict*
  (no-drift) bearer check") and `test_saml_provider.py`'s skew tests, which deliberately hold
  `sc_not_on_or_after_delta_seconds` generous while varying only the `Conditions` timestamps. Documented
  both halves of this distinction (this directly answers the brief's I-1-adjacent clock-skew ask).
- **`InResponseTo` / `SubjectConfirmationData` requirement (I-1):** confirmed via
  `saml_fixtures.py:109-110` that the test assertions place `InResponseTo` on
  `<saml:SubjectConfirmationData>`, and via the ACS flow (`auth.py:_extract_saml_in_response_to`,
  `saml_replay.py`) that this is the value bound to the pending-request replay store. Documented as an
  explicit IdP requirement (SubjectConfirmationData must carry InResponseTo) in the Troubleshooting
  section.
- **Cross-provider guard:** `services/backend-api/src/api/routes/_sso_guard.py` —
  `assert_no_other_provider_enabled` raises HTTP 422 ("only one SSO protocol may be active per
  deployment") if the *other* protocol has any enabled config; called from both `saml_config.py` and
  (per its docstring) `oidc_config.py`. Same-provider single-enabled (`_assert_no_other_enabled`) is a
  separate, pre-existing check per provider.
- **Settings UI:** `services/frontend-web/components/settings/SamlConfigCard.tsx` — confirmed field
  labels match the model 1:1 (IdP Entity ID, IdP SSO URL, IdP X.509 Certificate, Email Attribute
  (optional), Button Label, Allowed Email Domains, Enable SAML toggle); mounted below the OIDC card
  per commit `060eb7b`. `SamlSignInButton.tsx` navigates to `/api/v1/auth/saml/login` and polls
  `GET /saml/status` for `enabled`/`button_label` before rendering.
- **`.env.example`:** the SAML ACS note under `BACKEND_URL` (L28-30) was already present, added by the
  `deps-and-docker` aspect; confirmed no new `SAML_*` env var exists anywhere in the diff.
- **`requirements.txt` platform-split pins** (verified, feeds the macOS dev note):
  `xmlsec==1.3.13 ; sys_platform == "linux"` and `xmlsec==1.3.16 ; sys_platform == "darwin"`, both
  `--no-binary=lxml,xmlsec` (source builds); the Dockerfile installs
  `pkg-config libxml2 libxml2-dev libxmlsec1 libxmlsec1-dev libxmlsec1-openssl` for the Debian image.
  The macOS dev note in `SELF_HOSTING.md` mirrors this with the brew-prefix equivalents.

## Now-false claims corrected

1. `CHANGELOG.md` — OIDC "Added" block's closing line previously read *"only RS256-signed ID tokens are
   accepted today; SAML and ES256 are not yet supported."* → now reads *"...(ES256 and other algorithms
   are not); SAML is supported separately — see the SAML entry above."*
2. `services/landing-web/components/landing/FAQ.tsx` — the SSO FAQ answer's closing sentence *"SAML is
   not supported yet"* → replaced with an accurate SP-initiated-support statement plus an accurate list
   of what's still missing (IdP-initiated, SLO, SCIM).
3. `DEV-TRACKING.md` L168-169 and the M3.6 header/body both previously said *"SAML deferred"* — updated
   to reflect the shipped slice-1 scope.

Post-fix repo-wide grep `grep -rniE "SAML (is )?not (yet )?supported" CHANGELOG.md services/landing-web
DEV-TRACKING.md AI-TRACKING.md docs/SELF_HOSTING.md` returns **no matches**.

## Honesty-grep gate (Phase 7a) result

Ran the forbidden-capability scan against only the files this aspect touched (a superset scan against
`docs/` also picks up prior aspects' planning docs, which is expected — restricted the check to my own
diff to avoid false signal). Every hit for `IdP-initiated|SLO|SCIM|encrypted assertion|multiple IdP` is
in a negative/known-limitation context ("no IdP-initiated login", "no SLO", "not supported", "deferred")
— none is a positive capability claim. No fixes needed.

## Shipped-string cross-check (Phase 7b)

- ACS path `auth/saml/callback`: present in both the doc and `saml_provider.py`/route decorator.
- All 13 documented `sso_error` codes (`disabled, config, state, signature, assertion, audience,
  recipient, expired, replay, unsolicited, unverified, domain, token`) individually confirmed present in
  `SAML_SSO_ERROR_CODES` in `auth.py` — no invented code, none omitted.
- All documented config field names confirmed present in both the SQLAlchemy model and the Pydantic
  request/response schemas.

## Link/anchor sanity (Phase 7c)

- New TOC entry `[Single Sign-On (SAML 2.0)](#single-sign-on-saml-20)` added; heading slug matches.
- New heading does not collide with `## Single Sign-On (OIDC)` (different text → different slug).
- Confirmed the SAML section does **not** need the `LLM_ENCRYPTION_KEY`/BYOK cross-reference the OIDC
  section uses — the IdP cert is stored plaintext, not Fernet-encrypted (verified in the model
  docstring), so no such link was added; said so explicitly in the section's lead paragraph instead.
- `docker compose --profile dev-idp config -q` parses cleanly after the compose comment edit.

## Deviations from the plan

- **`.env.example`**: plan called this "confirm or add" — confirmed present, made **no** edit (correctly
  skipped per the plan's own instruction).
- **`sso_error` code table**: differs from the plan/spec's assumed set (`...expired|replay|unsolicited|
  unverified|domain|denied`) — replaced `denied` with the actually-emitted `state` and `token`, per the
  live-code verification above. This is the single most consequential correction in this aspect; every
  other item matched the plan's assumptions once verified.

## Base-branch note (R6, informational only)

Per the plan's Agent Execution Notes, `feat/saml-sso` was cut from local `master` (`c6d80da`, which
carries the OIDC slice); this aspect did not check or alter `origin/master` state — that is a PR/merge
concern outside a docs-only aspect's scope, flagged here for the human before opening the PR.
