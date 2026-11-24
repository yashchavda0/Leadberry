import argparse
import asyncio
import getpass
import os
import sys
from uuid import uuid4

from pydantic import EmailStr, SecretStr, TypeAdapter
from sqlalchemy import text
from sqlalchemy.engine import make_url

from ...core.database import create_database_engine
from ...core.event_loop import selector_event_loop
from ...core.settings import Settings
from .security import PasswordService


async def provision(email: str, full_name: str, access_level: str) -> None:
    database_url = os.environ.get("PLATFORM_PROVISION_DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "Set PLATFORM_PROVISION_DATABASE_URL to a restricted deployment-provisioning database credential."
        )
    settings = Settings(
        database_url=SecretStr(database_url),
        auth_database_url=None,
        app_environment=os.environ.get("APP_ENVIRONMENT", "development"),
    )
    if make_url(database_url).username != "crm_platform_provisioner":
        raise SystemExit(
            "PLATFORM_PROVISION_DATABASE_URL must authenticate as crm_platform_provisioner."
        )
    engine = create_database_engine(settings)
    try:
        async with engine.begin() as connection:
            user = (
                (
                    await connection.execute(
                        text("SELECT id,password_hash FROM crm.app_users WHERE email=:email FOR UPDATE"),
                        {"email": email},
                    )
                )
                .mappings()
                .first()
            )
            if user is not None:
                operator = await connection.scalar(
                    text("SELECT 1 FROM crm.platform_operators WHERE user_id=:id"),
                    {"id": user["id"]},
                )
                if not operator:
                    raise SystemExit(
                        "That email already belongs to a customer identity; use a dedicated platform-admin email."
                    )
            if user is None or user["password_hash"] is None:
                password = getpass.getpass("Set platform operator password (min 12 characters): ")
                confirmation = getpass.getpass("Confirm password: ")
                if len(password) < 12 or password != confirmation:
                    raise SystemExit("Passwords must match and contain at least 12 characters.")
                password_hash = await PasswordService().hash(password)
                if user is None:
                    user_id = uuid4()
                    await connection.execute(
                        text(
                            "INSERT INTO crm.app_users(id,email,full_name,password_hash) "
                            "VALUES(:id,:email,:name,:hash)"
                        ),
                        {"id": user_id, "email": email, "name": full_name, "hash": password_hash},
                    )
                else:
                    user_id = user["id"]
                    await connection.execute(
                        text(
                            "UPDATE crm.app_users SET password_hash=:hash,password_change_required=false,updated_at=now() "
                            "WHERE id=:id"
                        ),
                        {"id": user_id, "hash": password_hash},
                    )
            else:
                user_id = user["id"]
            await connection.execute(
                text(
                    "INSERT INTO crm.platform_operators(user_id,access_level) VALUES(:user,:level) "
                    "ON CONFLICT(user_id) DO UPDATE SET access_level=EXCLUDED.access_level"
                ),
                {"user": user_id, "level": access_level},
            )
    finally:
        await engine.dispose()
    print(f"Platform operator provisioned: {email} ({access_level}).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a LeadBerry platform operator")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Platform Operator")
    parser.add_argument("--access-level", choices=("support", "administrator"), default="administrator")
    args = parser.parse_args()
    email = str(TypeAdapter(EmailStr).validate_python(args.email)).strip().lower()
    asyncio.run(
        provision(email, args.name, args.access_level),
        loop_factory=selector_event_loop if sys.platform == "win32" else None,
    )


if __name__ == "__main__":
    main()