from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import logging

from .api.routes import router
from .core.config import settings
from .core.db import SessionLocal
from .core.nacos import NacosRegistrar
from .services.skill_service import skill_service

logger = logging.getLogger("agent.main")
_registrar = NacosRegistrar("agent-service", settings.port)


async def _clock_scan_loop(stop: asyncio.Event) -> None:
    """开发可选：生产默认仅 Celery Beat 扫描 clock。"""
    while not stop.is_set():
        try:
            from .workers.celery_app import scan_clock_jobs
            await asyncio.to_thread(scan_clock_jobs)
        except Exception:
            logger.exception("inline clock scan failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from .core.schema_migrate import ensure_schema
        ensure_schema()
    except Exception:
        logger.exception("schema migrate failed")
    try:
        from .graph.app import get_agent_graph
        get_agent_graph()
        logger.info("LangGraph compiled")
    except Exception:
        logger.exception("LangGraph compile failed at startup")
    db = SessionLocal()
    try:
        skill_service.ensure_paper_agent(db)
        skill_service.ensure_builtin_skills(db)
    except Exception:
        logger.exception("ensure paper-agent-default failed")
    finally:
        db.close()
    _registrar.start()
    stop = asyncio.Event()
    clock_task = None
    if settings.inline_clock_scan_enabled:
        clock_task = asyncio.create_task(_clock_scan_loop(stop))
        logger.info("inline clock scanner started (dev only)")
    else:
        logger.info("inline clock scanner disabled; use Celery Beat")
    try:
        yield
    finally:
        stop.set()
        if clock_task is not None:
            clock_task.cancel()
            try:
                await clock_task
            except asyncio.CancelledError:
                pass
        _registrar.stop()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.agent.main:app", host="0.0.0.0", port=settings.port, reload=False)
