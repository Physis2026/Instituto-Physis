"""Recorte em Python do contrato physis/1 (`physis-nucleo.js`).

Cobre o que o hub precisa: organizacao, topico, faixa e alarme de medicao.
As grandezas marcadas NOVAS (GRANDEZAS_NOVAS) ja estao tambem no nucleo em JavaScript (physis-nucleo.js,
FAIXAS, 15/11/2026); toda grandeza nova entra nos dois e no `physis-ponte.py` no mesmo passo (memo, secao 4.2).
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
    # pluviometro de bascula (TIPO:PLUV): chuva no intervalo e intensidade (mm/h, calculada pelo hub)
    "chuva": (0, 200, "mm"),
    "chuva_intensidade": (None, None, "mm/h"),
    # secador solar (TIPO:SEC, a homologar): o limite de temperatura e do produto (secador.py), nao daqui
    "temperatura_interna": (None, None, "C"),
    "umidade_interna": (0, 100, "%"),
    "temperatura_coletor": (None, None, "C"),
    "peso_produto": (None, None, "kg"),
    "irradiancia": (0, 1500, "W/m2"),
    # medidor de energia (TIPO:ENE, 15/11/2026): potência reativa e aparente; o fator de potência já é "fp"
    "potencia_reativa": (None, None, "kvar"),
    "potencia_aparente": (None, None, "kVA"),
    # veículo da frota (TIPO:VEI, em desenvolvimento): sem faixa de alarme (os alertas são do módulo frota.py)
    "velocidade": (None, None, "km/h"),
    "rumo": (None, None, "grau"),
    "vazao_combustivel": (None, None, "L/h"),
    "nivel_combustivel": (0, 100, "%"),
    "horimetro": (None, None, "h"),
    "odometro": (None, None, "km"),
}
GRANDEZAS_NOVAS = ("umidade_solo", "estado", "previsao_min", "bateria", "rssi", "snr",
                   "latitude", "longitude", "atividade", "impacto", "porcoes", "chuva", "chuva_intensidade",
                   "temperatura_interna", "umidade_interna", "temperatura_coletor", "peso_produto", "irradiancia",
                   "potencia_reativa", "potencia_aparente",
                   "velocidade", "rumo", "vazao_combustivel", "nivel_combustivel", "horimetro", "odometro")


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
