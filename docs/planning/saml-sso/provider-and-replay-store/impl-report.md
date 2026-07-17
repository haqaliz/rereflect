# Implementation Report — SAML SSO · provider-and-replay-store (aspect 3)

**Branch:** `feat/saml-sso` · **Service:** `services/backend-api` only · **Date:** 2026-07-18
**Author:** security-critical implementation pass (Opus 4.8 1M)

Aspect 3 of 6: the pure `SamlProvider` (build AuthnRequest + validate SAML
Response/Assertion) and the DB-backed replay store. No FastAPI routes (aspect 4
wires them). Strict TDD throughout (RED → watch-fail-for-right-reason → GREEN).

---

## Status

**DONE.** All phases implemented, scoped tests green, alembic round-trip
verified, baseline kept green, XSW/unsigned rejection proven to bite.

One deliberate, documented deviation from the plan's premise: the installed
`python3-saml 1.16.0` **does** have a clock-skew knob (`ALLOWED_CLOCK_DRIFT =
300s`), contrary to the plan's "no skew knob" assumption. See §Clock skew.

---

## Commits (short SHAs, in order)

| SHA | Phase | Summary |
|---|---|---|
| `f39c770` | 1 | DB-backed replay store: `SamlAuthRequest` model + `saml_replay` service (pending→consumed) |
| `30b1ffd` | 2 | Alembic migration `q1r2s3t4u5v6` for `saml_auth_requests` |
| `1f6c3d7` | 3 | `SamlProvider` skeleton — AuthnRequest builder + SSRF gate |
| `3fd9b25` | 4/5 | `SamlProvider.validate_response` — delegated validation + ±60s skew supplement |

---

## Files changed / added

**Production:**
- `src/models/saml_auth_request.py` — new `SamlAuthRequest` model (`saml_auth_requests`).
- `src/models/__init__.py` — export `SamlAuthRequest` (import near `OidcConfig`/`SamlConfig`, name in `__all__`).
- `src/services/saml_replay.py` — new replay-store service (`ConsumeOutcome`, `register_request`, `consume_request`, `_cleanup_expired`, `_now`).
- `src/services/saml_provider.py` — new provider service (`SamlProvider`, `ValidatedAssertion`, `SamlValidationError`, error map, email chain, ±60s skew supplement).
- `alembic/versions/q1r2s3t4u5v6_add_saml_auth_requests.py` — new migration.

**Tests:**
- `tests/test_saml_replay.py` — 9 tests (state machine + concurrency).
- `tests/test_saml_provider.py` — 22 tests (build/SSRF + full validation matrix).
- `tests/saml_fixtures.py` — in-test signed-fixture helpers.

---

## Test commands + output

### Scoped aspect suite (the deliverable)

```
$ source services/backend-api/venv/bin/activate
$ cd services/backend-api
$ python -m pytest tests/test_saml_provider.py tests/test_saml_replay.py -v
31 passed
```

Per plan §4, scoped (not the bare full suite — MEMORY notes a pre-existing
`test_report_ws.py` segfault unrelated to this aspect).

**`tests/test_saml_replay.py` (9 passed):**
- `test_register_then_consume_ok` — pending→consumed, `consumed_at` set.
- `test_second_consume_is_replay` — duplicate ACS POST → REPLAY.
- `test_unknown_request_is_unsolicited` — never-registered id → UNSOLICITED.
- `test_expired_request_is_rejected` — clock jumped past TTL → EXPIRED, never consumed.
- `test_opportunistic_cleanup_of_expired_rows_on_register` — stale row deleted on register.
- `test_cleanup_failure_is_swallowed` — broken session into `_cleanup_expired` does not raise; rollback called.
- `test_register_still_works_after_a_stale_row` — register lands the pending row.
- `test_concurrent_double_consume_exactly_one_ok` — 5 sequential consumes → exactly 1 OK, 4 REPLAY.
- `test_threaded_double_consume_file_sqlite_exactly_one_ok` — two real Sessions over a **file-based** SQLite race in threads (barrier-synchronised) → exactly one OK, one REPLAY (real row contention).

**`tests/test_saml_provider.py` (22 passed):**
- build: `test_build_authn_request_returns_redirect_and_request_id`, `..._rejects_private_ip_sso_url` (SSRF), `..._rejects_http_sso_url` (https-only).
- happy: `test_valid_signed_assertion_passes` (subject + lowercased email).
- signature: `test_unsigned_assertion_rejected` (assertion), `test_wrong_cert_signature_rejected` (signature), `test_xsw_wrapped_assertion_rejected_and_forged_subject_never_surfaces`, `test_response_signed_but_assertion_unsigned_rejected` (assertion), `test_assertion_signature_requirement_is_load_bearing` (bite proof).
- conditions: `test_wrong_audience_rejected` (audience), `test_wrong_recipient_rejected` (recipient), `test_wrong_issuer_rejected` (assertion), `test_mismatched_in_response_to_rejected` (unsolicited), `test_expired_assertion_rejected` (expired), `test_not_yet_valid_assertion_rejected` (expired), `test_null_subject_rejected` (assertion).
- skew: `test_skew_within_60s_still_passes`, `test_skew_beyond_60s_rejected`.
- email chain: `test_email_from_nameid_emailaddress_format`, `test_email_from_configured_attribute`, `test_email_from_default_chain_urn_oid`, `test_no_email_when_none_present`.

### Baseline regression check (kept green)

```
$ python -m pytest tests/test_oidc_config.py tests/test_oidc_login.py \
      tests/test_oidc_provider.py tests/test_saml_config.py tests/test_saml_deps.py -q
105 passed
```

No regression to the OIDC + SAML-config baseline.

---

## RED evidence (TDD discipline)

- Phase 1 RED: `tests/test_saml_replay.py` → `ModuleNotFoundError: No module named 'src.models.saml_auth_request'` (collection error) before the model existed.
- Phase 3 RED: `tests/test_saml_provider.py` → `ModuleNotFoundError: No module named 'src.services.saml_provider'` before the service existed.
- Phase 4 iteration: fixtures were driven RED by real library behaviour (Destination scheme mismatch, forced AttributeStatement) and fixed against the installed lib — see §Iteration points.

---

## Migration: revision + alembic round-trip

- **Revision id:** `q1r2s3t4u5v6` · **down_revision:** `p0q1r2s3t4u5`.
- **Live head confirmed before authoring:** `alembic heads` → `p0q1r2s3t4u5 (head)` (single head, as MEMORY predicts; the "6 heads" static-parse claim is an artifact).
- Table: `saml_auth_requests(request_id PK, organization_id FK→organizations.id CASCADE, created_at, expires_at, consumed_at nullable)` + indexes `ix_saml_auth_requests_org_id`, `ix_saml_auth_requests_expires_at`.

**Round-trip verified** on a scratch SQLite DB in isolation (the full-chain-from-scratch fails on a *pre-existing, unrelated* SQLite ALTER-constraint limitation in an earlier migration, so the new migration was verified by stamping the prior head then up/down/up):

```
$ export DATABASE_URL="sqlite:////tmp/.../scratch_saml_iso.db"
$ alembic stamp p0q1r2s3t4u5
$ alembic upgrade q1r2s3t4u5v6      # p0q1r2s3t4u5 -> q1r2s3t4u5v6 (creates table + 2 indexes)
$ alembic downgrade p0q1r2s3t4u5    # drops indexes + table (table gone: 0)
$ alembic upgrade q1r2s3t4u5v6      # re-creates; alembic current -> q1r2s3t4u5v6 (head)
```

Schema/indexes confirmed via `.schema` / `.indexes` on the scratch DB.

---

## How signed fixtures were generated (`tests/saml_fixtures.py`)

- **Throwaway signer:** `make_keypair_cert()` generates a 2048-bit RSA key + a self-signed X.509 cert via `cryptography` (mirrors how `test_oidc_provider.py` makes JWKS keys). The cert PEM becomes the provider's `idp_x509_cert`.
- **Response assembly:** a minimal SAML `Response` (Issuer, Status=Success, one `Assertion` with Subject/NameID, `SubjectConfirmationData@InResponseTo/@Recipient/@NotOnOrAfter`, `Conditions@NotBefore/@NotOnOrAfter/AudienceRestriction`, `AuthnStatement`, optional `AttributeStatement`) is built by string templating.
- **Signing:** the **Assertion** is signed with the library's own `OneLogin_Saml2_Utils.add_sign(xml, key_pem, cert_pem, RSA_SHA256, SHA256)` — so the bytes the provider validates are signed exactly as a real IdP would. `sign_response=True` signs the **Response** element instead (for the response-signed-but-assertion-unsigned policy test).
- **`_make_response(**overrides)` factory:** every rejection case is one template tweak — `sign=False` (unsigned), `sign_key_pem/sign_cert_pem` (wrong-cert), `xsw=True` (wrapping), `audience/recipient/destination/issuer/in_response_to` overrides, `not_before/not_on_or_after/sc_not_on_or_after` deltas, `include_subject=False` (null NameID), and `attributes` / `name_id_format` for the email-source variants.
- Separate control of **Conditions NotOnOrAfter** vs **SubjectConfirmationData NotOnOrAfter** was added because python3-saml applies the 300s drift only to Conditions while the SubjectConfirmation bearer check is strict — the skew tests need to hold SC open while moving the Conditions window.

---

## XSW test — explicit evidence it bites

Two complementary proofs:

1. **`test_xsw_wrapped_assertion_rejected_and_forged_subject_never_surfaces`**
   - The fixture (`xsw=True`) embeds a **forged, unsigned** second assertion with
     `NameID = attacker@evil.example.com` placed *before* the legitimately-signed
     assertion (classic wrapping). The test asserts the raw decoded XML actually
     contains `attacker@evil.example.com` — i.e. a naive "read the first NameID"
     parser *would* return the attacker.
   - **What it rejects & why:** `validate_response` raises `SamlValidationError`;
     python3-saml's `validate_num_assertions()` fires first with
     `WRONG_NUMBER_OF_ASSERTIONS` → reason *"SAML Response must contain 1
     assertion"* → mapped to code `assertion`. The forged subject is never
     returned (identity is only ever read from `auth.get_nameid()` **after** full
     validation, which never runs on a rejected document).

2. **`test_assertion_signature_requirement_is_load_bearing`** — the "flip the flag
   and watch it go RED" proof, automated. The SAME response-signed /
   assertion-unsigned message is:
   - **rejected** (code `assertion`) under the real config (`wantAssertionsSigned=True`), and
   - **accepted** (subject returned) once `wantAssertionsSigned` is flipped to `False`.
   This demonstrates the strict flag — not an incidental fixture defect — is what
   closes the unsigned/wrapped-assertion hole. (Note: python3-saml *always*
   requires at least one signature somewhere, so a fully-unsigned message is
   always rejected; the load-bearing distinction is specifically
   *assertion-signed* vs *response-only-signed*, which is the policy this feature
   enforces.)

**R2 compliance:** identity (`subject`/`email`/`attributes`) is read **only** from
`auth.get_nameid()` / `auth.get_nameid_format()` / `auth.get_attributes()`. The
only raw-XML read is in `_enforce_skew_tolerance`, which reads **timestamps only**
(`Conditions@NotBefore/@NotOnOrAfter`) from the already-signature-validated,
single-assertion document — never identity — so it does not reintroduce XSW.

---

## Clock skew (±60s) — deviation from plan premise, documented

The plan (§2.4) assumed *"python3-saml has NO skew knob"* and prescribed Option A
(supplement on the failure path). **That premise is inaccurate for the installed
`python3-saml 1.16.0`:** it has a native `OneLogin_Saml2_Constants.ALLOWED_CLOCK_DRIFT
= 300` applied to the Conditions `NotBefore`/`NotOnOrAfter` check (the
SubjectConfirmation bearer check is strict/no-drift).

To honour the spec's exact **±60s** — and be strictly **more secure** than the
library default — the supplement was implemented as a **success-path tightening**
(`SamlProvider._enforce_skew_tolerance`): after the library's full validation
succeeds (so exactly one signed assertion exists), it re-reads the Conditions
`NotBefore`/`NotOnOrAfter` and rejects (code `expired`, detail contains "skew") if
`now` is outside `[NotBefore − 60s, NotOnOrAfter + 60s]`. This is the spirit of
Option A (re-read timestamps from the validated assertion), adapted to the reality
that the knob exists and is *looser* than the spec, so we tighten rather than add.

Demonstrated by:
- `test_skew_within_60s_still_passes` — Conditions expired 30s ago, SC still open → accepted.
- `test_skew_beyond_60s_rejected` — Conditions expired 120s ago (library would accept at 300s) → our supplement rejects (`expired`, "skew").

---

## Error-reason → sso_error code map (adjusted to installed lib phrasings)

`auth.get_last_error_reason()` phrasings were confirmed against the installed lib
and the substring map tuned accordingly (plan §2.2 flagged this as an iteration
point). Notable real phrasings and their codes:

| Observed reason (substring) | code |
|---|---|
| `Signature validation failed…` | `signature` |
| `The Assertion of the Response is not signed…` | `assertion` |
| `…Audience…` | `audience` |
| `The response was received at X instead of Y` (Destination) | `recipient` (added `"received at"` needle) |
| `Invalid issuer in the Assertion/Response` | `assertion` (no dedicated issuer code) |
| `The InResponseTo of the Response…` | `unsolicited` |
| `Could not validate timestamp: expired / not yet valid` | `expired` |
| anything else / no reason | `assertion` (fail-closed) |

---

## Replay store notes

- Exactly-once consume via race-safe `UPDATE saml_auth_requests SET consumed_at=:now WHERE request_id=:id AND consumed_at IS NULL AND expires_at >= :now`; `rowcount==1` → OK, else disambiguate (no row→UNSOLICITED, consumed→REPLAY, past-expiry→EXPIRED).
- Opportunistic, best-effort, **bounded** cleanup on register (id-select + IN-delete, portable across SQLite/Postgres; failure is caught + logged, never blocks a login). No Celery beat.
- Two `_now()` shims kept intentionally distinct: `saml_replay._now()` returns naive UTC `datetime`; `saml_provider._now()` returns epoch seconds. Documented in-module to avoid unit confusion.

---

## Follow-ups for the routes aspect (4)

- The provider is route-free by design; `_backend_url()` is replicated locally (not imported from `auth.py`). The ACS route must call `saml_replay.consume_request` and map `ConsumeOutcome`/`SamlValidationError.code` to `?sso_error=`.
- `SAML_REQUEST_TTL_SECONDS` (default 600) is the only new optional env; document in `.env.example` in the docs aspect.
- The library forces `https` on the computed ACS current-URL; deployments must set `BACKEND_URL` to the real `https://…` origin so Destination/Recipient checks pass (tests set `BACKEND_URL=https://localhost:8000`).
