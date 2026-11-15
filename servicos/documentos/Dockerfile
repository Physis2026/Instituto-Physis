# Physis Doc: LibreOffice headless (ODT/ODS -> PDF/A-2b) + veraPDF (validação PDF/A), API local na porta 8720.
# Licenças: LibreOffice MPL-2.0; veraPDF GPLv3+ / MPLv2+ (dupla). Ambos rodam como programas separados,
# chamados por linha de comando por este serviço; nada é ligado ao código do hub.
#
#   docker compose build --build-arg VERAPDF_URL=<zip do instalador> --build-arg VERAPDF_SHA256=<sha256> documentos
FROM debian:bookworm-slim

# veraPDF "greenfield" fixo. [CONFERIR] em https://docs.verapdf.org/install/ e na página de downloads:
# versão 1.26.x, arquivo verapdf-greenfield-<versão>-installer.zip e o SHA-256 dele. Vazio = sem veraPDF (/pdfa/validar -> 503).
ARG VERAPDF_VERSAO=1.26.2
ARG VERAPDF_URL=""
ARG VERAPDF_SHA256=""

ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp \
    PHYSIS_DOC_PORTA=8720 PHYSIS_DOC_ENDERECO=0.0.0.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 ca-certificates curl unzip \
        libreoffice-writer-nogui libreoffice-calc-nogui \
        fonts-dejavu fonts-liberation2 fonts-crosextra-carlito fonts-crosextra-caladea \
        openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

COPY verapdf-auto-install.xml /tmp/verapdf-auto-install.xml
RUN if [ -n "$VERAPDF_URL" ]; then \
        test -n "$VERAPDF_SHA256" || { echo "VERAPDF_SHA256 obrigatorio"; exit 1; }; \
        curl -fsSL "$VERAPDF_URL" -o /tmp/verapdf.zip \
        && echo "$VERAPDF_SHA256  /tmp/verapdf.zip" | sha256sum -c - \
        && unzip -q /tmp/verapdf.zip -d /tmp/verapdf \
        && java -jar /tmp/verapdf/*/verapdf-izpack-installer-*.jar /tmp/verapdf-auto-install.xml \
        && ln -s /opt/verapdf/verapdf /usr/local/bin/verapdf \
        && rm -rf /tmp/verapdf /tmp/verapdf.zip; \
    fi

RUN useradd --system --uid 10720 --no-create-home --shell /usr/sbin/nologin physisdoc && mkdir -p /srv/doc
COPY physis_doc /srv/doc/physis_doc
WORKDIR /srv/doc
USER physisdoc
EXPOSE 8720
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8720/saude', timeout=4)"
CMD ["python3", "-m", "physis_doc.servidor"]
