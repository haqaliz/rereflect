# Aspect Spec — deps-and-docker

**Parent PRD:** `../prd.md` · **Aspect:** `deps-and-docker` · **Sequence:** 1 (FIRST — de-risks R1)

## Problem slice & outcome

`python3-saml` depends on `xmlsec`, which needs native `libxmlsec1` / `libxml2` (+ `pkg-config`) system
libraries. If the backend image / CI environment lacks them, **the entire test suite fails to import**.
This aspect lands the dependency + build changes and proves they import — before any SAML logic exists.

## In scope

- Add to `services/backend-api/requirements.txt`: `python3-saml` (pin a current version) and its
  transitive `xmlsec` / `lxml` as needed (let pip resolve, but pin what we add).
- Add OS packages to `services/backend-api/Dockerfile`: `libxml2`, `libxml2-dev`, `libxmlsec1`,
  `libxmlsec1-dev`, `libxmlsec1-openssl`, `pkg-config`, `build-essential` (as required by the base image;
  verify against the existing base — Debian/Alpine differ). Keep the layer minimal; group with existing
  `apt-get`/`apk` steps.
- A trivial **import smoke test** `tests/test_saml_deps.py`: `import saml2`/`from onelogin.saml2...` (the
  actual import path of the chosen lib) + `import xmlsec` succeed. This is the RED→GREEN anchor.
- `.env.example` note: SAML config is DB-stored (like OIDC); the ACS URL is `{BACKEND_URL}/api/v1/auth/saml/callback`
  (document under the existing `BACKEND_URL` comment). No new required env var in slice 1 (no SP private key).

## Out of scope

- Any SAML model/route/provider logic (later aspects).
- CI pipeline file edits beyond what's needed for the image to build (flag if CI is a separate config).

## Acceptance criteria (testable)

- `tests/test_saml_deps.py` imports the SAML lib + xmlsec successfully (fails before the requirement is
  added, passes after).
- `docker build` of `services/backend-api` succeeds with the new system packages (or: documented as
  verified locally if Docker isn't runnable in the worktree — state which).
- `pip install -r requirements.txt` resolves in a clean venv.
- Existing backend test suite still imports/collects (no regression from the new dep).

## Dependencies & sequencing

- **Blocks:** all other backend aspects (they import the SAML lib).
- **Depends on:** nothing. Do this first.

## Open questions / risks

- **R1** (parent): native deps. Confirm the Dockerfile base (Debian slim vs Alpine) — Alpine needs
  `xmlsec-dev`/`libxml2-dev` via `apk` and can be finicky with `xmlsec` wheels; Debian is smoother.
- Pin versions to avoid a future `xmlsec`/`lxml` ABI break.
