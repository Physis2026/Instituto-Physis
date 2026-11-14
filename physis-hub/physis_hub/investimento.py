"""Analise de investimento usada na Gestao do cliente (espelhada em web/painel.html, analiseInvest).

Fluxo mensal: o ganho do primeiro mes e 'ganho_mes'; cresce com a inflacao. A taxa de juros desconta.
E uma conta de apoio a decisao, no espirito de uma auditoria de grau de investimento; nao substitui o estudo completo.
"""
from __future__ import annotations


def analise(valor: float, ganho_mes: float, vida_anos: float | None, taxa_ano_pct: float | None,
            inflacao_ano_pct: float | None = None) -> dict:
    r: dict = {"retorno_simples_meses": None, "retorno_descontado_meses": None, "vpl": None, "tir_ano_pct": None}
    if not valor or not ganho_mes or valor <= 0 or ganho_mes <= 0:
        return r
    f = (1 + (inflacao_ano_pct or 0) / 100) ** (1 / 12) - 1
    n = int(round((vida_anos or 0) * 12))
    if n <= 0:
        r["retorno_simples_meses"] = valor / ganho_mes
        return r
    fluxo = [ganho_mes * (1 + f) ** t for t in range(n)]
    acum = 0.0
    for t, c in enumerate(fluxo, 1):
        acum += c
        if acum >= valor:
            r["retorno_simples_meses"] = t - (acum - valor) / c
            break
    if taxa_ano_pct is not None:
        i = (1 + taxa_ano_pct / 100) ** (1 / 12) - 1
        acum = 0.0
        for t, c in enumerate(fluxo, 1):
            d = c / (1 + i) ** t
            acum += d
            if r["retorno_descontado_meses"] is None and acum >= valor:
                r["retorno_descontado_meses"] = t - (acum - valor) / d
        r["vpl"] = acum - valor

    def vpl_a(taxa_m: float) -> float:
        return sum(c / (1 + taxa_m) ** t for t, c in enumerate(fluxo, 1)) - valor
    lo, hi = -0.9, 1.0
    if vpl_a(lo) > 0 > vpl_a(hi):
        for _ in range(80):
            mid = (lo + hi) / 2
            if vpl_a(mid) > 0:
                lo = mid
            else:
                hi = mid
        r["tir_ano_pct"] = ((1 + (lo + hi) / 2) ** 12 - 1) * 100
    return r
