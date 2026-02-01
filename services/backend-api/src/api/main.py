from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import auth, organizations, feedback, dashboard, analyze, integrations
from src.api.routes import source_webhooks, feedback_sources, pending_feedback, billing
from src.seed import seed_admin_user
import logging
import os
import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migrations():
    """Run Alembic migrations on startup."""
    try:
        logger.info("Running database migrations...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        if result.returncode == 0:
            logger.info("Migrations completed successfully")
        else:
            logger.error(f"Migration failed: {result.stderr}")
    except Exception as e:
        logger.error(f"Could not run migrations: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - runs on startup and shutdown."""
    # Startup: run migrations then seed admin user
    run_migrations()
    try:
        seed_admin_user()
    except Exception as e:
        logger.warning(f"Could not seed admin user: {e}")
    yield
    # Shutdown: cleanup if needed


# Root path for reverse proxy (e.g., when served under /api)
root_path = os.getenv("ROOT_PATH", "")

app = FastAPI(
    title="Customer Feedback Analyzer API",
    version="1.0.0",
    description="Multi-tenant SaaS API for customer feedback analysis",
    lifespan=lifespan,
    root_path=root_path,
)

# CORS - configurable via environment variable
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:3000")
cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
