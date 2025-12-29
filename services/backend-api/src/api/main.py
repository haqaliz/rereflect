from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import auth, organizations, feedback, dashboard, analyze
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Customer Feedback Analyzer API",
    version="1.0.0",
    description="Multi-tenant SaaS API for customer feedback analysis",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
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
