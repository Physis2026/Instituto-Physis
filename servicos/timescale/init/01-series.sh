#!/bin/sh
# Séries de alto volume (opcional, perfil "series"). A ponte (exportar_hub.py) grava; o Superset só lê.
set -eu
: "${SERIES_SENHA:?}" "${SERIES_LEITOR_SENHA:?}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v gr="$SERIES_SENHA" -v le="$SERIES_LEITOR_SENHA" <<'SQL'
CREATE EXTENSION IF NOT EXISTS timescaledb;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE ROLE series_gravador LOGIN PASSWORD :'gr';
CREATE ROLE series_leitor LOGIN PASSWORD :'le';
CREATE TABLE medida (
  instante   timestamptz NOT NULL,
  seq        bigint      NOT NULL,
  ativo      text        NOT NULL,
  grandeza   text        NOT NULL,
  valor      double precision NOT NULL,
  alarme     text        NOT NULL DEFAULT ''
);
SELECT create_hypertable('medida', 'instante', chunk_time_interval => INTERVAL '7 days');
CREATE UNIQUE INDEX medida_seq ON medida (seq, instante);
CREATE INDEX medida_ativo ON medida (ativo, grandeza, instante DESC);
ALTER TABLE medida SET (timescaledb.compress, timescaledb.compress_segmentby = 'ativo, grandeza');
SELECT add_compression_policy('medida', INTERVAL '30 days');
CREATE TABLE ponte_estado (id int PRIMARY KEY CHECK (id = 1), ultimo_seq bigint NOT NULL, quando timestamptz NOT NULL);
GRANT SELECT, INSERT ON medida TO series_gravador;
GRANT SELECT, INSERT, UPDATE ON ponte_estado TO series_gravador;
GRANT SELECT ON medida TO series_leitor;
ALTER ROLE series_leitor SET default_transaction_read_only = on;
SQL
