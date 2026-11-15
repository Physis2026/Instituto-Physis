"""Configuração do Superset (BI aberto no lugar do Power BI). Segredos só por ambiente (env/superset.env)."""
import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://{u}:{s}@superset-db:5432/{d}".format(
        u=os.environ.get("SUPERSET_DB_USUARIO", "superset"), s=os.environ["SUPERSET_DB_SENHA"],
        d=os.environ.get("SUPERSET_DB_NOME", "superset")))

# atrás do Caddy (HTTPS); cookies só por HTTPS
ENABLE_PROXY_FIX = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
WTF_CSRF_ENABLED = True
TALISMAN_ENABLED = True

# nada de SQLite nem de conexões "perigosas": os dados do hub chegam pelo PostGIS (schema bi, só leitura)
PREVENT_UNSAFE_DB_CONNECTIONS = True
FEATURE_FLAGS = {"DASHBOARD_RBAC": True, "ENABLE_TEMPLATE_PROCESSING": False}
SQLLAB_TIMEOUT = 60
SUPERSET_WEBSERVER_TIMEOUT = 120
ROW_LIMIT = 50000

# independência: sem mapas de terceiros com chave; sem envio de uso
MAPBOX_API_KEY = ""

CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}
DATA_CACHE_CONFIG = CACHE_CONFIG
RATELIMIT_STORAGE_URI = "memory://"
BABEL_DEFAULT_LOCALE = "pt_BR"
