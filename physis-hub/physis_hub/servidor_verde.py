"""Servidor verde: dimensionamento de servidores com pouca pegada (espelho em Python de sistema/physis-servidor-verde.js).

Explicacao simples: a partir do que o sistema precisa fazer (usuarios, sensores, mapas, IA), calcula a maquina
(nucleos, memoria, placas de video), o disco e as copias, a internet, a energia (com nobreak e energia solar),
o calor que sai da sala, o carbono e os custos. Serve para qualquer projeto (Casa Physis, clientes, terceiros).

Mesmas contas da tela; os testes conferem os casos de mesa. Regras praticas marcadas "verificar": sao ordem de
grandeza para comecar a conversa, nao substituem medicao nem a ficha tecnica do equipamento escolhido.
So biblioteca padrao.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import pegada_servidor as ps

RAIZ = Path(__file__).resolve().parents[2]
CATALOGO = RAIZ / "sistema" / "physis-servidor-catalogo.json"
ESTADO = "dev"              # modulo em desenvolvimento: item interno da loja, rotulo "Em desenvolvimento"

BTU_POR_W = 3.412            # 1 W = 3,412 BTU/h
BTU_POR_TR = 12000           # 1 TR (tonelada de refrigeracao) = 12.000 BTU/h
EF_80PLUS = {"sem": 0.80, "bronze": 0.85, "prata": 0.88, "ouro": 0.90, "platina": 0.92, "titanio": 0.94}   # perto de 50% de carga; verificar
DOD = {"lifepo4": 0.90, "chumbo": 0.50}                   # profundidade de descarga usada
RAID_UTIL = {"nenhum": lambda n: 1.0, "raid1": lambda n: 0.5, "raid10": lambda n: 0.5,
             "raid5": lambda n: (n - 1) / n if n >= 3 else 0.5, "raid6": lambda n: (n - 2) / n if n >= 4 else 0.5}
H_MES = 730.0


def n(v, padrao=0.0) -> float:
    x = ps.carbono.num(v)
    return padrao if x is None else x


# ─────────────── computacao ───────────────
def vram_gb(params_b: float, bits: float, sobra: float = 1.2) -> float:
    """Memoria de video para rodar o modelo: bilhoes de parametros × bytes por parametro × 1,2 (contexto e ativacoes)."""
    return params_b * bits / 8 * sobra


def vram_treino_gb(params_b: float, bits: float, modo: str = "qlora") -> float:
    """Ajuste fino: QLoRA/LoRA ≈ 1,5 × a de rodar; ajuste completo ≈ 16 bytes por parametro (pesos, gradientes, otimizador)."""
    return params_b * 16 * 1.2 if modo == "completo" else vram_gb(params_b, bits) * 1.5


def gpus_necessarias(vram_total_gb: float, vram_por_gpu_gb: float, folga_pct: float = 0) -> int:
    if vram_total_gb <= 0:
        return 0
    if vram_por_gpu_gb <= 0:
        return 0
    return math.ceil(vram_total_gb * (1 + folga_pct / 100) / vram_por_gpu_gb - 1e-9)


def tok_s_estimado(params_b: float) -> float:
    """Tokens por segundo de uma placa de consumo com modelo quantizado: ~280 ÷ bilhoes de parametros (verificar)."""
    return 280 / params_b if params_b > 0 else 0


def computacao(p: dict) -> dict:
    us, bi, cam = n(p.get("usuarios_sim")), n(p.get("bi_usuarios")), n(p.get("geo_camadas"))
    calc_nuc = n(p.get("calc_rodadas_dia")) * n(p.get("calc_min_rodada")) / 1440 * n(p.get("calc_nucleos_rodada"), 1)
    req = n(p.get("req_min"))
    nucleos = 2 + us / 25 + bi / 5 + (1 + cam / 20 if cam else 0) + req / 600 + calc_nuc * 4 + n(p.get("docs_dia")) / 500
    ram = 2 + us * 0.05 + bi * 0.5 + (2 if cam else 0) + n(p.get("sensores")) * 0.002 + (1 if n(p.get("calc_rodadas_dia")) else 0) * 2
    ia = bool(p.get("ia_ativa"))
    params, bits = n(p.get("ia_params_b")), n(p.get("ia_bits"), 4)
    v_run = vram_gb(params, bits) * max(1, math.ceil(n(p.get("ia_usuarios_sim"), 1) / 4)) if ia else 0.0
    v_trn = vram_treino_gb(params, bits, p.get("treino_modo") or "qlora") if ia and n(p.get("treino_h_mes")) else 0.0
    v_need = max(v_run, v_trn)
    folga = n(p.get("folga_pct"), 30)
    tok_s = n(p.get("ia_tok_s")) or tok_s_estimado(params)
    h_ia_dia = (n(p.get("ia_tokens_dia")) / tok_s / 3600 if ia and tok_s else 0) + n(p.get("treino_h_mes")) / 30
    if ia:
        ram += params * bits / 8          # o modelo passa pela memoria do sistema ao carregar
    gq, gv = int(n(p.get("gpu_qtd"))), n(p.get("gpu_vram_gb"))
    aq, av = int(n(p.get("gpu_alt_qtd"))), n(p.get("gpu_alt_vram_gb"))
    r = {"nucleos": math.ceil(nucleos * (1 + folga / 100)), "ram_gb": math.ceil(ram * (1 + folga / 100)),
         "vram_rodar_gb": v_run, "vram_treino_gb": v_trn, "vram_precisa_gb": v_need * (1 + folga / 100),
         "gpus_precisa": gpus_necessarias(v_need, gv or 8, folga) if ia else 0,
         "vram_atual_gb": gq * gv, "atende_atual": (gq * gv) >= v_need * (1 + folga / 100) if ia else True,
         "vram_alt_gb": aq * av, "atende_alt": (aq * av) >= v_need * (1 + folga / 100) if ia and aq else None,
         "tok_s": tok_s, "h_ia_dia": h_ia_dia}
    r["classe"] = classe_recomendada(r["nucleos"], r["ram_gb"], ia)
    return r


def classe_recomendada(nucleos: int, ram_gb: float, ia: bool, armazenamento_tb: float = 0) -> str:
    if ia:
        return "servidor_gpu"
    if nucleos <= 4 and ram_gb <= 8 and armazenamento_tb <= 1:
        return "rpi5"
    if nucleos <= 8 and ram_gb <= 64:
        return "mini_pc"
    return "servidor_x86"


# ─────────────── armazenamento ───────────────
def banco_gb(sensores: float, leituras_min: float, bytes_leitura: float, anos: float) -> float:
    """Leituras guardadas: sensores × leituras por minuto × minutos do ano × bytes × anos de retencao."""
    return sensores * leituras_min * 525600 * bytes_leitura * anos / 1e9


def disco_bruto_gb(util_gb: float, raid: str, discos: int) -> float:
    f = RAID_UTIL.get(raid, RAID_UTIL["raid1"])(max(1, discos))
    return util_gb / f


def tempo_restauro_h(gb: float, mbps: float) -> float:
    return gb * 8000 / mbps / 3600 if mbps > 0 else float("inf")


def armazenamento(p: dict, comp: dict) -> dict:
    anos = n(p.get("retencao_anos"), 1)
    db = banco_gb(n(p.get("sensores")), n(p.get("leituras_min")), n(p.get("bytes_leitura"), 200), anos) * max(1, n(p.get("instalacoes"), 1))
    arq = n(p.get("arquivos_gb_ano")) * anos
    tiles = n(p.get("geo_tiles_gb"))
    mod = n(p.get("modelos_gb")) or (n(p.get("ia_params_b")) * n(p.get("ia_bits"), 4) / 8 * 3 if p.get("ia_ativa") else 0)   # 3 versoes
    so = 32
    util = (db + arq + tiles + mod + so) * (1 + n(p.get("folga_pct"), 30) / 100)
    snap = util * n(p.get("snapshots_pct"), 20) / 100
    bruto = disco_bruto_gb(util + snap, p.get("raid") or "raid1", int(n(p.get("discos"), 2)))
    versoes = n(p.get("backup_versoes"), 7)
    backup = (db + arq + tiles + mod) * (1 + versoes * n(p.get("mudanca_dia_pct"), 2) / 100)
    return {"banco_gb": db, "arquivos_gb": arq, "tiles_gb": tiles, "modelos_gb": mod, "util_gb": util, "snapshots_gb": snap,
            "bruto_gb": bruto, "backup_fora_gb": backup, "copias": 3, "restauro_h": tempo_restauro_h(backup, n(p.get("backup_mbps"), 50))}


# ─────────────── rede ───────────────
def rede(p: dict, arm: dict) -> dict:
    us = n(p.get("usuarios_remotos")) * n(p.get("kbps_usuario"), 500) / 1000
    sync = n(p.get("sync_mb_dia")) * 8 / 86400
    bk_dia = arm["backup_fora_gb"] * n(p.get("mudanca_dia_pct"), 2) / 100
    janela_h = n(p.get("janela_backup_h"), 6)
    bk = bk_dia * 8000 / (janela_h * 3600) if janela_h else 0
    return {"subida_mbps": (us + sync + bk) * 1.5, "descida_mbps": (us * 0.5 + sync) * 1.5 + 5, "backup_dia_gb": bk_dia,
            "latencia_ok": n(p.get("latencia_ms"), 40) <= 100}


# ─────────────── energia ───────────────
def w_componente(c: dict, ciclo_ia: float | None = None) -> tuple[float, float, float]:
    """(W medio, W de pico, W parado) de uma linha de componentes: qtd × (parado + (carga − parado) × ciclo)."""
    q = n(c.get("qtd"), 1)
    wo, wc = n(c.get("w_ocioso")), n(c.get("w_carga"))
    ciclo = ps.carbono.num(c.get("ciclo"))
    if ciclo is None:
        ciclo = ciclo_ia if (c.get("tipo") == "gpu" and ciclo_ia is not None) else 0.3
    ciclo = max(0.0, min(1.0, ciclo))
    return q * (wo + (wc - wo) * ciclo), q * wc, q * wo


def eficiencia_curva(curva: dict, fracao: float) -> float:
    """Eficiencia da fonte na fracao de carga (pontos 10, 20, 50 e 100%; reta entre eles)."""
    pts = sorted((float(k) / 100, v) for k, v in curva.items() if not str(k).startswith("_") and isinstance(v, (int, float)))
    if not pts:
        return 0.9
    if fracao <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if fracao <= x1:
            return y0 + (y1 - y0) * (fracao - x0) / (x1 - x0)
    return pts[-1][1]


def energia(p: dict, comp: dict, fonte_w: float = 0, curva: dict | None = None) -> dict:
    """Com a fonte escolhida no catalogo (fonte_w e curva 80 PLUS), a eficiencia sai da carga media dela."""
    ciclo_ia = min(1.0, comp["h_ia_dia"] / 24)
    brutas = [(c, *w_componente(c, ciclo_ia)) for c in p.get("componentes") or []]
    dc_med = sum(wm for c, wm, wp, wo in brutas if c.get("fonte", True))
    if fonte_w and curva:
        ef = eficiencia_curva(curva, dc_med / fonte_w)
    else:
        ef = EF_80PLUS.get(p.get("fonte_80plus") or "ouro", 0.90)
    med = pico = 0.0
    linhas = []
    for c, wm, wp, wo in brutas:
        k = 1 / ef if c.get("fonte", True) else 1.0           # passa pela fonte do servidor?
        linhas.append({"nome": c.get("nome", ""), "w_medio": wm * k, "w_pico": wp * k})
        med += wm * k
        pico += wp * k
    kwh_dia = med * 24 / 1000
    return {"w_medio": med, "w_pico": pico, "kwh_dia": kwh_dia, "kwh_mes": med * H_MES / 1000, "eficiencia_fonte": ef, "linhas": linhas,
            "ciclo_ia": ciclo_ia, "dc_medio": dc_med}


def nobreak(w_pico: float, w_medio: float, autonomia_min: float, bateria: str = "lifepo4", tensao_v: float = 24,
            fp: float = 0.9, folga: float = 0.25, ef_inversor: float = 0.9) -> dict:
    """VA do nobreak (pico ÷ fator de potencia, com folga) e banco de baterias para a autonomia pedida."""
    va = w_pico / fp * (1 + folga)
    wh = w_medio * autonomia_min / 60 / (DOD.get(bateria, 0.9) * ef_inversor)
    return {"va": va, "w": w_pico * (1 + folga), "bateria_wh": wh, "bateria_ah": wh / tensao_v if tensao_v else 0}


def solar(kwh_dia: float, hsp: float, pr: float = 0.75, fracao: float = 1.0, w_medio: float = 0.0, horas_noite: float = 14,
          dias_nublados: float = 0, bateria: str = "lifepo4", ef: float = 0.9) -> dict:
    """kWp = energia do dia × fracao ÷ (horas de sol pleno × PR); bateria para a noite e para os dias nublados."""
    kwp = kwh_dia * fracao / (hsp * pr) if hsp > 0 and pr > 0 else 0.0
    bat = (w_medio * horas_noite / 1000 + kwh_dia * dias_nublados) * fracao / (DOD.get(bateria, 0.9) * ef)
    return {"kwp": kwp, "bateria_kwh": bat, "ger_dia_kwh": kwp * hsp * pr}


# ─────────────── termico ───────────────
def btu_h(w: float) -> float:
    return w * BTU_POR_W


def tr(w: float) -> float:
    return btu_h(w) / BTU_POR_TR


def pue(ti_kw: float, resfriamento_kw: float, perdas_kw: float = 0, iluminacao_kw: float = 0) -> float:
    return (ti_kw + resfriamento_kw + perdas_kw + iluminacao_kw) / ti_kw if ti_kw > 0 else 0.0


def termico(p: dict, en: dict) -> dict:
    calor = en["w_medio"]
    cop = n(p.get("cop"), 3) or 3
    resf = 0.0 if p.get("free_cooling") else calor / cop
    perdas = calor * n(p.get("perdas_ups_pct"), 5) / 100
    return {"calor_w": calor, "btu_h": btu_h(en["w_pico"]), "tr": tr(en["w_pico"]), "resfriamento_w": resf,
            "pue": pue(calor, resf, perdas, n(p.get("iluminacao_w"))), "temp_min": 18, "temp_max": 27}


# ─────────────── catalogo de modulos (selecao de hardware e programas) ───────────────
CATS_POTENCIA = ("plataforma", "cpu", "ram", "gpu", "armazenamento", "raid", "rede")     # equipamentos de TI
ORDEM_CLASSE = ("servidor_gpu", "servidor_x86", "workstation", "mini_pc", "rpi5", "rpi4")


def carregar_catalogo(caminho: Path | str | None = None) -> dict:
    return json.loads(Path(caminho or CATALOGO).read_text(encoding="utf-8"))


def _itens(C: dict) -> dict:
    return {x["id"]: x for x in C.get("hardware", []) + C.get("software", [])}


def selecao_do_perfil(C: dict, perfil: str) -> dict:
    pf = (C.get("perfis") or {}).get(perfil) or {}
    return {"hardware": dict(pf.get("hardware") or {}), "software": list(pf.get("software") or []), "modelo": dict(pf.get("modelo") or {})}


def totais(sel: dict, C: dict) -> dict:
    """Somas da selecao: nucleos, memoria, video, disco, encaixes PCIe, potencia (parada e pico) e o que os programas pedem."""
    I = _itens(C)
    hw = [(I[k], int(q)) for k, q in (sel.get("hardware") or {}).items() if k in I and int(q or 0) > 0]
    sw = [I[k] for k in sel.get("software") or [] if k in I]
    soma = lambda cat, campo: sum(x.get(campo, 0) * q for x, q in hw if x["cat"] in cat)
    plats = [(x, q) for x, q in hw if x["cat"] == "plataforma"]
    gpus = [(x, q) for x, q in hw if x["cat"] == "gpu"]
    fonte = next((x for x, q in hw if x["cat"] == "fonte"), None)
    ups = next((x for x, q in hw if x["cat"] == "nobreak"), None)
    refr = [x for x, q in hw if x["cat"] == "refrigeracao"]
    dc_o = sum(x["w_ocioso"] * q for x, q in hw if x["cat"] in CATS_POTENCIA and x.get("fonte", True))
    dc_p = sum(x["w_carga"] * q for x, q in hw if x["cat"] in CATS_POTENCIA and x.get("fonte", True))
    ac_o = sum(x["w_ocioso"] * q for x, q in hw if x["cat"] in CATS_POTENCIA and not x.get("fonte", True))
    ac_p = sum(x["w_carga"] * q for x, q in hw if x["cat"] in CATS_POTENCIA and not x.get("fonte", True))
    motores = [x for x in sw if x.get("motor_ia")]
    m = sel.get("modelo") or {}
    vram_modelo = vram_gb(n(m.get("params_b")), n(m.get("bits"), 4)) if motores and n(m.get("params_b")) else 0.0
    return {"nucleos": soma(("plataforma", "cpu"), "nucleos"), "threads": soma(("plataforma", "cpu"), "threads"),
            "ram_gb": soma(("plataforma",), "ram_gb") + soma(("ram",), "gb"), "ram_max_gb": soma(("plataforma",), "ram_max_gb"),
            "ram_modulos_gb": soma(("ram",), "gb"),
            "vram_gb": soma(("gpu",), "vram_gb"), "gpus": sum(q for x, q in gpus), "disco_tb": soma(("armazenamento",), "tb"),
            "pcie_x16": soma(("plataforma",), "pcie_x16"), "pcie_slots": soma(("plataforma",), "pcie_slots"),
            "pcie_usado": soma(("gpu", "raid"), "pcie"),
            "x86": any(x.get("arch") == "x86_64" for x, q in plats), "arm": any(x.get("arch") == "arm64" for x, q in plats),
            "plataformas": len(plats), "w_ocioso_dc": dc_o, "w_pico_dc": dc_p, "w_ocioso_ac": ac_o, "w_pico_ac": ac_p,
            "fonte_w": fonte["w"] if fonte else 0, "fonte_classe": fonte["classe80"] if fonte else None,
            "ups_va": ups["va"] if ups else 0, "ups_w": ups["w"] if ups else 0, "ups_wh": ups["bateria_wh"] if ups else 0,
            "ups_quimica": ups["quimica"] if ups else None, "ups_proprio_w": ups["w_ocioso"] if ups else 0,
            "refrig_cop": max([x.get("cop", 0) for x in refr] or [0]), "free_cooling": any(x["id"] == "vent_forcada" for x in refr),
            "sw_nucleos": sum(x.get("nucleos", 0) for x in sw), "sw_ram_gb": sum(x.get("ram_gb", 0) for x in sw) + soma(("raid",), "ram_gb"),
            "sw_disco_gb": sum(x.get("disco_gb", 0) for x in sw), "motores_ia": [x["id"] for x in motores], "vram_modelo_gb": vram_modelo,
            "kg_fabricacao_plataformas": None}


def componentes_da_selecao(sel: dict, C: dict) -> list:
    I = _itens(C)
    out = []
    for k, q in (sel.get("hardware") or {}).items():
        x = I.get(k)
        if not x or x["cat"] not in CATS_POTENCIA or not int(q or 0):
            continue
        tipo = {"gpu": "gpu", "armazenamento": "disco", "rede": "rede"}.get(x["cat"], "cpu")
        out.append({"nome": x["nome"], "tipo": tipo, "qtd": int(q), "w_ocioso": x["w_ocioso"], "w_carga": x["w_carga"],
                    "ciclo": "" if tipo == "gpu" else (0.5 if tipo == "rede" else 0.3), "fonte": x.get("fonte", True), "id": k})
    return out


def compat(sel: dict, C: dict, arm_bruto_gb: float | None = None, ef: float = 0.9) -> list:
    """Conferencias da selecao: cada uma {id, ok, nivel ('erro' ou 'aviso'), msg}."""
    I = _itens(C)
    T = totais(sel, C)
    hw = {k: int(q) for k, q in (sel.get("hardware") or {}).items() if k in I and int(q or 0) > 0}
    sw = [k for k in sel.get("software") or [] if k in I]
    plats = [I[k] for k in hw if I[k]["cat"] == "plataforma"]
    r = []

    def ck(ident, ok, nivel, msg):
        r.append({"id": ident, "ok": bool(ok), "nivel": nivel, "msg": msg})

    ck("plataforma", bool(plats), "erro", "Escolha ao menos uma plataforma (a máquina).")
    ck("so", any(I[k]["cat"] == "so" for k in sw), "aviso", "Escolha o sistema operacional.")
    precisa_cpu = [x for x in plats if x.get("encaixe") in ("desktop", "servidor")]
    cpus = [I[k] for k in hw if I[k]["cat"] == "cpu"]
    for x in precisa_cpu:
        ck("cpu_" + x["id"], any(c["encaixe"] == x["encaixe"] for c in cpus), "erro", f"{x['nome']}: falta o processador do encaixe '{x['encaixe']}'.")
    for c in cpus:
        ck("encaixe_" + c["id"], any(x.get("encaixe") == c["encaixe"] for x in plats), "erro", f"{c['nome']} não encaixa em nenhuma plataforma escolhida.")
    for k in hw:
        x = I[k]
        if x["cat"] == "ram":
            ck("ram_fmt_" + k, any(p.get("ram_formato") == x["formato"] for p in plats), "erro", f"{x['nome']}: nenhuma plataforma usa esse formato de memória.")
            if any(p.get("ram_ecc") for p in plats) and not x.get("ecc"):
                ck("ecc_" + k, False, "aviso", f"{x['nome']}: servidor pede memória ECC.")
    if T["ram_max_gb"]:
        ck("ram_max", T["ram_modulos_gb"] <= T["ram_max_gb"], "erro", f"Memória ({T['ram_modulos_gb']:g} GB) acima do máximo das plataformas ({T['ram_max_gb']:g} GB).")
    if T["gpus"]:
        ck("gpu_encaixe", T["pcie_x16"] > 0, "erro", "Placa de vídeo pede encaixe PCIe x16: Raspberry Pi e mini PC não recebem placa.")
        if T["pcie_x16"]:
            ck("pcie_x16", T["gpus"] <= T["pcie_x16"], "erro", f"{T['gpus']} placas de vídeo para {T['pcie_x16']} encaixes x16.")
    ck("pcie", T["pcie_usado"] <= T["pcie_slots"] or not T["pcie_usado"], "erro", f"Placas PCIe ({T['pcie_usado']}) acima dos encaixes ({T['pcie_slots']}).")
    for k in sw:
        x = I[k]
        rq = x.get("requer") or {}
        if rq.get("x86"):
            ck("x86_" + k, T["x86"], "erro", f"{x['nome']} precisa de processador x86 (não roda no Raspberry Pi).")
        if rq.get("arm"):
            ck("arm_" + k, T["arm"], "erro", f"{x['nome']} é só para Raspberry Pi.")
        if rq.get("gpu"):
            ck("gpu_" + k, T["gpus"] > 0, "erro", f"{x['nome']} precisa de placa de vídeo.")
        for d in x.get("deps") or []:
            ck(f"dep_{k}_{d}", d in sw, "erro", f"{x['nome']} precisa de {I[d]['nome'] if d in I else d}.")
    ram_ia = T["vram_modelo_gb"] if (T["vram_modelo_gb"] and T["vram_gb"] < T["vram_modelo_gb"]) else 0
    ck("ram", T["ram_gb"] >= T["sw_ram_gb"] + ram_ia, "erro",
       f"Memória {T['ram_gb']:g} GB para {T['sw_ram_gb'] + ram_ia:.1f} GB pedidos pelos programas" + (" e pelo modelo (sem placa suficiente)" if ram_ia else "") + ".")
    ck("nucleos", T["threads"] >= T["sw_nucleos"], "aviso", f"{T['threads']:g} threads para {T['sw_nucleos']:.1f} núcleos pedidos pelos programas.")
    if T["vram_modelo_gb"]:
        obrig = any((I[k].get("gpu") == "obrigatoria") for k in T["motores_ia"])
        ck("vram", T["vram_gb"] >= T["vram_modelo_gb"], "erro" if obrig else "aviso",
           f"Modelo pede {T['vram_modelo_gb']:.1f} GB de vídeo; a seleção tem {T['vram_gb']:g} GB" + ("" if obrig else " (sem isso, roda na memória, bem mais devagar)") + ".")
    if T["w_pico_dc"]:
        if T["fonte_w"]:
            ck("fonte", T["fonte_w"] >= T["w_pico_dc"] * 1.3, "erro", f"Fonte de {T['fonte_w']:g} W para pico de {T['w_pico_dc']:.0f} W (pede 30% de folga: {T['w_pico_dc'] * 1.3:.0f} W).")
        elif any(x.get("fonte", True) for x in plats):
            ck("fonte", False, "aviso", "Escolha a fonte do servidor.")
    pico_ac = T["w_pico_dc"] / ef + T["w_pico_ac"]
    if T["ups_w"]:
        ck("nobreak", T["ups_w"] >= pico_ac, "erro", f"Nobreak de {T['ups_w']:g} W para pico de {pico_ac:.0f} W.")
    if arm_bruto_gb is not None:
        ck("disco", T["disco_tb"] * 1000 >= arm_bruto_gb + T["sw_disco_gb"], "erro",
           f"Discos com {T['disco_tb']:g} TB para {(arm_bruto_gb + T['sw_disco_gb']) / 1000:.2f} TB pedidos (dados, cópias locais e programas).")
    return r


def kg_fabricacao_selecao(sel: dict, C: dict, S: dict) -> tuple[float, float]:
    """(kgCO2e, tCO2e por ano) da fabricacao: classe de cada plataforma + placas de video."""
    I = _itens(C)
    kg = t = 0.0
    for k, q in (sel.get("hardware") or {}).items():
        x = I.get(k)
        if not x or not int(q or 0):
            continue
        if x["cat"] == "plataforma":
            cl = S["classes"].get(x.get("classe"), S["classes"]["mini_pc"])
            kg += cl["kgco2e_fabricacao"] * int(q)
            t += cl["kgco2e_fabricacao"] * int(q) / 1000 / cl["vida_anos"]
        elif x["cat"] == "gpu":
            g = S["gpu_placa"]
            kg += g["kgco2e_fabricacao"] * int(q)
            t += g["kgco2e_fabricacao"] * int(q) / 1000 / g.get("vida_anos", 4)
    return kg, t


# ─────────────── tudo ───────────────
def dimensionar(p: dict, fator_rede: float = ps.FATOR_REDE_RESERVA, hsp: float | None = None, S: dict | None = None,
                sel: dict | None = None, C: dict | None = None) -> dict:
    """Resultado completo de um projeto. fator_rede (tCO2/MWh) e hsp (kWh/m²·dia) vem do lugar do projeto.
    Com a selecao de modulos (sel + catalogo C), as pecas escolhidas alimentam energia, nobreak, termico e carbono."""
    S = S or ps.PADRAO
    usa_sel = bool(sel and C and (sel.get("hardware") or {}) and p.get("usar_selecao", True))
    T = totais(sel, C) if usa_sel else None
    if usa_sel:
        p = dict(p, componentes=componentes_da_selecao(sel, C))
        if T["ups_wh"]:
            p["ups_bateria"] = T["ups_quimica"] or p.get("ups_bateria")
        if T["refrig_cop"]:
            p["cop"] = T["refrig_cop"]
        if T["free_cooling"] and not T["refrig_cop"]:
            p["free_cooling"] = True
    comp = computacao(p)
    if usa_sel:
        comp["ram_software_gb"] = T["sw_ram_gb"]
        comp["ram_gb"] = max(comp["ram_gb"], math.ceil(T["sw_ram_gb"] * (1 + n(p.get("folga_pct"), 30) / 100)))
    arm = armazenamento(p, comp)
    arm_tb = arm["bruto_gb"] / 1000
    comp["classe"] = classe_recomendada(comp["nucleos"], comp["ram_gb"], bool(p.get("ia_ativa")), arm_tb)
    net = rede(p, arm)
    curvas = (C or {}).get("eficiencia_80plus") or {}
    en = energia(p, comp, T["fonte_w"] if T else 0, curvas.get(T["fonte_classe"]) if T and T["fonte_classe"] else None)
    ter = termico(p, en)
    ups = nobreak(en["w_pico"], en["w_medio"], n(p.get("ups_autonomia_min"), 30), p.get("ups_bateria") or "lifepo4", n(p.get("ups_tensao"), 24))
    if T and T["ups_wh"]:
        ups["autonomia_min_selecao"] = T["ups_wh"] * DOD.get(T["ups_quimica"] or "chumbo", 0.5) * 0.9 / en["w_medio"] * 60 if en["w_medio"] else 0
    h = n(p.get("hsp")) or (hsp or 0)
    modo = p.get("solar_modo") or "dedicado"
    fr = 0.0 if modo == "nenhum" else n(p.get("solar_fracao"), 100) / 100
    sol = solar(en["kwh_dia"], h, n(p.get("pr"), 0.75), fr, en["w_medio"], n(p.get("horas_noite"), 14), n(p.get("dias_nublados"), 0),
                p.get("ups_bateria") or "lifepo4")
    f = n(p.get("fator_rede")) or fator_rede
    kwh_ano_inst = en["kwh_dia"] * 365 * ter["pue"]
    rede_kwh = kwh_ano_inst * (1 - fr if h > 0 else 1)
    cl = S["classes"].get(comp["classe"], S["classes"]["mini_pc"])
    kg_fab = cl["kgco2e_fabricacao"] + (max(comp["gpus_precisa"], int(n(p.get("gpu_qtd")))) * S["gpu_placa"]["kgco2e_fabricacao"] if p.get("ia_ativa") else 0)
    t_fab = kg_fab / 1000 / cl["vida_anos"]
    if usa_sel:
        kg_fab, t_fab = kg_fabricacao_selecao(sel, C, S)
    f_dc, pue_dc = n(p.get("fator_dc"), f), n(p.get("pue_dc"), 1.5)
    tarifa = n(p.get("tarifa"))
    custo_mes = rede_kwh / 12 * tarifa if tarifa else None
    capex_sol = (sol["kwp"] * n(p.get("custo_kwp")) + sol["bateria_kwh"] * n(p.get("custo_bat_kwh"))) if n(p.get("custo_kwp")) else None
    econ_ano = (kwh_ano_inst - rede_kwh) * tarifa if tarifa else None
    carb = {"fator": f, "kwh_ano": kwh_ano_inst, "kwh_rede_ano": rede_kwh, "t_operacao": rede_kwh / 1000 * f, "t_sem_solar": kwh_ano_inst / 1000 * f,
            "kg_fabricacao": kg_fab, "t_fabricacao_ano": t_fab, "t_datacenter": en["kwh_dia"] * 365 * pue_dc / 1000 * f_dc,
            "custo_mes": custo_mes, "capex_solar": capex_sol, "economia_ano": econ_ano,
            "payback_anos": capex_sol / econ_ano if capex_sol and econ_ano else None}
    r = {"computacao": comp, "armazenamento": arm, "rede": net, "energia": en, "nobreak": ups, "solar": sol, "termico": ter, "carbono": carb}
    if usa_sel:
        r["selecao"] = {"totais": T, "compat": compat(sel, C, arm["bruto_gb"], en["eficiencia_fonte"])}
    return r
