"""/pv — geração fotovoltaica horária com pvlib (modelo PVWatts).

Entrada: {"lat", "lon", "kwp", "inclinacao"?, "azimute"?, "altitude"?, "ano"?, "fuso"?,
          "ghi"? (8760/8784 W/m², ex.: da série do hub), "temp_ar"? (°C, mesma duração ou um valor),
          "perdas"? (fração), "coef_temp"? (1/°C), "inversor_kw"?, "albedo"?}
Sem "ghi": céu claro (modelo Solis simplificado) = TETO teórico, não a geração esperada (o resultado avisa).
Azimute na convenção do pvlib: 0 = norte, 90 = leste, 180 = sul. Padrão: voltado para o equador.
"""
from __future__ import annotations

from .comum import EntradaInvalida, exigir, lista_num, num

# Padrões do PVWatts (NREL, PVWatts Version 5 Manual, 2014): perdas do sistema 14 %, coeficiente de
# temperatura do módulo "standard" -0,37 %/°C, eficiência nominal do inversor 96 %.
PERDAS_PVWATTS = 0.14
COEF_TEMP_PVWATTS = -0.0037
ETA_INVERSOR_PVWATTS = 0.96


def validar(e: dict) -> dict:
    lat = num(e, "lat", None, -90, 90)
    p = {
        "lat": lat,
        "lon": num(e, "lon", None, -180, 180),
        "kwp": num(e, "kwp", None, 0.01, 1e6),
        "inclinacao": num(e, "inclinacao", round(abs(lat)), 0, 90),
        "azimute": num(e, "azimute", 0 if lat < 0 else 180, 0, 360),
        "altitude": num(e, "altitude", 0, -500, 9000),
        "ano": int(num(e, "ano", 2025, 1990, 2100)),
        "fuso": str(e.get("fuso") or "America/Sao_Paulo"),
        "perdas": num(e, "perdas", PERDAS_PVWATTS, 0, 0.9),
        "coef_temp": num(e, "coef_temp", COEF_TEMP_PVWATTS, -0.01, 0),
        "albedo": num(e, "albedo", 0.2, 0, 1),
        "ghi": lista_num(e, "ghi", 0, 1500, 8760, 8784, obrigatoria=False),
    }
    p["inversor_kw"] = num(e, "inversor_kw", p["kwp"], 0.01, 1e6)
    t = e.get("temp_ar")
    if isinstance(t, list):
        p["temp_ar"] = lista_num(e, "temp_ar", -50, 70, 8760, 8784)
    elif t is not None:
        p["temp_ar"] = num(e, "temp_ar", None, -50, 70)
    else:
        p["temp_ar"] = None
    if p["ghi"] is None and p["temp_ar"] is None:
        raise EntradaInvalida("sem 'ghi', informe ao menos 'temp_ar' (°C médio do lugar)")
    return p


def calcular(e: dict) -> dict:
    p = validar(e)
    exigir("pvlib", "pandas")
    import pandas as pd
    import pvlib

    tempos = pd.date_range(f"{p['ano']}-01-01", f"{p['ano'] + 1}-01-01", freq="h", tz=p["fuso"], inclusive="left")
    if p["ghi"] is not None and len(p["ghi"]) != len(tempos):
        raise EntradaInvalida(f"'ghi' tem {len(p['ghi'])} horas; o ano {p['ano']} tem {len(tempos)}")
    local = pvlib.location.Location(p["lat"], p["lon"], tz=p["fuso"], altitude=p["altitude"])
    sol = local.get_solarposition(tempos)
    avisos = []
    if p["ghi"] is None:
        cc = local.get_clearsky(tempos, model="simplified_solis")
        ghi, dni, dhi = cc["ghi"], cc["dni"], cc["dhi"]
        avisos.append("Sem série de irradiância: usado céu claro (teto teórico). Para a geração esperada, envie 'ghi' horário.")
        fonte = "ceu_claro"
    else:
        ghi = pd.Series(p["ghi"], index=tempos)
        dec = pvlib.irradiance.erbs(ghi, sol["zenith"], tempos)
        dni, dhi = dec["dni"], dec["dhi"]
        fonte = "informada"
    poa = pvlib.irradiance.get_total_irradiance(p["inclinacao"], p["azimute"], sol["apparent_zenith"], sol["azimuth"],
                                                dni, ghi, dhi, albedo=p["albedo"])
    gpoa = poa["poa_global"].fillna(0).clip(lower=0)
    tar = pd.Series(p["temp_ar"], index=tempos) if isinstance(p["temp_ar"], list) else p["temp_ar"]
    if tar is None:
        raise EntradaInvalida("informe 'temp_ar'")
    par = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_polymer"]
    tcel = pvlib.temperature.sapm_cell(gpoa, tar, 1.0, **par)
    pdc = pvlib.pvsystem.pvwatts_dc(gpoa, tcel, p["kwp"] * 1000, p["coef_temp"]) * (1 - p["perdas"])
    pac = pvlib.inverter.pvwatts(pdc, p["inversor_kw"] * 1000 / ETA_INVERSOR_PVWATTS, eta_inv_nom=ETA_INVERSOR_PVWATTS)
    pac = pac.fillna(0).clip(lower=0) / 1000.0     # kW, passo de 1 h = kWh
    mensal = pac.groupby(pac.index.month).sum()
    anual = float(pac.sum())
    return {"ok": True, "motor": f"pvlib {pvlib.__version__} (PVWatts)", "fonte_irradiancia": fonte,
            "entrada": {k: v for k, v in p.items() if k not in ("ghi", "temp_ar")},
            "anual_kwh": round(anual, 1), "produtividade_kwh_kwp": round(anual / p["kwp"], 1),
            "mensal_kwh": [round(float(mensal.get(m, 0.0)), 1) for m in range(1, 13)],
            "horario_kw": [round(float(x), 3) for x in pac.values],
            "irradiacao_plano_kwh_m2": round(float(gpoa.sum()) / 1000, 1), "avisos": avisos}
