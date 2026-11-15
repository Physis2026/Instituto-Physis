# Physis Hub em contêiner (servidor da Physis: site, loja e Gestão interna).
# O código vem do contexto adicional "pacote" (compose: PHYSIS_PACOTE = pasta do pacote montado ou ../physis-hub).
# Só biblioteca padrão do Python: nada de pip.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --system --uid 10700 --home-dir /dados --no-create-home --shell /usr/sbin/nologin physis \
    && mkdir -p /opt/physis /dados && chown physis:physis /dados

COPY --from=pacote physis_hub /opt/physis/physis_hub
COPY --from=pacote web /opt/physis/web
COPY --from=pacote docs /opt/physis/docs
COPY --from=pacote tests /opt/physis/tests
RUN find /opt/physis -name __pycache__ -prune -exec rm -rf {} + \
    && find /opt/physis -name '*.db' -delete \
    && chmod -R a+rX,go-w /opt/physis

WORKDIR /opt/physis
USER physis
EXPOSE 8700
STOPSIGNAL SIGINT
CMD ["python", "-m", "physis_hub.servidor"]
