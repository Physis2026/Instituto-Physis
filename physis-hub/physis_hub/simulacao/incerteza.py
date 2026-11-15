"""Monte Carlo / incerteza, Fase 1 (espelho de SIMULACAO.incerteza em sistema/physis-simulacao.js).

Propagação genérica: distribuições das entradas → percentis da saída. Sorteio pelo gerador mulberry32 de
comum.Rng (só biblioteca padrão), que dá a MESMA sequência no Python e no navegador com a mesma semente; o
random.Random do Python não teria espelho no navegador. Modelos com nome (usados por Carbono, Solar, payback e
Biogás) ficam em MODELOS; qualquer função Python também serve (só no servidor).
"""
from __future__ import annotations

import math

from .comum import Rng, percentil, premissa, resultado, usada


def sortear(d, rng: Rng) -> float:
    """d: número (fixo) | {tipo: normal, media, dp} | {tipo: uniforme, min, max} |
    {tipo: triangular, min, moda, max} | {tipo: lognormal, media, dp} (média e desvio da própria variável)."""
    if isinstance(d, (int, float)):
        return float(d)
    t = d.get("tipo")
    if t == "normal":
        return d["media"] + d["dp"] * rng.normal()
    if t == "uniforme":
        return d["min"] + (d["max"] - d["min"]) * rng()
    if t == "triangular":
        a, c, b = d["min"], d["moda"], d["max"]
        u = rng()
        fc = (c - a) / (b - a)
        return a + math.sqrt(u * (b - a) * (c - a)) if u < fc else b - math.sqrt((1 - u) * (b - a) * (b - c))
    if t == "lognormal":
        m, s = d["media"], d["dp"]
        s2 = math.log(1 + (s / m) ** 2)
        return math.exp(math.log(m) - s2 / 2 + math.sqrt(s2) * rng.normal())
    raise ValueError(f"distribuição desconhecida: {t}")


# ── modelos com nome (mesmos no navegador) ──
def _carbono(x):
    """Σ atividade_i × fator_i (kgCO2e). Entradas: a0, f0, a1, f1, …"""
    s, i = 0.0, 0
    while f"a{i}" in x:
        s += x[f"a{i}"] * x[f"f{i}"]
        i += 1
    return s


def _solar(x):
    """kWh/ano = kWp × H (kWh/m²·dia) × PR × 365."""
    return x["kwp"] * x["h"] * x["pr"] * 365


def _payback(x):
    """anos = custo ÷ economia anual (simples)."""
    return x["custo"] / x["economia"] if x["economia"] > 0 else float("inf")


def _biogas(x):
    """m³ CH₄/dia = Σ kg/dia × ST × SV × BMP × fração_CH4 × fração alcançada (entradas planas com sufixo i)."""
    s, i = 0.0, 0
    while f"kg{i}" in x:
        s += x[f"kg{i}"] * x[f"st{i}"] * x[f"sv{i}"] * x[f"bmp{i}"] * x[f"ch4{i}"] * x.get(f"fr{i}", 1.0)
        i += 1
    return s


MODELOS = {"carbono": _carbono, "solar": _solar, "payback": _payback, "biogas": _biogas}


def monte_carlo(entradas: dict, modelo, n: int | None = None, semente: int | None = None,
                percentis=(5, 25, 50, 75, 95)) -> dict:
    n = int(n or premissa("sim.mc.amostras", 2000))
    semente = premissa("sim.mc.semente", 42) if semente is None else semente
    f = MODELOS[modelo] if isinstance(modelo, str) else modelo
    rng = Rng(semente)
    nomes = sorted(entradas)
    ys = []
    for _ in range(n):
        x = {k: sortear(entradas[k], rng) for k in nomes}
        ys.append(f(x))
    ok = sorted(y for y in ys if math.isfinite(y))
    m = sum(ok) / len(ok) if ok else float("nan")
    sd = math.sqrt(sum((y - m) ** 2 for y in ok) / (len(ok) - 1)) if len(ok) > 1 else 0.0
    return resultado("Monte Carlo (amostragem aleatória simples, gerador mulberry32 com semente fixa)",
                     ["entradas independentes (sem correlação)", "distribuições escolhidas pela pessoa ou premissa"],
                     [usada("sim.mc.amostras", n), usada("sim.mc.semente", semente)],
                     {"amostras": n, "semente": semente, "ordem_entradas": nomes},
                     "A faixa só é tão boa quanto as distribuições de entrada. Entradas correlacionadas (ex.: tarifa e "
                     "inflação) ficam mais largas ou estreitas do que o real.",
                     {"media": m, "dp": sd, "percentis": {str(p): percentil(ok, p) for p in percentis},
                      "n_validos": len(ok), "modelo": modelo if isinstance(modelo, str) else "função"})
