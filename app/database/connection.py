import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# Ensure a valid DB URL – fall back to SQLite for local/dev environments if none provided
if not settings.DATABASE_URL:
    # SQLite file placed in the project root (works without external DB)
    DATABASE_URL = "sqlite+aiosqlite:///./dev.db"
    connect_args = {}
else:
    DATABASE_URL = settings.DATABASE_URL
    # Preserve existing SSL handling logic
    if "?sslmode=require" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("?sslmode=require", "")
        connect_args = {"ssl": True}
    else:
        connect_args = {}
    

engine = create_async_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
    pool_pre_ping=True,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
