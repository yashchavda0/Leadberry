"""Run local tests against a uniquely created database, never the working CRM."""

import os
import json
from pathlib import Path
import subprocess
import sys
import time
import tempfile
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.marketplace.crypto import generate_keys


def main() -> int:
    secrets = ROOT / ".docker-secrets"
    passwords = {name: (secrets / f"{name}_password").read_text().strip() for name in ("postgres",)}
    if not all(passwords.values()):
        raise RuntimeError("Local test database secrets must not be empty")
    database = f"crm_frontend_{uuid4().hex}_test"
    arguments = {"host": "127.0.0.1", "port": 55432, "user": "postgres", "password": passwords["postgres"], "connect_timeout": 5}

    def url(user: str, password: str) -> str:
        return URL.create("postgresql+psycopg", username=user, password=password, host="127.0.0.1", port=55432, database=database).render_as_string(hide_password=False)

    created = False
    server = None
    try:
        with psycopg.connect(**arguments, dbname="postgres", autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {} OWNER crm_migrator").format(sql.Identifier(database)))
            created = True
        environment = {**os.environ, "DATABASE_URL": url("crm_migrator", passwords["postgres"]), "APP_ENVIRONMENT": "test"}
        key_directory = tempfile.TemporaryDirectory(prefix="crm-marketplace-test-")
        generate_keys(Path(key_directory.name))
        environment.update(MARKETPLACE_PUBLIC_KEY_FILE=str(Path(key_directory.name) / "marketplace-public.pem"),
                   TEST_MARKETPLACE_PRIVATE_KEY_FILE=str(Path(key_directory.name) / "marketplace-private.pem"))
        environment.pop("AUTH_DATABASE_URL", None)
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend", env=environment, check=True)
        environment.update(TEST_DATABASE_URL=url("postgres", passwords["postgres"]),
                           TEST_RUNTIME_DATABASE_URL=url("crm_api", passwords["postgres"]),
                           TEST_AUTH_DATABASE_URL=url("crm_auth", passwords["postgres"]))
        environment["TEST_WORKER_DATABASE_URL"] = url("crm_worker", passwords["postgres"])
        tests = [sys.executable, "-m", "pytest", "-q"]
        if "--marketplace" in sys.argv:
            tests.extend(["tests/test_marketplace.py", "tests/test_route_groups.py"])
        with (ROOT / "frontend" / "marketplace-test-results.log").open("w", encoding="utf-8") as test_log:
            result = subprocess.run(tests, cwd=ROOT / "backend", env=environment, stdout=test_log, stderr=subprocess.STDOUT).returncode
        print((ROOT / "frontend" / "marketplace-test-results.log").read_text(encoding="utf-8"))
        if result or "--browser" not in sys.argv:
            return result
        environment.update(DATABASE_URL=environment["TEST_RUNTIME_DATABASE_URL"],
                           AUTH_DATABASE_URL=environment["TEST_AUTH_DATABASE_URL"],
                           ALLOWED_ORIGINS=json.dumps(["http://127.0.0.1:3012"]))
        with (ROOT / "frontend" / "test-api.log").open("w") as log:
            server = subprocess.Popen(
                [sys.executable, "-c",
                 "import asyncio,sys,uvicorn; from app.main import create_app; "
                 "server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8013,access_log=False)); "
                 "asyncio.run(server.serve(),loop_factory=asyncio.SelectorEventLoop if sys.platform=='win32' else None)"],
                cwd=ROOT / "backend", env=environment, stdout=log, stderr=log,
            )
            for _ in range(60):
                if server.poll() is not None:
                    raise RuntimeError("Isolated browser-test API failed to start; inspect frontend test-api.log")
                try:
                    with urlopen("http://127.0.0.1:8013/api/v1/health/ready", timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    time.sleep(1)
            else:
                raise RuntimeError("Browser-test API did not become ready")
            browser_command = ["node", str(ROOT / "frontend" / "node_modules" / "@playwright" / "test" / "cli.js"), "test"]
            if "--marketplace" in sys.argv:
                browser_command.extend(["-g", "marketplace"])
            with (ROOT / "frontend" / "marketplace-browser-results.log").open("w", encoding="utf-8") as browser_log:
                result = subprocess.run(browser_command, cwd=ROOT / "frontend", env=environment, stdout=browser_log, stderr=subprocess.STDOUT).returncode
            print((ROOT / "frontend" / "marketplace-browser-results.log").read_text(encoding="utf-8"))
            return result
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        if created:
            with psycopg.connect(**arguments, dbname="postgres", autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
            print("Removed only the uniquely created disposable test database.")
        if "key_directory" in locals():
            key_directory.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
