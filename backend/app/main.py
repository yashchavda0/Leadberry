import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .core.database import check_database_readiness, create_database_engine
from .core.settings import Settings
from .modules.identity.routes import router as identity_router
from .modules.identity.service import AccessError, IdentityService
from .modules.leads.dashboard import router as dashboard_router
from .modules.leads.configuration import router as lead_configuration_router
from .modules.leads.routes import router as leads_router
from .modules.leads.teams import router as teams_router
from .modules.marketplace.routes import router as marketplace_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    configuration = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        engine = create_database_engine(configuration)
        app.state.database_engine = engine
        auth_engine = None
        app.state.identity_engine = None
        if configuration.auth_database_url is not None:
            auth_settings = configuration.model_copy(
                update={
                    "database_url": configuration.auth_database_url,
                    "auth_database_url": None,
                    "db_pool_size": 2,
                }
            )
            auth_engine = create_database_engine(auth_settings)
            app.state.identity_engine = auth_engine
            app.state.identity_service = IdentityService(
                auth_engine, configuration.session_hours
            )
        try:
            yield
        finally:
            await engine.dispose()
            if auth_engine is not None:
                await auth_engine.dispose()

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
    app.include_router(identity_router)
    app.include_router(leads_router)
    app.include_router(lead_configuration_router)
    app.include_router(teams_router)
    app.include_router(dashboard_router)
    app.include_router(marketplace_router)

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AccessError)
    async def access_error(request: Request, error: AccessError):
        logger.warning("access_rejected code=%s", error.code)
        return JSONResponse(
            {"type": "about:blank", "status": error.status, "code": error.code},
            status_code=error.status,
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # FastAPI's default input echo could expose submitted passwords/tokens.
        logger.warning(
            "request_validation_rejected %s",
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
            logger.warning("database_constraint_rejected sqlstate=%s", sqlstate)
            return JSONResponse(
                {"status": 409, "code": "conflicting_state"}, status_code=409
            )
        logger.error("database_operation_unavailable sqlstate=%s", sqlstate)
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
