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
    """进程内扫描 clock 任务：不依赖独立 Celery Beat 也能推进下游自动提交。"""
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
    # 预热 LangGraph + 内置 Skill
    try:
        from .graph.app import get_agent_graph
        get_agent_graph()
        logger.info("LangGraph compiled")
    except Exception:
        logger.exception("LangGraph compile failed at startup")
    db = SessionLocal()
    try:
        skill_service.ensure_paper_agent(db)
    except Exception:
        logger.exception("ensure paper-agent-default failed")
    finally:
        db.close()
    _registrar.start()
    stop = asyncio.Event()
    clock_task = asyncio.create_task(_clock_scan_loop(stop))
    logger.info("inline clock scanner started")
    try:
        yield
    finally:
        stop.set()
        clock_task.cancel()
        try:
            await clock_task
        except asyncio.CancelledError:
            pass
        _registrar.stop()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
# CORS is handled solely by vibepaper-gateway to avoid duplicate Allow-Origin headers
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.agent.main:app", host="0.0.0.0", port=settings.port, reload=False)
