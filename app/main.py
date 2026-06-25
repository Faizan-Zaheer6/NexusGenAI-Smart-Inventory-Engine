from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logger import logger
from app.core.seeder import initialize_database
from app.database.connection import AsyncSessionLocal, engine
from app.database.models import Base
from app.database.migrate import apply_migrations
from app.routers.admin import router as admin_router
from app.routers.api.v1 import router as api_v1_router
from app.routers.auth import api_router as auth_api_router
from app.routers.auth import limiter, pages_router as auth_pages_router
from app.routers.orders import router as orders_router
from app.routers.storefront import router as storefront_router

settings = get_settings()
settings.validate_required()
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    async def _init_db():
        logger.info("Initializing Neon DB schema synchronization in the background...")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await apply_migrations(conn)
            logger.info("Neon DB tables synchronized successfully.")
            async with AsyncSessionLocal() as session:
                await initialize_database(session)
                try:
                    from app.services.ai_service import init_vector_store
                    await init_vector_store(session)
                except Exception as e:
                    logger.error("Failed to initialize vector store: %s", e)
            logger.info("Database initialization and seeding completed successfully.")
        except Exception as exc:
            logger.critical("Failed to synchronize DB or seed in the background: %s", exc, exc_info=True)

    init_task = asyncio.create_task(_init_db())
    yield
    if not init_task.done():
        init_task.cancel()
    logger.info("Disposing connection pool on application shutdown...")
    await engine.dispose()


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path in {"/", "/admin", "/login", "/signup", "/admin/login", "/orders"}:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise Smart Inventory Engine — async PostgreSQL, JWT, orders, warehouses, coupons, API v1.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(NoCacheMiddleware)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth_api_router, prefix="/auth")
app.include_router(auth_pages_router)
app.include_router(storefront_router)
app.include_router(orders_router)
app.include_router(admin_router)
app.include_router(api_v1_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (401, 403) and request.url.path.startswith("/admin"):
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=exc.status_code, content={"data": None, "meta": {}, "errors": [{"code": str(exc.status_code), "message": exc.detail}]})
    accept = request.headers.get("accept", "")
    if "application/json" in accept or request.url.path.startswith("/auth"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Validation error on %s: %s", request.url.path, exc.errors())
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=422, content={"data": None, "meta": {}, "errors": exc.errors()})
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "An internal server error occurred."})
