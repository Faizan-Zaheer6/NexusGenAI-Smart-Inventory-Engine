import asyncio
from typing import Callable, Coroutine, Any

from app.core.logger import logger

_background_tasks: set[asyncio.Task] = set()


def run_background(coro: Coroutine[Any, Any, Any]) -> None:
    """Fire-and-forget async background task (ARQ/Celery-free lightweight runner)."""

    async def _wrapper():
        try:
            await coro
        except Exception as exc:
            logger.error("Background task failed: %s", exc, exc_info=True)

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_wrapper())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        asyncio.run(_wrapper())


async def invalidate_cache_async(key_pattern: str) -> None:
    from app.core.cache import cache_delete_pattern
    await cache_delete_pattern(key_pattern)
    logger.info("Cache invalidated: %s", key_pattern)
