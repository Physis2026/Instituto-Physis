# Instantâneo do banco do hub + exportação para PostGIS (BI e mapas) e TimescaleDB (séries).
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && pip check
RUN useradd --system --uid 10701 --no-create-home --shell /usr/sbin/nologin exportador
COPY instantaneo.py exportar_hub.py configurar_camadas.py camadas.json /app/
USER exportador
WORKDIR /app
CMD ["python", "/app/exportar_hub.py"]
