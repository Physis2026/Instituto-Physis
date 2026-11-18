"""Inventario de emissoes (GHG Protocol) do modulo Carbono: espelho em Python de sistema/physis-carbono.js.

Mesmas contas e mesma base de fatores (sistema/physis-fatores-emissao.json), para conferir a tela com
testes de mesa. So biblioteca padrao.

Regras seguidas (GHG Protocol, abordagem do Programa Brasileiro GHG Protocol):
- escopo 1: combustao estacionaria e movel, fugitivas (HFC), processos, agropecuaria, residuos tratados no lugar
  e mudanca de uso do solo (opcional);
- escopo 2: eletricidade da rede por localizacao (fator do SIN, anual ou mensal) e por escolha de compra;
- escopo 3: categorias escolhidas (1, 2, 4, 5, 6, 7, 9, 12 e linhas livres);
- CO2 biogenico, gases fora do Protocolo de Quioto (HCFC-22), remocoes e emissoes evitadas ficam a parte
  (nunca abatem o total).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BASE = RAIZ / "sistema" / "physis-fatores-emissao.json"

BIO = {"biodiesel", "etanol_anidro", "etanol_hidratado", "lenha", "carvao_vegetal"}
BOVINOS = {"gado_corte", "gado_leite", "bufalo"}
N2O_N = 44 / 28
C_CO2 = 44 / 12
CH4_C = 16 / 12

# rota da Economia circular -> (destino para a conta, tratado no lugar?)
ROTA_DESTINO = {
    "aterro": ("aterro", False), "aterro1": ("aterro", False), "reciclagem": ("reciclagem", False),
    "reversa": ("reciclagem", False), "incineracao": ("incineracao", False),
    "compostagem": ("compostagem", True), "vermi": ("compostagem", True), "biodigestor": ("biodigestor", True),
    "biomassa": ("queima", True),
}
RC_UN = {"kg_mes": 1, "kg_sem": 52 / 12, "kg_dia": 30, "t_mes": 1000, "l_mes": 0.92}
PREMISSAS = RAIZ / "sistema" / "physis-premissas.json"
# fora do repositório (sem a base de premissas): os mesmos padrões que physis-carbono.js usa sem o bloco PhysisCalc
BIOG_PAD = {"alimentos": 0.10, "esterco_bov": 0.04, "esterco_sui": 0.06, "cama_aviario": 0.07, "colheita": 0.05}
PCI_PAD = {"biogas.pci": 6.0, "glp.pci": 12.8}


def premissa(pid: str, padrao=None):
    """Valor padrão de uma premissa de sistema/physis-premissas.json (ou `padrao` sem a base)."""
    try:
        for p in json.loads(PREMISSAS.read_text(encoding="utf-8"))["premissas"]:
            if p.get("id") == pid:
                return p.get("valor_padrao")
    except (OSError, ValueError, KeyError):
        pass
    return padrao


def carregar(caminho: Path | str | None = None) -> dict:
    return json.loads(Path(caminho or BASE).read_text(encoding="utf-8"))


def num(v) -> float | None:
    """Numero digitado no jeito brasileiro ou com ponto decimal ('1.234,5', '0.0385', '1.000' = mil)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    s = str(v).strip().replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def n0(v) -> float:
    x = num(v)
    return x if x is not None else 0.0


def gwp_de(F: dict, versao: str) -> dict:
    return F["gwp"].get(versao) or F["gwp"][F["gwp"]["padrao"]]


def tco2e(gases: dict, gwp: dict) -> float:
    """kg de cada gas -> tCO2e."""
    return sum(kg * gwp.get(g, 0) for g, kg in gases.items()) / 1000


def _soma(a: dict, b: dict, k: float = 1.0) -> dict:
    for g, v in b.items():
        a[g] = a.get(g, 0) + v * k
    return a


# ─────────────── combustao ───────────────
def combustao(F: dict, comb: str, qtd: float, uso: str = "estacionaria", teor_bio: float | None = None,
              nao_renovavel: bool = False) -> tuple[dict, float]:
    """kg de cada gas e kg de CO2 biogenico. 'comb' pode ser combustivel puro ou mistura (diesel_b, gasolina_c, gnv)."""
    C, M = F["combustiveis"], F["misturas"]
    partes = []
    if comb in M:
        m = M[comb]
        t = m["teor_bio"] if teor_bio is None else teor_bio
        partes.append((m["fossil"], qtd * (1 - t)))
        if m.get("bio"):
            partes.append((m["bio"], qtd * t))
    else:
        partes.append((comb, qtd))
    gases: dict = {}
    bio_kg = 0.0
    for cid, q in partes:
        c = C[cid]
        tj = q * c["mj"] / 1e6
        e = c.get(uso) or c["estacionaria"]
        eh_bio = cid in BIO
        co2_bio = tj * c.get("co2_bio", 0)
        if nao_renovavel and eh_bio:
            gases["CO2"] = gases.get("CO2", 0) + co2_bio
            co2_bio = 0
        gases["CO2"] = gases.get("CO2", 0) + tj * c.get("co2", 0)
        ch4 = "CH4_bio" if eh_bio else "CH4_fossil"
        gases[ch4] = gases.get(ch4, 0) + tj * e["ch4"]
        gases["N2O"] = gases.get("N2O", 0) + tj * e["n2o"]
        bio_kg += co2_bio
    return gases, bio_kg


# ─────────────── fugitivas ───────────────
def refrigerante(F: dict, gas: str, kg_emitido: float) -> tuple[dict, bool]:
    r = F["refrigerantes"][gas]
    return {g: kg_emitido * f for g, f in r["gases"].items()}, bool(r["quioto"])


def refrigerante_carga(F: dict, gas: str, carga_kg: float, taxa: float) -> tuple[dict, bool]:
    return refrigerante(F, gas, carga_kg * taxa)


# ─────────────── agropecuaria ───────────────
def rebanho(F: dict, tipo: str, cabecas: float) -> dict:
    A = F["agro"]
    r, p = A["rebanho"][tipo], A["pastagem"]
    ef3 = p["ef3_prp_bovinos"] if tipo in BOVINOS else p["ef3_prp_outros"]
    nex = r["nex_kg_n_1000kg_dia"] * r["peso_kg"] / 1000 * 365 * cabecas
    n2o = nex * (ef3 + p["frac_gasm"] * p["ef4"] + p["frac_leach"] * p["ef5"]) * N2O_N
    return {"CH4_bio": cabecas * (r["enterica_ch4"] + r["dejetos_ch4"]), "N2O": n2o}


def fertilizante(F: dict, kg_n: float = 0, kg_ureia: float = 0, kg_calcario: float = 0, kg_dolomita: float = 0) -> dict:
    A = F["agro"]
    f = A["fertilizante"]
    n_total = kg_n + kg_ureia * A["teor_n_ureia"]
    n2o = n_total * (f["ef1"] + f["frac_gasf"] * f["ef4"] + f["frac_leach"] * f["ef5"]) * N2O_N
    co2 = (kg_ureia * A["ureia_tc_por_t"] + kg_calcario * A["calcario_tc_por_t"] + kg_dolomita * A["dolomita_tc_por_t"]) * C_CO2
    return {"CO2": co2, "N2O": n2o}


def uso_solo(F: dict, ha: float, bioma: str) -> dict:
    U = F["uso_solo"]
    return {"CO2": ha * U["estoque_tco2_ha"][bioma] / U["anos_amortizacao"] * 1000}


# ─────────────── residuos ───────────────
def residuo(F: dict, tipo: str, t: float, destino: str) -> dict:
    """kg de cada gas para t toneladas de residuo umido."""
    R = F["residuos"]
    if destino == "aterro":
        a = R["aterro"]
        doc = R["doc"].get(tipo, R["doc"]["_padrao"])
        ch4_t = t * doc * a["docf"] * a["mcf"] * a["f"] * CH4_C * (1 - a["r"]) * (1 - a["ox"])
        return {"CH4_bio": ch4_t * 1000}
    if destino in ("compostagem", "biodigestor"):
        x = R[destino]
        return {"CH4_bio": t * x["ch4"] * 1000, "N2O": t * x["n2o"] * 1000}
    if destino == "reciclagem":
        return {"CO2": t * R["reciclagem_tco2e_t"] * 1000}
    if destino == "incineracao":
        inc = R["incineracao_tco2_t"]
        return {"CO2": t * inc.get(tipo, inc["_padrao"]) * 1000}
    if destino == "queima":
        g, _ = combustao(F, "lenha", t * 1000)
        return g
    return {}


# ─────────────── escopo 2 ───────────────
def fator_rede(F: dict, escolha: str | None, manual=None) -> float:
    m = num(manual)
    if m is not None and m >= 0:
        return m
    A = F["rede"]["anual"]
    return A.get(escolha or F["rede"]["padrao"], A[F["rede"]["padrao"]])["valor"]


def rede_localizacao(kwh: float, fator_t_mwh: float) -> float:
    return kwh / 1000 * fator_t_mwh


def rede_mensal(kwh_mes: list, fatores: list) -> float:
    return sum(k / 1000 * f for k, f in zip(kwh_mes, fatores))


def rede_mercado(kwh: float, fator_residual: float, irec_mwh: float = 0, contratos: list | None = None) -> float:
    mwh = kwh / 1000
    t = 0.0
    coberto = min(irec_mwh, mwh)
    for c_mwh, c_f in contratos or []:
        c = min(c_mwh, max(0.0, mwh - coberto))
        t += c * c_f
        coberto += c
    return t + max(0.0, mwh - coberto) * fator_residual


# ─────────────── pegada do servidor (sistema digital) ───────────────
def servidor_contagem(eq: dict, escolha: str | None = "auto") -> str:
    """'ja_contado' (servidor dentro do lugar cujas contas de luz ja estao no inventario: so informacao)
    ou 'somar' (hospedado em outro lugar: fonte propria). 'auto' segue o local do equipamento."""
    if escolha in ("ja_contado", "somar"):
        return escolha
    return "somar" if eq.get("local") == "fora" else "ja_contado"


def servidor_inventario(equipamentos: list, f_loc: float, escolha: str | None = "auto", cats=None) -> dict:
    """Linhas do servidor no inventario. equipamentos: [{nome, kwh_ano (ja com PUE), local, controle,
    t_ano_fabricacao, qualidade}]. Energia: escopo 2 (controle 'proprio') ou escopo 3 cat. 1 ('servico',
    hospedagem comprada); so entra se 'somar'. Fabricacao: escopo 3 cat. 2, sempre (nao esta na conta de luz).
    cats: categorias do escopo 3 marcadas (None = todas)."""
    tem = (lambda k: True) if cats is None else (lambda k: k in cats)
    out = {"linhas": [], "e2_t": 0.0, "e3_cat1_t": 0.0, "cat2_t": 0.0, "ja_contado_t": 0.0}
    for eq in equipamentos or []:
        t = n0(eq.get("kwh_ano")) / 1000 * f_loc
        q = "medido" if eq.get("qualidade") == "medido" else "estimado"
        nome = str(eq.get("nome") or "Servidor")
        if servidor_contagem(eq, escolha) == "ja_contado":
            out["ja_contado_t"] += t
        elif eq.get("controle") == "servico":
            if tem(1):
                out["e3_cat1_t"] += t
                out["linhas"].append({"escopo": 3, "cat": 1, "fonte": nome + " (hospedagem comprada)", "t": t, "q": q})
        else:
            out["e2_t"] += t
            out["linhas"].append({"escopo": 2, "cat": None, "fonte": nome + " (energia do servidor)", "t": t, "q": q})
        fab = n0(eq.get("t_ano_fabricacao"))
        if fab and tem(2):
            out["cat2_t"] += fab
            out["linhas"].append({"escopo": 3, "cat": 2, "fonte": nome + " (fabricação, amortizada)", "t": fab, "q": "estimado"})
    return out


# ─────────────── remocoes, metas e SBCE ───────────────
def remocoes(F: dict, ha: float, bioma: str, idade_anos: float = 0) -> float:
    R = F["remocoes"]
    taxa = R["tco2_ha_ano"][bioma]
    if idade_anos > R["anos_crescimento_rapido"]:
        taxa *= R["fator_depois"]
    return ha * taxa


def trajetoria(base_t: float, ano_base: int, ano_alvo: int, pct_ano: float) -> list:
    return [(a, base_t * max(0.0, 1 - pct_ano / 100 * (a - ano_base))) for a in range(ano_base, ano_alvo + 1)]


def ano_net_zero(base_t: float, ano_base: int, pct_ano: float, residual_max: float = 0.10) -> int | None:
    if pct_ano <= 0:
        return None
    return ano_base + math.ceil((1 - residual_max) / (pct_ano / 100) - 1e-9)


def sbce(F: dict, escopo1_t: float) -> str:
    S = F["sbce"]
    if escopo1_t > S["limite_obrigacao_t"]:
        return "obrigacao"
    if escopo1_t > S["limite_relato_t"]:
        return "relato"
    return "voluntario"


def incerteza(linhas: list) -> float | None:
    """linhas: [(tCO2e, incerteza relativa)] -> incerteza relativa do total (soma quadratica)."""
    tot = sum(t for t, _ in linhas)
    if tot <= 0:
        return None
    return math.sqrt(sum((t * u) ** 2 for t, u in linhas)) / tot


# ─────────────── estado salvo na tela ───────────────
def migrar(c: dict | None) -> dict:
    """Formato antigo {kwh, diesel, glp, gn, solar_kwh, medidas} -> formato 2 (os campos antigos continuam lidos)."""
    c = dict(c or {})
    if c.get("v") == 2:
        return c
    estac = []
    for k, comb in (("diesel", "diesel_b"), ("glp", "glp"), ("gn", "gas_natural")):
        if num(c.get(k)):
            estac.append({"comb": comb, "qtd": str(c.get(k)), "q": "estimado"})
    novo = {"v": 2, "kwh": c.get("kwh", ""), "solar_kwh": c.get("solar_kwh", ""), "estac": estac,
            "metas": {"medidas": list(c.get("medidas") or [])}}
    return novo


def calcular(estado: dict, ctx: dict | None = None, F: dict | None = None) -> dict:
    """Inventario completo. ctx traz os dados de outros modulos: rc (lista da Economia circular),
    kwh_ano, area_m2, producao, mudas_sbn, esgoto (parte Esgoto e biogas: pessoas, tratamento, reuso_m3_dia) e
    materiais (chave physis-calc-materiais: composicoes com area_m2 e kgco2e_m2). Mesmas regras do calcular() em
    physis-carbono.js. Sem o fator na base (F["efluentes"], F["agua_fornecida"]) a linha nao entra: [MARCADOR]."""
    F = F or carregar()
    ctx = ctx or {}
    c = migrar(estado)
    gw = gwp_de(F, c.get("gwp") or F["gwp"]["padrao"])
    U = F["incerteza"]
    linhas = []

    def add(escopo, fonte, gases, q="estimado", tipo_fator="combustivel", bio_kg=0.0, cat=None, fora=False):
        t = tco2e(gases, gw)
        u = math.hypot(U["dado"].get(q, U["dado"]["estimado"]), U["fator"].get(tipo_fator, 0.5))
        linhas.append({"escopo": escopo, "fonte": fonte, "gases": gases, "t": t, "bio_t": bio_kg / 1000,
                       "q": q, "u": u, "cat": cat, "fora": fora})

    def teor(x):
        t = num(x.get("teor_pct"))
        return None if t is None else t / 100

    for x in c.get("estac", []):
        g, b = combustao(F, x["comb"], n0(x.get("qtd")), "estacionaria", teor(x), bool(x.get("nr")))
        add(1, "estacionaria", g, x.get("q", "estimado"), bio_kg=b)
    # combustão móvel: o medido na Frota (ctx["frota_movel"], de frota.para_carbono) vale sobre o digitado, que fica de
    # reserva; c["movel_auto"] False volta ao digitado. Mesma regra de physis-carbono.js.
    med_frota = bool(ctx.get("frota_movel")) and c.get("movel_auto", True) is not False
    for x in (ctx["frota_movel"] if med_frota else c.get("movel", [])):
        g, b = combustao(F, x["comb"], n0(x.get("qtd")), "movel", teor(x))
        add(1, "movel", g, "medido" if med_frota else x.get("q", "estimado"), bio_kg=b)
    for x in c.get("refrig", []):
        if x.get("modo") == "carga":
            vz = F["vazamento"].get(x.get("equip") or "split", F["vazamento"]["split"])
            tx = num(x.get("taxa_pct"))
            kg = n0(x.get("carga")) * (tx / 100 if tx is not None else vz["taxa"])
        else:
            kg = n0(x.get("kg"))
        g, quioto = refrigerante(F, x["gas"], kg)
        add(1, "fugitivas", g, x.get("q", "estimado"), "refrigerante", fora=not quioto)
    for x in c.get("proc", []):
        add(1, "processos", {x.get("gas", "CO2"): n0(x.get("kg"))}, x.get("q", "estimado"), "processo")
    for x in c.get("rebanho", []):
        add(1, "agropecuaria", rebanho(F, x["tipo"], n0(x.get("cab"))), x.get("q", "estimado"), "agro")
    fe = c.get("fert") or {}
    if any(n0(fe.get(k)) for k in ("n_kg", "ureia_kg", "calcario_kg", "dolomita_kg")):
        add(1, "agropecuaria", fertilizante(F, n0(fe.get("n_kg")), n0(fe.get("ureia_kg")), n0(fe.get("calcario_kg")),
                                            n0(fe.get("dolomita_kg"))), fe.get("q", "estimado"), "agro")
    so = c.get("solo") or {}
    if so.get("ativo") and n0(so.get("ha")):
        add(1, "uso_solo", uso_solo(F, n0(so.get("ha")), so.get("bioma", "mata_atlantica")), "estimado", "solo")

    # residuos da Economia circular: tratados no lugar = escopo 1; enviados para fora = escopo 3, categoria 5
    e3 = c.get("e3") or {}
    cats = set(e3.get("cats", [1, 4, 5, 6, 7]))
    if e3.get("res_auto", True):
        for r in ctx.get("rc", []):
            dest, interno = ROTA_DESTINO.get(r.get("rota"), ("nenhum", True))
            t_ano = n0(r.get("qtd")) * RC_UN.get(r.get("un"), 1) * 12 / 1000
            g = residuo(F, r.get("tipo", ""), t_ano, dest)
            if not g:
                continue
            if interno:
                add(1, "residuos_no_lugar", g, "estimado", "residuos")
            elif 5 in cats:
                add(3, "residuos", g, "estimado", "residuos", cat=5)
    # tratamento de esgoto no lugar: escopo 1, so com o fator de metano na base (IPCC 2006, vol. 5, cap. 6)
    es = ctx.get("esgoto") or {}
    esgoto = None
    if n0(es.get("pessoas")) > 0:
        ef = F.get("efluentes") or {}
        trat = es.get("tratamento") or ""
        mcf, dbo, bo = num((ef.get("mcf") or {}).get(trat)), num(ef.get("dbo_kg_pessoa_dia")), num(ef.get("bo_kg_ch4_kg_dbo"))
        if None not in (mcf, dbo, bo):
            kg = n0(es.get("pessoas")) * dbo * 365 * bo * mcf
            add(1, "esgoto_no_lugar", {"CH4_bio": kg}, "estimado", "residuos")
            esgoto = {"marcador": False, "pessoas": n0(es.get("pessoas")), "tratamento": trat, "kg_ch4": kg}
        else:
            esgoto = {"marcador": True, "pessoas": n0(es.get("pessoas")), "tratamento": trat}
    if 5 in cats:
        for x in e3.get("residuos", []):
            add(3, "residuos", residuo(F, x.get("tipo", "rejeito"), n0(x.get("t")), x.get("destino", "aterro")),
                x.get("q", "estimado"), "residuos", cat=5)

    # escopo 2
    kwh = num(c.get("kwh"))
    if kwh is None:
        kwh = ctx.get("kwh_ano")
    rede = c.get("rede") or {}
    f_loc = fator_rede(F, rede.get("fator"), rede.get("fator_manual"))
    mensal = [num(v) for v in rede.get("mensal", [])]
    kwh_mes = ctx.get("kwh_mes")
    if (rede.get("usar_mensal") and len(mensal) == 12 and all(v is not None for v in mensal)
            and num(c.get("kwh")) is None and kwh_mes and len(kwh_mes) == 12):
        e2_loc = rede_mensal(kwh_mes, mensal)
    else:
        e2_loc = rede_localizacao(kwh or 0, f_loc)
    contratos = [(n0(k.get("mwh")), n0(k.get("fator"))) for k in rede.get("contratos", [])]
    e2_mkt = rede_mercado(kwh or 0, f_loc, n0(rede.get("irec_mwh")), contratos)
    if kwh:
        linhas.append({"escopo": 2, "fonte": "rede", "gases": {"CO2": e2_loc * 1000}, "t": e2_loc, "bio_t": 0,
                       "q": rede.get("q", "medido"), "u": math.hypot(U["dado"].get(rede.get("q", "medido"), 0.05), U["fator"]["rede"]),
                       "cat": None, "fora": False})

    # pegada do servidor (sistema digital): so com dado do hub (ctx["servidor"]), nunca com o exemplo da demonstracao
    sv_cfg = c.get("servidor") or {}
    sv = None
    if ctx.get("servidor") and sv_cfg.get("incluir", True):
        sv = servidor_inventario(ctx["servidor"], f_loc, sv_cfg.get("contagem", "auto"), cats)
        for x in sv["linhas"]:
            grupo = "servidor" if x["escopo"] == 2 else "servidor_fabricacao" if x["cat"] == 2 else "servidor_hospedagem"
            linhas.append({"escopo": x["escopo"], "fonte": grupo, "gases": {"CO2": x["t"] * 1000}, "t": x["t"], "bio_t": 0,
                           "q": x["q"], "u": math.hypot(U["dado"][x["q"]], U["fator"]["rede" if x["escopo"] == 2 else "escopo3"]),
                           "cat": x["cat"], "fora": False})
        e2_loc += sv["e2_t"]
        e2_mkt += sv["e2_t"]

    # escopo 3
    G3 = F["escopo3"]
    if 1 in cats:
        for x in e3.get("gastos", []):
            f = G3["gasto_kg_por_real"].get(x.get("cat"), {"kg": 0})["kg"]
            add(3, "compras", {"CO2": n0(x.get("valor")) * f}, "estimado", "gasto", cat=1)
        for x in e3.get("materiais", []):
            f = G3["materiais_kg_por_kg"].get(x.get("mat"), {"kg": 0})["kg"]
            add(3, "compras", {"CO2": n0(x.get("kg")) * f}, x.get("q", "estimado"), "escopo3", cat=1)
    # materiais da obra: area x carbono incorporado por m2 das composicoes escolhidas; sem o valor por m2, [MARCADOR]
    mat_falta = []
    if 1 in cats and e3.get("mat_auto", True):
        for m in (ctx.get("materiais") or {}).get("composicoes") or []:
            if not isinstance(m, dict):
                continue
            a, k = num(m.get("area_m2")), num(m.get("kgco2e_m2"))
            if not (a and a > 0):
                continue
            if k is None:
                mat_falta.append(str(m.get("nome") or m.get("id") or "Composição"))
                continue
            add(3, "materiais_obra", {"CO2": a * k}, "estimado", "escopo3", cat=1)
    if 2 in cats and n0(e3.get("capital")):
        add(3, "bens_capital", {"CO2": n0(e3.get("capital")) * G3["gasto_kg_por_real"]["manufaturados"]["kg"]},
            "estimado", "gasto", cat=2)
    for x in e3.get("transp", []):
        cat = int(n0(x.get("cat")) or 4)
        if cat in cats:
            f = G3["transporte_tkm"].get(x.get("modo"), {"kg": 0})["kg"]
            add(3, "transporte", {"CO2": n0(x.get("tkm")) * f}, x.get("q", "estimado"), "escopo3", cat=cat)
    if 6 in cats:
        for x in e3.get("viagens", []):
            f = G3["viagens_pkm"].get(x.get("modo"), {"kg": 0})["kg"]
            add(3, "viagens", {"CO2": n0(x.get("pkm")) * f}, x.get("q", "estimado"), "escopo3", cat=6)
    if 7 in cats:
        for x in e3.get("desloc", []):
            pkm = n0(x.get("pessoas")) * n0(x.get("km")) * n0(x.get("dias"))
            add(3, "deslocamento", {"CO2": pkm * fator_deslocamento(F, x.get("modo", "carro"), gw)}, "estimado", "escopo3", cat=7)
    if 12 in cats:
        for x in e3.get("fim", []):
            add(3, "fim_de_vida", residuo(F, x.get("tipo", "rejeito"), n0(x.get("t")), x.get("destino", "aterro")),
                "estimado", "residuos", cat=12)
    for x in e3.get("outras", []):
        cat = int(n0(x.get("cat")))
        if cat in cats:
            add(3, "outras", {"CO2": n0(x.get("t")) * 1000}, x.get("q", "estimado"), "escopo3", cat=cat)

    def soma(esc):
        return sum(l["t"] for l in linhas if l["escopo"] == esc and not l["fora"])

    e1, e3t = soma(1), soma(3)
    total = e1 + e2_loc + e3t
    por_gas = {"CO2": 0.0, "CH4": 0.0, "N2O": 0.0, "HFC": 0.0, "SF6": 0.0}
    for l in linhas:
        if l["fora"]:
            continue
        for g, kg in l["gases"].items():
            k = "CH4" if g.startswith("CH4") else "HFC" if g.startswith("HFC") else g
            por_gas[k] = por_gas.get(k, 0) + kg * gw.get(g, 0) / 1000

    # remocoes (a parte) e evitadas (a parte)
    rm = c.get("remo") or {}
    ha = n0(rm.get("ha")) + (n0(ctx.get("mudas_sbn")) / F["remocoes"]["mudas_por_ha"] if rm.get("usar_sbn", True) else 0)
    rem_t = remocoes(F, ha, rm.get("bioma", "mata_atlantica"), n0(rm.get("idade"))) if ha else 0.0
    # Solar, Secador e Turbinas entram sozinhos (R4, mesma regra de physis-carbono.js): o digitado vale; vazio, o do módulo
    solar = n0(c.get("solar_kwh")) if num(c.get("solar_kwh")) is not None else (n0(ctx.get("solar_kwh")) if c.get("solar_auto", True) is not False else 0.0)
    evit = {"solar": rede_localizacao(solar, f_loc), "secador": n0(ctx.get("secador_co2_kg")) / 1000,
            "turbinas": rede_localizacao(n0(ctx.get("turbinas_kwh")), f_loc)}
    # biogás no lugar do GLP (mesma regra de physis-carbono.js): o registro de Esgoto e biogás substitui a soma do plano
    rc = ctx.get("rc") or []
    bio_r = ctx.get("biogas") if isinstance(ctx.get("biogas"), dict) and num(ctx["biogas"].get("biogas_m3_dia")) is not None else None
    por_kg = premissa("residuos.biogas_por_kg") or BIOG_PAD
    if bio_r:
        biog_m3 = num(bio_r["biogas_m3_dia"]) * 365
    else:
        biog_m3 = sum(n0(r.get("qtd")) * RC_UN.get(r.get("un"), 1) * 12 * (por_kg.get(r.get("tipo")) or 0.05)
                      for r in rc if r.get("rota") == "biodigestor")
    pci_bio = premissa("biogas.pci", PCI_PAD["biogas.pci"])
    pci_glp = premissa("glp.pci", PCI_PAD["glp.pci"])
    glp_t_kg = tco2e(combustao(F, "glp", 1, "estacionaria")[0], gw)
    evit["biogas"] = biog_m3 * pci_bio / pci_glp * glp_t_kg
    # reciclagem: o que o aterro emitiria menos o que a reciclagem emite (nunca negativo), por item do plano
    recic = 0.0
    for r in rc:
        if ROTA_DESTINO.get(r.get("rota"), ("",))[0] != "reciclagem":
            continue
        t = n0(r.get("qtd")) * RC_UN.get(r.get("un"), 1) * 12 / 1000
        recic += max(0.0, tco2e(residuo(F, r.get("tipo", ""), t, "aterro"), gw) - tco2e(residuo(F, r.get("tipo", ""), t, "reciclagem"), gw))
    evit["reciclagem"] = recic
    reuso_m3 = n0((ctx.get("esgoto") or {}).get("reuso_m3_dia")) * 365
    f_agua = num((F.get("agua_fornecida") or {}).get("kg_m3"))
    evit["reuso"] = reuso_m3 * f_agua / 1000 if f_agua is not None else 0.0

    return {"linhas": linhas, "e1": e1, "e2_loc": e2_loc, "e2_mkt": e2_mkt, "e3": e3t, "total": total,
            "por_gas": por_gas, "bio_t": sum(l["bio_t"] for l in linhas),
            "fora_quioto_t": sum(l["t"] for l in linhas if l["fora"]), "remocoes_t": rem_t, "evitadas": evit,
            "evitadas_t": evit["solar"] + evit["secador"] + evit["turbinas"] + evit["biogas"] + evit["reciclagem"] + evit["reuso"], "biogas_m3": biog_m3,
            "incerteza": incerteza([(l["t"], l["u"]) for l in linhas if not l["fora"]]),
            "sbce": sbce(F, e1), "kwh": kwh, "fator_rede": f_loc, "servidor": sv, "esgoto": esgoto, "mat_falta": mat_falta,
            "reuso_m3": reuso_m3, "reuso_marcador": reuso_m3 > 0 and f_agua is None}


def fator_deslocamento(F: dict, modo: str, gw: dict) -> float:
    """kgCO2e por passageiro·km (carro e moto pelo combustivel e pelo consumo; os demais, fator fixo)."""
    d = F["escopo3"]["deslocamento"][modo]
    if "km_por_l" in d:
        g, _ = combustao(F, d["combustivel"], 1.0, "movel")
        return tco2e(g, gw) * 1000 / d["km_por_l"]
    return d["kg"]
