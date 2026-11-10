from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from .settings import Settings

SCHEMA_REVISION = "0013_lead_status_history"


def create_database_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=0,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        hide_parameters=True,
        echo=False,
        connect_args={
            "connect_timeout": 3,
            "options": (
                f"-c statement_timeout={settings.db_statement_timeout_ms} "
                f"-c lock_timeout={settings.db_lock_timeout_ms} "
                "-c idle_in_transaction_session_timeout=15000"
            ),
        },
    )


@asynccontextmanager
async def tenant_transaction(
    engine: AsyncEngine,
    org_id: UUID,
    membership_id: UUID | None = None,
) -> AsyncGenerator[AsyncConnection, None]:
    """Only call with tenant identity already verified by authentication."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "SELECT set_config('app.org_id', :org_id, true), "
                "set_config('app.membership_id', :membership_id, true)"
            ),
            {
                "org_id": str(org_id),
                "membership_id": (
                    str(membership_id) if membership_id is not None else ""
                ),
            },
        )
        yield connection


async def check_database_readiness(engine: AsyncEngine) -> bool:
    async with engine.connect() as connection:
        revision = await connection.scalar(
            text("SELECT version_num FROM public.alembic_version")
        )
        role_is_safe = await connection.scalar(
            text(
                "SELECT NOT (r.rolsuper OR r.rolbypassrls) "
                "AND NOT pg_has_role(current_user, c.relowner, 'MEMBER') "
                "FROM pg_roles r JOIN pg_class c ON c.oid = 'crm.organizations'::regclass "
                "WHERE r.rolname = current_user"
            )
        )
        return revision == SCHEMA_REVISION and role_is_safe is True
