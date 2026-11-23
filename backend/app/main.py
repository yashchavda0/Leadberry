import asyncio
import ipaddress
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .core.database import check_database_readiness
from .core.rate_limit import RequestBodyLimitMiddleware, RequestRateLimiter
from .core.resources import ProcessResources
from .core.settings import Settings
from .modules.identity.routes import router as identity_router
from .modules.identity.service import AccessError, IdentityService
from .modules.leads.dashboard import router as dashboard_router
from .modules.leads.assignment_rules import router as assignment_rules_router
from .modules.leads.activities import router as lead_activities_router
from .modules.leads.configuration import router as lead_configuration_router
from .modules.leads.export import router as lead_export_router
from .modules.leads.follow_ups import router as follow_ups_router
from .modules.leads.intake import router as intake_router
from .modules.leads.reports import router as reports_router
from .modules.leads.routes import router as leads_router
from .modules.leads.teams import router as teams_router
from .modules.marketplace.routes import router as marketplace_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    configuration = settings if settings is not None else Settings()

    trusted_proxies = tuple(
        ipaddress.ip_network(value) for value in configuration.trusted_proxy_networks
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        resources = ProcessResources(configuration)
        app.state.process_resources = resources
        app.state.request_limiter = RequestRateLimiter(
            resources.redis,
            request_limit=configuration.api_requests_per_minute,
            window_seconds=60,
            max_keys=configuration.api_rate_limit_buckets,
            max_inflight=configuration.api_max_inflight_requests,
        )
        app.state.database_engine = resources.database_engine
        app.state.identity_engine = resources.identity_engine
        app.state.http_client = resources.http_client
        app.state.redis = resources.redis
        if resources.identity_engine is not None:
            app.state.identity_service = IdentityService(
                resources.identity_engine, configuration.session_hours
            )
        await resources.start()
        try:
            yield
        finally:
            await resources.close()

    app = FastAPI(
        title="Lead-centric CRM API",
        version="0.3.0",
        lifespan=lifespan,
        docs_url=(
            "/api/v1/docs" if configuration.app_environment != "production" else None
        ),
        redoc_url=None,
        openapi_url=(
            "/api/v1/openapi.json"
            if configuration.app_environment != "production"
            else None
        ),
    )
    app.state.configuration = configuration
    app.state.trusted_proxy_networks = trusted_proxies
    app.state.request_limiter = RequestRateLimiter(
        None,
        request_limit=configuration.api_requests_per_minute,
        window_seconds=60,
        max_keys=configuration.api_rate_limit_buckets,
        max_inflight=configuration.api_max_inflight_requests,
    )
    app.add_middleware(
        RequestBodyLimitMiddleware, max_bytes=configuration.api_max_request_bytes
    )
    app.include_router(identity_router)
    # Before the leads router, whose /leads/{lead_id} would otherwise capture /leads/export.
    app.include_router(lead_export_router)
    app.include_router(reports_router)
    app.include_router(follow_ups_router)
    app.include_router(lead_activities_router)
    app.include_router(assignment_rules_router)
    app.include_router(intake_router)
    app.include_router(leads_router)
    app.include_router(lead_configuration_router)
    app.include_router(teams_router)
    app.include_router(dashboard_router)
    app.include_router(marketplace_router)

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        supplied_request_id = request.headers.get("X-Request-ID")
        try:
            request_id = (
                str(UUID(supplied_request_id)) if supplied_request_id else str(uuid4())
            )
        except ValueError:
            request_id = str(uuid4())
        request.state.request_id = request_id
        started = time.monotonic()
        acquired = False
        try:
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit():
                if int(content_length) > configuration.api_max_request_bytes:
                    return JSONResponse(
                        {"status": 413, "code": "request_too_large"},
                        status_code=413,
                        headers={"X-Request-ID": request_id},
                    )
            limiter = request.app.state.request_limiter
            if not await limiter.allow(request, trusted_proxies):
                logger.warning(
                    "api_rate_limit_rejected request_id=%s path=%s",
                    request_id,
                    request.url.path,
                )
                return JSONResponse(
                    {"status": 429, "code": "rate_limit_exceeded"},
                    status_code=429,
                    headers={
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(configuration.api_requests_per_minute),
                        "X-Request-ID": request_id,
                    },
                )
            try:
                await asyncio.wait_for(limiter.semaphore.acquire(), timeout=0.05)
                acquired = True
            except TimeoutError:
                logger.warning(
                    "api_capacity_rejected request_id=%s path=%s",
                    request_id,
                    request.url.path,
                )
                return JSONResponse(
                    {"status": 503, "code": "service_busy"},
                    status_code=503,
                    headers={"Retry-After": "1", "X-Request-ID": request_id},
                )
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(
                configuration.api_requests_per_minute
            )
        finally:
            if acquired:
                request.app.state.request_limiter.semaphore.release()
            logger.info(
                "request_finished method=%s path=%s request_id=%s elapsed_ms=%.2f",
                request.method,
                request.url.path,
                request_id,
                (time.monotonic() - started) * 1000,
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(AccessError)
    async def access_error(request: Request, error: AccessError):
        logger.warning(
            "access_rejected code=%s request_id=%s",
            error.code,
            request.state.request_id,
        )
        return JSONResponse(
            {"type": "about:blank", "status": error.status, "code": error.code},
            status_code=error.status,
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # FastAPI's default input echo could expose submitted passwords/tokens.
        logger.warning(
            "request_validation_rejected request_id=%s details=%s",
            request.state.request_id,
            [(item["loc"], item["type"]) for item in error.errors()],
        )
        return JSONResponse(
            {
                "status": 422,
                "code": "invalid_request",
                "errors": [
                    {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
                    for item in error.errors()
                ],
            },
            status_code=422,
            media_type="application/problem+json",
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
        if isinstance(error, IntegrityError) and sqlstate in (
            "23505",
            "23503",
            "23514",
        ):
            logger.warning(
                "database_constraint_rejected sqlstate=%s request_id=%s",
                sqlstate,
                request.state.request_id,
            )
            return JSONResponse(
                {"status": 409, "code": "conflicting_state"}, status_code=409
            )
        logger.error(
            "database_operation_unavailable sqlstate=%s request_id=%s",
            sqlstate,
            request.state.request_id,
        )
        return JSONResponse(
            {"status": 503, "code": "database_unavailable"}, status_code=503
        )

    @app.get("/api/v1/health/live", tags=["Health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready", response_model=None, tags=["Health"])
    async def ready(request: Request) -> JSONResponse:
        try:
            async with asyncio.timeout(3):
                healthy = await check_database_readiness(
                    request.app.state.database_engine
                )
                if healthy and request.app.state.identity_engine is not None:
                    healthy = await check_database_readiness(
                        request.app.state.identity_engine
                    )
        except (SQLAlchemyError, TimeoutError):
            # Driver exception messages can contain connection credentials.
            logger.warning("database_readiness_unavailable")
            return JSONResponse({"status": "not_ready"}, status_code=503)
        if not healthy:
            logger.warning("database_readiness_schema_or_role_invalid")
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready"})

    return app
