# Development

How to run Rereflect from source for local development. For containerized
deployment instead, see [SELF_HOSTING.md](SELF_HOSTING.md).

- [Prerequisites](#prerequisites)
- [The toolchain & package management](#the-toolchain--package-management)
- [First-time setup](#first-time-setup)
- [Running the stack](#running-the-stack)
- [Common commands](#common-commands)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Python 3.12+
- Node.js 18+ and **pnpm** 10+ (`corepack enable` to get the pinned version)
- PostgreSQL 14+
- Redis

## The toolchain & package management

Rereflect is a polyglot monorepo: JavaScript apps share a **pnpm workspace**, while the
Python services each manage their own virtualenv.

### JavaScript (pnpm workspace)

The repo root is a pnpm workspace (`pnpm-workspace.yaml`). It covers the two Next.js
apps and the shared UI package:

```
packages/ui              # shared React component library
services/frontend-web     # the dashboard app  (workspace name: customer-feedback-frontend)
services/landing-web      # the marketing site (workspace name: landing-web)
```

Install everything once from the root, then use the root scripts or `--filter`:

```bash
pnpm install                       # install all JS workspaces

pnpm dev:app                       # frontend-web dev server   (alias for --filter)
pnpm dev:landing                   # landing-web dev server
pnpm build:app                     # build the dashboard app
pnpm build:landing                 # build the landing site

# target any workspace directly
pnpm --filter customer-feedback-frontend <script>
pnpm --filter landing-web <script>
```

The package manager is pinned via `"packageManager": "pnpm@10.32.1"` in the root
`package.json`; `corepack` will use the right version automatically.

### Python (per-service virtualenvs)

`backend-api`, `worker-service` and `analysis-engine` each have their own `venv/` and
`requirements.txt`. The `start.sh` scripts create the venv and install dependencies on
first run, so the simplest setup is just to run them. Manual setup:

```bash
cd services/backend-api
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Repeat for `services/worker-service` and `services/analysis-engine`.

## First-time setup

```bash
# 1. JS deps
pnpm install

# 2. Database
createdb customer_feedback_saas
cd services/backend-api
source venv/bin/activate
alembic upgrade head
cd ../..

# 3. Backend env  (services/backend-api/.env)
cat > services/backend-api/.env <<'ENV'
DATABASE_URL=postgresql:///customer_feedback_saas
JWT_SECRET=dev-secret-key-change-in-production
REDIS_HOST=localhost
REDIS_PORT=6379
ENV

# 4. Frontend env  (services/frontend-web/.env.local)
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > services/frontend-web/.env.local
```

## Running the stack

You need Redis running first (`redis-server`), then the backend, worker and frontend.

### All at once

```bash
./start-all.sh     # starts everything in tmux
./stop-all.sh      # stops everything
```

### Individually

```bash
# Terminal 1 — Redis
redis-server

# Terminal 2 — Celery worker
cd services/worker-service && ./start.sh

# Terminal 3 — Backend API   (http://localhost:8000, docs at /docs)
cd services/backend-api && ./start.sh

# Terminal 4 — Frontend       (http://localhost:3000)
cd services/frontend-web && pnpm dev      # or: npm run dev
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Redis | localhost:6379 |

> Want to work on two branches at once without ports/services colliding? The
> `rereflect-worktrees` skill in `.claude/skills/` documents the isolated-worktree
> workflow.

## Common commands

```bash
# Backend tests
cd services/backend-api && pytest tests/ -v

# Database migrations
cd services/backend-api && alembic upgrade head
alembic revision -m "description"      # create a new migration

# Frontend
cd services/frontend-web
pnpm dev            # dev server
pnpm build          # production build
pnpm lint           # ESLint
pnpm test           # Vitest
```

## Testing

- **Backend / worker / analysis** — `pytest tests/ -v` inside each service.
- **Frontend** — `pnpm test` (Vitest) and `pnpm lint` inside `services/frontend-web`.

## Troubleshooting

### Port already in use
```bash
lsof -ti:8000 | xargs kill   # Backend
lsof -ti:3000 | xargs kill   # Frontend
```

### Database connection errors
```bash
pg_isready                       # is PostgreSQL up?
createdb customer_feedback_saas  # create the DB if missing
```

### Redis connection errors
```bash
redis-cli ping   # should return PONG
```

### Analysis not running
- Verify Redis is up: `redis-cli ping`
- Check the Celery worker is active and watch its logs
- Ensure the worker service is running (`cd services/worker-service && ./start.sh`)
