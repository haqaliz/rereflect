# Contributing to Rereflect

Thanks for your interest in contributing! Rereflect is open source under the
MIT License, and we welcome bug reports, features, docs, and tests.

## Code of Conduct

Be respectful and constructive. Assume good intent, keep discussions on-topic,
and help make this a welcoming project for everyone.

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 14+
- Redis

### Local Dev Setup

Clone the repo and start the services. The fastest path is the bundled script:

```bash
./start-all.sh        # starts Redis, worker, backend, and frontend
./stop-all.sh         # stops everything
```

Or run each service individually:

```bash
# Backend API (http://localhost:8000, docs at /docs)
cd services/backend-api && ./start.sh

# Celery worker
cd services/worker-service && ./start.sh

# Frontend (http://localhost:3000)
cd services/frontend-web && npm run dev
```

### Environment

Copy the root example env and adjust as needed:

```bash
cp .env.example .env
```

Backend (`services/backend-api/.env`):

```
DATABASE_URL=postgresql:///customer_feedback_saas
JWT_SECRET=dev-secret-key-change-in-production
REDIS_HOST=localhost
REDIS_PORT=6379
```

Frontend (`services/frontend-web/.env.local`):

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Database

```bash
createdb customer_feedback_saas
cd services/backend-api
source venv/bin/activate
alembic upgrade head
```

To create a new migration:

```bash
cd services/backend-api
alembic revision -m "describe your change"
```

## Running Tests

```bash
# Backend (pytest)
cd services/backend-api && pytest tests/ -v

# Frontend lint
cd services/frontend-web && npm run lint

# Frontend build (type-check + production build)
cd services/frontend-web && npm run build
```

Please add or update tests for any behavior you change. Backend route changes
should include endpoint tests; verify migrations against a real PostgreSQL
database, not just SQLite.

## Branching & Pull Requests

- Branch off `master` using a descriptive name, e.g. `fix/feedback-export-empty`
  or `feat/slack-webhook-retry`.
- Keep PRs focused — one logical change per PR is easier to review.
- Write clear commit messages describing **what** and **why**.
- Make sure tests, lint, and the frontend build pass before opening a PR.
- Fill out the pull request template and link any related issues.
- A maintainer will review; address feedback by pushing follow-up commits.

## Code Style

### Frontend (Next.js + TypeScript)

- TypeScript strict mode; avoid `any`.
- Follow existing shadcn/ui component patterns.
- Use CSS variables for theming — never hardcode colors. Prefer
  `color-mix(in oklch, ...)` for variations.
- Use Skeleton components for loading states.
- Keep components small and focused. Run `npm run lint` before committing.

### Backend (FastAPI + SQLAlchemy)

- All routes must validate `organization_id` (multi-tenant scoping).
- Use Pydantic models for request/response validation.
- Return appropriate HTTP status codes with clear error messages.
- Add tests for new endpoints.

## Project Layout

See [README.md](README.md) and [CLAUDE.md](CLAUDE.md) for the full architecture
overview and service responsibilities.

## Reporting Bugs / Requesting Features

Use the GitHub issue templates (Bug Report / Feature Request). Please include
clear reproduction steps, expected vs. actual behavior, and the affected
page/service.

## License

By contributing, you agree that your contributions will be licensed under the
MIT License that covers this project.
