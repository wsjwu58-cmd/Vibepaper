from fastapi import FastAPI
from contextlib import asynccontextmanager

from .api.routes import router
from .core.config import settings
from .core.nacos import NacosRegistrar

_registrar = NacosRegistrar("generation-service", settings.port)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .core.db import SessionLocal
    from .services.model_service import seed_models

    db = SessionLocal()
    try:
        seed_models(db)
    finally:
        db.close()
    _registrar.start()
    yield
    _registrar.stop()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
# CORS is handled solely by vibepaper-gateway to avoid duplicate Allow-Origin headers
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.generation.main:app", host="0.0.0.0", port=settings.port, reload=False)
