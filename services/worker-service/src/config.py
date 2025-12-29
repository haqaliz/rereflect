"""
Worker service configuration.
Uses Redis logical databases for isolation:
- DB 0: Celery broker (task queue)
- DB 1: Session storage (reserved for backend-api)
- DB 2: Application cache (reserved for backend-api)
- DB 3: Rate limiting (reserved for backend-api)
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis configuration (single instance, multiple logical DBs)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    # Celery uses DB 0
    celery_broker_db: int = 0
    celery_backend_db: int = 0

    # Database (use Unix socket by default, same as backend-api)
    database_url: str = "postgresql:///customer_feedback_saas"

    # Analysis engine path
    analysis_engine_path: str = "../analysis-engine/src"

    # Task configuration
    analysis_batch_size: int = 100
    analysis_timeout: int = 600  # 10 minutes

    # Retry configuration
    max_retries: int = 3
    retry_delay: int = 60  # seconds

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


def get_redis_url(db: int = 0) -> str:
    """Get Redis URL for a specific logical database."""
    if settings.redis_password:
        return f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/{db}"
    return f"redis://{settings.redis_host}:{settings.redis_port}/{db}"


# Celery broker and backend URLs
CELERY_BROKER_URL = get_redis_url(settings.celery_broker_db)
CELERY_BACKEND_URL = get_redis_url(settings.celery_backend_db)
