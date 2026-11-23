"""Create the least-privilege local database role used to provision platform operators."""

from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
PASSWORD_FILE = ROOT / ".docker-secrets" / "postgres_password"


def main() -> None:
    password = PASSWORD_FILE.read_text(encoding="utf-8").strip()
    if not password:
        raise RuntimeError("The local PostgreSQL password file is empty.")
    with psycopg.connect(
        host="127.0.0.1",
        port=55432,
        dbname="leadberry",
        user="postgres",
        password=password,
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname=%s", ("crm_platform_provisioner",)
        ).fetchone()
        if exists:
            connection.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier("crm_platform_provisioner"), sql.Literal(password)
                )
            )
        else:
            connection.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}"
                ).format(
                    sql.Identifier("crm_platform_provisioner"), sql.Literal(password)
                )
            )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier("leadberry"), sql.Identifier("crm_platform_provisioner")
            )
        )
        connection.execute("GRANT USAGE ON SCHEMA crm TO crm_platform_provisioner")
        connection.execute(
            "GRANT SELECT,INSERT,UPDATE ON crm.app_users TO crm_platform_provisioner"
        )
        connection.execute(
            "GRANT SELECT,INSERT,UPDATE ON crm.platform_operators TO crm_platform_provisioner"
        )
    print("Local platform provisioning role is ready.")


if __name__ == "__main__":
    main()