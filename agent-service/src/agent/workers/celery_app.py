"""Celery：记忆更新队列 + 定时唤醒扫描 + checkpoint 清理。"""

from __future__ import annotations

import json
import logging

from celery import Celery

from ..core.config import settings

logger = logging.getLogger("agent.workers")

celery_app = Celery(
    "agent_workers",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "drain-memory-queue": {
            "task": "agent.drain_memory_queue",
            "schedule": 5.0,
        },
        "scan-clock-jobs": {
            "task": "agent.scan_clock_jobs",
            "schedule": 5.0,
        },
        "prune-checkpoints": {
            "task": "agent.prune_checkpoints",
            "schedule": 300.0,
        },
    },
)


@celery_app.task(name="agent.drain_memory_queue")
def drain_memory_queue():
    import redis
    from ..core.db import SessionLocal
    from ..services.memory_service import memory_service
    from ..services.telemetry import memory_updated

    r = redis.Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)
    processed = 0
    while processed < 20:
        raw = r.rpop("memory_update_queue")
        if not raw:
            break
        try:
            task = json.loads(raw)
            db = SessionLocal()
            try:
                memory_service.process_memory_update(db, task)
                memory_updated(task.get("user_id"), task.get("scope", "long_term"))
            finally:
                db.close()
            processed += 1
        except Exception:
            logger.exception("memory update failed")
    return {"processed": processed}


@celery_app.task(name="agent.scan_clock_jobs")
def scan_clock_jobs():
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    import redis
    from ..graph.app import run_agent_wakeup
    from ..infrastructure.clock_queue import claim_due_jobs, schedule_job
    from ..services.telemetry import clock_wakeup

    r = redis.Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)
    done = 0
    for job in claim_due_jobs(r, limit=5):
        item = json.dumps(job, ensure_ascii=False)
        try:
            note = job.get("note") or {}
            user_id = int(job.get("user_id") or note.get("user_id") or 0)
            session_id = int(note.get("session_id") or 0)
            canvas_id = job.get("canvas_id") or note.get("canvas_id")
            clock_wakeup(session_id, str(note.get("task_id") or ""), user_id=user_id)
            if session_id and user_id:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(
                        run_agent_wakeup,
                        session_id,
                        user_id,
                        int(canvas_id) if canvas_id else None,
                        {**note, "canvas_id": canvas_id, "user_id": user_id},
                    )
                    try:
                        fut.result(timeout=90)
                    except FuturesTimeout:
                        logger.error(
                            "clock wakeup timed out session=%s task=%s",
                            session_id, note.get("task_id"),
                        )
                        import time
                        retry_at = time.time() + 30
                        schedule_job(r, job, retry_at)
            done += 1
        except Exception:
            logger.exception("clock job failed item=%s", item[:120])
    return {"done": done}


@celery_app.task(name="agent.prune_checkpoints")
def prune_checkpoints():
    from ..graph.app import prune_stale_checkpoints
    deleted = prune_stale_checkpoints()
    return {"deleted": deleted}
