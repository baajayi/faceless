"""FastAPI application entry point."""
from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.runs import router as runs_router
from app.utils.logging import configure_logging

configure_logging()

app = FastAPI(
    title="Faceless TikTok Pipeline API",
    description="Agentic pipeline that creates children's educational TikTok videos daily.",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(runs_router)


@app.get("/")
def root():
    return {"service": "faceless-pipeline", "docs": "/docs"}
