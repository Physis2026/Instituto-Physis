# Physis Fatiador (Physis 3D, em desenvolvimento): PrusaSlicer em linha de comando atrás de uma API local.
#   docker compose build fatiador
# Licença: PrusaSlicer é AGPL-3.0 (programa separado, chamado pela linha de comando; nada é ligado ao hub).
# Ao redistribuir a imagem, leve o aviso de licença e o código-fonte (ou o link) do PrusaSlicer.
FROM debian:bookworm-slim

# [CONFERIR] o pacote prusa-slicer do Debian bookworm (versão 2.5.x) roda o modo linha de comando sem tela.
# Se pedir X11, troque o CMD por "xvfb-run -a python3 -m physis_fatiador.servidor" e instale o pacote xvfb.
RUN apt-get update && apt-get install -y --no-install-recommends python3 prusa-slicer ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PHYSIS_FATIADOR_PORTA=8730 PHYSIS_FATIADOR_ENDERECO=0.0.0.0 PHYSIS_FATIADOR_BIN=prusa-slicer

RUN useradd --system --uid 10730 --home-dir /srv/fatiador --shell /usr/sbin/nologin fatiador \
    && mkdir -p /srv/fatiador && chown fatiador /srv/fatiador
WORKDIR /srv/fatiador
COPY physis_fatiador /srv/fatiador/physis_fatiador
USER fatiador
EXPOSE 8730
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8730/saude', timeout=4)"
CMD ["python3", "-m", "physis_fatiador.servidor"]
