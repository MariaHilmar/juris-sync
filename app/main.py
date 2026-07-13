from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.process import router as process_router
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("application_started", version=settings.VERSION, env=settings.ENV)
    yield
    logger.info("application_stopped")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    description=(
        "JurisSync API - Uma API RESTful profissional para monitoramento, "
        "ingestão de dados jurídicos (DataJud/CNJ) e análise de Jurimetria."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(process_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Monitoring"])
async def health_check():
    """Verifica a API, o banco e a disponibilidade do motor DataJud."""
    logger.info("health_check_called")

    db_status = "unhealthy"
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_status = "healthy"
    except Exception as error:
        logger.error("database_health_check_failed", error=str(error))

    datajud_status = "configured" if settings.DATAJUD_API_KEY else "mock_mode"

    overall = "healthy" if db_status == "healthy" else "degraded"
    return {
        "status": overall,
        "env": settings.ENV,
        "version": settings.VERSION,
        "services": {
            "database": db_status,
            "datajud_api": datajud_status,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
