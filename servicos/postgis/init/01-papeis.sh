#!/bin/sh
# Roda uma vez, quando o volume do PostGIS nasce. Papéis com o mínimo de poder:
#   exportador        grava nos schemas bi e geo (só o exportador_hub.py usa)
#   bi_leitor         só lê bi e geo (Superset); transação somente leitura
#   geoserver_leitor  só lê geo (GeoServer); transação somente leitura
set -eu
: "${EXPORTADOR_SENHA:?}" "${BI_LEITOR_SENHA:?}" "${GEOSERVER_LEITOR_SENHA:?}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v exp="$EXPORTADOR_SENHA" -v bi="$BI_LEITOR_SENHA" -v geo="$GEOSERVER_LEITOR_SENHA" <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS bi;
CREATE SCHEMA IF NOT EXISTS geo;
CREATE ROLE exportador LOGIN PASSWORD :'exp';
CREATE ROLE bi_leitor LOGIN PASSWORD :'bi';
CREATE ROLE geoserver_leitor LOGIN PASSWORD :'geo';
GRANT USAGE, CREATE ON SCHEMA bi, geo TO exportador;
GRANT USAGE ON SCHEMA bi, geo TO bi_leitor;
GRANT USAGE ON SCHEMA geo TO geoserver_leitor;
GRANT USAGE ON SCHEMA public TO bi_leitor, geoserver_leitor, exportador;
ALTER DEFAULT PRIVILEGES FOR ROLE exportador IN SCHEMA bi GRANT SELECT ON TABLES TO bi_leitor;
ALTER DEFAULT PRIVILEGES FOR ROLE exportador IN SCHEMA geo GRANT SELECT ON TABLES TO bi_leitor, geoserver_leitor;
ALTER ROLE bi_leitor SET default_transaction_read_only = on;
ALTER ROLE geoserver_leitor SET default_transaction_read_only = on;
SQL
