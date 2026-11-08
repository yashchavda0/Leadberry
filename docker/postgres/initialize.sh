#!/bin/sh
set -eu

# Local development only: every login role uses the one shared database password.
# Read it from the file without echoing it or expanding it into SQL.
export CRM_DB_PASSWORD="$(cat /run/secrets/postgres_password)"
test -n "$CRM_DB_PASSWORD"

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
\getenv db_password CRM_DB_PASSWORD
BEGIN;
CREATE ROLE crm_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'db_password';
CREATE ROLE crm_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'db_password';
CREATE ROLE crm_auth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'db_password';
CREATE ROLE crm_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'db_password';
ALTER DATABASE leadberry OWNER TO crm_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO crm_migrator;
COMMIT;
SQL
unset CRM_DB_PASSWORD
