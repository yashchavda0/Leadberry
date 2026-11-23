from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .database import create_database_engine
from .settings import Settings

logger = logging.getLogger(__name__)


class RedisResource:
    """Best-effort cache/coordination client backed by one process-owned pool."""

    def __init__(self, client: Redis) -> None:
        self.client = client
        self.available = False

    async def connect(self) -> None:
        try:
            async with asyncio.timeout(2):
                self.available = bool(await self.client.ping())
        except (RedisError, TimeoutError, OSError):
            self.available = False
            logger.warning("redis_unavailable_falling_back_to_postgres")

    async def get(self, key: str) -> str | None:
        if not self.available:
            return None
        try:
            return await self.client.get(key)
        except (RedisError, OSError):
            self.available = False
            logger.warning("redis_get_unavailable")
            return None

    async def set(
        self, key: str, value: Any, *, expires_seconds: int | None = None
    ) -> bool:
        if not self.available:
            return False
        try:
            return bool(await self.client.set(key, value, ex=expires_seconds))
        except (RedisError, OSError):
            self.available = False
            logger.warning("redis_set_unavailable")
            return False

    async def delete(self, *keys: str) -> int:
        if not self.available:
            return 0
        try:
            return int(await self.client.delete(*keys))
        except (RedisError, OSError):
            self.available = False
            logger.warning("redis_delete_unavailable")
            return 0

    async def allow(self, key: str, limit: int, window_seconds: int) -> bool | None:
        if not self.available:
            return None
        script = """
        local current = redis.call('INCR', KEYS[1])
        if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        return current
        """
        try:
            async with asyncio.timeout(1):
                attempts = await self.client.eval(
                    script, 1, f"crm:rate:{key}", window_seconds
                )
            return int(attempts) <= limit
        except (RedisError, TimeoutError, OSError):
            self.available = False
            logger.warning("redis_rate_limit_unavailable_using_local_fallback")
            return None

    async def close(self) -> None:
        await self.client.aclose()


class ProcessResources:
    """Owns reusable clients for the lifetime of one application process."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.export_executor = ThreadPoolExecutor(
            max_workers=settings.export_concurrency,
            thread_name_prefix="crm-export",
        )
        self.export_slots = asyncio.Semaphore(settings.export_concurrency)
        self.database_engine = create_database_engine(settings)
        self.identity_engine = None
        if settings.auth_database_url is not None:
            auth_settings = settings.model_copy(
                update={
                    "database_url": settings.auth_database_url,
                    "auth_database_url": None,
                    "db_pool_size": 2,
                }
            )
            self.identity_engine = create_database_engine(auth_settings)
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout_seconds, connect=5),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_connections,
            ),
            follow_redirects=False,
            trust_env=False,
        )
        self.redis = None
        if settings.redis_url is not None:
            self.redis = RedisResource(
                Redis.from_url(
                    settings.redis_url.get_secret_value(),
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    max_connections=settings.redis_max_connections,
                )
            )

    async def start(self) -> None:
        if self.redis is not None:
            await self.redis.connect()

    async def close(self) -> None:
        await asyncio.to_thread(
            self.export_executor.shutdown, wait=True, cancel_futures=True
        )
        await self.http_client.aclose()
        if self.redis is not None:
            await self.redis.close()
        if self.identity_engine is not None:
            await self.identity_engine.dispose()
        await self.database_engine.dispose()

    async def acquire_export(self) -> None:
        await self.export_slots.acquire()

    def release_export(self) -> None:
        self.export_slots.release()

    async def run_export(self, function, *args):
        future = asyncio.get_running_loop().run_in_executor(
            self.export_executor, function, *args
        )
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(future)
            except Exception:
                pass
            raise
