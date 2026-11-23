import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from starlette.requests import Request

from app.core.rate_limit import RequestBodyLimitMiddleware, RequestRateLimiter
from app.core.resources import ProcessResources, RedisResource
from app.core.settings import Settings
from app.main import create_app


class FailingRedis:
    available = True

    async def ping(self):
        raise RedisError("unavailable")

    async def get(self, key):
        raise RedisError("unavailable")

    async def set(self, *args, **kwargs):
        raise RedisError("unavailable")

    async def delete(self, *keys):
        raise RedisError("unavailable")

    async def aclose(self):
        return None

    async def eval(self, *args):
        raise RedisError("unavailable")


@pytest.mark.asyncio
async def test_redis_resource_degrades_without_raising():
    resource = RedisResource(FailingRedis())
    await resource.connect()
    assert resource.available is False
    assert await resource.get("cache-key") is None
    assert await resource.set("cache-key", "value") is False
    assert await resource.delete("cache-key") == 0
    assert await resource.allow("ip", 10, 60) is None


@pytest.mark.asyncio
async def test_export_capacity_queues_waiters_until_a_slot_is_released():
    settings = Settings(
        app_environment="test",
        database_url="postgresql+psycopg://test:test@localhost/test",
        export_concurrency=1,
    )
    resources = ProcessResources(settings)
    await resources.acquire_export()
    waiter = asyncio.create_task(resources.acquire_export())
    await asyncio.sleep(0)
    assert not waiter.done()
    resources.release_export()
    await asyncio.wait_for(waiter, timeout=1)
    resources.release_export()
    await resources.close()


@pytest.mark.asyncio
async def test_request_limiter_trusts_only_configured_forwarded_addresses():
    limiter = RequestRateLimiter(
        None, request_limit=1, window_seconds=60, max_keys=100, max_inflight=10
    )

    def request(forwarded: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/leads",
                "headers": [(b"x-forwarded-for", forwarded.encode())],
                "client": ("127.0.0.1", 50000),
                "server": ("testserver", 80),
                "scheme": "http",
            }
        )

    trusted = __import__("ipaddress").ip_network("127.0.0.0/8")
    assert await limiter.allow(request("198.51.100.1"), (trusted,))
    assert not await limiter.allow(request("198.51.100.1"), (trusted,))
    assert await limiter.allow(request("198.51.100.2"), (trusted,))


def test_api_rate_and_body_limits_reject_floods():
    settings = Settings(
        app_environment="test",
        database_url="postgresql+psycopg://test:test@localhost/test",
        api_requests_per_minute=10,
        api_max_request_bytes=1024,
    )
    client = TestClient(create_app(settings))
    for index in range(10):
        assert client.get("/api/v1/health/live").status_code == 200
    rejected = client.get("/api/v1/health/live")
    assert rejected.status_code == 429
    assert rejected.headers["Retry-After"] == "60"

    fresh = TestClient(create_app(settings))
    oversized = fresh.post("/api/v1/missing", content=b"x" * 1025)
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "request_too_large"


@pytest.mark.asyncio
async def test_chunked_body_is_rejected_without_reaching_the_app():
    reached = False

    async def downstream(scope, receive, send):
        nonlocal reached
        reached = True

    middleware = RequestBodyLimitMiddleware(downstream, max_bytes=4)
    messages = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"45", "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    await middleware(
        {"type": "http", "method": "POST", "path": "/", "headers": []},
        receive,
        send,
    )
    assert reached is False
    assert sent[0]["status"] == 413


def test_process_resources_are_reused_and_closed_once():
    settings = Settings(
        app_environment="test",
        database_url="postgresql+psycopg://test:test@localhost/test",
        db_pool_size=3,
        db_pool_recycle_seconds=600,
    )
    with TestClient(create_app(settings)) as client:
        engine = client.app.state.database_engine
        http_client = client.app.state.http_client
        assert engine.pool.size() == 3
        assert engine.pool._recycle == 600
        assert (
            client.get(
                "/api/v1/health/live", headers={"X-Request-ID": str(uuid4())}
            ).headers["Cache-Control"]
            == "no-store"
        )
        assert client.app.state.database_engine is engine
        assert client.app.state.http_client is http_client
        assert http_client.is_closed is False
    assert http_client.is_closed is True
