import os
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_ai.core.logger import logger
from nexus_ai.database.connection import engine, get_db
from nexus_ai.database.models import Base, Product, CartItem
from nexus_ai.routers import auth as auth_router
from nexus_ai.routers import storefront as storefront_router

# Resolve templates directory (app/templates) relative to project root
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "app" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Lifespan: DB schema sync
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Neon DB Schema synchronization...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Neon DB tables synchronized successfully.")
    except Exception as exc:
        logger.critical("Failed to synchronize DB tables on startup: %s", exc, exc_info=True)
    yield
    logger.info("Disposing connection pool on application shutdown...")
    await engine.dispose()
    logger.info("Connection pool cleaned up.")

app = FastAPI(
    title="NexusAI: Smart Inventory Engine",
    description="Enterprise-level Smart Inventory backend targeting mid-to-senior levels.",
    version="1.0.0",
    lifespan=lifespan,
)

# Include auth routes
app.include_router(auth_router.router, prefix="/auth")
# Include storefront/admin routes
app.include_router(storefront_router.router)

# Middleware to prevent caching on dynamic pages
@app.middleware("http")
async def nocache_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/admin") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

# Jinja2 template endpoints (wrapper for FastAPI routes defined in storefront_router)
# storefront_router already returns TemplateResponse objects using the same Jinja2Templates instance
