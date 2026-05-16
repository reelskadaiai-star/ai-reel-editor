import os
from celery import Celery

BROKER = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

celery_app = Celery(
    "reel_worker",
    broker=BROKER,
    backend=BACKEND,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    result_expires=86400,          # 24 h
    worker_prefetch_multiplier=1,  # don't hoard tasks
    task_acks_late=True,
    task_routes={
        "workers.tasks.analyze_video": {"queue": "default"},
        "workers.tasks.render_reel": {"queue": "render"},
    },
)
