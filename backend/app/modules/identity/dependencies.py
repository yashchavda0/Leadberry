from typing import Annotated

from fastapi import Depends, Header, Request, Response

from ...core.rate_limit import RequestRateLimiter
from .security import CSRF_COOKIE, SESSION_COOKIE
from .service import AccessError, IdentityService, Principal


def identity(request: Request) -> IdentityService:
    service = getattr(request.app.state, "identity_service", None)
    if service is None:
        raise AccessError(503, "identity_database_not_configured")
    return service


def validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if (
        origin is not None
        and origin not in request.app.state.configuration.allowed_origins
    ):
        raise AccessError(403, "origin_not_allowed")


async def principal(
    request: Request,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AccessError(401, "authentication_required")
    csrf = None
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        validate_origin(request)
        csrf = csrf_token
        if not csrf:
            raise AccessError(403, "csrf_required")
    user = await identity(request).authenticate(token, csrf)
    if user.password_change_required and request.url.path not in (
        "/api/v1/auth/me",
        "/api/v1/auth/password",
        "/api/v1/auth/logout",
    ):
        raise AccessError(403, "password_change_required")
    if (
        user.access_mode == "export_only"
        and request.method not in ("GET", "HEAD", "OPTIONS")
        and request.url.path not in ("/api/v1/auth/logout", "/api/v1/auth/password")
    ):
        raise AccessError(403, "export_only_access")
    return user


User = Annotated[Principal, Depends(principal)]


def set_session(request: Request, response: Response, tokens: tuple[str, str]) -> dict:
    secure = request.app.state.configuration.app_environment == "production"
    for name, value, http_only in (
        (SESSION_COOKIE, tokens[0], True),
        (CSRF_COOKIE, tokens[1], False),
    ):
        response.set_cookie(
            name,
            value,
            httponly=http_only,
            secure=secure,
            samesite="strict",
            max_age=request.app.state.configuration.session_hours * 3600,
            path="/",
        )
    return {"status": "authenticated", "csrf_token": tokens[1]}


async def public_throttle(
    request: Request, operation: str, account: str | None = None
) -> IdentityService:
    validate_origin(request)
    service = identity(request)
    client_key = RequestRateLimiter.client_key(
        request, request.app.state.trusted_proxy_networks
    )
    await service.throttle(
        f"{operation}:ip:{client_key}", 5 if operation == "onboard" else 30
    )
    if account:
        await service.throttle(f"{operation}:account:{account}", 10)
    return service
