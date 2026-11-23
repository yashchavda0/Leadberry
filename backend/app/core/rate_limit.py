from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import time
from collections import deque
from typing import Protocol

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class CoordinatedRateLimit(Protocol):
    async def allow(self, key: str, limit: int, window_seconds: int) -> bool | None: ...


class RequestRateLimiter:
    """Bounded local failover around an optional cross-process coordinator."""

    def __init__(
        self,
        coordinated: CoordinatedRateLimit | None,
        *,
        request_limit: int,
        window_seconds: int,
        max_keys: int,
        max_inflight: int,
    ) -> None:
        self.coordinated = coordinated
        self.request_limit = request_limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self.semaphore = asyncio.Semaphore(max_inflight)
        self._windows: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def client_key(
        request: Request,
        trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
    ) -> str:
        remote = request.client.host if request.client else "0.0.0.0"
        try:
            address = ipaddress.ip_address(remote)
        except ValueError:
            address = ipaddress.ip_address("0.0.0.0")
        if any(address in network for network in trusted_proxies):
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                candidate = forwarded.split(",", 1)[0].strip()
                try:
                    address = ipaddress.ip_address(candidate)
                except ValueError:
                    pass
        return hashlib.sha256(str(address).encode("ascii")).hexdigest()

    async def allow(
        self,
        request: Request,
        trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
    ) -> bool:
        key = f"api:{self.client_key(request, trusted_proxies)}"
        if self.coordinated is not None:
            coordinated = await self.coordinated.allow(
                key, self.request_limit, self.window_seconds
            )
            if coordinated is not None:
                return coordinated

        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            timestamps = self._windows.get(key)
            if timestamps is None:
                if len(self._windows) >= self.max_keys:
                    oldest = next(iter(self._windows))
                    self._windows.pop(oldest, None)
                timestamps = deque()
                self._windows[key] = key_times = timestamps
            else:
                key_times = timestamps
            while key_times and key_times[0] <= cutoff:
                key_times.popleft()
            if len(key_times) >= self.request_limit:
                return False
            key_times.append(now)
            return True

    def evict_expired(self) -> None:
        cutoff = time.monotonic() - self.window_seconds
        expired = [
            key
            for key, timestamps in self._windows.items()
            if not timestamps or timestamps[-1] <= cutoff
        ]
        for key in expired:
            self._windows.pop(key, None)


class RequestBodyLimitMiddleware:
    """Reject oversized and fragmented bodies before FastAPI parses them."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        messages: list[Message] = []
        body_bytes = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                await self.app(scope, self._replay(messages), send)
                return
            if message["type"] != "http.request":
                continue
            body_bytes += len(message.get("body", b""))
            if body_bytes > self.max_bytes or len(messages) > 2048:
                response = JSONResponse(
                    {"status": 413, "code": "request_too_large"},
                    status_code=413,
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        await self.app(scope, self._replay(messages), send)

    @staticmethod
    def _replay(messages: list[Message]) -> Receive:
        position = 0

        async def receive() -> Message:
            nonlocal position
            if position < len(messages):
                message = messages[position]
                position += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        return receive
