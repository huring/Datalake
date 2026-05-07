from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, APIRouter

from auth import require_token
from config import get_settings
from database import check_database_readiness
from routers.apple_health import router as apple_health_router
from routers.events import router as events_router
from routers.sources import router as sources_router


settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger("datalake.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting api", extra={"version": settings.app_version})
    yield


app = FastAPI(
    title="Homelab Data Lake API",
    version=settings.app_version,
    lifespan=lifespan,
)

protected_router = APIRouter(dependencies=[Depends(require_token)])


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, object]:
    db_status = check_database_readiness()
    return {
        "status": "ok" if db_status["status"] == "ok" else "degraded",
        "db": db_status,
        "version": settings.app_version,
    }


@protected_router.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "api",
        "status": "running",
        "version": settings.app_version,
    }


app.include_router(protected_router)
app.include_router(events_router)
app.include_router(apple_health_router)
app.include_router(sources_router)
