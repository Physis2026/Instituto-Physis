"""Recorte em Python do contrato physis/1 (`physis-nucleo.js`).

Cobre o que o hub precisa: organizacao, topico, faixa e alarme de medicao.
As grandezas marcadas NOVA ainda nao existem no nucleo em JavaScript e tem de
entrar la e no `physis-ponte.py` no mesmo passo (memo, secao 4.2).
"""
from __future__ import annotations

import re

VERSAO_CONTRATO = "physis/1"
RE_ORG = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
RE_GRANDEZA = re.compile(r"^[a-z0-9_-]+$")
RE_ATIVO = re.compile(r"^[a-z0-9._-]+$")

# grandeza: (minimo, maximo, unidade). None = sem faixa de alarme.
FAIXAS: dict[str, tuple[float | None, float | None, str]] = {
    # ja existentes em physis-nucleo.js
    "energia": (0, 500, "kW"), "tensao": (198, 242, "V"), "corrente": (0, 630, "A"),
    "fp": (0.92, 1, "-"), "temperatura": (0, 80, "C"), "umidade": (20, 90, "%"),
    "nivel": (5, 95, "%"), "pressao": (0, 10, "bar"), "vazao": (0, 100, "m3/h"),
    # NOVAS — rede V6 e dispositivos via ESP
    "umidade_solo": (0, 100, "%"),
    "estado": (None, None, "0/1"),
    "previsao_min": (None, None, "min"),
    "bateria": (3.3, 4.3, "V"),
    "rssi": (-120, 0, "dBm"),
    "snr": (None, None, "dB"),
    "latitude": (-90, 90, "grau"),
    "longitude": (-180, 180, "grau"),
    "atividade": (None, None, "0-2"),
    "impacto": (None, None, "0/1"),
    "porcoes": (None, None, "un"),
}
GRANDEZAS_NOVAS = ("umidade_solo", "estado", "previsao_min", "bateria", "rssi", "snr",
                   "latitude", "longitude", "atividade", "impacto", "porcoes")


def org_valido(org: str) -> bool:
    return bool(RE_ORG.match(str(org or "")))


def montar_topico(org: str, grandeza: str, ativo: str) -> str | None:
    if not org_valido(org):
        return None
    g, a = str(grandeza or "").lower(), str(ativo or "").lower()
    if not RE_GRANDEZA.match(g) or not RE_ATIVO.match(a):
        return None
    return f"physis/{org}/{g}/{a}"


def avaliar_alarme(grandeza: str, valor: float) -> str:
    f = FAIXAS.get(grandeza)
    if f is None or (f[0] is None and f[1] is None):
        return "sem_faixa"
    if f[0] is not None and valor < f[0]:
        return "baixo"
    if f[1] is not None and valor > f[1]:
        return "alto"
    return "ok"


def unidade(grandeza: str) -> str:
    f = FAIXAS.get(grandeza)
    return f[2] if f else ""
