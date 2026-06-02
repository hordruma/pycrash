"""Celery worker configuration."""
from celery import Celery
from crashout.config import settings

app = Celery(
    "pycrash_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    result_expires=3600 * 24,  # 24 hours
    worker_prefetch_multiplier=1,  # One task at a time per worker for MC
)

# Auto-discover tasks
app.conf.include = ["crashout.tasks.simulation_tasks"]
