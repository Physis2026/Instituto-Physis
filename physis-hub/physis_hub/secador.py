"""Secador solar (TIPO:SEC, a homologar): premissas por produto, modelo de secagem, dimensionamento e alertas.

Espelho de sistema/physis-secador.js (window.SECADOR): as contas são as mesmas, com as mesmas constantes;
tests/test_secador.py confere as duas com casos feitos à mão. Ver docs/SECADOR.md.

Tudo o que é número de produto (temperatura máxima, umidade inicial e final, velocidade de secagem) é
premissa "verificar": vem de literatura geral (Embrapa Café, manuais de secagem de frutas e ervas), não de
ensaio da Physis. Quem confere troca o valor aqui e no .js no mesmo passo.

Modelo de secagem (Lewis, exponencial simples): o peso cai como
    W(t) = We + (W0 - We)·exp(-k·t)
We é o peso de equilíbrio (o produto não seca abaixo dele com aquele ar), k a velocidade (1/h).
Com a série de pesos da célula de carga, o ajuste procura We numa grade (100 passos entre 0 e o menor peso)
e afina com seção áurea (40 passos); para cada We, ln(W - We) = a - k·t é uma reta (mínimos quadrados).
O erro que se minimiza é o do peso (não o do logaritmo). Determinístico: o mesmo dado dá o mesmo resultado.
"""
from __future__ import annotations

import json
import math

# ── Premissas por produto (todas "verificar") ─────────────────────────────────────────────────────
# t_ideal: faixa de temperatura do ar/massa recomendada (°C); t_max: acima disso, alerta de superaquecimento.
# u0: umidade inicial típica (% base úmida); alvo: umidade final (% b.u.); ue: umidade de equilíbrio típica
# do ar de secagem (% b.u.); k: velocidade típica (1/h) só para a curva estimada quando não há balança.
PRODUTOS = {
    "cafe": {"nome": "Café (cereja ou pergaminho)", "t_ideal": (35.0, 40.0), "t_max": 45.0, "u0": 60.0, "alvo": 11.5,
             "ue": 10.0, "k": 0.024,
             "fonte": "Embrapa Café / Consórcio Pesquisa Café: massa até 40 °C para qualidade, 45 °C no máximo; "
                      "sementes até 35 °C; armazenar com 11 a 12 % b.u. — verificar"},
    "ervas": {"nome": "Ervas e folhas (medicinais, aromáticas)", "t_ideal": (30.0, 35.0), "t_max": 40.0, "u0": 80.0,
              "alvo": 10.0, "ue": 8.0, "k": 0.06,
              "fonte": "literatura de plantas medicinais (óleos essenciais se perdem acima de 35 a 40 °C) — verificar"},
    "frutas": {"nome": "Frutas em fatias", "t_ideal": (50.0, 60.0), "t_max": 65.0, "u0": 85.0, "alvo": 18.0,
               "ue": 15.0, "k": 0.03,
               "fonte": "manuais de frutas desidratadas: 55 a 65 °C; umidade final de 15 a 20 % b.u. — verificar"},
    "cogumelos": {"nome": "Cogumelos", "t_ideal": (40.0, 50.0), "t_max": 55.0, "u0": 90.0, "alvo": 10.0,
                  "ue": 8.0, "k": 0.05,
                  "fonte": "literatura de secagem de cogumelos: 40 a 55 °C; umidade final perto de 10 % b.u. — verificar"},
    "outro": {"nome": "Outro produto", "t_ideal": (40.0, 55.0), "t_max": 60.0, "u0": 70.0, "alvo": 12.0,
              "ue": 10.0, "k": 0.03, "fonte": "valores genéricos — trocar pelos do produto"},
}
UMIDADE_INTERNA_ALTA = 80.0        # % UR dentro do secador sem ventilação: atenção (verificar)
CHUVA_PREVISTA_MM = 1.0            # mm nas próximas 6 h (Open-Meteo) para avisar com o secador aberto
CHUVA_PREVISTA_PROB = 60.0         # ou chance de chuva do dia (%) a partir da qual avisa
VALIDADE_PREVISAO_S = 6 * 3600     # a mesma validade da Open-Meteo em clima.py
T_SEGURANCA_PADRAO = 60.0          # °C: a ponte MQTT força o ventilador ligado (verificar com o produto)
HISTERESE_T = 5.0                  # °C abaixo do limite para soltar o ventilador forçado

# ── Constantes físicas do dimensionamento ─────────────────────────────────────────────────────────
CALOR_LATENTE_MJ_KG = 2.45         # MJ por kg de água evaporada (≈ 20 a 30 °C); água ligada ao produto pede mais
CP_AR_KJ_KG_K = 1.006              # kJ/(kg·K), ar seco
RHO_AR = 1.15                      # kg/m³ perto de 30 °C ao nível do mar
MJ_POR_KWH = 3.6
PCI_LENHA_MJ_KG = 13.0             # o mesmo da base de fatores de emissão (lenha, PCI)
FATOR_REDE_PADRAO = 0.0289         # tCO2/MWh, o mesmo do núcleo physis/1 (verificar o ano)
GWP_CH4, GWP_N2O = 28, 265         # AR5, como a base de fatores
LENHA_CH4_KG_TJ, LENHA_N2O_KG_TJ, LENHA_CO2_KG_TJ = 300.0, 4.0, 112000.0


def produto(chave: str | None) -> dict:
    return PRODUTOS.get(str(chave or "").lower(), PRODUTOS["outro"])


# ── Balanço de massa ──────────────────────────────────────────────────────────────────────────────
def materia_seca(peso: float, umidade_bu: float) -> float:
    """kg de matéria seca de um peso com umidade em % base úmida."""
    return peso * (1.0 - umidade_bu / 100.0)


def peso_na_umidade(peso0: float, u0: float, u: float) -> float:
    """Peso que o lote terá quando chegar à umidade u (% b.u.), partindo de peso0 com u0."""
    return materia_seca(peso0, u0) / (1.0 - u / 100.0)


def agua_a_remover(peso0: float, u0: float, alvo: float) -> float:
    """kg de água para sair de u0 até alvo (% b.u.): W0·(u0 − uf)/(100 − uf)."""
    if alvo >= u0:
        return 0.0
    return peso0 * (u0 - alvo) / (100.0 - alvo)


def umidade_do_peso(peso0: float, u0: float, peso: float) -> float | None:
    """Umidade atual (% b.u.) pelo peso: a matéria seca não muda."""
    if not peso or peso <= 0:
        return None
    return 100.0 * (1.0 - materia_seca(peso0, u0) / peso)


def rendimento(peso0: float, peso_final: float) -> float | None:
    """% do peso inicial que sobra no fim do lote."""
    return 100.0 * peso_final / peso0 if peso0 and peso0 > 0 else None


# ── Modelo exponencial ────────────────────────────────────────────────────────────────────────────
def _reta(ts: list[float], ys: list[float]) -> tuple[float, float] | None:
    n = len(ts)
    mt, my = sum(ts) / n, sum(ys) / n
    sxx = sum((t - mt) ** 2 for t in ts)
    if sxx <= 0:
        return None
    b = sum((t - mt) * (y - my) for t, y in zip(ts, ys)) / sxx
    return my - b * mt, b


def _ajuste_com_we(ts, ws, we):
    """(sse, a, k) para um We fixo; None se algum peso não ficar acima de We."""
    if any(w <= we for w in ws):
        return None
    r = _reta(ts, [math.log(w - we) for w in ws])
    if r is None:
        return None
    a, b = r
    k = -b
    sse = sum((we + math.exp(a - k * t) - w) ** 2 for t, w in zip(ts, ws))
    return sse, a, k


def ajustar(serie: list[tuple[float, float]]) -> dict | None:
    """serie: [(horas desde o início, peso kg)]. Devolve {we, w0, k, sse, n} ou None (menos de 3 pontos,
    peso que não cai ou série sem variação de tempo)."""
    pts = sorted((float(t), float(w)) for t, w in serie if w is not None and w > 0 and t is not None)
    if len(pts) < 3:
        return None
    ts, ws = [p[0] for p in pts], [p[1] for p in pts]
    teto = min(ws) * 0.999
    melhor = None
    passos = 100
    for i in range(passos):
        we = teto * i / passos
        r = _ajuste_com_we(ts, ws, we)
        if r and (melhor is None or r[0] < melhor[0]):
            melhor = (r[0], we, i)
    if melhor is None:
        return None
    lo = teto * max(0, melhor[2] - 1) / passos
    hi = teto * min(passos - 1, melhor[2] + 1) / passos
    phi = (math.sqrt(5) - 1) / 2
    f = lambda we: (_ajuste_com_we(ts, ws, we) or (float("inf"),))[0]
    x1, x2 = hi - phi * (hi - lo), lo + phi * (hi - lo)
    f1, f2 = f(x1), f(x2)
    for _ in range(40):
        if f1 <= f2:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - phi * (hi - lo)
            f1 = f(x1)
        else:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + phi * (hi - lo)
            f2 = f(x2)
    we = (lo + hi) / 2
    r = _ajuste_com_we(ts, ws, we)
    if r is None or (melhor[0] < r[0]):
        we = melhor[1]
        r = _ajuste_com_we(ts, ws, we)
    sse, a, k = r
    if k <= 0:
        return None                      # o peso não está caindo: não há previsão
    return {"we": we, "w0": we + math.exp(a), "k": k, "sse": sse, "n": len(pts)}


def peso_previsto(modelo: dict, t_h: float) -> float:
    return modelo["we"] + (modelo["w0"] - modelo["we"]) * math.exp(-modelo["k"] * t_h)


def horas_ate(modelo: dict, peso_alvo: float) -> float | None:
    """Horas desde o início até o peso alvo; None quando o equilíbrio fica acima do alvo (este ar não chega lá)."""
    we, w0, k = modelo["we"], modelo["w0"], modelo["k"]
    if peso_alvo <= we or k <= 0:
        return None
    if peso_alvo >= w0:
        return 0.0
    return -math.log((peso_alvo - we) / (w0 - we)) / k


def modelo_estimado(peso0: float, u0: float, chave_produto: str, k: float | None = None) -> dict:
    """Curva sem balança: W0 do lote, We pela umidade de equilíbrio típica do produto, k típico (verificar)."""
    p = produto(chave_produto)
    we = peso_na_umidade(peso0, u0, p["ue"]) if p["ue"] < u0 else peso0 * 0.999
    return {"we": we, "w0": peso0, "k": k if k else p["k"], "sse": None, "n": 0, "estimado": True}


def previsao_lote(lote: dict, serie: list[tuple[float, float]] | None = None) -> dict:
    """lote: {produto, peso0, u0, alvo}; serie opcional [(h, kg)]. Devolve o peso alvo, o modelo usado e as horas
    até o fim (desde o início do lote)."""
    peso0, u0 = float(lote["peso0"]), float(lote["u0"])
    alvo = float(lote.get("alvo") if lote.get("alvo") is not None else produto(lote.get("produto"))["alvo"])
    m = ajustar(serie or []) if serie else None
    if m is None:
        m = modelo_estimado(peso0, u0, lote.get("produto"))
    p_alvo = peso_na_umidade(peso0, u0, alvo)
    return {"peso_alvo": p_alvo, "agua_kg": agua_a_remover(peso0, u0, alvo), "modelo": m,
            "horas_fim": horas_ate(m, p_alvo), "medido": not m.get("estimado")}


# ── Dimensionamento ───────────────────────────────────────────────────────────────────────────────
def dimensionar(p: dict) -> dict:
    """Área de coletor e vazão de ar de um secador solar de ar forçado.

    p: massa (kg por lote), u0, alvo (% b.u.), irradiacao (kWh/m²·dia no plano do coletor), eta_coletor (0–1),
    aproveitamento (0–1: parte do calor do ar que vira evaporação), dias (de sol por lote), horas_sol (h/dia),
    delta_t (°C de aquecimento do ar no coletor), lotes_ano, eta_eletrico, eta_lenha, fator_rede (tCO2/MWh),
    lenha_nao_renovavel (bool).
    """
    g = lambda k, d: d if p.get(k) in (None, "") else float(p[k])
    massa, u0, alvo = g("massa", 0), g("u0", 60), g("alvo", 12)
    H, eta, aprov = g("irradiacao", 5.0), g("eta_coletor", 0.40), g("aproveitamento", 0.5)
    dias, horas, dT = g("dias", 5), g("horas_sol", 8), g("delta_t", 15)
    agua = agua_a_remover(massa, u0, alvo)
    q_evap = agua * CALOR_LATENTE_MJ_KG                       # MJ que a água leva
    q_ar = q_evap / aprov if aprov > 0 else 0.0                # MJ que o coletor tem de pôr no ar
    por_m2 = H * MJ_POR_KWH * eta * dias                       # MJ por m² de coletor no lote
    area = q_ar / por_m2 if por_m2 > 0 else None
    dw = CP_AR_KJ_KG_K * dT * aprov / (CALOR_LATENTE_MJ_KG * 1000.0)   # kg de água por kg de ar
    m_ar = agua / dw if dw > 0 else None
    vazao = m_ar / RHO_AR / (dias * horas) if m_ar and dias * horas > 0 else None   # m³/h
    eta_el, eta_le = g("eta_eletrico", 0.5), g("eta_lenha", 0.35)
    lotes = g("lotes_ano", 10)
    kwh_el = q_evap / eta_el / MJ_POR_KWH if eta_el > 0 else None
    kg_lenha = q_evap / (PCI_LENHA_MJ_KG * eta_le) if eta_le > 0 else None
    f_rede = g("fator_rede", FATOR_REDE_PADRAO)
    co2_el = kwh_el * f_rede if kwh_el is not None else None             # kg CO2 (tCO2/MWh = kg/kWh)
    co2_lenha = None
    if kg_lenha is not None:
        tj = kg_lenha * PCI_LENHA_MJ_KG / 1e6
        co2_lenha = tj * (LENHA_CH4_KG_TJ * GWP_CH4 + LENHA_N2O_KG_TJ * GWP_N2O)
        if p.get("lenha_nao_renovavel"):
            co2_lenha += tj * LENHA_CO2_KG_TJ
    return {"agua_kg": agua, "q_evap_mj": q_evap, "q_ar_mj": q_ar, "mj_m2_lote": por_m2, "area_m2": area,
            "dw_kg_kg": dw, "ar_kg": m_ar, "vazao_m3h": vazao,
            "kwh_eletrico_lote": kwh_el, "kg_lenha_lote": kg_lenha,
            "kwh_eletrico_ano": kwh_el * lotes if kwh_el is not None else None,
            "kg_lenha_ano": kg_lenha * lotes if kg_lenha is not None else None,
            "co2_eletrico_kg_ano": co2_el * lotes if co2_el is not None else None,
            "co2_lenha_kg_ano": co2_lenha * lotes if co2_lenha is not None else None}


# ── Alertas do hub ────────────────────────────────────────────────────────────────────────────────
def chuva_prevista(db, agora: float) -> dict | None:
    """Open-Meteo guardada por clima.py (tabela clima_fonte): {mm_6h, prob_hoje}. None sem previsão válida."""
    try:
        r = db.execute("SELECT dados, consultado FROM clima_fonte WHERE fonte='openmeteo'").fetchone()
    except Exception:          # noqa: BLE001 — sem a tabela do clima (hub sem previsão): sem aviso de chuva
        return None
    if not r or not r[1] or agora - r[1] > VALIDADE_PREVISAO_S:
        return None
    try:
        d = json.loads(r[0] or "{}")
    except ValueError:
        return None
    dias = d.get("dias") or []
    return {"mm_6h": d.get("proximas_6h_mm"), "prob_hoje": dias[0].get("prob") if dias else None}


def alertas(est: dict, produto_chave: str | None = None, chuva: dict | None = None) -> list[tuple[str, str]]:
    """[(nivel, texto)] de um nó SEC (estado de adaptador.interpretar). Não inclui 'nó fora' nem bateria:
    o hub já avisa isso para todos os nós."""
    out: list[tuple[str, str]] = []
    p = produto(produto_chave)
    ti = est.get("ti")
    if ti is not None and ti > p["t_max"]:
        out.append(("alarme", f"superaquecimento: {ti:.1f} °C dentro do secador, acima de {p['t_max']:.0f} °C "
                              f"para {p['nome'].lower()}"))
    ui = est.get("ui")
    if ui is not None and ui >= UMIDADE_INTERNA_ALTA and not est.get("vent"):
        out.append(("atencao", f"umidade alta dentro do secador ({ui:.0f} %) com o ventilador desligado"))
    if chuva and est.get("abt") is not False:          # aberto ou sem sensor de tampa: avisa
        mm, prob = chuva.get("mm_6h"), chuva.get("prob_hoje")
        if (mm is not None and mm >= CHUVA_PREVISTA_MM) or (prob is not None and prob >= CHUVA_PREVISTA_PROB):
            out.append(("atencao", "chuva prevista e o secador está aberto: feche a tampa ou recolha o produto"))
    if ti is None and est.get("ui") is None:
        out.append(("alarme", "sensor de temperatura e umidade interna sem leitura"))
    return out
