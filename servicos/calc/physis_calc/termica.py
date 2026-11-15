"""/termica — carga térmica de uma zona única no EnergyPlus (cargas ideais), a partir das entradas da
Carga Térmica da plataforma (physis_hub/cargatermica.py: clima + um ambiente com superfícies).

Entrada:
  clima:    {"lat", "lon"?, "alt"?, "fuso"? (h, ex. -3), "tbs" (°C, projeto), "tbu" (°C), "dr" (amplitude diária, K),
             "tint" (°C, setpoint de resfriamento), "mes"? (1-12; padrão: janeiro no hemisfério sul, julho no norte)}
  ambiente: {"area" (m²), "pe_direito" (m), "pessoas"?, "atividade_w"? (W/pessoa, total), "iluminacao_wm2"?,
             "equipamentos_wm2"?, "infiltracao_ach"?, "ar_externo_ls"? (L/s), "ini"?, "fim"? (horas de uso),
             "superficies": [{"tipo": "parede"|"vidro"|"cobertura", "orient"?: "N|NE|L|SE|S|SO|O|NO",
                              "area", "u" (W/m²K), "alfa"? (parede/cobertura), "fs"? (vidro, fator solar)}]}
  epw?: nome de um arquivo .epw na pasta de clima do serviço (PHYSIS_CALC_EPW) para rodar também o ano todo.

Modelo: caixa de planta quadrada (lado = √área), paredes por orientação com o U médio informado, janelas
centradas na parede da orientação, piso adiabático (como piso_solo na plataforma), cargas ideais (ideal loads).
Valores que a plataforma já resolve (U, α, FS) devem vir resolvidos: aqui nada é inventado.
"""
from __future__ import annotations

import csv
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .comum import EntradaInvalida, MotorIndisponivel, num

VERSAO_IDF = "24.2"
RSI_RSE = {"parede": (0.13, 0.04), "cobertura": (0.17, 0.04)}   # NBR 15220-2 (igual a cargatermica.py)
ORIENT = {"N": "N", "NE": "N", "L": "L", "E": "L", "SE": "L", "S": "S", "SO": "S", "SW": "S", "O": "O", "W": "O", "NO": "O", "NW": "O"}


def validar(e: dict) -> dict:
    cl = e.get("clima") if isinstance(e.get("clima"), dict) else None
    amb = e.get("ambiente") if isinstance(e.get("ambiente"), dict) else None
    if not cl or not amb:
        raise EntradaInvalida("informe 'clima' e 'ambiente'")
    lat = num(cl, "lat", None, -90, 90)
    c = {"lat": lat, "lon": num(cl, "lon", 0, -180, 180), "alt": num(cl, "alt", 0, -400, 6000),
         "fuso": num(cl, "fuso", -3, -12, 14), "tbs": num(cl, "tbs", None, -40, 55), "tbu": num(cl, "tbu", None, -40, 40),
         "dr": num(cl, "dr", None, 0, 30), "tint": num(cl, "tint", None, 10, 35),
         "mes": int(num(cl, "mes", 1 if lat < 0 else 7, 1, 12))}
    if c["tbu"] > c["tbs"]:
        raise EntradaInvalida("'tbu' maior que 'tbs'")
    a = {"area": num(amb, "area", None, 1, 100000), "pe_direito": num(amb, "pe_direito", None, 2, 30),
         "pessoas": num(amb, "pessoas", 0, 0, 100000), "iluminacao_wm2": num(amb, "iluminacao_wm2", 0, 0, 200),
         "equipamentos_wm2": num(amb, "equipamentos_wm2", 0, 0, 2000), "infiltracao_ach": num(amb, "infiltracao_ach", 0, 0, 50),
         "ar_externo_ls": num(amb, "ar_externo_ls", 0, 0, 1e6), "ini": int(num(amb, "ini", 0, 0, 23)),
         "fim": int(num(amb, "fim", 24, 1, 24))}
    if a["fim"] <= a["ini"]:
        raise EntradaInvalida("'fim' deve ser maior que 'ini'")
    a["atividade_w"] = num(amb, "atividade_w", None, 50, 1000) if a["pessoas"] > 0 else 0.0
    sups = amb.get("superficies")
    if not isinstance(sups, list) or not sups:
        raise EntradaInvalida("'superficies' vazia: informe ao menos paredes e cobertura com U")
    paredes = {k: [] for k in "NLSO"}
    vidros = {k: [] for k in "NLSO"}
    cobertura = []
    ignoradas = 0
    for i, s in enumerate(sups):
        if not isinstance(s, dict):
            raise EntradaInvalida(f"superfície {i} inválida")
        tipo = s.get("tipo") or "parede"
        if tipo in ("piso_solo", "adjacente", "piso_exterior"):
            ignoradas += 1     # zona única: piso adiabático; adjacentes ficam de fora (avisado no resultado)
            continue
        area = num(s, "area", None, 0.01, 100000)
        u = num(s, "u", None, 0.05, 10)
        if tipo == "cobertura":
            cobertura.append((area, u, num(s, "alfa", None, 0, 1)))
            continue
        o = ORIENT.get(str(s.get("orient") or "").upper())
        if not o:
            raise EntradaInvalida(f"superfície {i}: 'orient' deve ser N, NE, L, SE, S, SO, O ou NO")
        if tipo == "parede":
            paredes[o].append((area, u, num(s, "alfa", None, 0, 1)))
        elif tipo == "vidro":
            vidros[o].append((area, u, num(s, "fs", None, 0.01, 1)))
        else:
            raise EntradaInvalida(f"superfície {i}: tipo '{tipo}' desconhecido")
    if not cobertura:
        raise EntradaInvalida("falta a cobertura (tipo 'cobertura' com U e alfa)")
    if not any(paredes.values()):
        raise EntradaInvalida("falta ao menos uma parede (tipo 'parede' com orient, U e alfa)")
    return {"clima": c, "amb": a, "paredes": paredes, "vidros": vidros, "cobertura": cobertura,
            "epw": str(e.get("epw") or ""), "ignoradas": ignoradas}


def _media(itens):
    """Média ponderada pela área de (área, a, b) -> (área total, a médio, b médio)."""
    at = sum(x[0] for x in itens)
    return at, sum(x[0] * x[1] for x in itens) / at, sum(x[0] * x[2] for x in itens) / at


def pressao(alt: float) -> float:
    """Pressão atmosférica padrão (Pa) — ASHRAE Fundamentals cap. 1, eq. 3."""
    return 101325 * (1 - 2.25577e-5 * alt) ** 5.2559


def _r_material(u: float, tipo: str) -> float:
    rsi, rse = RSI_RSE[tipo]
    return max(1 / u - rsi - rse, 0.001)


def _v(p) -> str:
    return ", ".join(f"{x:.4f}" for x in p)


def montar_idf(p: dict, com_ano: bool = False) -> tuple[str, list[str]]:
    """IDF (texto) da zona única + avisos. Só biblioteca padrão."""
    c, a = p["clima"], p["amb"]
    avisos = []
    lado = math.sqrt(a["area"])
    L = W = lado
    H = a["pe_direito"]
    avisos.append(f"Modelo: caixa {lado:.2f} × {lado:.2f} × {H:.2f} m, cada fachada com {lado * H:.1f} m² brutos; "
                  "as áreas de parede informadas entram só na média do U e do α por orientação.")
    o = []
    add = o.append
    add(f"Version, {VERSAO_IDF};")
    add(f"SimulationControl, No, No, No, Yes, {'Yes' if com_ano else 'No'}, No, 1;")
    add("Building, Physis zona unica, 0, Suburbs, 0.04, 0.4, FullInteriorAndExterior, 25, 6;")
    add("Timestep, 4;")
    add("GlobalGeometryRules, UpperLeftCorner, Counterclockwise, Relative;")
    add(f"Site:Location, Local, {c['lat']:.4f}, {c['lon']:.4f}, {c['fuso']:.1f}, {c['alt']:.1f};")
    add(f"SizingPeriod:DesignDay, Projeto verao, {c['mes']}, 21, SummerDesignDay, {c['tbs']:.2f}, {c['dr']:.2f}, "
        f"DefaultMultipliers, , WetBulb, {c['tbu']:.2f}, , , , , {pressao(c['alt']):.0f}, 3.0, 0, No, No, No, "
        "ASHRAEClearSky, , , , , 1.0;")
    if com_ano:
        add("RunPeriod, Ano, 1, 1, , 12, 31, , , Yes, Yes, No, Yes, Yes;")
    add("ScheduleTypeLimits, Fracao, 0, 1, Continuous;")
    add("ScheduleTypeLimits, Temperatura, -60, 200, Continuous;")
    add("ScheduleTypeLimits, Qualquer;")
    add("Schedule:Constant, Sempre, Fracao, 1;")
    if a["ini"] == 0 and a["fim"] == 24:
        add("Schedule:Constant, Ocupacao, Fracao, 1;")
    else:
        partes = []
        if a["ini"] > 0:
            partes.append(f"Until: {a['ini']:02d}:00, 0")
        partes.append(f"Until: {a['fim']:02d}:00, 1")
        if a["fim"] < 24:
            partes.append("Until: 24:00, 0")
        add("Schedule:Compact, Ocupacao, Fracao, Through: 12/31, For: AllDays, " + ", ".join(partes) + ";")
    add(f"Schedule:Constant, Resfriamento, Temperatura, {c['tint']:.2f};")
    add("Schedule:Constant, TipoControle, Qualquer, 2;")
    if a["pessoas"] > 0:
        add(f"Schedule:Constant, Atividade, Qualquer, {a['atividade_w']:.1f};")

    # materiais e construções (sem massa: o U informado manda; a inércia fica fora deste modelo)
    paredes = {}
    for k, itens in p["paredes"].items():
        if itens:
            paredes[k] = _media(itens)
    todas = [x for itens in p["paredes"].values() for x in itens]
    padrao = _media(todas)
    for k in "NLSO":
        if k not in paredes:
            paredes[k] = padrao
            avisos.append(f"Parede {k} sem dado: usada a média das paredes informadas (U {padrao[1]:.2f}).")
    for k, (_, u, alfa) in paredes.items():
        add(f"Material:NoMass, Parede{k}, MediumRough, {_r_material(u, 'parede'):.4f}, 0.9, {alfa:.3f}, {alfa:.3f};")
        add(f"Construction, ConstParede{k}, Parede{k};")
    _, uc, ac = _media(p["cobertura"])
    add(f"Material:NoMass, Cobertura, MediumRough, {_r_material(uc, 'cobertura'):.4f}, 0.9, {ac:.3f}, {ac:.3f};")
    add("Construction, ConstCobertura, Cobertura;")
    add("Material:NoMass, PisoAdiabatico, Smooth, 0.1, 0.9, 0.7, 0.7;")
    add("Construction, ConstPiso, PisoAdiabatico;")

    add(f"Zone, Zona, 0, 0, 0, 0, 1, 1, {H:.3f}, autocalculate;")
    # paredes: origem (canto inferior esquerdo visto de fora), direção "para a direita", comprimento
    geo = {"S": ((0, 0, 0), (1, 0, 0), L), "L": ((L, 0, 0), (0, 1, 0), W),
           "N": ((L, W, 0), (-1, 0, 0), L), "O": ((0, W, 0), (0, -1, 0), W)}

    def ponto(p0, u, s, z):
        return (p0[0] + u[0] * s, p0[1] + u[1] * s, z)

    for k, (p0, u, comp) in geo.items():
        vs = [ponto(p0, u, 0, H), ponto(p0, u, 0, 0), ponto(p0, u, comp, 0), ponto(p0, u, comp, H)]
        add(f"BuildingSurface:Detailed, Parede{k}, Wall, ConstParede{k}, Zona, , Outdoors, , SunExposed, WindExposed, "
            f"autocalculate, 4, " + ", ".join(_v(x) for x in vs) + ";")
        if p["vidros"][k]:
            aw, uw, fs = _media(p["vidros"][k])
            maxima = 0.8 * comp * H
            if aw > maxima:
                avisos.append(f"Vidro {k}: {aw:.1f} m² não cabe na parede da caixa; limitado a {maxima:.1f} m².")
                aw = maxima
            hw = min(0.9 * H, max(aw / (0.9 * comp), 0.6 * H))
            w = min(aw / hw, 0.9 * comp)
            hw = aw / w
            a0 = (comp - w) / 2
            z0 = (H - hw) / 2
            add(f"WindowMaterial:SimpleGlazingSystem, Vidro{k}, {uw:.3f}, {fs:.3f};")
            add(f"Construction, ConstVidro{k}, Vidro{k};")
            jv = [ponto(p0, u, a0, z0 + hw), ponto(p0, u, a0, z0), ponto(p0, u, a0 + w, z0), ponto(p0, u, a0 + w, z0 + hw)]
            add(f"FenestrationSurface:Detailed, Janela{k}, Window, ConstVidro{k}, Parede{k}, , autocalculate, , 1, 4, "
                + ", ".join(_v(x) for x in jv) + ";")
    add("BuildingSurface:Detailed, Cobertura, Roof, ConstCobertura, Zona, , Outdoors, , SunExposed, WindExposed, autocalculate, 4, "
        + ", ".join(_v(x) for x in [(0, W, H), (0, 0, H), (L, 0, H), (L, W, H)]) + ";")
    add("BuildingSurface:Detailed, Piso, Floor, ConstPiso, Zona, , Adiabatic, , NoSun, NoWind, autocalculate, 4, "
        + ", ".join(_v(x) for x in [(L, W, 0), (L, 0, 0), (0, 0, 0), (0, W, 0)]) + ";")

    if a["pessoas"] > 0:
        add(f"People, Pessoas, Zona, Ocupacao, People, {a['pessoas']:.2f}, , , 0.3, autocalculate, Atividade;")
    if a["iluminacao_wm2"] > 0:
        add(f"Lights, Iluminacao, Zona, Ocupacao, Watts/Area, , {a['iluminacao_wm2']:.3f};")
    if a["equipamentos_wm2"] > 0:
        add(f"ElectricEquipment, Equipamentos, Zona, Ocupacao, Watts/Area, , {a['equipamentos_wm2']:.3f};")
    if a["infiltracao_ach"] > 0:
        add(f"ZoneInfiltration:DesignFlowRate, Infiltracao, Zona, Sempre, AirChanges/Hour, , , , {a['infiltracao_ach']:.3f}, 1, 0, 0, 0;")
    if a["ar_externo_ls"] > 0:
        add(f"ZoneInfiltration:DesignFlowRate, ArExterno, Zona, Ocupacao, Flow/Zone, {a['ar_externo_ls'] / 1000:.5f}, , , , 1, 0, 0, 0;")

    add("ThermostatSetpoint:SingleCooling, Resfriar, Resfriamento;")
    add("ZoneControl:Thermostat, Termostato, Zona, TipoControle, ThermostatSetpoint:SingleCooling, Resfriar;")
    add("ZoneHVAC:IdealLoadsAirSystem, Ideal, , Zona Insuflamento;")
    add("ZoneHVAC:EquipmentList, Zona Equipamentos, SequentialLoad, ZoneHVAC:IdealLoadsAirSystem, Ideal, 1, 1, , ;")
    add("NodeList, Zona Insuflamento Nos, Zona Insuflamento;")
    add("ZoneHVAC:EquipmentConnections, Zona, Zona Equipamentos, Zona Insuflamento Nos, , Zona No Ar, Zona Retorno;")
    for var in ("Zone Ideal Loads Zone Total Cooling Rate", "Zone Ideal Loads Zone Sensible Cooling Rate",
                "Zone Ideal Loads Zone Latent Cooling Rate", "Zone Mean Air Temperature"):
        add(f"Output:Variable, *, {var}, Hourly;")
    add("Output:Diagnostics, DisplayExtraWarnings;")
    if p.get("ignoradas"):
        avisos.append(f"{p['ignoradas']} superfície(s) de piso/adjacente fora do modelo (zona única com piso adiabático).")
    return "\n".join(o) + "\n", avisos


def energyplus() -> str | None:
    return shutil.which(os.environ.get("PHYSIS_ENERGYPLUS", "energyplus"))


def ler_csv(caminho: Path) -> dict:
    with open(caminho, newline="", encoding="utf-8", errors="replace") as f:
        linhas = list(csv.reader(f))
    cab = linhas[0]
    dados = linhas[1:]

    def coluna(trecho):
        for i, nome in enumerate(cab):
            if trecho in nome:
                return [float(x[i]) if x[i] else 0.0 for x in dados]
        return []
    return {"total": coluna("Zone Total Cooling Rate"), "sens": coluna("Zone Sensible Cooling Rate"),
            "lat": coluna("Zone Latent Cooling Rate"), "tar": coluna("Zone Mean Air Temperature")}


def calcular(e: dict, somente_idf: bool = False) -> dict:
    p = validar(e)
    pasta_epw = Path(os.environ.get("PHYSIS_CALC_EPW", "/dados/epw"))
    epw = None
    if p["epw"]:
        nome = Path(p["epw"]).name
        if not nome.endswith(".epw") or not (pasta_epw / nome).is_file():
            raise EntradaInvalida(f"arquivo de clima '{nome}' não está em {pasta_epw}")
        epw = pasta_epw / nome
    idf, avisos = montar_idf(p, com_ano=epw is not None)
    if somente_idf:
        return {"ok": True, "idf": idf, "avisos": avisos}
    exe = energyplus()
    if not exe:
        raise MotorIndisponivel("motor indisponível: EnergyPlus não instalado (imagem com INSTALAR_ENERGYPLUS=1)")
    tempo = float(os.environ.get("PHYSIS_CALC_TEMPO", "180"))
    with tempfile.TemporaryDirectory(prefix="eplus-") as d:
        (Path(d) / "in.idf").write_text(idf, encoding="utf-8")
        cmd = [exe, "--readvars", "--output-directory", d]
        cmd += ["--weather", str(epw)] if epw else ["--design-day"]
        cmd.append(str(Path(d) / "in.idf"))
        try:
            r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=tempo)
        except subprocess.TimeoutExpired:
            raise MotorIndisponivel(f"EnergyPlus passou de {tempo:.0f} s") from None
        err = Path(d) / "eplusout.err"
        erros = err.read_text(encoding="utf-8", errors="replace") if err.is_file() else ""
        if r.returncode != 0 or not (Path(d) / "eplusout.csv").is_file():
            graves = [x.strip() for x in erros.splitlines() if "** Severe" in x or "**  Fatal" in x][:10]
            return {"ok": False, "erro": "EnergyPlus não terminou", "detalhes": graves, "idf": idf}
        s = ler_csv(Path(d) / "eplusout.csv")
    dd = {k: v[:24] for k, v in s.items()}
    i = max(range(len(dd["total"])), key=lambda j: dd["total"][j]) if dd["total"] else 0
    pico = dd["total"][i] if dd["total"] else 0.0
    res = {"ok": True, "motor": f"EnergyPlus {VERSAO_IDF} (cargas ideais, zona única)",
           "projeto": {"W": round(pico, 1), "btuh": round(pico * 3.412142, 0), "tr": round(pico / 3516.853, 3),
                       "sens": round(dd["sens"][i], 1) if dd["sens"] else None,
                       "lat": round(dd["lat"][i], 1) if dd["lat"] else None, "hora": i + 1},
           "por_hora_W": [round(x, 1) for x in dd["total"]], "avisos": avisos,
           "avisos_energyplus": sum(1 for x in erros.splitlines() if "** Warning" in x)}
    if epw and len(s["total"]) > 24:
        anual = s["total"][24:]
        res["anual"] = {"resfriamento_kwh_termico": round(sum(anual) / 1000, 1), "horas": len(anual), "clima": epw.name}
    return res
