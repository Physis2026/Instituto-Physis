"""Painel municipal de resiliência (Defesa Civil e prefeituras).

O que junta, para UM município configurado (código IBGE, nome e UF):
- chuva medida em cada pluviômetro automático do CEMADEN no município (1 h, 24 h e 72 h), com o nível de
  deslizamento pelos limiares configuráveis (padrão 40/80 mm em 24 h e 60/120 mm em 72 h — os mesmos do
  alertas_clima.py; a Defesa Civil de cada cidade troca pelos seus, em "limiares");
- avisos meteorológicos do INMET que citam o código IBGE do município;
- a previsão combinada do hub (clima.py) e a chance de chuva aprendida no lugar (aprendizado.py), só como apoio
  (o hub prevê para o lugar dele; a tela avisa quando o lugar do hub não é o município);
- rio e enchente (GloFAS via gis.GisExtra.rio) nos pontos de rio configurados;
- bairros com classe de risco (R1 a R4, como na setorização de risco do Serviço Geológico do Brasil), importados
  de GeoJSON (polígonos ou pontos) ou CSV (pontos), desenhados num mapa SVG sem internet;
- pluviômetros da Physis (linhas V6 com TIPO:PLUV, quando o hub passar a aceitá-las; ver docs/ROBOS.md);
- lista de alertas por bairro com nível (atenção/alerta), início, última atualização e fim, e exportação CSV.

Dois modos de leitura:
- público (cidadão, sem conta): bairros, risco, chuva por estação, avisos e alertas. Nenhum dado pessoal; os
  pluviômetros da Physis só aparecem se marcados "publico" (podem estar em propriedade particular);
- operador (equipe): tudo do público mais a configuração, os erros das consultas e o histórico completo.

A tela (web/municipio.html) nunca chama a internet: lê só as rotas do hub. Quem chama os serviços abertos é o
laço de fundo (rodar) ou o botão "Atualizar agora" do operador.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import clima as clima_mod

FUSO = clima_mod.FUSO
NIVEIS = {"atencao": 1, "alerta": 2}
NOMES_NIVEL = {"atencao": "Atenção", "alerta": "Alerta"}
# classes de risco (setorização de risco geológico do SGB/CPRM: R1 baixo, R2 médio, R3 alto, R4 muito alto)
RISCOS = ("baixo", "medio", "alto", "muito_alto")
NOMES_RISCO = {"baixo": "Baixo (R1)", "medio": "Médio (R2)", "alto": "Alto (R3)", "muito_alto": "Muito alto (R4)"}
LIMIARES_PADRAO = {"atencao_24h": 40.0, "alerta_24h": 80.0, "atencao_72h": 60.0, "alerta_72h": 120.0}
VALIDADE_S = {"cemaden": 2 * 3600, "inmet": 6 * 3600}
JANELA_ATIVA_H = 3                 # como o clima.py: estação sem dado há mais de 3 h não vale
FECHADOS_VISIVEIS_H = 72           # alertas encerrados ainda mostrados na tela
MAX_BAIRROS, MAX_VERTICES, MAX_RIOS, MAX_PLUV = 500, 5000, 20, 50
TIPOS_ALERTA = {"chuva": "Chuva acumulada (encostas e deslizamento)", "rio": "Rio acima do normal (inundação)",
                "inmet": "Aviso meteorológico do INMET"}

URL = {
    # avisos ativos do INMET (Alert-AS). Formato conferido só com dados de exemplo: [VERIFICAR] na primeira instalação.
    "inmet_avisos": "https://apiprevmet3.inmet.gov.br/avisos/ativos",
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS mun_config (id INTEGER PRIMARY KEY CHECK (id = 1), dados TEXT NOT NULL, atualizado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS mun_bairro (
  id TEXT PRIMARY KEY, nome TEXT NOT NULL, risco TEXT NOT NULL, geometria TEXT NOT NULL,
  estacoes TEXT NOT NULL DEFAULT '[]', rio TEXT NOT NULL DEFAULT '', atualizado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS mun_fonte (
  fonte TEXT PRIMARY KEY, dados TEXT NOT NULL, consultado REAL NOT NULL, erro TEXT NOT NULL DEFAULT '', erro_em REAL);
CREATE TABLE IF NOT EXISTS mun_alerta (
  id INTEGER PRIMARY KEY AUTOINCREMENT, chave TEXT NOT NULL, bairro TEXT NOT NULL, bairro_nome TEXT NOT NULL,
  tipo TEXT NOT NULL, nivel TEXT NOT NULL, nivel_max TEXT NOT NULL, texto TEXT NOT NULL, valor REAL, fonte TEXT NOT NULL,
  inicio REAL NOT NULL, atualizado REAL NOT NULL, fim REAL);
CREATE INDEX IF NOT EXISTS mun_alerta_aberto ON mun_alerta(chave, fim);
"""


def _url(nome: str) -> str:
    return os.environ.get(f"PHYSIS_MUN_{nome.upper()}_URL") or URL[nome]


def _sem_acento(s) -> str:
    return clima_mod._sem_acento(str(s or ""))


def _num(v) -> float | None:
    if v in ("-", "", None):
        return 0.0 if v == "-" else None
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) < 1e9 else None


def _br(v, casas: int = 1) -> str:
    return f"{(v or 0):.{casas}f}".replace(".", ",")


def _hora(t: float | None) -> str:
    return datetime.fromtimestamp(t, FUSO).strftime("%Y-%m-%d %H:%M") if t else ""


def _ident(nome: str, usados: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _sem_acento(nome)).strip("-")[:40] or "bairro"
    i, ident = 2, base
    while ident in usados:
        ident, i = f"{base}-{i}", i + 1
    usados.add(ident)
    return ident


# ══ Validação e importação (funções puras) ═══════════════════════════════════════════════════════
def normalizar_risco(v) -> str | None:
    """R1..R4, 1..4, baixo/médio/alto/muito alto (com ou sem acento) ou low/medium/high/very high."""
    t = re.sub(r"[\s_-]+", " ", _sem_acento(v)).strip()
    mapa = {"r1": "baixo", "1": "baixo", "baixo": "baixo", "low": "baixo",
            "r2": "medio", "2": "medio", "medio": "medio", "moderado": "medio", "medium": "medio",
            "r3": "alto", "3": "alto", "alto": "alto", "high": "alto",
            "r4": "muito_alto", "4": "muito_alto", "muito alto": "muito_alto", "very high": "muito_alto"}
    return mapa.get(t)


def _no_brasil(lon, lat) -> bool:
    return isinstance(lon, (int, float)) and isinstance(lat, (int, float)) and -75.0 <= lon <= -28.0 and -35.0 <= lat <= 6.0


def _anel(pts) -> list[list[float]]:
    if not isinstance(pts, list):
        raise ValueError("anel do polígono inválido")
    out = []
    for p in pts:
        if not (isinstance(p, list) and len(p) >= 2 and _no_brasil(p[0], p[1])):
            raise ValueError("coordenada fora do Brasil ou inválida (use longitude, latitude em graus)")
        out.append([round(float(p[0]), 5), round(float(p[1]), 5)])
    if len(out) < 3:
        raise ValueError("polígono com menos de 3 pontos")
    return out


def validar_geometria(g) -> dict:
    """{"tipo": "ponto", "coords": [lon, lat]} ou {"tipo": "poligono", "coords": [[anel externo], ...]}."""
    if not isinstance(g, dict):
        raise ValueError("geometria ausente")
    t = g.get("type") or g.get("tipo")
    c = g.get("coordinates") if "coordinates" in g else g.get("coords")
    if t in ("Point", "ponto"):
        if not (isinstance(c, list) and len(c) >= 2 and _no_brasil(c[0], c[1])):
            raise ValueError("ponto fora do Brasil ou inválido")
        return {"tipo": "ponto", "coords": [round(float(c[0]), 5), round(float(c[1]), 5)]}
    if t == "Polygon":
        polis = [_anel((c or [None])[0])]
    elif t == "MultiPolygon":
        polis = [_anel((p or [None])[0]) for p in (c or [])]
    elif t == "poligono":
        polis = [_anel(p) for p in (c or [])]
    else:
        raise ValueError("geometria deve ser ponto, polígono ou multipolígono")
    if not polis:
        raise ValueError("polígono vazio")
    if sum(len(p) for p in polis) > MAX_VERTICES:
        raise ValueError(f"polígono com mais de {MAX_VERTICES} vértices: simplifique antes de importar")
    return {"tipo": "poligono", "coords": polis}


def _prop(p: dict, *nomes):
    baixo = {_sem_acento(k): v for k, v in (p or {}).items()}
    for n in nomes:
        if baixo.get(n) not in (None, ""):
            return baixo[n]
    return None


def importar_geojson(j) -> list[dict]:
    """FeatureCollection com bairros (Polygon/MultiPolygon/Point). Propriedades aceitas: nome/name/bairro e
    risco/classe/grau/risk. Bairro sem classe de risco entra como "baixo" e é marcado para revisão."""
    if not isinstance(j, dict) or j.get("type") != "FeatureCollection" or not isinstance(j.get("features"), list):
        raise ValueError("esperado um GeoJSON FeatureCollection")
    if len(j["features"]) > MAX_BAIRROS:
        raise ValueError(f"mais de {MAX_BAIRROS} bairros")
    out, usados = [], set()
    for i, f in enumerate(j["features"], 1):
        p = (f or {}).get("properties") or {}
        nome = str(_prop(p, "nome", "name", "bairro", "nm_bairro", "localidade") or f"Bairro {i}").strip()[:80]
        try:
            geo = validar_geometria((f or {}).get("geometry"))
        except ValueError as exc:
            raise ValueError(f"item {i} ({nome}): {exc}") from None
        risco = normalizar_risco(_prop(p, "risco", "classe", "grau", "grau de risco", "risk", "classe de risco"))
        out.append({"id": _ident(str(_prop(p, "id", "codigo") or nome), usados), "nome": nome,
                    "risco": risco or "baixo", "revisar": risco is None, "geometria": geo})
    return out


def importar_csv(texto: str) -> list[dict]:
    """CSV com cabeçalho nome;risco;lat;lon (separador ; , ou tabulação). Só pontos."""
    linhas = [x for x in (texto or "").lstrip("﻿").splitlines() if x.strip()]
    if len(linhas) < 2:
        raise ValueError("CSV vazio: a primeira linha é o cabeçalho (nome;risco;lat;lon)")
    sep = max((";", ",", "\t"), key=lambda s: linhas[0].count(s))
    leitor = csv.reader(linhas, delimiter=sep)
    cab = [_sem_acento(c) for c in next(leitor)]
    def col(*nomes):
        return next((cab.index(n) for n in nomes if n in cab), None)
    cn, cr, cla, clo = col("nome", "bairro", "name"), col("risco", "classe", "grau", "risk"), col("lat", "latitude"), col("lon", "lng", "longitude")
    if None in (cn, cla, clo):
        raise ValueError("faltam colunas: nome, lat e lon são obrigatórias")
    out, usados = [], set()
    for i, r in enumerate(leitor, 2):
        if len(out) >= MAX_BAIRROS:
            raise ValueError(f"mais de {MAX_BAIRROS} bairros")
        try:
            lat, lon = float(r[cla].replace(",", ".")), float(r[clo].replace(",", "."))
        except (IndexError, ValueError):
            raise ValueError(f"linha {i}: lat/lon inválidas") from None
        if not _no_brasil(lon, lat):
            raise ValueError(f"linha {i}: coordenada fora do Brasil")
        nome = (r[cn] if cn < len(r) else "").strip()[:80] or f"Bairro {i - 1}"
        risco = normalizar_risco(r[cr]) if cr is not None and cr < len(r) else None
        out.append({"id": _ident(nome, usados), "nome": nome, "risco": risco or "baixo", "revisar": risco is None,
                    "geometria": {"tipo": "ponto", "coords": [round(lon, 5), round(lat, 5)]}})
    return out


IMPORTAR_MAX_BYTES = 5 * 1024 * 1024      # GeoJSON de bairros (a rota usa _corpo_grande com este limite)
MAX_VERTICES_TOTAL = 100_000


def ler_importacao(dados: bytes | str, tipo: str = "") -> list[dict]:
    """Corpo da rota de importação: GeoJSON (começa com "{") ou CSV. JSON lido pelo seguranca.carregar_json
    (sem NaN, profundidade limitada), com mais itens que o normal porque polígonos têm muitos vértices."""
    from . import seguranca as seg
    texto = dados.decode("utf-8", errors="replace") if isinstance(dados, (bytes, bytearray)) else str(dados or "")
    texto = texto.lstrip("﻿")
    if texto.lstrip().startswith("{") or "json" in (tipo or ""):
        lista = importar_geojson(seg.carregar_json(texto, max_profundidade=12, max_itens=4 * MAX_VERTICES_TOTAL + 50_000))
    else:
        lista = importar_csv(texto)
    total = sum(len(b["geometria"]["coords"]) if b["geometria"]["tipo"] == "ponto" else sum(len(a) for a in b["geometria"]["coords"]) for b in lista)
    if total > MAX_VERTICES_TOTAL:
        raise ValueError(f"mais de {MAX_VERTICES_TOTAL} vértices no total: simplifique os polígonos")
    return lista


def validar_limiares(d) -> tuple[dict | None, str]:
    lim = dict(LIMIARES_PADRAO)
    for k in LIMIARES_PADRAO:
        if isinstance(d, dict) and d.get(k) is not None:
            v = _num(d[k])
            if v is None or not 0 < v <= 2000:
                return None, f"limiar {k} precisa ser número entre 0 e 2000 mm"
            lim[k] = round(v, 1)
    if lim["atencao_24h"] >= lim["alerta_24h"] or lim["atencao_72h"] >= lim["alerta_72h"]:
        return None, "o limiar de atenção precisa ser menor que o de alerta"
    return lim, ""


def validar_config(d: dict) -> tuple[dict | None, str]:
    if not isinstance(d, dict):
        return None, "json invalido"
    ibge = str(d.get("ibge") or "").strip()
    if not re.fullmatch(r"\d{7}", ibge):
        return None, "código IBGE do município tem 7 dígitos"
    uf = str(d.get("uf") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", uf):
        return None, "UF com 2 letras"
    cfg = {"ibge": ibge, "uf": uf, "municipio": str(d.get("municipio") or "").strip()[:80], "lat": None, "lon": None,
           "orgao": str(d.get("orgao") or "").strip()[:120], "telefone_emergencia": str(d.get("telefone_emergencia") or "199").strip()[:20]}
    if d.get("lat") is not None or d.get("lon") is not None:
        lat, lon = _num(d.get("lat")), _num(d.get("lon"))
        if lat is None or lon is None or not _no_brasil(lon, lat):
            return None, "centro do mapa fora do Brasil"
        cfg["lat"], cfg["lon"] = round(lat, 5), round(lon, 5)
    lim, erro = validar_limiares(d.get("limiares") or {})
    if not lim:
        return None, erro
    cfg["limiares"] = lim
    rios = d.get("rios") or []
    if not isinstance(rios, list) or len(rios) > MAX_RIOS:
        return None, f"até {MAX_RIOS} pontos de rio"
    cfg["rios"], usados = [], set()
    for r in rios:
        lat, lon = _num((r or {}).get("lat")), _num((r or {}).get("lon"))
        if lat is None or lon is None or not _no_brasil(lon, lat):
            return None, "ponto de rio fora do Brasil"
        nome = str(r.get("nome") or "Rio").strip()[:80]
        cfg["rios"].append({"id": str(r.get("id") or "")[:40] or _ident(nome, usados), "nome": nome, "lat": round(lat, 4), "lon": round(lon, 4)})
    pl = d.get("pluviometros") or []
    if not isinstance(pl, list) or len(pl) > MAX_PLUV:
        return None, f"até {MAX_PLUV} pluviômetros"
    cfg["pluviometros"] = []
    for p in pl:
        try:
            no = int((p or {}).get("no"))
        except (TypeError, ValueError):
            return None, "pluviômetro sem número do nó"
        if not 1 <= no <= 99:
            return None, "número do nó de 1 a 99"
        lat, lon = _num(p.get("lat")), _num(p.get("lon"))
        if (lat is not None or lon is not None) and (lat is None or lon is None or not _no_brasil(lon, lat)):
            return None, "pluviômetro fora do Brasil"
        cfg["pluviometros"].append({"no": no, "nome": str(p.get("nome") or f"Pluviômetro {no:02d}").strip()[:80],
                                    "lat": lat, "lon": lon, "bairro": str(p.get("bairro") or "")[:40],
                                    "publico": p.get("publico") is True})
    return cfg, ""


# ══ Leitura das fontes (funções puras) ═══════════════════════════════════════════════════════════
def nivel_chuva(mm24: float | None, mm72: float | None, lim: dict) -> str | None:
    a24, a72 = mm24 or 0.0, mm72 or 0.0
    if a24 >= lim["alerta_24h"] or a72 >= lim["alerta_72h"]:
        return "alerta"
    if a24 >= lim["atencao_24h"] or a72 >= lim["atencao_72h"]:
        return "atencao"
    return None


def estacoes_cemaden(j, ibge: str, agora: float, lim: dict) -> list[dict]:
    """Todas as estações do CEMADEN no município (o serviço é por UF), ativas ou não."""
    agora_dt = datetime.fromtimestamp(agora, timezone.utc)
    out = []
    for e in j if isinstance(j, list) else []:
        if not isinstance(e, dict) or str(e.get("codibge")) != str(ibge):
            continue
        t = clima_mod._quando_cemaden(e.get("datahoraUltimovalor"))
        ativa = bool(t and agora_dt - t <= timedelta(hours=JANELA_ATIVA_H))
        m1, m24, m72 = _num(e.get("acc1hr")), _num(e.get("acc24hr")), _num(e.get("acc72hr"))
        out.append({"codigo": str(e.get("codestacao") or e.get("idestacao") or "")[:40], "nome": str(e.get("nomeestacao") or "")[:120],
                    "ativa": ativa, "ultimo": t.timestamp() if t else None,
                    "mm_1h": m1 if ativa else None, "mm_24h": m24 if ativa else None, "mm_72h": m72 if ativa else None,
                    "nivel": nivel_chuva(m24, m72, lim) if ativa else None})
    out.sort(key=lambda x: (not x["ativa"], -(x["mm_24h"] or 0), x["nome"]))
    return out


_SEVERIDADE = {"perigo potencial": "atencao", "perigo": "alerta", "grande perigo": "alerta",
               "amarelo": "atencao", "laranja": "alerta", "vermelho": "alerta"}


def _quando_inmet(v) -> float | None:
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=FUSO).timestamp()
        except ValueError:
            continue
    return None


def ler_avisos_inmet(j, ibge: str) -> list[dict]:
    """Avisos do INMET que citam o município. Aceita lista ou {"hoje": [...], "futuro": [...]}; o campo dos
    municípios atingidos é "geocodes" (texto com códigos IBGE) ou "municipios" (lista)."""
    itens = j if isinstance(j, list) else [x for k in ("hoje", "futuro", "avisos") for x in ((j or {}).get(k) or [])] if isinstance(j, dict) else []
    out, vistos = [], set()
    for a in itens:
        if not isinstance(a, dict):
            continue
        geo = a.get("geocodes") if a.get("geocodes") is not None else a.get("municipios")
        codigos = set(re.findall(r"\d{7}", json.dumps(geo))) if geo is not None else set()
        if str(ibge) not in codigos:
            continue
        ident = str(a.get("id") or a.get("id_aviso") or f"{a.get('descricao')}|{a.get('inicio')}")[:80]
        if ident in vistos:
            continue
        vistos.add(ident)
        sev = _sem_acento(a.get("severidade") or a.get("aviso_cor") or "")
        out.append({"id": ident, "evento": str(a.get("descricao") or a.get("evento") or "Aviso")[:160],
                    "severidade": str(a.get("severidade") or "")[:40], "nivel": _SEVERIDADE.get(sev, "atencao"),
                    "inicio": _quando_inmet(a.get("inicio")), "fim": _quando_inmet(a.get("fim")),
                    "riscos": str(a.get("riscos") or "")[:600], "instrucoes": str(a.get("instrucoes") or "")[:600]})
    return out


def _campos_v6(linha: str) -> dict:
    d = {}
    for par in linha.split(","):
        if ":" in par:
            k, v = par.split(":", 1)
            d[k.strip().upper()] = v.strip()
    return d


def chuva_physis(linhas: list[tuple[str, float]], agora: float) -> dict[int, dict]:
    """Soma o CHI (mm no intervalo) das linhas TIPO:PLUV por nó, em 1 h, 24 h e 72 h (pela hora de chegada)."""
    out: dict[int, dict] = {}
    for linha, recebido in linhas:
        c = _campos_v6(linha)
        if c.get("TIPO", "").upper() != "PLUV":
            continue
        try:
            no = int(c.get("ID", ""))
        except ValueError:
            continue
        mm = _num(c.get("CHI"))
        if mm is None or mm < 0:
            continue
        r = out.setdefault(no, {"mm_1h": 0.0, "mm_24h": 0.0, "mm_72h": 0.0, "ultimo": None})
        idade = agora - recebido
        for k, h in (("mm_1h", 1), ("mm_24h", 24), ("mm_72h", 72)):
            if 0 <= idade <= h * 3600:
                r[k] = round(r[k] + mm, 2)
        r["ultimo"] = max(r["ultimo"] or 0, recebido)
    return out


def avaliar(bairros: list[dict], estacoes: list[dict], pluvs: list[dict], rios: dict[str, dict],
            avisos: list[dict], lim: dict) -> list[dict]:
    """Alertas do momento por bairro. Chuva: estações do bairro (CEMADEN) e pluviômetros da Physis nele; sem
    nenhuma, a maior chuva medida no município (para alerta, melhor não subestimar). Rio: o ponto ligado ao bairro.
    INMET: vale para o município todo (bairro "")."""
    ativas = [e for e in estacoes if e.get("ativa")]
    maior = max(ativas, key=lambda e: (e.get("mm_24h") or 0, e.get("mm_72h") or 0), default=None)
    out = []
    for b in bairros:
        nomes = {_sem_acento(n) for n in b.get("estacoes") or []}
        fontes = [(f"CEMADEN {e['nome']}", e.get("mm_24h"), e.get("mm_72h")) for e in ativas if _sem_acento(e["nome"]) in nomes]
        fontes += [(f"Physis {p['nome']}", p.get("mm_24h"), p.get("mm_72h")) for p in pluvs if p.get("bairro") == b["id"] and p.get("mm_24h") is not None]
        estimado = False
        if not fontes and maior:
            fontes, estimado = [(f"CEMADEN {maior['nome']} (maior do município)", maior.get("mm_24h"), maior.get("mm_72h"))], True
        if fontes:
            f = max(fontes, key=lambda x: (NIVEIS.get(nivel_chuva(x[1], x[2], lim) or "", 0), x[1] or 0, x[2] or 0))
            nv = nivel_chuva(f[1], f[2], lim)
            if nv:
                txt = (("Chuva acumulada alta: risco de deslizamento em encostas." if nv == "alerta" else
                        "Solo encharcando: observe trincas, árvores e postes inclinados e água barrenta.")
                       + f" Medido: {_br(f[1])} mm em 24 h e {_br(f[2])} mm em 72 h ({f[0]})."
                       + (" Sem estação no bairro: usada a maior chuva do município." if estimado else "")
                       + f" Risco do bairro: {NOMES_RISCO.get(b.get('risco'), '-')}.")
                out.append({"chave": f"{b['id']}|chuva", "bairro": b["id"], "bairro_nome": b["nome"], "tipo": "chuva",
                            "nivel": nv, "texto": txt, "valor": f[1], "fonte": f[0]})
        r = rios.get(b.get("rio") or "")
        if r and r.get("nivel") in NIVEIS:
            out.append({"chave": f"{b['id']}|rio", "bairro": b["id"], "bairro_nome": b["nome"], "tipo": "rio", "nivel": r["nivel"],
                        "texto": (f"{r.get('nome') or 'Rio'}: vazão prevista de {_br(r.get('pico'), 0)} m³/s, acima do "
                                  + ("percentil 99 (cheia rara)." if r["nivel"] == "alerta" else "percentil 90 (cheia comum).")
                                  + " Evite margens e travessias alagadas."),
                        "valor": r.get("pico"), "fonte": "GloFAS (Copernicus) via Open-Meteo"})
    for a in avisos:
        out.append({"chave": f"|inmet|{a['id']}", "bairro": "", "bairro_nome": "Município inteiro", "tipo": "inmet",
                    "nivel": a["nivel"], "texto": a["evento"] + (f" ({a['severidade']})" if a.get("severidade") else ""),
                    "valor": None, "fonte": "INMET"})
    return out


def _bairro_publico(b: dict) -> dict:
    return {k: b[k] for k in ("id", "nome", "risco", "geometria", "estacoes", "rio", "revisar") if k in b}


# ══ Ligação com o banco do hub ═══════════════════════════════════════════════════════════════════
class Municipio:
    def __init__(self, hub, clima=None, aprendizado=None, rio=None, buscar=clima_mod.buscar_json, relogio=None):
        """rio = função(lat, lon) -> dict no formato de gis.GisExtra.rio (padrão: a do hub, com cache)."""
        self.hub, self.clima, self.aprendizado, self.buscar = hub, clima, aprendizado, buscar
        self.relogio = relogio or hub.relogio
        if rio is None:
            from . import gis as gis_mod
            rio = gis_mod.GisExtra(gis_mod.Irradiacao(hub)).rio
        self.rio = rio
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    # ── Configuração ─────────────────────────────────────────────────────────────────────────
    def config(self) -> dict | None:
        r = self._db.execute("SELECT dados FROM mun_config WHERE id=1").fetchone()
        return json.loads(r[0]) if r else None

    def definir_config(self, d: dict, por: str = "") -> dict:
        cfg, erro = validar_config(d)
        if not cfg:
            return {"ok": False, "erro": erro}
        with self.hub._trava:
            antes = self.config()
            self._db.execute("INSERT INTO mun_config(id,dados,atualizado) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET "
                             "dados=excluded.dados, atualizado=excluded.atualizado", (json.dumps(cfg, ensure_ascii=False), self.relogio()))
            if antes and (antes.get("ibge"), antes.get("uf")) != (cfg["ibge"], cfg["uf"]):
                self._db.execute("DELETE FROM mun_fonte")          # outro município: as consultas antigas não valem
            self._db.commit()
            self.hub.registrar("municipio", por or "operador", {"o_que": "configuração", "ibge": cfg["ibge"], "limiares": cfg["limiares"]})
            self._db.commit()
        return {"ok": True, "config": cfg}

    def bairros(self) -> list[dict]:
        linhas = self._db.execute("SELECT id,nome,risco,geometria,estacoes,rio FROM mun_bairro ORDER BY nome").fetchall()
        return [{"id": i, "nome": n, "risco": r, "geometria": json.loads(g), "estacoes": json.loads(e), "rio": rio}
                for i, n, r, g, e, rio in linhas]

    def importar(self, lista: list[dict], por: str = "", substituir: bool = False) -> dict:
        if len(lista) > MAX_BAIRROS:
            return {"ok": False, "erro": f"mais de {MAX_BAIRROS} bairros"}
        agora = self.relogio()
        with self.hub._trava:
            if substituir:
                self._db.execute("DELETE FROM mun_bairro")
            for b in lista:
                self._db.execute("INSERT INTO mun_bairro(id,nome,risco,geometria,atualizado) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                                 "nome=excluded.nome, risco=excluded.risco, geometria=excluded.geometria, atualizado=excluded.atualizado",
                                 (b["id"], b["nome"], b["risco"], json.dumps(b["geometria"]), agora))
            n = self._db.execute("SELECT COUNT(*) FROM mun_bairro").fetchone()[0]
            if n > MAX_BAIRROS:
                self._db.rollback()
                return {"ok": False, "erro": f"mais de {MAX_BAIRROS} bairros no total"}
            self._db.commit()
            self.hub.registrar("municipio", por or "operador", {"o_que": "bairros importados", "quantos": len(lista)})
            self._db.commit()
        return {"ok": True, "importados": len(lista), "total": n, "revisar": [b["nome"] for b in lista if b.get("revisar")]}

    def editar_bairro(self, d: dict, por: str = "") -> dict:
        """Muda classe de risco, nome, estações do CEMADEN e ponto de rio de um bairro; {"apagar": true} remove."""
        ident = str((d or {}).get("id") or "")
        with self.hub._trava:
            atual = self._db.execute("SELECT nome,risco,estacoes,rio FROM mun_bairro WHERE id=?", (ident,)).fetchone()
            if not atual:
                return {"ok": False, "erro": "bairro desconhecido"}
            if d.get("apagar") is True:
                self._db.execute("DELETE FROM mun_bairro WHERE id=?", (ident,))
                self._db.commit()
                return {"ok": True, "apagado": ident}
            nome, risco, est, rio = atual[0], atual[1], json.loads(atual[2]), atual[3]
            if d.get("nome") is not None:
                nome = str(d["nome"]).strip()[:80] or nome
            if d.get("risco") is not None:
                risco = normalizar_risco(d["risco"])
                if not risco:
                    return {"ok": False, "erro": "classe de risco: R1, R2, R3 ou R4"}
            if d.get("estacoes") is not None:
                if not isinstance(d["estacoes"], list) or len(d["estacoes"]) > 20:
                    return {"ok": False, "erro": "estações: lista de até 20 nomes"}
                est = [str(x).strip()[:120] for x in d["estacoes"] if str(x).strip()]
            if d.get("rio") is not None:
                rio = str(d["rio"])[:40]
                cfg = self.config() or {}
                if rio and rio not in {r["id"] for r in cfg.get("rios") or []}:
                    return {"ok": False, "erro": "ponto de rio desconhecido"}
            self._db.execute("UPDATE mun_bairro SET nome=?, risco=?, estacoes=?, rio=?, atualizado=? WHERE id=?",
                             (nome, risco, json.dumps(est, ensure_ascii=False), rio, self.relogio(), ident))
            self._db.commit()
            self.hub.registrar("municipio", por or "operador", {"o_que": "bairro alterado", "bairro": ident, "risco": risco})
            self._db.commit()
        return {"ok": True}

    # ── Consultas (internet: só aqui, no laço de fundo ou pelo operador) ─────────────────────
    def _guardar(self, fonte: str, dados, erro: str = "") -> None:
        agora = self.relogio()
        with self.hub._trava:
            if dados is not None:
                self._db.execute("INSERT INTO mun_fonte(fonte,dados,consultado,erro,erro_em) VALUES(?,?,?,'',NULL) ON CONFLICT(fonte) "
                                 "DO UPDATE SET dados=excluded.dados, consultado=excluded.consultado, erro='', erro_em=NULL",
                                 (fonte, json.dumps(dados, ensure_ascii=False), agora))
            else:
                self._db.execute("INSERT INTO mun_fonte(fonte,dados,consultado,erro,erro_em) VALUES(?, 'null', 0, ?, ?) ON CONFLICT(fonte) "
                                 "DO UPDATE SET erro=excluded.erro, erro_em=excluded.erro_em", (fonte, erro[:200], agora))
            self._db.commit()

    def _fonte(self, fonte: str) -> dict:
        r = self._db.execute("SELECT dados, consultado, erro FROM mun_fonte WHERE fonte=?", (fonte,)).fetchone()
        if not r:
            return {"dados": None, "consultado": None, "erro": None, "atual": False}
        return {"dados": json.loads(r[0]) if r[1] else None, "consultado": r[1] or None, "erro": r[2] or None,
                "atual": bool(r[1]) and self.relogio() - r[1] <= VALIDADE_S.get(fonte, 6 * 3600)}

    def consultar(self) -> dict:
        cfg = self.config()
        if not cfg:
            return {"ok": False, "erro": "configure o município primeiro"}
        feitos = {}
        try:
            j = self.buscar(clima_mod._url("cemaden").format(uf=urllib.parse.quote(cfg["uf"])))
            self._guardar("cemaden", estacoes_cemaden(j, cfg["ibge"], self.relogio(), cfg["limiares"]))
            feitos["cemaden"] = True
        except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
            self._guardar("cemaden", None, f"sem resposta: {exc}")
            feitos["cemaden"] = False
        try:
            self._guardar("inmet", ler_avisos_inmet(self.buscar(_url("inmet_avisos")), cfg["ibge"]))
            feitos["inmet"] = True
        except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
            self._guardar("inmet", None, f"sem resposta: {exc}")
            feitos["inmet"] = False
        rios = {}
        for r in cfg.get("rios") or []:
            try:
                x = self.rio(r["lat"], r["lon"]) or {}
            except Exception as exc:          # noqa: BLE001 — um rio fora do ar não derruba os outros
                x = {"ok": False, "avisos": [str(exc)]}
            prev = [v for v in ((x.get("previsao") or {}).get("vazao") or []) if v is not None]
            hist = x.get("historico") or {}
            rios[r["id"]] = {"id": r["id"], "nome": r["nome"], "lat": r["lat"], "lon": r["lon"], "nivel": x.get("nivel"),
                             "pico": max(prev) if prev else None, "p90": hist.get("p90"), "p99": hist.get("p99"),
                             "avisos": (x.get("avisos") or [])[:3]}
        self._guardar("rios", rios)
        feitos["rios"] = len(rios)
        self.reavaliar()
        return {"ok": True, "consultas": feitos}

    def pluviometros(self) -> list[dict]:
        cfg = self.config() or {}
        agora = self.relogio()
        linhas = self._db.execute("SELECT linha, recebido FROM leitura WHERE linha LIKE '%TIPO:PLUV%' AND recebido >= ?",
                                  (agora - 72 * 3600,)).fetchall()
        soma = chuva_physis(linhas, agora)
        out = []
        for p in cfg.get("pluviometros") or []:
            s = soma.get(p["no"])
            out.append(dict(p, mm_1h=s["mm_1h"] if s else None, mm_24h=s["mm_24h"] if s else None,
                            mm_72h=s["mm_72h"] if s else None, ultimo=s["ultimo"] if s else None,
                            nivel=nivel_chuva(s["mm_24h"], s["mm_72h"], cfg["limiares"]) if s else None))
        return out

    def reavaliar(self) -> list[dict]:
        cfg = self.config()
        if not cfg:
            return []
        cem, inm, rios = self._fonte("cemaden"), self._fonte("inmet"), self._fonte("rios")
        agora = self.relogio()
        avisos = [a for a in (inm["dados"] or []) if not a.get("fim") or a["fim"] >= agora] if inm["atual"] else []
        atuais = avaliar(self.bairros(), cem["dados"] or [] if cem["atual"] else [], self.pluviometros(),
                         rios["dados"] or {}, avisos, cfg["limiares"])
        self._gravar_alertas(atuais)
        return atuais

    def _gravar_alertas(self, atuais: list[dict]) -> None:
        agora = self.relogio()
        with self.hub._trava:
            abertos = {c: (i, nmax) for i, c, nmax in self._db.execute("SELECT id, chave, nivel_max FROM mun_alerta WHERE fim IS NULL")}
            for a in atuais:
                if a["chave"] in abertos:
                    i, nmax = abertos.pop(a["chave"])
                    nmax = a["nivel"] if NIVEIS[a["nivel"]] > NIVEIS.get(nmax, 0) else nmax
                    self._db.execute("UPDATE mun_alerta SET nivel=?, nivel_max=?, texto=?, valor=?, fonte=?, atualizado=? WHERE id=?",
                                     (a["nivel"], nmax, a["texto"], a["valor"], a["fonte"], agora, i))
                else:
                    self._db.execute("INSERT INTO mun_alerta(chave,bairro,bairro_nome,tipo,nivel,nivel_max,texto,valor,fonte,inicio,atualizado) "
                                     "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (a["chave"], a["bairro"], a["bairro_nome"], a["tipo"], a["nivel"],
                                                                       a["nivel"], a["texto"], a["valor"], a["fonte"], agora, agora))
                    self.hub.registrar("municipio_alerta", a["bairro"] or "municipio", {"o_que": "aberto", "tipo": a["tipo"], "nivel": a["nivel"]})
            for chave, (i, _) in abertos.items():
                self._db.execute("UPDATE mun_alerta SET fim=?, atualizado=? WHERE id=?", (agora, agora, i))
                self.hub.registrar("municipio_alerta", chave.split("|")[0] or "municipio", {"o_que": "encerrado", "chave": chave})
            self._db.commit()

    def alertas(self, desde: float | None = None, limite: int = 500) -> list[dict]:
        desde = self.relogio() - FECHADOS_VISIVEIS_H * 3600 if desde is None else desde
        linhas = self._db.execute("SELECT id,bairro,bairro_nome,tipo,nivel,nivel_max,texto,valor,fonte,inicio,atualizado,fim FROM mun_alerta "
                                  "WHERE fim IS NULL OR fim >= ? ORDER BY fim IS NOT NULL, inicio DESC LIMIT ?", (desde, limite)).fetchall()
        cols = ("id", "bairro", "bairro_nome", "tipo", "nivel", "nivel_max", "texto", "valor", "fonte", "inicio", "atualizado", "fim")
        return [dict(zip(cols, x), aberto=x[11] is None) for x in linhas]

    # ── O que a tela mostra ──────────────────────────────────────────────────────────────────
    def _previsao(self, cfg: dict) -> dict:
        r = {"combinada": None, "aprendida": None, "dias": [], "mesmo_lugar": False, "aviso": ""}
        if self.clima is not None:
            loc = self.clima.local() or {}
            r["mesmo_lugar"] = str(loc.get("ibge") or "") == cfg["ibge"]
            if not r["mesmo_lugar"]:
                r["aviso"] = ("A previsão do hub é do lugar dele" + (f" ({loc.get('municipio')})" if loc.get("municipio") else "")
                              + ", não deste município: use só como referência.")
            try:
                est = self.clima.estado()
                r["combinada"] = est.get("combinada")
                om = (est.get("fontes") or {}).get("openmeteo") or {}
                r["dias"] = [{k: d.get(k) for k in ("dia", "mm", "prob")} for d in ((om.get("dados") or {}).get("dias") or [])] if om.get("atual") else []
            except Exception:      # noqa: BLE001 — previsão é apoio; sem ela o painel segue
                pass
        if self.aprendizado is not None:
            try:
                p = self.aprendizado.previsao_chuva()
                r["aprendida"] = {"dia": p.get("dia"), "prob": p.get("prob"), "texto": p.get("texto") or p.get("explicacao")}
            except Exception:      # noqa: BLE001
                pass
        return r

    def estado(self, operador: bool = False) -> dict:
        cfg = self.config()
        if not cfg:
            return {"ok": True, "configurado": False, "operador": operador,
                    "aviso": "Município ainda não configurado pela equipe da Defesa Civil."}
        cem, inm, rios = self._fonte("cemaden"), self._fonte("inmet"), self._fonte("rios")
        pluvs = self.pluviometros()
        abertos = {}
        for a in self.alertas():
            if a["aberto"] and a["bairro"]:
                abertos[a["bairro"]] = max(abertos.get(a["bairro"], 0), NIVEIS[a["nivel"]])
        nv = {1: "atencao", 2: "alerta"}
        bairros = [dict(_bairro_publico(b), nivel=nv.get(abertos.get(b["id"], 0))) for b in self.bairros()]
        out = {"ok": True, "configurado": True, "operador": operador, "agora": self.relogio(),
               "municipio": {k: cfg.get(k) for k in ("ibge", "municipio", "uf", "lat", "lon", "orgao", "telefone_emergencia")},
               "limiares": cfg["limiares"], "riscos": NOMES_RISCO, "tipos": TIPOS_ALERTA,
               "cemaden": {"estacoes": cem["dados"] or [], "consultado": cem["consultado"], "atual": cem["atual"]},
               "inmet": {"avisos": inm["dados"] or [], "consultado": inm["consultado"], "atual": inm["atual"]},
               "rios": list((rios["dados"] or {}).values()), "previsao": self._previsao(cfg), "bairros": bairros,
               "pluviometros": [p for p in pluvs if operador or p.get("publico")],
               "alertas": self.alertas(),
               "fontes": "CEMADEN (pluviômetros automáticos), INMET (avisos), GloFAS/Copernicus (rios), hub Physis "
                         "(previsão combinada e modelo aprendido no lugar). Siga sempre a Defesa Civil: em emergência, ligue "
                         + (cfg.get("telefone_emergencia") or "199") + "."}
        if not operador:
            for p in out["pluviometros"]:
                p.pop("no", None)
        else:
            out["config"] = cfg
            out["erros"] = {k: v["erro"] for k, v in (("cemaden", cem), ("inmet", inm), ("rios", rios)) if v["erro"]}
        return out

    def exportar_csv(self, tipo: str = "alertas", operador: bool = False) -> str:
        """CSV (separador ;, UTF-8 com BOM para abrir direto no LibreOffice/Excel)."""
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        if tipo == "chuva":
            w.writerow(["fonte", "estacao", "ativa", "ultimo_dado", "mm_1h", "mm_24h", "mm_72h", "nivel"])
            for e in self._fonte("cemaden")["dados"] or []:
                w.writerow(["CEMADEN", e["nome"], "sim" if e["ativa"] else "não", _hora(e.get("ultimo")),
                            e.get("mm_1h"), e.get("mm_24h"), e.get("mm_72h"), e.get("nivel") or ""])
            for p in self.pluviometros():
                if operador or p.get("publico"):
                    w.writerow(["Physis", p["nome"], "sim" if p.get("ultimo") else "não", _hora(p.get("ultimo")),
                                p.get("mm_1h"), p.get("mm_24h"), p.get("mm_72h"), p.get("nivel") or ""])
        elif tipo == "bairros":
            w.writerow(["id", "nome", "risco", "tipo_geometria", "lon", "lat", "estacoes_cemaden", "ponto_rio"])
            for b in self.bairros():
                g = b["geometria"]
                c = g["coords"] if g["tipo"] == "ponto" else g["coords"][0][0]
                w.writerow([b["id"], b["nome"], NOMES_RISCO.get(b["risco"], b["risco"]), g["tipo"], c[0], c[1],
                            ", ".join(b["estacoes"]), b["rio"]])
        else:
            w.writerow(["bairro", "tipo", "nivel_atual", "nivel_maximo", "inicio", "atualizado", "fim", "valor", "fonte", "texto"])
            desde = 0.0 if operador else None
            for a in self.alertas(desde=desde, limite=5000):
                w.writerow([a["bairro_nome"], TIPOS_ALERTA.get(a["tipo"], a["tipo"]), NOMES_NIVEL[a["nivel"]],
                            NOMES_NIVEL.get(a["nivel_max"], a["nivel_max"]), _hora(a["inicio"]), _hora(a["atualizado"]),
                            _hora(a["fim"]), "" if a["valor"] is None else a["valor"], a["fonte"], a["texto"]])
        return "﻿" + buf.getvalue()


def rodar(mun: Municipio, parar: threading.Event, passo: float = 900.0) -> None:
    """Laço de fundo: consulta as fontes a cada 15 min (o CEMADEN atualiza a cada 10 a 15 min)."""
    while not parar.is_set():
        try:
            if mun.config():
                mun.consultar()
        except Exception:          # noqa: BLE001 — o laço não pode morrer
            pass
        parar.wait(passo)
