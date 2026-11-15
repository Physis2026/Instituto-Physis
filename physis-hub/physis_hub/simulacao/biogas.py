"""Simulador de produção de biogás (espelho de SIMULACAO.biogas em sistema/physis-simulacao.js).

O que já existia e continua valendo (não duplicado): a Economia circular estima biogás por kg fresco
(premissa residuos.biogas_por_kg, rota "biodigestor" do plano RC_ROTAS) e o Carbono conta o biogás no lugar do
GLP (carbono.py, evitadas["biogas"] = m³/ano × biogas.pci ÷ glp.pci × fator do GLP). Este simulador refina a
conta para quem vai PROJETAR o biodigestor e entrega biogas_m3_dia no mesmo formato que o Carbono lê
(ctx["biogas"]["biogas_m3_dia"]), então as emissões evitadas pelo GLP saem iguais às do carbono.py.

Modelo:
- por substrato: ST (fração da massa fresca), SV (fração dos ST), BMP (m³ de biogás por kg SV) e fração de CH₄
  (premissa sim.biogas.substratos, "conferir"; valor ausente = [MARCADOR], nada inventado);
- carga orgânica volumétrica (COV, kg SV/m³·dia) contra o limite do regime (premissa sim.biogas.cov_max);
- cinética de 1ª ordem: k(T) = k_ref·θ^(T − T_ref) (premissa sim.biogas.cinetica); fração do BMP alcançada no TRH:
  mistura completa f = k·TRH/(1 + k·TRH), fluxo pistonado (tubular) f = 1 − e^(−k·TRH); TRH longo → f → 1;
- temperatura: regime fixo (psicrofílico, mesofílico, termofílico; premissa sim.biogas.temperaturas) ou digestor
  sem aquecimento seguindo a temperatura média mensal DO LOCAL da instalação (hub.local_da_instalacao + NASA POWER
  T2M), nunca um padrão: sem local, a conta para e pede o local;
- produção diária (365 dias, temperatura interpolada entre os meios dos meses) e mensal;
- energia: térmica = biogás × biogas.pci; elétrica = térmica × rendimento do gerador; GLP equivalente; horas de
  queimador; P, Q e S do gerador (regra dos módulos de energia, fator de potência de premissa);
- CO₂e evitado: GLP (regra do carbono.py), eletricidade da rede, diesel e manejo de dejetos (fatores da base do
  Carbono, sistema/physis-fatores-emissao.json);
- digestato (volume) e N-P-K estimado (premissa [CONFERIR]); avisos de sobrecarga, TRH curto, frio, H₂S e segurança;
- faixa de Monte Carlo no rendimento.
"""
from __future__ import annotations

import math

from .comum import FaltaDado, MARCADOR, premissa, resultado, usada
from .incerteza import monte_carlo

DIAS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
DENS_CH4 = 0.716        # kg/m³ a 0 °C e 1 atm (mesmo valor de physis-carbono.js)
AVISOS_SEGURANCA = [
    "Biogás é inflamável e o H₂S é tóxico e corrosivo: filtro de H₂S (limalha de ferro ou similar), "
    "dreno de condensado, válvula de alívio e corta-chamas antes do queimador ou do motor.",
    "Local ventilado, sem chama perto do gasômetro; nunca entrar no digestor sem ventilação e acompanhante.",
    "Digestato de dejetos ainda pode ter patógenos: aplicar no solo seguindo a orientação agronômica.",
]


# ── fatores do Carbono (mesmas contas do carbono.py) ──
def fatores_carbono(F: dict | None = None) -> dict:
    """GLP (tCO2e/kg), diesel B (tCO2e/L), rede (tCO2/MWh), GWP do CH4 biogênico, CH4 de dejetos por cabeça e
    PCI (MJ) do GLP e do diesel, lidos da base de fatores pelo próprio carbono.py."""
    from .. import carbono
    F = F or carbono.carregar()
    gw = carbono.gwp_de(F, F["gwp"]["padrao"])
    return {"glp_t_por_kg": carbono.tco2e(carbono.combustao(F, "glp", 1, "estacionaria")[0], gw),
            "diesel_t_por_l": carbono.tco2e(carbono.combustao(F, "diesel_b", 1, "estacionaria")[0], gw),
            "rede_t_por_mwh": carbono.fator_rede(F, None),
            "gwp_ch4": gw.get("CH4_bio"),
            "diesel_mj_por_l": F["combustiveis"]["diesel"]["mj"],
            "dejetos_ch4_kg_cab_ano": {k: v.get("dejetos_ch4") for k, v in F["agro"]["rebanho"].items()}}


def clima_do_local(hub, irradiacao) -> dict:
    """Temperatura média mensal do local da instalação (fonte única hub.local_da_instalacao + NASA POWER T2M)."""
    loc = hub.local_da_instalacao()
    if loc.get("lat") is None or loc.get("lon") is None:
        return {"ok": False, "erro": "local não informado (cadastre o local no Início ou no Planejador)"}
    r = irradiacao.consultar(loc["lat"], loc["lon"], "temperatura")
    meses = ((r.get("ponto") or {}).get("meses")) if r.get("ok") else None
    if not meses or len(meses) != 12:
        return {"ok": False, "erro": "temperatura do local indisponível agora", "local": loc}
    return {"ok": True, "temperatura_mensal": meses, "local": {k: loc.get(k) for k in ("lat", "lon", "municipio", "uf", "fonte")},
            "fonte": r.get("fonte")}


def _sub(s: dict) -> dict:
    tab = premissa("sim.biogas.substratos") or {}
    base = dict(tab.get(s.get("tipo")) or {})
    for k in ("st", "sv", "bmp", "ch4", "k_ref", "npk", "esterco", "rebanho"):
        if s.get(k) is not None:
            base[k] = s[k]
    falt = [k for k in ("st", "sv", "bmp", "ch4") if base.get(k) is None]
    if falt:
        raise FaltaDado(f"{MARCADOR} {', '.join(falt).upper()} do substrato '{s.get('tipo')}' (análise de laboratório ou tabela [CONFERIR])")
    base["tipo"] = s.get("tipo")
    base["nome"] = base.get("nome") or s.get("tipo")
    base["kg_dia"] = float(s["kg_dia"])
    base["cabecas"] = s.get("cabecas")
    return base


def k_temperatura(T: float, k_ref: float | None = None) -> float:
    c = premissa("sim.biogas.cinetica") or {}
    k_ref = c.get("k_ref_dia") if k_ref is None else k_ref
    if k_ref is None or c.get("theta") is None or c.get("t_ref_c") is None:
        raise FaltaDado(f"{MARCADOR} cinética (premissa sim.biogas.cinetica)")
    return k_ref * c["theta"] ** (T - c["t_ref_c"])


def fracao_bmp(k: float, trh: float, modelo: str = "mistura") -> float:
    if trh <= 0:
        return 0.0
    return 1.0 - math.exp(-k * trh) if modelo == "pistonado" else k * trh / (1.0 + k * trh)


def _temps_diarias(mensal: list) -> list:
    meio = []
    acc = 0
    for d in DIAS:
        meio.append(acc + d / 2.0)
        acc += d
    out = []
    for dia in range(365):
        t = dia + 0.5
        m = 0
        while m < 11 and meio[m + 1] <= t:
            m += 1
        if t < meio[0]:
            a, b, ta, tb = meio[11] - 365, meio[0], mensal[11], mensal[0]
        elif m == 11:
            a, b, ta, tb = meio[11], meio[0] + 365, mensal[11], mensal[0]
        else:
            a, b, ta, tb = meio[m], meio[m + 1], mensal[m], mensal[m + 1]
        out.append(ta + (tb - ta) * (t - a) / (b - a))
    return out


def simular(p: dict, fatores: dict | None = None) -> dict:
    """p: substratos [{tipo, kg_dia, (st, sv, bmp, ch4, k_ref, cabecas) opcionais}]; agua_l_dia (diluição);
    digestor {tipo: tubular|indiano|chines|lagoa_coberta|mistura_completa, volume_m3 (útil)} ou trh_alvo_dias para
    dimensionar; regime: psicrofilico|mesofilico|termofilico|ambiente; temperatura_mensal [12] (°C, do local; só
    no regime ambiente); usos {glp, eletricidade, diesel} (frações da energia, somam até 1); horas_gerador;
    fp_medido; manejo_dejetos (true: conta o CH₄ de dejetos evitado com as cabeças informadas); mc (amostras)."""
    fatores = fatores or fatores_carbono()
    subs = [_sub(s) for s in p["substratos"]]
    tipos = premissa("sim.biogas.tipos_digestor") or {}
    dg = p.get("digestor") or {}
    tipo = dg.get("tipo", "mistura_completa")
    modelo = (tipos.get(tipo) or {}).get("modelo", "mistura")
    reg = p.get("regime", "mesofilico")
    temps = premissa("sim.biogas.temperaturas") or {}
    avisos = []
    q_in = sum(s["kg_dia"] for s in subs) / 1000.0 + float(p.get("agua_l_dia", 0.0)) / 1000.0     # m³/dia (ρ ≈ 1000 kg/m³)
    folga = premissa("sim.biogas.folga_volume", 1.25)
    dimensionado = None
    if dg.get("volume_m3"):
        v_util = float(dg["volume_m3"])
    else:
        trh_a = p.get("trh_alvo_dias") or (premissa("sim.biogas.trh_min_dias") or {}).get(reg)
        if trh_a is None:
            raise FaltaDado(f"{MARCADOR} volume do digestor ou TRH alvo")
        v_util = q_in * float(trh_a)
        dimensionado = {"trh_alvo_dias": float(trh_a), "volume_util_m3": v_util, "volume_total_m3": v_util * folga, "folga": folga}
    trh = v_util / q_in if q_in > 0 else 0.0
    sv_dia = sum(s["kg_dia"] * s["st"] * s["sv"] for s in subs)
    cov = sv_dia / v_util if v_util > 0 else float("inf")
    cov_max = (premissa("sim.biogas.cov_max") or {}).get("ambiente" if reg == "ambiente" else reg)
    if cov_max is not None and cov > cov_max:
        avisos.append(f"Sobrecarga: carga orgânica {cov:.2f} kg SV/m³·dia acima do limite {cov_max:g} do regime "
                      f"(premissa sim.biogas.cov_max): risco de acidificação; aumente o volume ou reduza a carga.")
    trh_min = (premissa("sim.biogas.trh_min_dias") or {}).get(reg)
    if trh_min is not None and trh < trh_min:
        avisos.append(f"TRH curto: {trh:.1f} dias, abaixo de {trh_min:g} dias para o regime (lavagem das bactérias).")
    if reg == "ambiente":
        tm = p.get("temperatura_mensal")
        if not tm or len(tm) != 12:
            raise FaltaDado("local não informado: digestor sem aquecimento precisa da temperatura mensal do local da "
                            "instalação (Início ou Planejador); nenhum padrão é usado")
        ganho = premissa("sim.biogas.ganho_enterrado_c", 0.0)
        t_mes = [float(t) + ganho for t in tm]
    else:
        tf = temps.get(reg)
        if tf is None:
            raise FaltaDado(f"{MARCADOR} temperatura do regime '{reg}'")
        t_mes = [float(tf)] * 12
    t_min = premissa("sim.biogas.t_min_c")
    if t_min is not None and min(t_mes) < t_min:
        avisos.append(f"Temperatura baixa: {min(t_mes):.1f} °C no mês mais frio (abaixo de {t_min:g} °C): a produção cai "
                      "muito; pense em estufa, enterrar ou aquecer com o próprio biogás.")
    t_dia = _temps_diarias(t_mes)

    def ch4_e_biogas(T):
        bio = ch4 = 0.0
        for s in subs:
            f = fracao_bmp(k_temperatura(T, s.get("k_ref")), trh, modelo)
            b = s["kg_dia"] * s["st"] * s["sv"] * s["bmp"] * f
            bio += b
            ch4 += b * s["ch4"]
        return bio, ch4
    diario = [ch4_e_biogas(T) for T in t_dia]
    mensal, d0 = [], 0
    for m, nd in enumerate(DIAS):
        bio = sum(x[0] for x in diario[d0:d0 + nd])
        ch4 = sum(x[1] for x in diario[d0:d0 + nd])
        mensal.append({"mes": m + 1, "t_c": t_mes[m], "biogas_m3": bio, "ch4_m3": ch4})
        d0 += nd
    bio_ano = sum(x[0] for x in diario)
    ch4_ano = sum(x[1] for x in diario)
    bio_dia = bio_ano / 365.0
    bmp_pot = sum(s["kg_dia"] * s["st"] * s["sv"] * s["bmp"] for s in subs)
    # energia
    pci = premissa("biogas.pci")
    pci_glp = premissa("glp.pci")
    eta_el = premissa("sim.biogas.eta_eletrica")
    eta_t = premissa("sim.biogas.eta_termica")
    q_h = premissa("sim.biogas.queimador_m3_h")
    e_th_dia = bio_dia * pci
    e_el_dia = e_th_dia * eta_el
    horas = float(p.get("horas_gerador") or premissa("sim.biogas.horas_gerador", 24))
    p_kw = e_el_dia / horas if horas > 0 else 0.0
    fp_m = p.get("fp_medido")
    fp = fp_m if fp_m and 0 < fp_m <= 1 else premissa("eletrica.fator_potencia_padrao")
    s_kva = p_kw / fp if fp else None
    q_kvar = math.sqrt(max(0.0, s_kva * s_kva - p_kw * p_kw)) if s_kva is not None else None
    fp_min = premissa("eletrica.fator_potencia_minimo")
    # calor para aquecer a carga (meso/termo) — só a carga fria, sem perdas pelas paredes
    t_amb = p.get("temperatura_mensal")
    aquec = None
    if reg in ("mesofilico", "termofilico") and t_amb and len(t_amb) == 12:
        aquec = sum(q_in * 1000 * 4.186 * max(0.0, t_mes[m] - t_amb[m]) / 3600 * DIAS[m] for m in range(12)) / 365
    # usos e CO2e evitado
    usos = p.get("usos") or {"glp": 1.0}
    fg, fe, fd = float(usos.get("glp", 0.0)), float(usos.get("eletricidade", 0.0)), float(usos.get("diesel", 0.0))
    if fg + fe + fd > 1.0 + 1e-9:
        raise ValueError("as frações de uso (glp + eletricidade + diesel) passam de 1")
    bio_m3_ano = bio_ano
    ev_glp = bio_m3_ano * fg * pci / pci_glp * fatores["glp_t_por_kg"]       # mesma regra de carbono.py
    ev_el = e_th_dia * 365 * fe * eta_el / 1000 * fatores["rede_t_por_mwh"]
    ev_di = e_th_dia * 365 * fd * 3.6 / fatores["diesel_mj_por_l"] * fatores["diesel_t_por_l"]
    ev_dej = 0.0
    vaz = premissa("sim.biogas.vazamento", 0.0)
    if p.get("manejo_dejetos"):
        for s in subs:
            if s.get("esterco") and s.get("cabecas") and s.get("rebanho"):
                f = fatores["dejetos_ch4_kg_cab_ano"].get(s["rebanho"])
                if f is None:
                    avisos.append(f"{MARCADOR} CH₄ de dejetos do rebanho '{s['rebanho']}' na base do Carbono")
                    continue
                ev_dej += float(s["cabecas"]) * f * (1 - vaz) * fatores["gwp_ch4"] / 1000
            elif s.get("esterco"):
                avisos.append(f"Manejo de dejetos de '{s['nome']}': informe o número de cabeças para contar o metano evitado.")
    vaz_t = ch4_ano * vaz * DENS_CH4 * fatores["gwp_ch4"] / 1000
    # digestato
    dens_b = premissa("sim.biogas.densidade_biogas", 1.15)
    dig_m3 = max(0.0, q_in - bio_dia * dens_b / 1000.0)
    npk = {"N": 0.0, "P2O5": 0.0, "K2O": 0.0}
    npk_falta = []
    for s in subs:
        n = s.get("npk")
        if not n or any(n.get(k) is None for k in npk):
            npk_falta.append(s["nome"])
            continue
        for k in npk:
            npk[k] += s["kg_dia"] / 1000.0 * n[k]
    if npk_falta:
        avisos.append(f"{MARCADOR} N-P-K de: {', '.join(npk_falta)} (análise do digestato)")
    if reg == "termofilico":
        avisos.append("Termofílico é mais sensível a variação de temperatura e amônia: controle diário.")
    # Monte Carlo no rendimento
    inc = premissa("sim.biogas.incerteza") or {}
    ent = {}
    for i, s in enumerate(subs):
        fr = sum(fracao_bmp(k_temperatura(T, s.get("k_ref")), trh, modelo) for T in t_dia) / 365.0
        for nome, val, cv in (("kg", s["kg_dia"], inc.get("kg_cv")), ("st", s["st"], inc.get("st_cv")),
                              ("sv", s["sv"], inc.get("sv_cv")), ("bmp", s["bmp"], inc.get("bmp_cv")),
                              ("ch4", s["ch4"], inc.get("ch4_cv"))):
            ent[f"{nome}{i}"] = {"tipo": "normal", "media": val, "dp": val * cv} if cv else val
        ent[f"fr{i}"] = fr
    mc = monte_carlo(ent, "biogas", n=int(p.get("mc") or premissa("sim.mc.amostras", 2000)), semente=p.get("semente"))
    avisos += AVISOS_SEGURANCA
    return resultado(
        "Biogás: potencial (ST × SV × BMP) × fração alcançada por cinética de 1ª ordem com k(T) = k_ref·θ^(T−T_ref)",
        ["alimentação diária constante", "densidade da carga 1000 kg/m³", f"modelo de reator: {modelo}",
         "temperatura do digestor = do regime ou a média mensal do local (+ ganho de enterrar)", "sem inibição (amônia, H₂S, óleo)"],
        [usada("sim.biogas.substratos"), usada("sim.biogas.cinetica"), usada("sim.biogas.cov_max"),
         usada("sim.biogas.trh_min_dias"), usada("sim.biogas.temperaturas"), usada("biogas.pci"), usada("glp.pci"),
         usada("sim.biogas.eta_eletrica"), usada("sim.biogas.eta_termica"), usada("eletrica.fator_potencia_padrao", fp),
         usada("sim.biogas.vazamento"), usada("sim.biogas.incerteza")],
        {"dias": 365, "meses": 12, "substratos": len(subs)},
        "Pré-dimensionamento. BMP e ST mudam com a dieta dos animais e a idade do resíduo: o ensaio de BMP do "
        "substrato real vale mais. Partida, codigestão desequilibrada e inibição não estão no modelo.",
        {"q_entrada_m3_dia": q_in, "volume_util_m3": v_util, "trh_dias": trh, "cov_kg_sv_m3_dia": cov, "cov_max": cov_max,
         "dimensionamento": dimensionado, "modelo_reator": modelo, "regime": reg,
         "biogas_m3_dia": bio_dia, "ch4_m3_dia": ch4_ano / 365.0, "biogas_m3_ano": bio_ano, "ch4_m3_ano": ch4_ano,
         "potencial_bmp_m3_dia": bmp_pot, "fracao_media_bmp": bio_dia / bmp_pot if bmp_pot > 0 else None,
         "mensal": mensal, "diario_biogas_m3": [x[0] for x in diario], "temperatura_dia_c": t_dia,
         "energia": {"termica_kwh_dia": e_th_dia, "eletrica_kwh_dia": e_el_dia, "calor_util_kwh_dia": e_th_dia * eta_t,
                     "glp_kg_dia": e_th_dia / pci_glp, "horas_queimador_dia": bio_dia / q_h if q_h else None,
                     "aquecimento_carga_kwh_dia": aquec},
         "gerador": {"p_kw": p_kw, "q_kvar": q_kvar, "s_kva": s_kva, "fp": fp, "horas_dia": horas,
                     "fp_fonte": "medido" if fp_m and 0 < fp_m <= 1 else "premissa", "fp_baixo": fp_min is not None and fp is not None and fp < fp_min},
         "evitadas_t_ano": {"glp": ev_glp, "eletricidade": ev_el, "diesel": ev_di, "dejetos": ev_dej,
                            "vazamento": -vaz_t, "total": ev_glp + ev_el + ev_di + ev_dej - vaz_t},
         "carbono_ctx": {"biogas_m3_dia": bio_dia * fg, "fonte": "Simulação de biogás (physis_hub.simulacao.biogas), parte usada no lugar do GLP"},
         "digestato": {"m3_dia": dig_m3, "npk_kg_dia": npk if not npk_falta else None},
         "faixa_ch4_m3_dia": {k: v for k, v in mc["percentis"].items()}, "faixa_media": mc["media"]}, avisos)
