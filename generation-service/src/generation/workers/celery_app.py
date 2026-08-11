"""Celery 应用（队列：generation_image/video/audio/agent_exec/media_processing）。"""

from celery import Celery

from ..core.config import settings

celery_app = Celery(
    "vibepaper_generation",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["src.generation.workers.tasks"],
)

celery_app.conf.update(
    task_default_queue="generation_image",
    task_routes={
        "src.generation.workers.tasks.run_generation_task": {
            "queue": "generation_image",
            "routing_key": "generation_image",
        },
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
