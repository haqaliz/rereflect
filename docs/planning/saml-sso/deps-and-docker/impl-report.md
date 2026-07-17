# Implementation Report — `deps-and-docker` (SAML SSO, aspect 1 of 6)

**Branch:** `feat/saml-sso` · **Worktree:** `.claude/worktrees/feat-saml-sso`
**Date:** 2026-07-18 · **Plan followed:** `docs/planning/saml-sso/deps-and-docker/plan_20260717.md`

## Status: DONE_WITH_CONCERNS

The RED→GREEN cycle for `test_saml_deps.py` could **not** be fully closed in this macOS venv —
`xmlsec==1.3.13` fails to build against this host's Homebrew `libxmlsec1` (1.3.12), for a
well-understood, host-specific reason documented in detail below. The pin is verified-correct
for the actual deployment target (Debian bookworm, `libxmlsec1 1.2.37`) by source-level
inspection + a matching upstream GitHub issue, but the authoritative proof (`docker build`) could
not run because the Docker daemon is down in this worktree. This is exactly the fallback path
the plan pre-authorized (§3 Phase 2, §7.5, §8) — flagging as a concern rather than claiming an
unrun/unverified GREEN.

---

## What was done (phases 1–4, per plan)

### Phase 1 — RED (confirmed)
Created `services/backend-api/tests/test_saml_deps.py` verbatim per plan §5 (3 tests: onelogin
auth/settings import, `xmlsec` import + `__version__` touch, `lxml.etree` import).

Ran on the pre-existing clean venv (`services/backend-api/venv`, Python 3.12.13) **before** any
requirements change:

```
$ pytest tests/test_saml_deps.py -v
Pytest: 0 passed, 3 failed
1. test_onelogin_saml_auth_imports — ModuleNotFoundError: No module named 'onelogin'
2. test_xmlsec_native_binding_imports — ModuleNotFoundError: No module named 'xmlsec'
3. test_lxml_backend_imports — ModuleNotFoundError: No module named 'lxml'
```
RED confirmed exactly as expected — all 3 fail on missing modules, nothing else.

### Phase 2 — GREEN attempt: pin the dependency
Added the exact block from plan §3 Phase 2 to `services/backend-api/requirements.txt`, after the
OIDC block:
```
python3-saml==1.16.0
xmlsec==1.3.13
lxml>=4.9.0,<6
```

**`pip install -r requirements.txt` in the clean venv did NOT fully resolve.** Isolated the
failure precisely:

| Package | Host install result |
|---|---|
| `lxml>=4.9.0,<6` | ✅ installed cleanly — prebuilt wheel `lxml-5.4.0-cp312-cp312-macosx...whl` |
| `python3-saml==1.16.0` | ✅ installed cleanly — prebuilt wheel `python3_saml-1.16.0-py3-none-any.whl` (76 KB) |
| `isodate` (transitive dep of `python3-saml`) | ✅ installed cleanly — `isodate-0.7.2` |
| `xmlsec==1.3.13` | ❌ **fails to build** — no prebuilt wheel for macOS/this Python; falls back to sdist; C compile fails |

Build failure (`clang`), root cause traced to `src/constants.c` in the `xmlsec` 1.3.13 sdist:
```
error: use of undeclared identifier 'xmlSecSoap11Ns'
error: use of undeclared identifier 'xmlSecSoap12Ns'
```

**Root cause (confirmed via source inspection + upstream research):** `xmlsec==1.3.13`'s
`constants.c` unconditionally references `xmlSecSoap11Ns`/`xmlSecSoap12Ns` — SOAP namespace
constants that exist in `libxmlsec1 < 1.3.0` but were **removed** in `libxmlsec1 >= 1.3.0`. This
host's Homebrew `libxmlsec1` is **1.3.12** (post-removal), so the build fails. This is a known,
documented issue — see [xmlsec/python-xmlsec#254](https://github.com/xmlsec/python-xmlsec/issues/254)
("Unable to (pip install xmlsec) since brew version 4.0.13"), same symptom, same cause.

**This does NOT indicate a problem with the pin for the actual target.** Debian bookworm ships
`libxmlsec1 1.2.37` (confirmed live via `packages.debian.org/bookworm/libxmlsec1-openssl` →
version `1.2.37-2`), which **predates** the 1.3.0 SOAP-removal boundary — i.e. it still has the
symbols `xmlsec==1.3.13`'s source needs. The plan's rationale ("xmlsec==1.3.13 is the last line
compatible with libxmlsec1 1.2.x") is confirmed correct; the failure here is purely a
**Homebrew-shipped-a-newer-C-library-than-Debian-bookworm** mismatch, the mirror image of the
risk the plan called out in §7.2 (there, the concern was a too-new *xmlsec* pip package; here it's
a too-new *libxmlsec1* system library on this specific host).

**Per plan §3 Phase 2's explicit instruction** ("If the host cannot build xmlsec... do NOT weaken
the pin — proceed to Phase 3 and let the Docker image (Debian) be the verification surface.
Record that host build was skipped."), the pin in `requirements.txt` was left unchanged
(`xmlsec==1.3.13`), and I did not attempt to substitute a different xmlsec version.

**Host workaround attempts considered and abandoned (proportionality):**
- Building `libxmlsec1 1.2.37` from source locally to unblock the venv install: `autoconf`/
  `automake` are not installed on this host, and Homebrew's local core tap isn't cloned (API-based
  Homebrew), so pinning an old formula revision would require fetching formula history from
  GitHub with no guarantee an old arm64 bottle is still hosted (bottles are pruned). Given the
  plan explicitly designates Docker/bookworm as the authoritative gate and host verification as
  "a convenience," this was not pursued further — it would have added real time/risk for a result
  no more authoritative than the Docker build we're already deferring.

**Net result of Phase 2 on this host:**
```
$ pytest tests/test_saml_deps.py -v
2 failed, 1 passed
- test_onelogin_saml_auth_imports: FAILED (ModuleNotFoundError: xmlsec, via onelogin/saml2/utils.py's `import xmlsec`)
- test_xmlsec_native_binding_imports: FAILED (ModuleNotFoundError: xmlsec)
- test_lxml_backend_imports: PASSED
```

### Phase 3 — HARDEN: Dockerfile
Edited `services/backend-api/Dockerfile`, extending the existing single apt layer (was L18-21)
exactly per plan §3 Phase 3 — added `build-essential`, `pkg-config`, `libxml2`, `libxml2-dev`,
`libxmlsec1`, `libxmlsec1-dev`, `libxmlsec1-openssl` alongside the existing `libpq-dev`, `gcc`,
kept the single `rm -rf /var/lib/apt/lists/*` layer-hygiene pattern, and added the explanatory
comment block from the plan.

**Docker daemon status:** confirmed down both at task start and re-checked after Phase 3
(`docker info` → `ERROR: request returned 500 Internal Server Error ... check if the server
supports the requested API version`). **`docker build` was NOT run.** Package names were verified
instead by checking Debian's live package index:
- `libxmlsec1-openssl` confirmed present in bookworm, version `1.2.37-2` (via
  `packages.debian.org/bookworm/libxmlsec1-openssl`).
- `libxml2`, `libxml2-dev`, `libxmlsec1`, `libxmlsec1-dev`, `build-essential`, `pkg-config` are
  standard, long-stable Debian package names present in every Debian release including bookworm.

**Flag for a Docker-capable CI/reviewer:** run
```bash
cd services
docker build -f backend-api/Dockerfile -t rereflect-backend-saml-check .
docker run --rm rereflect-backend-saml-check \
  python -c "from onelogin.saml2.auth import OneLogin_Saml2_Auth; import xmlsec; print('SAML deps OK', xmlsec.__version__)"
docker run --rm rereflect-backend-saml-check python -m pytest tests/test_saml_deps.py -v
```
This is expected to fully pass — `libxmlsec1 1.2.37` in bookworm has the SOAP symbols
`xmlsec==1.3.13` needs (see Phase 2 root-cause analysis above).

### Phase 4 — regression + docs
**No-regression check** (ran via `./venv/bin/python -m pytest ...` directly — the shell's `pytest`
alias, from an installed `rtk` CLI proxy, was silently mis-summarizing output as "No tests
collected"; bypassing it with the venv's python binary directly gave accurate results):

```
$ ./venv/bin/python -m pytest tests/ --collect-only -q
======================== 3935 tests collected in 1.63s =========================
```
Zero collection errors — the new (partially-installed) SAML deps do not break collection of any
existing test file.

```
$ ./venv/bin/python -m pytest tests/test_saml_deps.py tests/test_oidc_provider.py \
    tests/test_oidc_config.py tests/test_oidc_login.py tests/test_auth.py -v
================== 2 failed, 91 passed, 302 warnings in 8.91s ==================
```
The 2 failures are the expected/documented host-only `xmlsec` ones. All 69 OIDC tests
(`test_oidc_provider.py` + `test_oidc_config.py` + `test_oidc_login.py`) plus `test_auth.py` and
`test_lxml_backend_imports` pass — **no regression**, matching the green baseline stated in the
task brief.

```
$ pytest tests/test_oidc_provider.py tests/test_oidc_config.py tests/test_oidc_login.py -v
Pytest: 69 passed
```

**`.env.example` note:** extended the existing `BACKEND_URL` comment block
(`services/backend-api/.env.example`) with the SAML ACS-URL note from plan §3 Phase 4 verbatim.
No new required env var added — matches plan §6 ("None new required in slice 1").

---

## Files changed

| File | Action | Notes |
|---|---|---|
| `services/backend-api/tests/test_saml_deps.py` | **created** | Verbatim per plan §5, import-only smoke test |
| `services/backend-api/requirements.txt` | **edited** | Added `python3-saml==1.16.0`, `xmlsec==1.3.13`, `lxml>=4.9.0,<6` block after the OIDC block |
| `services/backend-api/Dockerfile` | **edited** | Extended the single apt layer with native xmlsec/libxml2 build+runtime packages |
| `services/backend-api/.env.example` | **edited** | Added SAML ACS-URL doc note under the existing `BACKEND_URL` block |

No other files touched (no models, routes, provider, frontend, migrations, or new env vars —
matches plan §4 scope exactly).

---

## Installed versions (this host, partial — `xmlsec` NOT installed)

| Package | Version | Install method |
|---|---|---|
| `python3-saml` | 1.16.0 | prebuilt wheel |
| `lxml` | 5.4.0 | prebuilt wheel |
| `isodate` (transitive) | 0.7.2 | prebuilt wheel |
| `xmlsec` | **not installed** | sdist build fails on this host (see Phase 2) — pin unchanged in `requirements.txt` |

The committed pin remains exactly as specified in the plan: `python3-saml==1.16.0`,
`xmlsec==1.3.13`, `lxml>=4.9.0,<6`.

---

## Test commands + final output summary

| Command | Result |
|---|---|
| `pytest tests/test_saml_deps.py -v` (before requirements.txt edit) | RED — 3/3 fail, `ModuleNotFoundError` (onelogin, xmlsec, lxml) |
| `pip install -r requirements.txt` (clean venv) | Partial — `lxml`, `python3-saml` install; `xmlsec==1.3.13` fails to build (host-only, documented) |
| `pytest tests/test_saml_deps.py -v` (after) | 1 passed (`test_lxml_backend_imports`), 2 failed (xmlsec-dependent, host-only reason) |
| `pytest tests/test_oidc_provider.py tests/test_oidc_config.py tests/test_oidc_login.py -v` | **69 passed** — baseline OIDC suite unaffected |
| `pytest tests/test_saml_deps.py tests/test_oidc_provider.py tests/test_oidc_config.py tests/test_oidc_login.py tests/test_auth.py -v` | 91 passed, 2 failed (same 2 as above) |
| `pytest tests/ --collect-only -q` | **3935 tests collected, 0 errors** — no regression |
| `docker build ...` | **NOT RUN** — Docker daemon down (`docker info` fails with 500 error) both at task start and after Phase 3 |

---

## Concerns / follow-ups for a Docker-capable reviewer

1. **Run the real `docker build`** (commands above) to get the authoritative GREEN for
   `test_saml_deps.py` — expected to pass cleanly since bookworm's `libxmlsec1 1.2.37` has the
   SOAP symbols the pin needs, verified by source/package-index inspection but not executed here.
2. This host (macOS + Homebrew `libxmlsec1 1.3.12`) **cannot** run `test_saml_deps.py` green
   locally with the committed pin, and — per the plan's own risk analysis — never will, without a
   local libxmlsec1 downgrade outside this aspect's scope. Later SAML aspects' local dev loops on
   this machine will hit the same `ModuleNotFoundError: xmlsec` until either (a) Docker is used
   for local dev/test of SAML-touching code, or (b) a maintainer downgrades this host's
   `libxmlsec1` to a pre-1.3.0 build. Flagging this now so it isn't a surprise in aspect 2+.
3. The `rtk` shell-level `pytest`/`python` wrapper on this host silently misreports failures as
   "No tests collected" — used the venv's `python -m pytest` directly to get trustworthy output
   for this report. Worth being aware of for anyone re-running these commands via the wrapped
   shell aliases.
