import asyncio
import os
import sys

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.settings import Settings


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=None,
        version_table_schema="public",
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    url = os.environ.get("MIGRATION_DATABASE_URL") or Settings().database_url.get_secret_value()
    engine = create_async_engine(
        url,
        poolclass=pool.NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        dialect_name="postgresql",
        literal_binds=True,
        version_table_schema="public",
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    # Psycopg async connections require a selector loop on Windows.
    asyncio.run(
        run_online(),
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None,
    )
