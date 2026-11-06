#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_password="$PORTFLOW_DB_PASSWORD" <<'EOSQL'
CREATE ROLE portflow_app
  LOGIN
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOINHERIT
  NOREPLICATION
  NOBYPASSRLS
  PASSWORD :'app_password';
GRANT CONNECT ON DATABASE portflow TO portflow_app;
GRANT USAGE, CREATE ON SCHEMA public TO portflow_app;
EOSQL
