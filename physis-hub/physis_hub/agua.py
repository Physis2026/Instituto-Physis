"""Analises de agua alem do eletrodo de pH: diferenca de pH com atraso de mistura, vazamento pela vazao
noturna, sinais de limpeza do filtro e protecao de bomba. Espelhado em web/painel.html (anDeltaPh, anVazamento,
anFiltro, anBomba).

Nenhum limite vem de fabrica: todos sao informados por quem opera, conforme o lugar e o equipamento.
A plataforma AVISA; desligar bomba ou fechar valvula e funcao do quadro eletrico e do firmware.
"""
from __future__ import annotations

import math
from statistics import median


def atraso_de_mistura_s(comprimento_m: float | None, diametro_mm: float | None, vazao_l_min: float | None,
                        atraso_fixo_s: float | None = None) -> float | None:
    """Tempo para a agua ir do ponto 'antes' ao ponto 'depois': volume do trecho dividido pela vazao."""
    if comprimento_m and diametro_mm and vazao_l_min and vazao_l_min > 0:
        volume_l = math.pi * (diametro_mm / 2000.0) ** 2 * comprimento_m * 1000.0
        return volume_l / vazao_l_min * 60.0
    return atraso_fixo_s


def delta_ph(pos: list[tuple[float, float]], pre: list[tuple[float, float]], atraso_s: float | None,
             tolerancia_s: float = 60.0) -> list[dict]:
    """pos e pre: listas (instante em segundos, pH compensado). Compara cada 'depois' com o 'antes' de atraso_s atras."""
    saida = []
    for t, ph in pos:
        alvo = t - (atraso_s or 0.0)
        perto = min(pre, key=lambda x: abs(x[0] - alvo), default=None)
        if perto is None or abs(perto[0] - alvo) > tolerancia_s:
            continue
        saida.append({"t": t, "delta": ph - perto[1], "atraso_s": atraso_s or 0.0})
    return saida


def vazao_noturna(leituras: list[tuple[float, float]], inicio_h: float, fim_h: float, limite_l_min: float | None,
                  minimo: int = 3) -> dict:
    """leituras: (hora local do dia em horas decimais, vazao em L/min). A janela pode atravessar a meia-noite."""
    def dentro(h: float) -> bool:
        return (inicio_h <= h or h < fim_h) if inicio_h > fim_h else (inicio_h <= h < fim_h)
    v = [q for h, q in leituras if dentro(h)]
    if len(v) < minimo:
        return {"n": len(v), "falta": True}
    med = median(v)
    return {"n": len(v), "mediana": med, "alerta": limite_l_min is not None and med > limite_l_min}


def sinais_filtro(dp_bar: float | None, dp_max: float | None, turbidez: float | None, turb_max: float | None,
                  dias_desde_limpeza: float | None, dias_max: float | None) -> dict:
    sinais = {
        "pressao": dp_bar is not None and dp_max is not None and dp_bar > dp_max,
        "turbidez": turbidez is not None and turb_max is not None and turbidez > turb_max,
        "tempo": dias_desde_limpeza is not None and dias_max is not None and dias_desde_limpeza > dias_max,
    }
    n = sum(sinais.values())
    return {"sinais": sinais, "n": n, "limpar": n >= 2}      # regra proposta: dois sinais ao mesmo tempo


def protecao_bomba(corrente_a: float | None, tensao_v: float | None, vazao_l_min: float | None,
                   corrente_min: float | None, corrente_max: float | None, tensao_min: float | None) -> list[str]:
    avisos = []
    ligada = corrente_a is not None and corrente_a > 0
    if ligada and corrente_max is not None and corrente_a > corrente_max:
        avisos.append("corrente_alta")
    if ligada and corrente_min is not None and corrente_a < corrente_min:
        avisos.append("corrente_baixa")
    if tensao_v is not None and tensao_min is not None and tensao_v < tensao_min:
        avisos.append("tensao_baixa")
    if ligada and vazao_l_min is not None and vazao_l_min <= 0:
        avisos.append("sem_fluxo")
    return avisos


def resolver_modo(escolha: str, nivel_represa_pct: float | None, chuva_24h_mm: float | None,
                  nivel_seca_pct: float | None, chuva_mm: float | None) -> tuple[str, str]:
    """(modo em uso, motivo). 'obra' so por decisao manual; no automatico, seca vem antes de chuva."""
    if escolha != "auto":
        return escolha, "escolha manual"
    if nivel_represa_pct is not None and nivel_seca_pct is not None and nivel_represa_pct < nivel_seca_pct:
        return "seca", "nivel da represa abaixo do limite"
    if chuva_24h_mm is not None and chuva_mm is not None and chuva_24h_mm > chuva_mm:
        return "chuva", "chuva de 24 horas acima do limite"
    return "normal", "nivel e chuva dentro dos limites"


def queda_de_energia(quedas_por_mes: float, duracao_h: float, horas_irrigacao_dia: float, potencia_kw: float) -> dict:
    """Dois cenarios para a mesma queda. A escolha entre eles e do cliente e muda o tamanho das baterias."""
    fracao = max(0.0, min(1.0, horas_irrigacao_dia / 24.0))
    return {
        "bomba_desliga": {"horas_de_irrigacao_perdidas_mes": quedas_por_mes * duracao_h * fracao, "energia_das_baterias_kwh": 0.0},
        "bomba_continua": {"horas_de_irrigacao_perdidas_mes": 0.0, "energia_das_baterias_kwh": potencia_kw * duracao_h},
    }
