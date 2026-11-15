# Physis Calc — motores de cálculo (pvlib, windpowerlib, EnergyPlus, EPANET/wntr, SWMM/pyswmm)
#   docker compose build calc
#   docker compose build --build-arg INSTALAR_ENERGYPLUS=1 \
#       --build-arg EPLUS_URL=<url do .tar.gz Linux da release> --build-arg EPLUS_SHA256=<sha256> calc
# O EnergyPlus é opcional (≈ 1 GB). Sem ele, /termica devolve o IDF (?somente_entrada=1) e 503 ao rodar.
FROM python:3.12-slim-bookworm

ARG INSTALAR_ENERGYPLUS=0
# [CONFERIR] na página de releases do EnergyPlus (github.com/NREL/EnergyPlus/releases), versão 24.2.x,
# arquivo Linux Ubuntu 22.04 x86_64 .tar.gz, e o SHA-256 publicado/calculado. Vazio = não instala.
ARG EPLUS_URL=""
ARG EPLUS_SHA256=""

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PHYSIS_CALC_PORTA=8710 PHYSIS_CALC_ENDERECO=0.0.0.0 PHYSIS_CALC_EPW=/dados/epw

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && pip check

RUN if [ "$INSTALAR_ENERGYPLUS" = "1" ]; then \
        test -n "$EPLUS_URL" && test -n "$EPLUS_SHA256" || { echo "EPLUS_URL e EPLUS_SHA256 obrigatorios"; exit 1; }; \
        curl -fsSL "$EPLUS_URL" -o /tmp/eplus.tar.gz \
        && echo "$EPLUS_SHA256  /tmp/eplus.tar.gz" | sha256sum -c - \
        && mkdir -p /opt/energyplus && tar -xzf /tmp/eplus.tar.gz -C /opt/energyplus --strip-components=1 \
        && ln -s /opt/energyplus/energyplus /usr/local/bin/energyplus && rm /tmp/eplus.tar.gz; \
    fi

RUN useradd --system --uid 10710 --home-dir /srv/calc --shell /usr/sbin/nologin calc \
    && mkdir -p /srv/calc /dados/epw && chown calc /srv/calc
WORKDIR /srv/calc
COPY physis_calc /srv/calc/physis_calc
USER calc
EXPOSE 8710
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8710/saude', timeout=4)"
CMD ["python", "-m", "physis_calc.servidor"]
