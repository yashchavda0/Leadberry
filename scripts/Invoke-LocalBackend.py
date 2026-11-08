"""Native local launcher for environments that disable PowerShell scripts."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy.engine import URL
from app.modules.marketplace.crypto import generate_keys


def database_url(role: str) -> str:
    password = (ROOT / ".docker-secrets" / "postgres_password").read_text(encoding="utf-8").strip()
    if not password:
        raise RuntimeError("Local database secret is empty")
    return URL.create("postgresql+psycopg", username=role, password=password, host="127.0.0.1", port=55432,
                      database="leadberry").render_as_string(hide_password=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["migrate", "keys", "run", "worker"])
    parser.add_argument("--organization", type=UUID)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int)
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()
    os.chdir(BACKEND)
    os.environ["APP_ENVIRONMENT"] = "development"
    os.environ.pop("AUTH_DATABASE_URL", None)
    if arguments.frontend_port is not None:
        os.environ["ALLOWED_ORIGINS"] = json.dumps([f"http://localhost:{arguments.frontend_port}", f"http://127.0.0.1:{arguments.frontend_port}"])
    if arguments.action == "keys":
        generate_keys(ROOT / ".docker-secrets")
        return
    if arguments.action == "migrate":
        os.environ["DATABASE_URL"] = database_url("crm_migrator")
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
        return
    public_key = ROOT / ".docker-secrets" / "marketplace-public.pem"
    if public_key.exists():
        os.environ["MARKETPLACE_PUBLIC_KEY_FILE"] = str(public_key)
    if arguments.action == "worker":
        if arguments.organization is None:
            parser.error("worker requires --organization")
        os.environ["DATABASE_URL"] = database_url("crm_worker")
        command = [sys.executable, "-m", "app.modules.marketplace.worker", "--organization", str(arguments.organization),
                   "--private-key", str(ROOT / ".docker-secrets" / "marketplace-private.pem")]
        if arguments.once:
            command.append("--once")
        subprocess.run(command, check=True)
        return
    os.environ["DATABASE_URL"] = database_url("crm_api")
    os.environ["AUTH_DATABASE_URL"] = database_url("crm_auth")
    import uvicorn
    from app.main import create_app
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=arguments.port, access_log=False))
    asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)


if __name__ == "__main__":
    main()