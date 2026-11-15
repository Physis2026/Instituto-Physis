"""Fluidos simplificados, Fase 1 (espelho de SIMULACAO.fluidos em sistema/physis-simulacao.js).

- Redes de tubos e dutos: NÃO estão aqui. Use as que já existem: perda de carga em tubo em vento.perda_darcy e
  vento.perda_hazen (turbinas hidráulicas), dutos e ventilação mecânica na aba AVAC (sistema/physis-avac.js) e
  calhas/condutores em PhysisCalc.calhas (physis-calc-comum.js).
- ventilacao_natural: efeito chaminé e vento com coeficientes de premissa (Cd, ΔCp).
- lbm: Lattice-Boltzmann D2Q9 (BGK), demonstração QUALITATIVA de Fase 1 (vento em volta de um corte de prédio,
  ar passando no secador). Não dá pressão de projeto nem coeficiente de arrasto confiável.
- eolica_serie: potência de turbina a partir de uma série de vento (reusa vento.py: curva, Weibull, energia).
"""
from __future__ import annotations

import math

from .. import vento
from .comum import FaltaDado, MARCADOR, premissa, resultado, usada

G = 9.81


def ventilacao_natural(p: dict) -> dict:
    """p: a1, a2 (m², aberturas de entrada e saída), h (m, diferença de altura entre elas), ti, te (°C),
    v (m/s, vento na altura de referência), dcp (ΔCp; padrão = premissa barlavento − sotavento), cd (premissa),
    volume (m³, para trocas por hora).
    Área efetiva em série: 1/A*² = 1/A1² + 1/A2². Chaminé: Q = Cd·A*·√(2·g·h·|ΔT|/T_média).
    Vento: Q = Cd·A*·v·√ΔCp. Combinado: √(Qc² + Qv²) (soma quadrática, aproximação [CONFERIR])."""
    cd = p.get("cd", premissa("sim.ventilacao.cd"))
    cps = premissa("sim.ventilacao.cp_vento") or {}
    dcp = p.get("dcp")
    if dcp is None and cps.get("barlavento") is not None and cps.get("sotavento") is not None:
        dcp = cps["barlavento"] - cps["sotavento"]
    if cd is None or dcp is None:
        raise FaltaDado(f"{MARCADOR} coeficiente de descarga Cd ou ΔCp (premissas sim.ventilacao)")
    a1, a2 = float(p["a1"]), float(p["a2"])
    ae = 1.0 / math.sqrt(1.0 / a1 ** 2 + 1.0 / a2 ** 2)
    ti, te = float(p.get("ti", 25.0)), float(p.get("te", 25.0))
    tm = (ti + te) / 2 + 273.15
    qc = cd * ae * math.sqrt(2 * G * float(p.get("h", 0.0)) * abs(ti - te) / tm)
    qv = cd * ae * float(p.get("v", 0.0)) * math.sqrt(max(0.0, dcp))
    q = math.sqrt(qc * qc + qv * qv)
    vol = p.get("volume")
    return resultado("Ventilação natural: efeito chaminé e vento por orifício (coeficientes de premissa)",
                     ["escoamento por orifício, ar incompressível", "temperatura uniforme dentro",
                      "chaminé e vento somados em quadratura (aproximação)"],
                     [usada("sim.ventilacao.cd", cd), usada("sim.ventilacao.cp_vento", {"dcp": dcp})],
                     None,
                     "Ordem de grandeza para pré-dimensionar aberturas. Vento real varia com a direção e o entorno: "
                     "ΔCp de túnel de vento ou de norma vale mais. Para o Secador, a vazão do coletor depende da insolação.",
                     {"area_efetiva": ae, "q_chamine_m3s": qc, "q_vento_m3s": qv, "q_m3s": q,
                      "trocas_h": q * 3600 / float(vol) if vol else None, "dcp": dcp, "cd": cd})


# ── Lattice-Boltzmann D2Q9 ──
EX = (0, 1, 0, -1, 0, 1, -1, -1, 1)
EY = (0, 0, 1, 0, -1, 1, 1, -1, -1)
W = (4 / 9, 1 / 9, 1 / 9, 1 / 9, 1 / 9, 1 / 36, 1 / 36, 1 / 36, 1 / 36)
OPOSTO = (0, 3, 4, 1, 2, 7, 8, 5, 6)


def _feq(k, rho, ux, uy):
    eu = EX[k] * ux + EY[k] * uy
    return W[k] * rho * (1.0 + 3.0 * eu + 4.5 * eu * eu - 1.5 * (ux * ux + uy * uy))


def lbm(p: dict) -> dict:
    """p: nx, ny; obstaculo (lista ny·nx 0/1, linha 0 = base); u_entrada (unidades de rede, < 0,1);
    tau (> 0,5); passos; modo 'canal' (entrada à esquerda, saída à direita, paredes deslizantes em cima e embaixo)
    ou 'periodico' (caixa periódica, sem entrada: teste de conservação); u0_campo opcional [[ux], [uy]].
    Devolve ux, uy, rho e |u| finais, massa inicial e final."""
    nx, ny = int(p["nx"]), int(p["ny"])
    N = nx * ny
    obs = p.get("obstaculo") or [0] * N
    u0 = float(p.get("u_entrada", 0.05))
    tau = float(p.get("tau", 0.6))
    if tau <= 0.5:
        raise ValueError("tau precisa ser maior que 0,5 (estabilidade)")
    om = 1.0 / tau
    modo = p.get("modo", "canal")
    passos = int(p.get("passos", 200))
    ini = p.get("u0_campo")
    f = [[0.0] * N for _ in range(9)]
    for s in range(N):
        ux = (ini[0][s] if ini else (u0 if modo == "canal" else 0.0)) if not obs[s] else 0.0
        uy = (ini[1][s] if ini else 0.0) if not obs[s] else 0.0
        for k in range(9):
            f[k][s] = _feq(k, 1.0, ux, uy)
    massa0 = sum(f[k][s] for k in range(9) for s in range(N) if not obs[s])
    rho = [1.0] * N
    UX = [0.0] * N
    UY = [0.0] * N
    for _ in range(passos):
        # colisão (BGK) nas células de fluido
        for s in range(N):
            if obs[s]:
                continue
            r = 0.0
            mx = 0.0
            my = 0.0
            for k in range(9):
                fk = f[k][s]
                r += fk
                mx += fk * EX[k]
                my += fk * EY[k]
            ux = mx / r
            uy = my / r
            rho[s] = r
            UX[s] = ux
            UY[s] = uy
            for k in range(9):
                f[k][s] += om * (_feq(k, r, ux, uy) - f[k][s])
        # propagação com volta (bounce-back) nos obstáculos e nas bordas
        g = [[0.0] * N for _ in range(9)]
        for s in range(N):
            if obs[s]:
                continue
            y, x = divmod(s, nx)
            for k in range(9):
                xx, yy = x + EX[k], y + EY[k]
                if modo == "periodico":
                    xx %= nx
                    yy %= ny
                else:
                    if yy < 0 or yy >= ny:              # parede deslizante: reflete só a componente vertical
                        kk = (0, 1, 4, 3, 2, 8, 7, 6, 5)[k]
                        g[kk][s] += f[k][s]
                        continue
                    if xx < 0 or xx >= nx:
                        continue                         # sai do domínio; entrada e saída são repostas abaixo
                d = yy * nx + xx
                if obs[d]:
                    g[OPOSTO[k]][s] += f[k][s]
                else:
                    g[k][d] += f[k][s]
        f = g
        if modo == "canal":
            for y in range(ny):
                s = y * nx
                if not obs[s]:
                    for k in range(9):
                        f[k][s] = _feq(k, 1.0, u0, 0.0)
                s2, s1 = y * nx + nx - 1, y * nx + nx - 2
                if not obs[s2]:
                    for k in range(9):
                        f[k][s2] = f[k][s1]
    vel = []
    for s in range(N):
        if obs[s]:
            rho[s], UX[s], UY[s] = 0.0, 0.0, 0.0
            vel.append(0.0)
            continue
        r = sum(f[k][s] for k in range(9))
        ux = sum(f[k][s] * EX[k] for k in range(9)) / r
        uy = sum(f[k][s] * EY[k] for k in range(9)) / r
        rho[s], UX[s], UY[s] = r, ux, uy
        vel.append(math.sqrt(ux * ux + uy * uy))
    massa = sum(rho[s] for s in range(N) if not obs[s])
    nu = (tau - 0.5) / 3
    largura = max((sum(1 for x in range(nx) if obs[y * nx + x]) for y in range(ny)), default=0)
    altura = max((sum(1 for y in range(ny) if obs[y * nx + x]) for x in range(nx)), default=0)
    re = u0 * (altura or ny) / nu
    avisos = []
    if u0 * math.sqrt(3) > 0.15:
        avisos.append("Mach de rede acima de 0,15: erro de compressibilidade; reduza u_entrada")
    if any(v != v for v in vel):
        avisos.append("instável (NaN): aumente tau ou reduza u_entrada")
    return resultado("Lattice-Boltzmann D2Q9, colisão BGK — QUALITATIVO, Fase 1",
                     ["2D, escoamento quase incompressível (Mach baixo)", "unidades de rede (sem escala física direta)",
                      "paredes por volta simples (bounce-back)", "sem turbulência modelada"],
                     [], {"nx": nx, "ny": ny, "passos": passos, "tau": tau},
                     "Qualitativo, Fase 1: mostra onde o ar acelera, separa e forma esteira. Não usar para pressão de "
                     "projeto, conforto ou dimensionamento. Projeto: OpenFOAM na Fase 2.",
                     {"ux": UX, "uy": UY, "rho": rho, "vel": vel, "massa_inicial": massa0, "massa_final": massa,
                      "reynolds_rede": re, "viscosidade_rede": nu, "qualitativo": True}, avisos)


# ── turbina eólica a partir de série de vento (reusa vento.py) ──
def weibull_momentos(serie: list) -> tuple[float, float]:
    """k e c pelo método empírico de Justus: k = (σ/v̄)^−1,086; c = v̄/Γ(1 + 1/k)."""
    v = [float(x) for x in serie if x is not None and x >= 0]
    if len(v) < 2:
        raise FaltaDado("série de vento curta demais")
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
    if m <= 0 or sd <= 0:
        raise FaltaDado("série de vento constante ou nula")
    k = (sd / m) ** -1.086
    return k, m / math.gamma(1 + 1 / k)


def eolica_serie(p: dict) -> dict:
    """p: serie (m/s, na altura h_ref), passo_h (1), h_ref, altura_cubo, alfa (ou terreno), turbina
    {diametro, cp, v_in, v_nom, v_out, p_nom, curva}, altitude, temperatura, perdas (%).
    Energia direta (Σ P(v)·Δt) e pela Weibull ajustada (vento.energia_weibull) para comparar."""
    tb = p.get("turbina") or {}
    rho = vento.densidade_ar(p.get("altitude", 0.0), p.get("temperatura", 25.0))
    alfa = p.get("alfa")
    if alfa is None:
        alfa = vento.ALFA_TERRENO.get(p.get("terreno", "aberto"), vento.ALFA_TERRENO["aberto"])[0]
    t = vento.turbina_eolica(tb.get("diametro", 0.0), tb.get("cp", 0.30), tb.get("v_in", 0.0), tb.get("v_nom"),
                             tb.get("v_out"), tb.get("p_nom"), rho)
    cf = vento.curva_fabricante(tb.get("curva"))
    if cf:
        t["curva"], t["p_nom"] = cf, max(x[1] for x in cf)
    h_ref, h = float(p.get("h_ref", 10.0)), float(p.get("altura_cubo", 12.0))
    passo = float(p.get("passo_h", 1.0))
    perdas = max(0.0, min(float(p.get("perdas", 0.0)), 100.0)) / 100
    vc = [vento.cisalhamento(float(v), h_ref, h, alfa) for v in p["serie"]]
    e_dir = sum(vento.potencia_vento(v, t) for v in vc) * passo * (1 - perdas)
    horas = len(vc) * passo
    k, c = weibull_momentos(vc)
    e_wb = vento.energia_weibull(t, k, c, horas) * (1 - perdas)
    return resultado("Energia da série (Σ P(v)·Δt) e pela Weibull ajustada (método de Justus), contas de vento.py",
                     ["lei de potência para a altura do cubo", "curva de potência ideal ou do fabricante",
                      "série representativa do período"],
                     [], {"amostras": len(vc), "passo_h": passo},
                     "Série curta (menos de 1 ano) não representa o ano. Meça no local, na altura do cubo.",
                     {"kwh_serie": e_dir, "kwh_weibull": e_wb, "k": k, "c": c, "v_media_cubo": sum(vc) / len(vc),
                      "horas": horas, "rho": rho, "alfa": alfa, "p_nom": t["p_nom"]})
