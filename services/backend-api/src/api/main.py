from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from src.api.routes import auth, organizations, feedback, dashboard, analyze, integrations
from src.api.routes import source_webhooks, feedback_sources, pending_feedback, billing, team, invites, audit_logs
from src.api.routes import categories, ai_settings, anomalies, insights, changelog, notifications, analytics, saved_views, shared_links, workflow, email_webhooks
from src.api.routes import customer_health, activity_feed, dashboard_layout, admin_users, admin_orgs
from src.api.routes import customers, admin_backtest, admin_ai_models
from src.api.routes import conversation_folders, conversations, copilot_ws, copilot
from src.api.routes import events_ws
from src.api.routes import linear_integration, linear_webhook
from src.api.routes import hubspot_integration as hubspot_integration_router
from src.api.routes import salesforce_integration as salesforce_integration_router
from src.api.routes import jira_integration as jira_integration_router
from src.api.routes import asana_integration as asana_integration_router
from src.api.routes import zendesk_integration as zendesk_integration_router
from src.api.routes import response_templates, response_settings, feedback_responses
from src.api.routes import feedback_issue_draft as feedback_issue_draft_router  # noqa: E402 — ai-drafted-issue-content
from src.api.routes import webhooks as webhooks_router
from src.api.routes import health as health_routes
from src.api.routes import reports as reports_router
from src.api.routes import account as account_router
from src.api.routes import ai_corrections as ai_corrections_router  # noqa: E402 — M3.8 Track B
from src.api.routes import automations as automations_router  # noqa: E402 — M4.4 AI Workflow Automation
from src.api.routes import churn_events as churn_events_router  # noqa: E402 — M4.1 Advanced Churn Prediction
from src.api.routes import churn_suggestions as churn_suggestions_router  # noqa: E402 — review-queue (M5 CRM churn labels)
from src.api.routes import api_keys as api_keys_router  # noqa: E402 — Feature C: Public REST API key management
from src.api.routes import public_api as public_api_router  # noqa: E402 — Feature C: Public REST API surface
from src.api.routes import churn_analytics as churn_analytics_router  # noqa: E402 — M4.1 Cohort Analytics
from src.api.routes import churn_accuracy as churn_accuracy_router  # noqa: E402 — M4.1 Accuracy API
from src.api.routes import ai_readiness as ai_readiness_router  # noqa: E402 — M5.0 readiness report
from src.api.routes import playbooks as playbooks_router  # noqa: E402 — M4.1 Churn Playbooks
from src.api.routes import usage_webhooks as usage_webhooks_router  # noqa: E402 — product-usage ingest receiver
from src.api.routes import sentiment_accuracy as sentiment_accuracy_router  # noqa: E402 — eval-harness-and-card (M5.1 disclosure)
from src.api.routes import classifier_accuracy as classifier_accuracy_router  # noqa: E402 — M5.2 settings-api-and-accuracy-card
from src.api.routes import oidc_config as oidc_config_router  # noqa: E402 — oidc-sso: oidc-config aspect (M2/M3/M12)
from src.seed import seed_admin_user, seed_system_templates
from src.services.copilot.template_saver import TemplateSaver
from src.services.embeddings import resolve_embedding_provider
import logging
import os
import subprocess

# ---------------------------------------------------------------------------
# Sentry error tracking — opt-in only.
# Disabled unless the operator sets SENTRY_DSN, so a self-hosted install makes
# no outbound calls by default.
# ---------------------------------------------------------------------------
import sentry_sdk

_sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
_sentry_initialized = bool(_sentry_dsn)

if _sentry_initialized:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        send_default_pii=False,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
    )

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_copilot_system_templates(db) -> None:
    """
    Resolve the active embedding provider and seed/re-seed Copilot system templates.

    ── PHASE 4 CHECKPOINT (human review requested) ────────────────────────────
    System templates are org-less (organization_id IS NULL), but
    resolve_embedding_provider() requires an org_id to look up OrgAIConfig.

    DECISION: For self-hosted single-tenant deployments (the primary OSS use
    case), we resolve the embedder from the FIRST organization in the database.
    This is the only org in a typical self-hosted install.

    Rationale:
      - The embedding model config is set once by the operator in the UI / env
        and applies to the whole self-hosted instance.
      - The first org's OrgAIConfig is the de-facto global config.
      - If no org exists yet (fresh DB before first signup), we log and skip;
        seeding will succeed on the next boot after the first org is created.

    Multi-tenant cloud note: this approach is intentionally single-org.  A
    cloud SaaS deployment would need per-org system-template sets, which is
    beyond the scope of this aspect (the spec targets self-hosted OSS).

    PLEASE CONFIRM this approach is acceptable for your deployment model.
    ─────────────────────────────────────────────────────────────────────────
    """
    try:
        from src.models.organization import Organization
        first_org = db.query(Organization).first()
        if first_org is None:
            logger.info(
                "seed_copilot_system_templates: no organizations in DB yet — "
                "skipping (will seed on next boot after first org is created)"
            )
            return

        resolved = resolve_embedding_provider(first_org.id, db)
        saver = TemplateSaver()
        saver.seed_system_templates(db, embedder=resolved)
        logger.info(
            "seed_copilot_system_templates: seeding complete "
            "(provider=%s)", resolved.provider if resolved else "none"
        )
    except Exception as e:
        logger.warning(
            "seed_copilot_system_templates: failed, boot continues: %s", e
        )


def run_migrations():
    """Run Alembic migrations on startup."""
    try:
        logger.info("Running database migrations...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        if result.returncode == 0:
            logger.info("Migrations completed successfully")
        else:
            logger.error(f"Migration failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("Migration timed out after 60 seconds")
    except Exception as e:
        logger.error(f"Could not run migrations: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - runs on startup and shutdown."""
    # Startup: run migrations, seed admin user, sync changelog
    run_migrations()
    try:
        seed_admin_user()
    except Exception as e:
        logger.warning(f"Could not seed admin user: {e}")
    try:
        seed_system_templates()
    except Exception as e:
        logger.warning(f"Could not seed system templates: {e}")
    try:
        from src.services.playbook_seeder import seed_playbook_templates
        from src.database.session import SessionLocal
        _pb_db = SessionLocal()
        try:
            seed_playbook_templates(_pb_db)
        finally:
            _pb_db.close()
    except Exception as e:
        logger.warning(f"Could not seed playbook templates: {e}")
    # Seed Copilot system templates with the active embedding provider.
    # Provider-aware: re-embeds if the active provider changed since last boot.
    # Never blocks boot: errors are caught and logged.
    try:
        from src.database.session import SessionLocal
        _emb_db = SessionLocal()
        try:
            seed_copilot_system_templates(_emb_db)
        finally:
            _emb_db.close()
    except Exception as e:
        logger.warning(f"Could not seed copilot system templates: {e}")
    try:
        from scripts.sync_changelog import run_changelog_sync
        run_changelog_sync()
    except Exception as e:
        logger.warning(f"Changelog sync skipped: {e}")
    # Q1 (OSS pivot): seed operator's env keys into the primary org's OrgApiKey
    # store so the BYOK resolver can find them via the DB (not via env at runtime).
    try:
        from src.seed_byok import seed_byok_keys_from_env
        from src.database.session import SessionLocal
        _byok_db = SessionLocal()
        try:
            seed_byok_keys_from_env(_byok_db)
        finally:
            _byok_db.close()
    except Exception as e:
        logger.warning(f"Could not seed env BYOK keys: {e}")
    yield
    # Shutdown: cleanup if needed


# Root path for reverse proxy (e.g., when served under /api)
root_path = os.getenv("ROOT_PATH", "")

app = FastAPI(
    title="Customer Feedback Analyzer API",
    version="1.1.0",
    description="Multi-tenant SaaS API for customer feedback analysis",
    lifespan=lifespan,
    root_path=root_path,
)

# CORS - configurable via environment variable
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Cache-Control header middleware for read-only endpoints
CACHE_CONTROL_RULES = {
    "/api/v1/dashboard": "private, max-age=60",
    "/api/v1/analytics": "private, max-age=120",
    "/api/v1/categories": "private, max-age=300",
    "/api/v1/feedback-sources": "private, max-age=300",
}


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.method == "GET" and response.status_code == 200:
            path = request.url.path
            for prefix, header_value in CACHE_CONTROL_RULES.items():
                if path.startswith(prefix):
                    response.headers["Cache-Control"] = header_value
                    break
        return response


app.add_middleware(CacheControlMiddleware)


# Include routers
app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(feedback.router)
app.include_router(dashboard.router)
app.include_router(analyze.router)
app.include_router(integrations.router)
app.include_router(source_webhooks.router)
app.include_router(feedback_sources.router)
app.include_router(pending_feedback.router)
app.include_router(billing.router)
app.include_router(team.router, prefix="/api/v1/team", tags=["team"])
app.include_router(invites.router, prefix="/api/v1/invites", tags=["invites"])
app.include_router(audit_logs.router, prefix="/api/v1/audit-logs", tags=["audit-logs"])
app.include_router(categories.router)
app.include_router(ai_settings.router)
app.include_router(anomalies.router)
app.include_router(insights.router)
app.include_router(changelog.router)
app.include_router(notifications.router)
app.include_router(analytics.router)
app.include_router(saved_views.router)
app.include_router(shared_links.router)
app.include_router(shared_links.public_router)
app.include_router(workflow.router)
app.include_router(email_webhooks.router)
app.include_router(customer_health.router)
app.include_router(activity_feed.router)
app.include_router(dashboard_layout.router)
app.include_router(admin_users.router)
app.include_router(admin_orgs.router)
app.include_router(admin_backtest.router)
app.include_router(admin_ai_models.router)
# Advanced Churn Prediction — Churn Events (M4.1)
# NOTE: must be included BEFORE customers.router — its static paths (/churn-events/bulk, etc.)
# must win over customers.router's /{email} wildcard.
app.include_router(churn_events_router.router)
# CRM churn-suggestion review queue (review-queue aspect, M5) — must also be
# included BEFORE customers.router for the same reason: our static
# /churn-suggestions/bulk path must win over customers.router's /{email}.
app.include_router(churn_suggestions_router.router)
# Advanced Churn Prediction — Cohort Analytics (M4.1 Phase 4)
app.include_router(churn_analytics_router.router)
# Advanced Churn Prediction — Accuracy API (M4.1 Phase 6.2a)
app.include_router(churn_accuracy_router.analytics_router)
app.include_router(churn_accuracy_router.system_router)
# AI training-readiness report (M5.0 — no ML, per-org data counts)
app.include_router(ai_readiness_router.router)
# Sentiment eval accuracy card (M5.1 disclosure — transformer vs VADER, not a merge gate)
app.include_router(sentiment_accuracy_router.router)
# Per-org corrections classifier accuracy card (M5.2 settings-api-and-accuracy-card)
app.include_router(classifier_accuracy_router.router)
app.include_router(customers.router)
# AI Copilot (M2.2) — folder router MUST come before conversations to avoid route conflicts
app.include_router(conversation_folders.router)
app.include_router(conversations.router)
app.include_router(copilot_ws.router)
app.include_router(copilot.router)
app.include_router(events_ws.router)
app.include_router(linear_integration.router)
app.include_router(linear_webhook.router)
# HubSpot CRM enrichment (hubspot-connection aspect)
app.include_router(hubspot_integration_router.router)
# Salesforce CRM enrichment (salesforce-connection aspect)
app.include_router(salesforce_integration_router.router)
# Jira Cloud integration (jira-integration backend-connection aspect)
app.include_router(jira_integration_router.router)
# Asana integration (asana-integration backend-connection aspect)
app.include_router(asana_integration_router.router)
# Zendesk inbound integration (zendesk-integration backend-connection aspect)
app.include_router(zendesk_integration_router.router)
app.include_router(response_templates.router)
app.include_router(response_settings.router)
app.include_router(feedback_responses.router)
# AI-drafted issue content (ai-drafted-issue-content)
app.include_router(feedback_issue_draft_router.router)
# Custom Webhooks (M3.1)
app.include_router(webhooks_router.router)
app.include_router(health_routes.router)
# On-Demand AI Reports (M2.4)
app.include_router(reports_router.router)
# GDPR Compliance (M3.7)
app.include_router(account_router.router)
# AI Trust — Human-in-the-Loop corrections (M3.8 Track B)
app.include_router(ai_corrections_router.router)
# AI Workflow Automation (M4.4)
app.include_router(automations_router.router)
# OIDC SSO config CRUD (oidc-sso: oidc-config aspect, M2/M3/M12)
app.include_router(oidc_config_router.router)
# Churn Playbooks (M4.1 Phase 5.1)
# NOTE: executions static route must win over {playbook_id} wildcard — router
# handles this via ordering of routes within the module.
app.include_router(playbooks_router.router)
# Product-Usage Ingest Receiver (aspect 2)
app.include_router(usage_webhooks_router.router)
# Feature C — Public REST API (key management + public surface)
app.include_router(api_keys_router.router)
app.include_router(public_api_router.router)


@app.get("/")
async def root():
    return {
        "message": "Customer Feedback Analyzer API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/worker/status")
async def worker_status():
    """Get the status of the Celery worker connection."""
    from src.background import get_celery_status
    return get_celery_status()


@app.get("/tasks/{task_id}")
async def task_status(task_id: str):
    """Get the status of a Celery task."""
    from src.background import get_task_status
    return get_task_status(task_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
