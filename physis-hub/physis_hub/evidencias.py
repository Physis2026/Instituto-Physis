"""Certificação assistida: motor de evidências automáticas (espelho de sistema/physis-evidencias.js).

Para cada critério da base de certificações (sistema/physis-certificacoes.json), o mapa
sistema/physis-evidencias.json diz de onde tirar evidência que o sistema JÁ tem: contas de água e luz do Início,
medidores do hub, cisterna, energia solar, Economia circular, inventário de carbono, plano de SbN, preferências de
acessibilidade, sensores e calibrações, documentos guardados na Gestão e evidências anexadas à mão.
Cada regra devolve {status: atendido | parcial | sem_evidencia, valor, fonte, data, tela}.

Regra 4 do CLAUDE.md (conta espelho): as funções de fonte (FONTES) existem iguais no JavaScript; mudou lá, muda
aqui, e o test_evidencias.py confere os dois lados com os mesmos casos.

Lado do servidor:
- dados_servidor(hub): o que só o hub sabe (dias medidos de água, energia e nível; sensores vistos; modelos de
  consumo treinados; nomes e datas dos arquivos da Gestão; evidências anexadas). Nunca devolve o conteúdo dos
  arquivos, nem dado pessoal além do nome do responsável que a própria equipe escreveu no anexo.
- anexar / anexos / remover: metadados de evidência manual (tabela evidencia_anexo).
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MAPA_ARQ = RAIZ / "sistema" / "physis-evidencias.json"
CERT_ARQ = RAIZ / "sistema" / "physis-certificacoes.json"
ORDEM = {"sem_evidencia": 0, "parcial": 1, "atendido": 2}
GRANDEZAS = {"agua": "vazao", "energia": "energia", "nivel": "nivel"}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS evidencia_anexo (
  id INTEGER PRIMARY KEY AUTOINCREMENT, cert TEXT NOT NULL, criterio TEXT NOT NULL, nome TEXT NOT NULL,
  data TEXT NOT NULL, validade TEXT NOT NULL DEFAULT '', responsavel TEXT NOT NULL DEFAULT '', arquivo TEXT NOT NULL DEFAULT '',
  obs TEXT NOT NULL DEFAULT '', criado REAL NOT NULL, por TEXT NOT NULL);
"""

_cache: dict = {}


def carregar_mapa(arq: Path = MAPA_ARQ) -> dict:
    if str(arq) not in _cache:
        _cache[str(arq)] = json.loads(Path(arq).read_text(encoding="utf-8"))
    return _cache[str(arq)]


def carregar_certs(arq: Path = CERT_ARQ) -> list[dict]:
    if str(arq) not in _cache:
        _cache[str(arq)] = json.loads(Path(arq).read_text(encoding="utf-8"))["certificacoes"]
    return _cache[str(arq)]


# ══ Utilidades (iguais no JS) ════════════════════════════════════════════════════════════════════
def num(v):
    """Número digitado na plataforma: aceita 1.234,5 (pt-BR) e 1234.5. Vazio ou inválido = None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v else None
    s = str(v).strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    if not _NUMERO.match(s):
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return x if x == x and abs(x) != float("inf") else None


_NUMERO = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def fmt_g(x: float) -> str:
    """Como String(Number(x)) no JS: 10 -> "10", 12.5 -> "12.5"."""
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def fix(x: float, casas: int) -> str:
    """Como fix() no JS: arredonda meio para cima (toFixed/round do Python arredondam diferente)."""
    return f"{math.floor(x * 10 ** casas + 0.5) / 10 ** casas:.{casas}f}"


def norm(s) -> str:
    """Sem acento, minúsculo, só letras e números separados por um espaço."""
    t = "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def palavras_da_evidencia(texto) -> list[str]:
    """Trechos do campo 'evidencia' do critério que valem como nome de documento (≥ 8 letras, sem códigos)."""
    t = re.sub(r"\b[A-Z]{2,4}-[A-Z]{2,4}-\d+\b", " ", str(texto or ""))
    out = []
    for parte in re.split(r"[;,/+()]| e | ou ", t):
        n = norm(parte)
        if len(n) >= 8 and n not in out:
            out.append(n)
    return out


def _r(status, valor, data=None) -> dict:
    return {"status": status, "valor": valor, "data": data or None}


def _pct(x) -> int:
    return math.floor(x * 100 + 0.5)


def _meses(d, campo):
    h = [x for x in ((d.get("perfil") or {}).get("historico") or []) if isinstance(x, dict) and num(x.get(campo)) is not None]
    return sorted(h, key=lambda x: str(x.get("mes") or ""))


# ══ Fontes (uma função por fonte; espelho de FONTES no JS) ═══════════════════════════════════════
def f_agua_contas(d, p, crit):
    h = _meses(d, "m3")
    if not h:
        return None
    n = len(h)
    return _r("atendido" if n >= (p.get("min_meses") or 12) else "parcial", f"{n} meses de consumo de água nas contas", h[-1].get("mes"))


def f_energia_hist(d, p, crit):
    h = _meses(d, "kwh")
    if not h:
        return None
    n = len(h)
    return _r("atendido" if n >= (p.get("min_meses") or 12) else "parcial", f"{n} meses de consumo de energia nas contas", h[-1].get("mes"))


def f_medidor(d, p, crit):
    g = p.get("grandeza") or "agua"
    m = (((d.get("servidor") or {}).get("medidores") or {}).get(g)) or {}
    dias = int(num(m.get("dias")) or 0)
    if not dias:
        return None
    nome = {"agua": "água", "energia": "energia", "nivel": "nível"}.get(g, g)
    return _r("atendido" if dias >= (p.get("min_dias") or 30) else "parcial", f"{dias} dias de {nome} medidos pelo hub", m.get("ultimo"))


def f_agua_cisterna(d, p, crit):
    m = (((d.get("servidor") or {}).get("medidores") or {}).get("nivel")) or {}
    dias = int(num(m.get("dias")) or 0)
    vol = num(((d.get("calc") or {}).get("agua") or {}).get("cisterna_m3"))
    if dias >= (p.get("min_dias") or 30):
        return _r("atendido", f"Cisterna em operação: {dias} dias de nível medido pelo hub", m.get("ultimo"))
    if vol and vol > 0:
        return _r("parcial", f"Cisterna dimensionada: {fmt_g(vol)} m³ (falta medição de operação)".replace(".", ","))
    if dias:
        return _r("parcial", f"{dias} dias de nível medido pelo hub", m.get("ultimo"))
    return None


def f_solar(d, p, crit):
    c, s = d.get("carbono") or {}, ((d.get("calc") or {}).get("solar") or {})
    g, cons = num(c.get("solar_kwh")), num(c.get("kwh"))
    if g and g > 0:
        cob = g / (g + cons) if cons is not None and g + cons > 0 else None
        minimo = p.get("min_cobertura")
        st = ("atendido" if cob >= minimo else "parcial") if minimo is not None and cob is not None else "atendido"
        return _r(st, f"Geração solar de {fix(g, 0)} kWh/ano" + (f" ({_pct(cob)}% do consumo)" if cob is not None else ""))
    if (num(s.get("kwp")) or 0) > 0 or (num(s.get("consumo")) or 0) > 0:
        return _r("parcial", "Sistema solar dimensionado na aba Energia solar (falta a geração medida)")
    return None


def f_enpi(d, p, crit):
    mods = [m for m in ((d.get("servidor") or {}).get("modelos_consumo") or []) if "energia" in str(m.get("nome") or "")]
    if mods:
        m = max(mods, key=lambda x: num(x.get("n_amostras")) or 0)
        return _r("atendido", f"Linha de base de energia ajustada por clima e produção (modelo do hub, {int(num(m.get('n_amostras')) or 0)} dias)",
                  m.get("treinado_em"))
    h = _meses(d, "kwh")
    if len(h) < 12:
        return None
    area = num((((d.get("perfil") or {}).get("c")) or {}).get("area_construida"))
    soma = sum(num(x["kwh"]) for x in h[-12:])
    if area and area > 0:
        return _r("parcial", f"Indicador: {fix(soma / area, 1)} kWh/m² por ano (12 meses de contas)".replace(".", ","), h[-1].get("mes"))
    return _r("parcial", "12 meses de contas de luz; falta a área construída para normalizar o indicador", h[-1].get("mes"))


def f_residuos_desvio(d, p, crit):
    r = d.get("residuos") or {}
    pct = num(r.get("pct"))
    if pct is None:
        return _r("parcial", f"{int(num(r.get('n')) or 0)} resíduos no plano; falta a quantidade para o desvio") if num(r.get("n")) else None
    meta = p.get("meta") if p.get("meta") is not None else 0.5
    return _r("atendido" if pct >= meta else "parcial", f"{_pct(pct)}% desviado do aterro (meta {_pct(meta)}%)", r.get("data"))


def f_residuos_plano(d, p, crit):
    r = d.get("residuos") or {}
    n, com = int(num(r.get("n")) or 0), int(num(r.get("com_rota")) or 0)
    if not n:
        return None
    return _r("atendido" if com >= n else "parcial", f"{com} de {n} resíduos com rota definida", r.get("data"))


def f_carbono_inventario(d, p, crit):
    c = d.get("carbono") or {}
    e2 = num(c.get("kwh")) is not None
    e1 = any(num(c.get(k)) is not None for k in ("diesel", "glp", "gn"))
    if not (e1 or e2):
        return None
    return _r("atendido" if e1 and e2 else "parcial", "Inventário com escopos 1 e 2" if e1 and e2 else
              ("Inventário só com escopo 2 (eletricidade)" if e2 else "Inventário só com escopo 1 (combustíveis)"))


def f_sbn_plano(d, p, crit):
    pl = [x for x in ((d.get("sbn") or {}).get("plano") or []) if isinstance(x, dict)]
    if not pl:
        return None
    return _r("atendido" if len(pl) >= (p.get("min_especies") or 1) else "parcial", f"{len(pl)} espécies no plano de plantio")


def f_acessibilidade(d, p, crit):
    if not isinstance(d.get("pref"), dict):
        return None
    return _r("parcial", "Plataforma com recursos de acessibilidade digital (LBI 13.146/2015, art. 63); "
                         "a acessibilidade do espaço (NBR 9050) pede evidência própria")


def f_calibracao(d, p, crit):
    cal = [c for c in (d.get("calibracoes") or []) if isinstance(c, dict) and c.get("data")]
    sens = (d.get("servidor") or {}).get("sensores") or []
    if not cal and not sens:
        return None
    if not cal:
        return _r("parcial", f"{len(sens)} sensores no hub, sem registro de calibração")
    hoje = d.get("hoje") or ""
    ultimo: dict = {}
    for c in cal:
        k = str(c.get("ponto") or "?")
        if k not in ultimo or str(c["data"]) > str(ultimo[k]["data"]):
            ultimo[k] = c
    vencidas = [k for k, c in ultimo.items() if c.get("validade") and str(c["validade"]) < hoje]
    sem_val = [k for k, c in ultimo.items() if not c.get("validade")]
    data = max(str(c["data"]) for c in ultimo.values())
    txt = f"{len(ultimo)} pontos com calibração registrada"
    if vencidas:
        return _r("parcial", txt + f"; {len(vencidas)} vencida(s)", data)
    if sem_val:
        return _r("parcial", txt + "; validade não informada em " + str(len(sem_val)), data)
    return _r("atendido", txt + ", todas na validade", data)


def f_documentos(d, p, crit):
    pal = [norm(x) for x in (p.get("palavras") or []) if norm(x)]
    if p.get("da_evidencia"):
        pal += palavras_da_evidencia((crit or {}).get("evidencia"))
    if not pal:
        return None
    arqs = list(((d.get("servidor") or {}).get("arquivos")) or []) + list(d.get("arquivos") or [])
    for a in sorted(arqs, key=lambda x: str(x.get("data") or ""), reverse=True):
        n = norm(a.get("nome"))
        if any(w in n for w in pal):
            return _r("atendido", "Documento: " + str(a.get("nome"))[:120], a.get("data"))
    return None


def f_perfil(d, p, crit):
    pf = d.get("perfil") or {}
    return _r("parcial", "Início preenchido (perfil e lugar)") if pf.get("tipo") and pf.get("nivel") else None


def f_riscos(d, p, crit):
    ri = (d.get("calc") or {}).get("riscos") or {}
    return _r("parcial", "Matriz de riscos preenchida na Resiliência climática") if any((num(v) or 0) > 0 for v in ri.values()) else None


def f_risco_municipal(d, p, crit):
    r = (d.get("municipio") or (d.get("servidor") or {}).get("municipio") or {}).get("risco_lugar")
    if r not in ("baixo", "medio", "alto", "muito_alto"):
        return None
    nome = {"baixo": "baixo (R1)", "medio": "médio (R2)", "alto": "alto (R3)", "muito_alto": "muito alto (R4)"}[r]
    st = {"baixo": "atendido", "medio": "parcial"}.get(r, "sem_evidencia")
    return _r(st, f"Bairro do lugar com risco {nome} no painel municipal" + ("" if r == "baixo" else ": pede laudo e consulta à Defesa Civil"))


def f_custos(d, p, crit):
    inv = [c for c in ((d.get("gestao") or {}).get("compras") or []) if isinstance(c, dict) and c.get("cat") == "Investimento"]
    if inv:
        return _r("parcial", f"{len(inv)} investimento(s) com retorno em Gestão → Compras e investimentos")
    if num(((d.get("calc") or {}).get("solar") or {}).get("custo_kwp")):
        return _r("parcial", "Custo e retorno do sistema solar calculados")
    return None


def f_agua_reuso(d, p, crit):
    e = d.get("esgoto") or {}
    r = num(e.get("reuso_m3_dia"))
    if not (r and r > 0):
        return None
    f = str(e.get("fonte") or "")
    return _r("parcial", "Reúso de efluente tratado planejado: " + fix(r, 2).replace(".", ",", 1) + " m³/dia" + (f" ({f})" if f else ""), e.get("atualizado"))


def f_biogas(d, p, crit):
    b = d.get("biogas") or {}
    g = num(b.get("biogas_m3_dia"))
    if not (g and g > 0):
        return None
    v, f = num(b.get("biodigestor_m3")), str(b.get("fonte") or "")
    return _r("parcial", "Biodigestor dimensionado: " + fix(g, 2).replace(".", ",", 1) + " m³/dia de biogás"
              + (", " + fix(v, 1).replace(".", ",", 1) + " m³" if v else "") + (f" ({f})" if f else ""), b.get("atualizado"))


def f_materiais(d, p, crit):
    m = d.get("materiais") or {}
    comps = [c for c in (m.get("composicoes") or []) if isinstance(c, dict)]
    if not comps:
        return None
    if p.get("modo") == "envoltoria":
        av = [c for c in comps if c.get("nbr15575") in ("atende", "parcial", "nao")]
        if not av:
            return None
        ok = sum(1 for c in av if c.get("nbr15575") == "atende")
        return _r("atendido" if ok == len(av) else "parcial", f"{ok} de {len(av)} composições atendem à NBR 15575 (procedimento simplificado"
                  + (f", zona {m.get('zona')}" if m.get("zona") else "") + ")", m.get("atualizado"))
    com = [c for c in comps if num(c.get("kgco2e_m2")) is not None and (num(c.get("area_m2")) or 0) > 0]
    if not com:
        return _r("parcial", f"{len(comps)} composições escolhidas, sem carbono incorporado por m²", m.get("atualizado"))
    t = sum(num(c.get("area_m2")) * num(c.get("kgco2e_m2")) for c in com) / 1000
    return _r("parcial", "Carbono incorporado das composições: " + fix(t, 1).replace(".", ",", 1) + f" tCO₂e ({len(com)} de {len(comps)} com valor por m²)", m.get("atualizado"))


FONTES = {"agua_contas": f_agua_contas, "energia_hist": f_energia_hist, "medidor": f_medidor, "agua_cisterna": f_agua_cisterna,
          "solar": f_solar, "enpi": f_enpi, "residuos_desvio": f_residuos_desvio, "residuos_plano": f_residuos_plano,
          "carbono_inventario": f_carbono_inventario, "sbn_plano": f_sbn_plano, "acessibilidade": f_acessibilidade,
          "calibracao": f_calibracao, "documentos": f_documentos, "perfil": f_perfil, "riscos": f_riscos,
          "risco_municipal": f_risco_municipal, "custos": f_custos, "agua_reuso": f_agua_reuso, "biogas": f_biogas,
          "materiais": f_materiais}


# ══ Motor ════════════════════════════════════════════════════════════════════════════════════════
def regras_do_criterio(crit: dict, mapa: dict) -> list[dict]:
    regras = list((mapa.get("por_criterio") or {}).get(crit["id"]) or [])
    if not regras and crit.get("auto"):
        regras = list((mapa.get("por_auto") or {}).get(crit["auto"]) or [])
    return regras + list(mapa.get("regra_geral") or [])


def _anexos(d: dict, crit_id: str) -> list[dict]:
    lst = list(((d.get("servidor") or {}).get("anexos")) or []) + list(d.get("anexos") or [])
    hoje, out = d.get("hoje") or "", []
    for a in lst:
        if not isinstance(a, dict) or a.get("criterio") != crit_id:
            continue
        vencido = bool(a.get("validade")) and str(a["validade"]) < hoje
        out.append({"status": "parcial" if vencido else "atendido", "fonte": "anexo", "tela": "certificacoes",
                    "valor": str(a.get("nome") or "Evidência")[:160] + (" (vencida em " + str(a["validade"]) + ")" if vencido else "")
                             + (" · " + str(a["responsavel"])[:80] if a.get("responsavel") else ""),
                    "data": a.get("data")})
    return out


def avaliar_criterio(crit: dict, dados: dict, mapa: dict | None = None) -> dict:
    mapa = mapa or carregar_mapa()
    fontes = mapa.get("fontes") or {}
    evid = []
    for regra in regras_do_criterio(crit, mapa):
        fn = FONTES.get(regra.get("fonte"))
        if not fn:
            continue
        r = fn(dados, regra, crit)
        if not r:
            continue
        teto = regra.get("teto")
        if teto in ORDEM and ORDEM[r["status"]] > ORDEM[teto]:
            r = dict(r, status=teto)
        evid.append(dict(r, fonte=regra["fonte"], tela=(fontes.get(regra["fonte"]) or {}).get("tela")))
    evid += _anexos(dados, crit["id"])
    # sem duplicar a mesma evidência (duas regras da mesma fonte com o mesmo texto)
    vistos, unicos = set(), []
    for e in evid:
        k = (e["fonte"], e["valor"])
        if k not in vistos:
            vistos.add(k)
            unicos.append(e)
    unicos.sort(key=lambda e: -ORDEM[e["status"]])
    status = unicos[0]["status"] if unicos else "sem_evidencia"
    return {"criterio": crit["id"], "status": status, "evidencias": unicos,
            "sugestao": {"atendido": "atende", "parcial": "parcial"}.get(status)}


def evidencias_para(cert_id: str, dados: dict, certs: list[dict] | None = None, mapa: dict | None = None) -> dict:
    certs = certs if certs is not None else carregar_certs()
    cert = next((c for c in certs if c["id"] == cert_id), None)
    if not cert:
        return {"ok": False, "erro": "certificação desconhecida"}
    res, resumo = {}, {"atendido": 0, "parcial": 0, "sem_evidencia": 0, "total": 0}
    for g in cert["grupos"]:
        for k in g["criterios"]:
            r = avaliar_criterio(k, dados, mapa)
            res[k["id"]] = r
            resumo[r["status"]] += 1
            resumo["total"] += 1
    return {"ok": True, "cert": cert_id, "criterios": res, "resumo": resumo}


# ══ Servidor: o que só o hub sabe ════════════════════════════════════════════════════════════════
def _dia(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else None


def preparar(hub) -> None:
    with hub._trava:
        hub._db.executescript(ESQUEMA)
        hub._db.commit()


def dentro(lon: float, lat: float, anel: list) -> bool:
    """Ponto dentro do polígono (raio cruzando as arestas)."""
    d, j = False, len(anel) - 1
    for i in range(len(anel)):
        xi, yi, xj, yj = anel[i][0], anel[i][1], anel[j][0], anel[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            d = not d
        j = i
    return d


def risco_do_lugar(db) -> dict | None:
    """Classe de risco do bairro (painel municipal) que contém o lugar do hub (clima_local). Só polígonos."""
    try:
        loc = db.execute("SELECT dados FROM clima_local WHERE id=1").fetchone()
        linhas = db.execute("SELECT nome, risco, geometria FROM mun_bairro").fetchall()
    except Exception:          # noqa: BLE001 — módulos ainda não criados neste banco
        return None
    if not loc:
        return None
    lugar = json.loads(loc[0])
    for nome, risco, g in linhas:
        geo = json.loads(g)
        if geo.get("tipo") == "poligono" and any(dentro(lugar["lon"], lugar["lat"], anel) for anel in geo["coords"]):
            return {"risco_lugar": risco, "bairro": nome}
    return None


def dados_servidor(hub, incluir_arquivos: bool = True) -> dict:
    """Resumo para o motor (sem conteúdo de arquivo, sem leitura bruta)."""
    preparar(hub)
    db, out = hub._db, {"medidores": {}, "sensores": [], "modelos_consumo": [], "arquivos": [], "anexos": anexos(hub)}
    with hub._trava:
        for chave, g in GRANDEZAS.items():
            r = db.execute("SELECT COUNT(DISTINCT CAST(ts / 86400 AS INTEGER)), MAX(ts) FROM medicao WHERE grandeza=? AND ts > 0", (g,)).fetchone()
            if r and r[0]:
                out["medidores"][chave] = {"dias": r[0], "ultimo": _dia(r[1])}
        out["sensores"] = [{"no": no, "visto": _dia(v)} for no, v in db.execute("SELECT no, MAX(recebido) FROM leitura GROUP BY no ORDER BY no")]
        try:
            for nome, n, quando in db.execute("SELECT nome, n_amostras, treinado_em FROM modelo m WHERE nome LIKE 'consumo:%' AND "
                                              "versao = (SELECT MAX(versao) FROM modelo WHERE nome = m.nome)"):
                out["modelos_consumo"].append({"nome": nome, "n_amostras": n, "treinado_em": _dia(quando)})
        except Exception:          # noqa: BLE001 — tabela do aprendizado ainda não criada
            pass
        out["municipio"] = risco_do_lugar(db)
        if incluir_arquivos:
            try:
                out["arquivos"] = [{"id": i, "nome": n, "data": _dia(c), "origem": "gestao"}
                                   for i, n, c in db.execute("SELECT id, nome, criado FROM gestao_arquivo ORDER BY criado DESC LIMIT 2000")]
            except Exception:      # noqa: BLE001
                pass
    return out


_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def anexar(hub, d: dict, quem: str, certs: list[dict] | None = None) -> dict:
    """Metadados de evidência manual: certificação, critério, nome do documento, data, validade, responsável,
    id de um arquivo já guardado na Gestão (opcional) e observação."""
    preparar(hub)
    if not isinstance(d, dict):
        return {"ok": False, "erro": "json invalido"}
    certs = certs if certs is not None else carregar_certs()
    cert = next((c for c in certs if c["id"] == d.get("cert")), None)
    if not cert or not any(k["id"] == d.get("criterio") for g in cert["grupos"] for k in g["criterios"]):
        return {"ok": False, "erro": "certificação ou critério desconhecido"}
    nome = str(d.get("nome") or "").strip()
    if not nome or len(nome) > 160:
        return {"ok": False, "erro": "nome do documento obrigatório (até 160 letras)"}
    data, validade = str(d.get("data") or ""), str(d.get("validade") or "")
    if not _DATA.match(data) or (validade and not _DATA.match(validade)):
        return {"ok": False, "erro": "datas no formato AAAA-MM-DD"}
    arquivo = str(d.get("arquivo") or "")[:40]
    with hub._trava:
        if arquivo:
            try:
                ok = hub._db.execute("SELECT 1 FROM gestao_arquivo WHERE id=?", (arquivo,)).fetchone()
            except Exception:      # noqa: BLE001
                ok = None
            if not ok:
                return {"ok": False, "erro": "arquivo da Gestão não encontrado"}
        cur = hub._db.execute("INSERT INTO evidencia_anexo(cert,criterio,nome,data,validade,responsavel,arquivo,obs,criado,por) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (cert["id"], d["criterio"], nome, data, validade, str(d.get("responsavel") or "").strip()[:80], arquivo,
                               str(d.get("obs") or "").strip()[:500], hub.relogio(), quem))
        hub.registrar("evidencia", quem or "plataforma", {"o_que": "anexada", "cert": cert["id"], "criterio": d["criterio"]})
        hub._db.commit()
    return {"ok": True, "id": cur.lastrowid}


def anexos(hub, cert: str | None = None) -> list[dict]:
    preparar(hub)
    cols = ("id", "cert", "criterio", "nome", "data", "validade", "responsavel", "arquivo", "obs")
    sql = "SELECT " + ",".join(cols) + " FROM evidencia_anexo" + (" WHERE cert=?" if cert else "") + " ORDER BY data DESC, id DESC"
    with hub._trava:
        return [dict(zip(cols, r)) for r in hub._db.execute(sql, (cert,) if cert else ())]


def remover(hub, ident: int, quem: str) -> dict:
    preparar(hub)
    with hub._trava:
        cur = hub._db.execute("DELETE FROM evidencia_anexo WHERE id=?", (int(ident),))
        if cur.rowcount:
            hub.registrar("evidencia", quem or "plataforma", {"o_que": "removida", "id": int(ident)})
        hub._db.commit()
    return {"ok": cur.rowcount > 0}
