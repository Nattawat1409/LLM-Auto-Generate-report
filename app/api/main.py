from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routers import health, metadata, reports
from app.api.services import workflow


# run the FastAPI integrated with LLM workflow (Langgraph)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await workflow.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="LLM Auto-Generate Report API", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(metadata.router)
    app.include_router(reports.router)
    return app


app = create_app()
