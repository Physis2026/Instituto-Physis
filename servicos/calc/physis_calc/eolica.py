"""/eolica — energia de um aerogerador com windpowerlib.

Entrada:
  curva: [{"v": m/s, "kw": kW}, ...]  (curva de potência do fabricante)  — ou —
  turbina: "E-82/2350"                 (tipo da biblioteca oedb que acompanha a windpowerlib)
  altura_cubo (m), e o vento:
    velocidades: lista horária (m/s) medida a altura_medicao (m)       — série; ou
    weibull: {"k", "c"} já na altura de medição                         — distribuição anual
  rugosidade (m, comprimento de rugosidade z0; ex.: 0,03 campo aberto, 0,1 lavoura, 0,4 subúrbio — Manwell et al.)
"""
from __future__ import annotations

import math

from .comum import EntradaInvalida, exigir, lista_num, num


def validar(e: dict) -> dict:
    p = {"altura_cubo": num(e, "altura_cubo", None, 2, 250),
         "altura_medicao": num(e, "altura_medicao", 10, 1, 250),
         "rugosidade": num(e, "rugosidade", None, 0.0001, 3)}
    curva = e.get("curva")
    if curva is not None:
        if not isinstance(curva, list) or len(curva) < 3:
            raise EntradaInvalida("'curva' precisa de ao menos 3 pontos {v, kw}")
        pts = sorted((num(c, "v", None, 0, 60), num(c, "kw", None, 0, 30000)) for c in curva if isinstance(c, dict))
        if len(pts) != len(curva) or len({v for v, _ in pts}) != len(pts):
            raise EntradaInvalida("'curva' com ponto inválido ou velocidade repetida")
        p["curva"] = pts
    elif isinstance(e.get("turbina"), str) and e["turbina"].strip():
        p["turbina"] = e["turbina"].strip()[:60]
    else:
        raise EntradaInvalida("informe 'curva' ou 'turbina'")
    if e.get("velocidades") is not None:
        p["velocidades"] = lista_num(e, "velocidades", 0, 80, 1, 8784)
    elif isinstance(e.get("weibull"), dict):
        p["weibull"] = (num(e["weibull"], "k", None, 0.5, 10), num(e["weibull"], "c", None, 0.1, 40))
    else:
        raise EntradaInvalida("informe 'velocidades' (série horária) ou 'weibull' {k, c}")
    return p


def _extrapolar(v: float, h_med: float, h_cubo: float, z0: float) -> float:
    """Perfil logarítmico (mesma fórmula de windpowerlib.wind_speed.logarithmic_profile, sem obstáculo)."""
    return v * math.log(h_cubo / z0) / math.log(h_med / z0)


def curva_da_turbina(p: dict):
    """(velocidades m/s, potências W) — da entrada ou da base oedb que vem com a windpowerlib."""
    if "curva" in p:
        return [v for v, _ in p["curva"]], [kw * 1000 for _, kw in p["curva"]]
    exigir("windpowerlib")
    from windpowerlib import WindTurbine
    try:
        t = WindTurbine(hub_height=p["altura_cubo"], turbine_type=p["turbina"])
    except Exception as exc:  # noqa: BLE001 — a biblioteca levanta tipos variados para tipo desconhecido
        raise EntradaInvalida(f"turbina '{p['turbina']}' não está na base da windpowerlib ({type(exc).__name__})") from None
    if t.power_curve is None:
        raise EntradaInvalida(f"turbina '{p['turbina']}' sem curva de potência na base")
    return list(t.power_curve["wind_speed"]), list(t.power_curve["value"])


def calcular(e: dict) -> dict:
    p = validar(e)
    exigir("windpowerlib", "pandas", "numpy")
    import numpy as np
    import pandas as pd
    import windpowerlib
    from windpowerlib import power_output, wind_speed

    vs, ws = curva_da_turbina(p)
    nominal_w = max(ws)
    fator = math.log(p["altura_cubo"] / p["rugosidade"]) / math.log(p["altura_medicao"] / p["rugosidade"])
    if "velocidades" in p:
        v_med = pd.Series(p["velocidades"])
        v_cubo = wind_speed.logarithmic_profile(v_med, p["altura_medicao"], p["altura_cubo"], p["rugosidade"])
        pot = power_output.power_curve(v_cubo, pd.Series(vs), pd.Series(ws), density_correction=False)
        horas = len(v_med)
        energia = float(pot.sum()) / 1000.0
        extra = {"horario_kw": [round(float(x) / 1000, 3) for x in pot.values],
                 "vento_medio_cubo": round(float(v_cubo.mean()), 2)}
        escala = 8760 / horas
    else:
        k, c = p["weibull"]
        c_cubo = c * fator                      # mesma forma k; escala sobe com o perfil logarítmico
        dv = 0.1
        v = np.arange(dv / 2, 40, dv)
        f = (k / c_cubo) * (v / c_cubo) ** (k - 1) * np.exp(-(v / c_cubo) ** k)
        pw = np.interp(v, vs, ws, left=0, right=0)
        horas = 8760
        energia = float(np.sum(pw * f * dv) * 8760) / 1000.0
        escala = 1.0
        extra = {"weibull_cubo": {"k": k, "c": round(c_cubo, 3)}}
    anual = energia * escala
    return {"ok": True, "motor": f"windpowerlib {windpowerlib.__version__}", "potencia_nominal_kw": round(nominal_w / 1000, 2),
            "energia_kwh": round(energia, 1), "horas_na_entrada": horas, "anual_estimado_kwh": round(anual, 1),
            "fator_capacidade": round(anual / (nominal_w / 1000 * 8760), 4) if nominal_w else 0.0,
            "fator_perfil_vento": round(fator, 4),
            "avisos": ["Sem correção de densidade do ar, perdas elétricas, esteira e disponibilidade."] + (
                ["Série com menos de um ano: anual estimado por proporção (sazonalidade ignorada)."] if horas < 8760 else []),
            **extra}
