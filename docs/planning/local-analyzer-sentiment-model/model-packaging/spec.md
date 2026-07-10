# Aspect Spec — model-packaging

**Parent PRD:** `../prd.md` · **Sequencing:** INFRASTRUCTURE — soft-depends on `sentiment-provider-core`
(needs its final model id + pinned revision to finish the pre-bake command), but can be **built in
parallel**: every phase here is Docker/deps/docs work with no import of provider code.

## Problem slice & outcome

Today `torch`/`transformers`/`sentence-transformers` are declared **only** in
`services/analysis-engine/requirements.txt:8-10` — a package that has **no Dockerfile and is not a
`docker-compose` service**. Sentiment actually executes in two other processes that don't have these
deps at all:

- **`worker-service`** (`services/worker-service/requirements.txt`) — copies
  `analysis-engine/src/analyzer` into its image (`Dockerfile:25`) but only pip-installs
  `vaderSentiment`/`nltk`/`scikit-learn`. This is the primary async runtime; if the transformer
  provider is ever selected by any org, these deps are **mandatory** here, not optional.
- **`backend-api`** (`services/backend-api/requirements.txt`) — has **no** `vaderSentiment`/
  `analysis-engine` dependency at all today, and its Dockerfile (`COPY . .` with build context
  `./services/backend-api`) never copies the `analysis-engine` package into the image. The
  synchronous re-analyze call site (`feedback.py:47`, invoked from `feedback.py:606`) resolves
  `analysis-engine/analyzer` via a `sys.path.insert` relative-path hack
  (`os.path.join(dirname(__file__), "../../../analysis-engine")`); computed from the real file
  location this resolves to `services/backend-api/analysis-engine`, a directory that **does not
  exist** in the repo and is never created by the current Dockerfile. **This call site is already
  broken in a real Docker build today** — a pre-existing bug, not a regression I'm introducing, but
  packaging the transformer provider is meaningless until the backend image can import `analyzer`
  at all (VADER or transformer).

This aspect makes the transformer model **installable** (deps pinned + present in the images that
actually run sentiment), **cacheable** (`HF_HOME` wired + a build-time pre-bake path mirroring the
existing `nltk.download` precedent, `Dockerfile:17-18`), and **air-gap-capable** (documented
`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` flags), while keeping the **default image lean** per the
PRD's opt-in framing (Risks: "don't bake by default").

## In scope

1. **Deps.** Add `torch==2.5.0` + `transformers==4.46.0` (version-pinned to match
   `analysis-engine/requirements.txt:8-10`) to `services/worker-service/requirements.txt` **and**
   `services/backend-api/requirements.txt`. Use the CPU-only PyTorch wheel index at install time
   (`--extra-index-url https://download.pytorch.org/whl/cpu`) in both Dockerfiles — plain
   `pip install torch==2.5.0` from PyPI on Linux pulls the CUDA-enabled wheel (multi-GB); this repo
   is CPU-only by design (PRD Non-Functional), so this is a real, load-bearing size lever, not a
   nice-to-have.
2. **Backend image fix (prerequisite for backend packaging to mean anything).** `COPY
   analysis-engine/src/analyzer` into the backend-api image at the exact relative location its
   existing `sys.path` hack expects (`/app/analysis-engine/analyzer/`), mirroring the worker's
   `COPY analysis-engine/src/analyzer ./analyzer` (`Dockerfile:25`) but at the backend's expected
   path instead. This requires changing the backend's Docker **build context** from
   `./services/backend-api` to `./services` (matching the worker's pattern) in both
   `docker-compose.yml` and `docker-compose.prod.yml`, since a build context cannot `COPY` a
   sibling directory outside itself. Also add `vaderSentiment==3.3.2` to
   `backend-api/requirements.txt` (currently absent — the sync path can't run *any* sentiment
   provider, including today's default VADER, without it).
3. **`HF_HOME` wiring.** `ENV HF_HOME=/app/models` in both `worker-service/Dockerfile` and
   `backend-api/Dockerfile` (always set — a cache-dir path costs nothing and doesn't imply network
   access). This supersedes the `analysis-engine/.env` `HF_HOME=./models` /
   `TRANSFORMERS_CACHE=./models/transformers` pair, which is dev-only and wired into no Dockerfile
   (`understanding.md` §4) — analysis-engine has no image to wire it into.
4. **Build-time pre-bake, gated by an ARG.** A `ARG BAKE_SENTIMENT_MODEL=false` in both
   Dockerfiles gates a `RUN` step — conditional shell, not a separate build stage, so the base
   layers stay identical whether or not the arg is set — that mirrors the existing NLTK line
   (`worker-service/Dockerfile:17-18`):
   ```dockerfile
   ARG BAKE_SENTIMENT_MODEL=false
   RUN if [ "$BAKE_SENTIMENT_MODEL" = "true" ]; then \
         python -c "from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
   AutoModelForSequenceClassification.from_pretrained('cardiffnlp/twitter-roberta-base-sentiment-latest', revision='<PINNED_SHA>'); \
   AutoTokenizer.from_pretrained('cardiffnlp/twitter-roberta-base-sentiment-latest', revision='<PINNED_SHA>')" ; \
       fi
   ```
   Default (`false`) → this step is a no-op, default image build makes **zero** network calls to
   Hugging Face and bakes **zero** weight bytes. `--build-arg BAKE_SENTIMENT_MODEL=true` → the
   weights + tokenizer land in `HF_HOME` at build time, air-gap ready.
5. **`docker-compose.yml` / `docker-compose.prod.yml` wiring.** Expose `BAKE_SENTIMENT_MODEL` as a
   pass-through `build.args` entry (default `false`) on the `worker` and `backend` services, and
   document (not default-on) the runtime env vars `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` an
   air-gapped operator sets after a baked build.
6. **`docs/SELF_HOSTING.md`.** A new section documenting: the model is off by default (no image
   bloat for operators who never enable it beyond the deps themselves); how to build with the
   model pre-baked (air-gap path); the two offline env flags; approximate minimum RAM and
   first-request (cold model load) latency, explicitly labeled as estimates pending measurement in
   implementation, not marketing numbers.
7. **Note (not build):** `services/analysis-engine` has no Dockerfile and is not a
   `docker-compose` service — there is nothing to pre-bake there. Its `.env`/`.env.example`
   `HF_HOME`/`TRANSFORMERS_CACHE` lines remain for local non-Docker development only and are
   explicitly out of scope to wire further.

## Out of scope

- The `SentimentProvider`/`TransformerSentimentProvider` implementation, softmax→contract mapping,
  and factory (`sentiment-provider-core`).
- `resolve_sentiment_provider`, the `OrgAIConfig.sentiment_provider` column/migration, the
  `ai_settings.py` route changes, and the two call-site injections at `analysis.py:479` /
  `feedback.py:47` (`per-org-resolution`). I only make the deps/image capable of running the
  provider **if** it's ever imported and constructed by that code — I don't write that code.
- Eval harness, accuracy card, M5.0 readiness report.
- Choosing/confirming the exact pinned model revision SHA — that's `sentiment-provider-core`'s
  call; I consume whatever it settles on (placeholder `<PINNED_SHA>` in the pre-bake `RUN` line
  until then — see Dependencies below).
- `AI-TRACKING.md` and the `README` capability-row updates (must-have #10) — only the
  `SELF_HOSTING.md` portion of #10 is mine.

## Acceptance criteria (testable)

- AC1: `docker build` of `worker-service/Dockerfile` (build context `./services`) with **default**
  args succeeds, makes no network call to Hugging Face, and the resulting image has no baked model
  weights under `/app/models`.
- AC2: `docker build --build-arg BAKE_SENTIMENT_MODEL=true` of the same Dockerfile succeeds and,
  inside the built image, `python -c "...from_pretrained('cardiffnlp/twitter-roberta-base-sentiment-latest', revision='<PINNED_SHA>', local_files_only=True)"` succeeds for **both** the model and
  tokenizer with zero network access (simulate via `HF_HUB_OFFLINE=1` at run time).
- AC3: same two builds (default + `BAKE_SENTIMENT_MODEL=true`) succeed for `backend-api/Dockerfile`
  after its build context moves to `./services`, **and** `python -c "import sys;
  sys.path.insert(0,'analysis-engine'); from analyzer.sentiment import SentimentAnalyzer;
  SentimentAnalyzer().analyze('great job')"` succeeds inside the built backend image (proves the
  pre-existing broken-import bug is fixed as a packaging prerequisite).
- AC4: `docker images` comparison shows the non-baked worker/backend images are smaller than the
  baked ones by roughly the model-weight size (~440–500 MB for `roberta-base`-class weights,
  fp32) — i.e. the ARG genuinely gates weight bytes, not just the deps.
- AC5: `docker-compose.yml` and `docker-compose.prod.yml` both build cleanly with default args
  (`docker compose build backend worker`) — no behavior change for existing self-hosters who don't
  touch `BAKE_SENTIMENT_MODEL`.
- AC6: `docs/SELF_HOSTING.md` documents the pre-bake command, both offline env vars, and states
  minimum RAM / first-request latency as estimates with a note to confirm empirically.

## Dependencies & sequencing

- **Soft-depends on `sentiment-provider-core`** for the final pinned model revision SHA (the
  pre-bake `RUN` line needs an exact `revision=` value, not `main`, for reproducibility/air-gap
  fidelity). This aspect can be fully implemented and validated in parallel using a placeholder
  revision (documented as such) and the placeholder swapped for the real SHA in a small follow-up
  commit once `sentiment-provider-core` lands — this does **not** block starting or finishing the
  Docker/deps/docs work here.
- **No dependency on `per-org-resolution`** — deps/image capability exist whether or not any org
  has ever enabled the provider.
- **Blocks nothing downstream that isn't already parallel** — `sentiment-provider-core` doesn't
  need this aspect to merge first (it can develop/test the provider class with `pip install -r
  analysis-engine/requirements.txt` locally); it needs this aspect's requirements.txt changes
  merged before the **worker/backend images** can actually run the transformer in a real deploy.

## Open questions / risks

- **OQ1 (revision pin):** exact `revision=<sha>` for
  `cardiffnlp/twitter-roberta-base-sentiment-latest` — owned by `sentiment-provider-core`; tracked
  as a placeholder here, reconciled at merge time. Flag if the two aspects land with mismatched
  revisions (bake references a different commit than the provider code requests — a cache miss
  that silently falls back to a network fetch, breaking air-gap).
- **R1 (image size, unconditional part):** adding `torch`+`transformers` to
  `worker-service/requirements.txt`/`backend-api/requirements.txt` grows **every** worker/backend
  image by the CPU-wheel size (~250–350 MB estimated) **regardless** of whether any org ever
  enables the transformer — this is a PRD-directed tradeoff (must-have #5 says add the deps
  unconditionally), not a bug; the ARG only gates the much larger weight bytes. Called out
  explicitly in `SELF_HOSTING.md` so it isn't a surprise.
- **R2 (pre-existing backend bug):** the backend sync path's broken `sys.path` import is fixed here
  as a byproduct of making backend packaging coherent — flag to the review gate that this is a
  latent bug being fixed opportunistically, not scope creep for its own sake; without the fix,
  nothing else in must-have #5 can be validated for the backend half.
- **R3 (build-context change is a real infra change):** moving the backend's Docker build context
  from `./services/backend-api` to `./services` touches `docker-compose.yml` **and**
  `docker-compose.prod.yml` — a small but real blast-radius change to the existing self-host entry
  point; validated by AC5 (both files still build cleanly with no other behavior change).
- **R4 (cold-start / RAM on small boxes):** carried from the PRD's own risk list — mitigated at the
  provider level (lazy singleton, must-have #9, out of scope here) but the *documentation* of
  minimum RAM/latency is mine (must-have #10/SELF_HOSTING slice) and is explicitly labeled
  provisional pending real measurement.
