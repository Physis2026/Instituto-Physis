#!/bin/sh
# Sobe o Superset de forma idempotente: migra o banco de metadados, garante o administrador e a conexão
# SOMENTE LEITURA com os dados do hub (PostGIS, papel bi_leitor), e então serve.
set -eu

superset db upgrade
if ! superset fab list-users 2>/dev/null | grep -q "username:${SUPERSET_ADMIN_USUARIO}"; then
  superset fab create-admin --username "$SUPERSET_ADMIN_USUARIO" --firstname Physis --lastname Admin \
    --email "$SUPERSET_ADMIN_EMAIL" --password "$SUPERSET_ADMIN_SENHA" >/dev/null
fi
superset init >/dev/null

# Conexões de dados (senhas só no ambiente; o Superset guarda cifrado com SECRET_KEY)
superset set-database-uri --database_name "Physis - dados do hub (somente leitura)" \
  --uri "postgresql+psycopg2://bi_leitor:${BI_LEITOR_SENHA}@postgis:5432/physis" >/dev/null || true
if [ -n "${SERIES_LEITOR_SENHA:-}" ]; then
  superset set-database-uri --database_name "Physis - séries (TimescaleDB, somente leitura)" \
    --uri "postgresql+psycopg2://series_leitor:${SERIES_LEITOR_SENHA}@timescaledb:5432/series" >/dev/null || true
fi

exec /usr/bin/run-server.sh
