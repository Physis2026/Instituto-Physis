"""Destinos de resíduos perto do lugar: aterros, lixões, cooperativas, ecopontos, PEVs, compostagem, RCC, ETE.

Fonte automática: OpenStreetMap pela Overpass API (dados © colaboradores do OpenStreetMap, licença ODbL).
O hub busca uma vez por lugar e raio, guarda na tabela gis_cache (a mesma do gis.py) e entrega do banco:
depois da primeira busca funciona sem internet. A cada 30 dias tenta renovar; se a Overpass estiver fora ou
ocupada, entrega o guardado e só tenta de novo depois de uma hora (para não insistir num serviço gratuito).

Bases nacionais (SINIR, IBGE/MUNIC, órgãos estaduais) não têm serviço aberto estável por coordenada: entram
por importação manual (CSV ou GeoJSON), com o esquema de importar_csv / importar_geojson. Ver docs/RESIDUOS_GIS.md.

O OpenStreetMap não diz se um aterro é sanitário, controlado ou lixão, nem se uma cooperativa está licenciada:
a categoria vem das etiquetas e do nome e precisa ser conferida (licença ambiental, CTF/IBAMA, MTR no SINIR).
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

URL_OVERPASS = "https://overpass-api.de/api/interpreter"
AGENTE = "PhysisHub/1.0"
RAIO_PADRAO, RAIO_MAX = 20.0, 50.0          # km (o máximo protege o serviço gratuito)
VALIDADE = 30 * 86400                        # renovar o guardado a cada 30 dias
ESPERA_FALHA = 3600                          # depois de uma falha, tentar de novo só após 1 hora
MAX_PONTOS = 800

# categoria -> (rótulo, grupo do mapa)
CATEGORIAS = {
    "aterro": ("Aterro (sanitário ou não informado)", "disposicao"),
    "aterro_controlado": ("Aterro controlado", "disposicao"),
    "lixao": ("Lixão (vazadouro a céu aberto)", "disposicao"),
    "transbordo": ("Estação de transbordo", "disposicao"),
    "cooperativa": ("Cooperativa ou associação de catadores", "reciclagem"),
    "reciclagem": ("Centro de reciclagem ou triagem", "reciclagem"),
    "ecoponto": ("Ecoponto", "reciclagem"),
    "pev": ("Ponto de entrega voluntária (PEV)", "reciclagem"),
    "sucata": ("Ferro-velho ou sucata", "reciclagem"),
    "compostagem": ("Compostagem", "organicos"),
    "rcc": ("Resíduos da construção (RCC, ATT)", "rcc"),
    "ete": ("Estação de tratamento de esgoto", "saneamento"),
}
# destino do plano de resíduos (RC_ROTAS[..].destino no painel) -> categorias que recebem
CATEGORIAS_POR_DESTINO = {
    "reciclagem": ["cooperativa", "reciclagem", "ecoponto", "sucata", "pev"],
    "reversa": ["ecoponto", "pev", "reciclagem"],
    "compostagem": ["compostagem"],
    "aterro2": ["aterro", "aterro_controlado", "transbordo"],
}
MATERIAIS = {"paper": "papel", "cardboard": "papelão", "plastic": "plástico", "plastic_bottles": "garrafas PET",
             "plastic_packaging": "embalagens plásticas", "glass": "vidro", "glass_bottles": "garrafas de vidro",
             "cans": "latas", "metal": "metal", "scrap_metal": "sucata", "aluminium": "alumínio",
             "batteries": "pilhas e baterias", "electrical_items": "eletroeletrônicos", "small_appliances": "pequenos eletrodomésticos",
             "cooking_oil": "óleo de cozinha", "engine_oil": "óleo lubrificante", "clothes": "roupas", "shoes": "calçados",
             "green_waste": "poda", "organic": "orgânicos", "wood": "madeira", "rubble": "entulho", "hardcore": "entulho",
             "tyres": "pneus", "light_bulbs": "lâmpadas", "fluorescent_tubes": "lâmpadas fluorescentes",
             "beverage_cartons": "longa vida", "styrofoam": "isopor"}
ESQUEMA_IMPORTACAO = ["nome", "categoria", "lat", "lon", "fonte", "municipio", "uf", "situacao", "licenca", "obs"]


def consulta_overpass(lat: float, lon: float, raio_km: float) -> str:
    r = int(raio_km * 1000)
    a = f"(around:{r},{lat:.5f},{lon:.5f})"
    return (f"[out:json][timeout:60];("
            f'nwr["landuse"="landfill"]{a};'
            f'nwr["amenity"="recycling"]{a};'
            f'nwr["amenity"="waste_transfer_station"]{a};'
            f'nwr["man_made"="wastewater_plant"]{a};'
            f'nwr["amenity"="composting"]{a};'
            f'nwr["industrial"~"^(scrap_yard|composting|recycling|waste_handling|construction_waste)$"]{a};'
            f'nwr["landuse"="industrial"]["name"~"(?i)(reciclag|cooperativa|entulho|compostag|sucata|ferro.velho)"]{a};'
            f");out center tags {MAX_PONTOS};")


def buscar_overpass(consulta: str, timeout: float = 90.0) -> dict:
    """POST educado à Overpass: User-Agent próprio, tempo limite, gzip."""
    url = os.environ.get("PHYSIS_OVERPASS_URL", URL_OVERPASS)
    corpo = urllib.parse.urlencode({"data": consulta}).encode()
    req = urllib.request.Request(url, data=corpo, headers={"User-Agent": AGENTE, "Accept": "application/json",
                                                           "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
        if r.headers.get("Content-Encoding", "").lower() == "gzip" or b[:2] == b"\x1f\x8b":
            b = gzip.decompress(b)
    return json.loads(b.decode("utf-8", errors="replace"))


# ═══════════════ Classificação ═══════════════

def _sim(v) -> bool:
    return str(v or "").lower() in ("yes", "sim", "true", "1")


def classificar(tags: dict) -> str | None:
    t = {k: str(v) for k, v in (tags or {}).items()}
    nome = (t.get("name", "") + " " + t.get("operator", "") + " " + t.get("description", "")).lower()
    if t.get("man_made") == "wastewater_plant":
        return "ete"
    if t.get("landuse") == "landfill":
        if "lixão" in nome or "lixao" in nome or "vazadouro" in nome:
            return "lixao"
        if "controlado" in nome:
            return "aterro_controlado"
        if t.get("landfill:waste") in ("construction", "rubble", "inert") or "entulho" in nome or "inerte" in nome:
            return "rcc"
        return "aterro"
    if t.get("amenity") == "waste_transfer_station":
        if "entulho" in nome or " att" in f" {nome}" or "constru" in nome:
            return "rcc"
        return "transbordo"
    if t.get("amenity") == "composting" or t.get("industrial") == "composting" or "compostag" in nome:
        return "compostagem"
    if t.get("industrial") == "construction_waste" or "entulho" in nome or "rcc" in nome.split():
        return "rcc"
    if t.get("industrial") == "scrap_yard" or "sucata" in nome or "ferro velho" in nome or "ferro-velho" in nome:
        return "sucata"
    if t.get("amenity") == "recycling" or t.get("industrial") in ("recycling", "waste_handling") or t.get("landuse") == "industrial":
        if "ecoponto" in nome or "eco ponto" in nome or "ecoparque" in nome:
            return "ecoponto"
        if "cooperativa" in nome or "associação" in nome or "associacao" in nome or "catador" in nome:
            return "cooperativa"
        if t.get("recycling_type") == "centre":
            if _sim(t.get("recycling:rubble")) or _sim(t.get("recycling:hardcore")):
                return "rcc"
            if _sim(t.get("recycling:green_waste")) and not any(_sim(t.get(f"recycling:{m}")) for m in ("paper", "plastic", "glass", "cans")):
                return "compostagem"
            return "reciclagem"
        if t.get("amenity") == "recycling":
            return "pev"
        return "reciclagem" if t.get("industrial") in ("recycling", "waste_handling") else None
    return None


def materiais(tags: dict) -> list[str]:
    return sorted({MATERIAIS[k.split(":", 1)[1]] for k, v in (tags or {}).items()
                   if k.startswith("recycling:") and k.split(":", 1)[1] in MATERIAIS and _sim(v)})


def ler_overpass(j: dict) -> list[dict]:
    """Elementos da Overpass -> pontos {id, nome, categoria, lat, lon, materiais, operador, ...}."""
    r = []
    for e in j.get("elements") or []:
        tags = e.get("tags") or {}
        cat = classificar(tags)
        if cat is None:
            continue
        la, lo = e.get("lat"), e.get("lon")
        if la is None and isinstance(e.get("center"), dict):
            la, lo = e["center"].get("lat"), e["center"].get("lon")
        if la is None or lo is None:
            continue
        r.append({"id": f"osm:{e.get('type', 'node')}/{e.get('id')}", "nome": tags.get("name") or None, "categoria": cat,
                  "lat": float(la), "lon": float(lo), "materiais": materiais(tags), "operador": tags.get("operator") or None,
                  "horario": tags.get("opening_hours") or None, "fonte": "OpenStreetMap"})
    return r


# ═══════════════ Distâncias, grupos e transporte ═══════════════

def haversine_km(la1: float, lo1: float, la2: float, lo2: float) -> float:
    R = 6371.0088
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def rumo_graus(la1: float, lo1: float, la2: float, lo2: float) -> float:
    p1, p2, dl = math.radians(la1), math.radians(la2), math.radians(lo2 - lo1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def agrupar(pontos: list[dict], lat: float, lon: float, raio_km: float) -> dict:
    """Distância (haversine) e rumo de cada ponto; só os dentro do raio, do mais perto ao mais longe; grupos por categoria."""
    lista = []
    for p in pontos:
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        if d <= raio_km:
            lista.append({**p, "dist_km": round(d, 3), "rumo": round(rumo_graus(lat, lon, p["lat"], p["lon"]))})
    lista.sort(key=lambda x: x["dist_km"])
    grupos = {}
    for p in lista:
        g = grupos.setdefault(p["categoria"], {"rotulo": CATEGORIAS.get(p["categoria"], (p["categoria"],))[0], "n": 0, "mais_proximo": p})
        g["n"] += 1
    return {"pontos": lista, "grupos": grupos}


def mais_proximo_para_destino(grupos: dict, destino: str) -> dict | None:
    cands = [grupos[c]["mais_proximo"] for c in CATEGORIAS_POR_DESTINO.get(destino, []) if c in grupos]
    return min(cands, key=lambda p: p["dist_km"]) if cands else None


def _diesel_premissa() -> float | None:
    """kgCO2e por litro de diesel da base de premissas (sistema/physis-premissas.json, id combustivel.diesel)."""
    for arq in (Path(__file__).resolve().parents[2] / "sistema" / "physis-premissas.json",
                Path(__file__).resolve().parents[1] / "web" / "physis-premissas.json"):
        try:
            for p in json.loads(arq.read_text(encoding="utf-8")).get("premissas", []):
                if p.get("id") == "combustivel.diesel":
                    return float(p["valor_padrao"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def co2_transporte(kg_mes: float, dist_km: float, fator_kg_tkm: float | None = None, consumo_km_l: float | None = None,
                   carga_t: float | None = None, ida_e_volta: bool = True, diesel_kg_l: float | None = None) -> dict:
    """CO₂ do transporte de um resíduo até o destino. Dois caminhos (o primeiro que tiver dado):
    1) fator por t·km: kgCO2e = (kg_mes/1000) · dist_km · fator_kg_tkm (distância carregada, só ida);
    2) por viagens de caminhão: viagens = ⌈t / carga⌉; litros = viagens · dist · (2 se ida e volta) / consumo;
       kgCO2e = litros · fator do diesel (premissa combustivel.diesel).
    Sem fator nem consumo e carga: devolve só as t·km, sem CO₂ (não inventamos o número)."""
    t = max(0.0, kg_mes) / 1000
    r = {"t_mes": t, "t_km": t * dist_km, "viagens": None, "litros": None, "kg_co2_mes": None, "metodo": None}
    if fator_kg_tkm:
        r.update(kg_co2_mes=r["t_km"] * fator_kg_tkm, metodo="fator por t·km")
    elif consumo_km_l and carga_t:
        diesel = diesel_kg_l if diesel_kg_l is not None else _diesel_premissa()
        if diesel is None:
            return r
        viagens = math.ceil(t / carga_t) if t > 0 else 0
        litros = viagens * dist_km * (2 if ida_e_volta else 1) / consumo_km_l
        r.update(viagens=viagens, litros=litros, kg_co2_mes=litros * diesel, metodo="viagens de caminhão a diesel")
    return r


# ═══════════════ Importação manual (SINIR, IBGE/MUNIC, órgãos estaduais) ═══════════════

def _validar(d: dict, origem: str) -> dict:
    cat = str(d.get("categoria") or "").strip().lower()
    if cat not in CATEGORIAS:
        raise ValueError(f"{origem}: categoria '{cat}' desconhecida (use: {', '.join(CATEGORIAS)})")
    try:
        la, lo = float(str(d.get("lat")).replace(",", ".")), float(str(d.get("lon")).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{origem}: lat e lon são obrigatórias e numéricas")
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        raise ValueError(f"{origem}: coordenadas inválidas")
    fonte = str(d.get("fonte") or "").strip()
    if not fonte:
        raise ValueError(f"{origem}: a fonte é obrigatória (ex.: SINIR 2024, MUNIC 2023, CETESB)")
    p = {"id": f"manual:{fonte}:{la:.5f},{lo:.5f}", "nome": (str(d.get("nome") or "").strip() or None), "categoria": cat,
         "lat": la, "lon": lo, "materiais": [], "operador": None, "horario": None, "fonte": fonte}
    for k in ("municipio", "uf", "situacao", "licenca", "obs"):
        v = str(d.get(k) or "").strip()
        if v:
            p[k] = v
    return p


def importar_csv(texto: str) -> list[dict]:
    """CSV com cabeçalho (vírgula ou ponto e vírgula). Colunas: nome, categoria, lat, lon, fonte (obrigatórias:
    categoria, lat, lon, fonte), municipio, uf, situacao, licenca, obs. Erro em qualquer linha recusa o arquivo."""
    amostra = texto[:2000]
    sep = ";" if amostra.count(";") > amostra.count(",") else ","
    leitor = csv.DictReader(io.StringIO(texto.lstrip("﻿")), delimiter=sep)
    return [_validar({(k or "").strip().lower(): v for k, v in linha.items()}, f"linha {i + 2}") for i, linha in enumerate(leitor)]


def importar_geojson(obj: dict) -> list[dict]:
    """FeatureCollection de pontos (ou polígonos: usa o centro da caixa). Propriedades com o mesmo esquema do CSV."""
    r = []
    for i, f in enumerate((obj or {}).get("features") or []):
        g = f.get("geometry") or {}
        c = g.get("coordinates")
        if g.get("type") == "Point":
            lo, la = c[0], c[1]
        elif g.get("type") in ("Polygon", "MultiPolygon", "LineString", "MultiPoint"):
            pts = []

            def achatar(x):
                if isinstance(x, (list, tuple)) and x and isinstance(x[0], (int, float)):
                    pts.append(x)
                elif isinstance(x, (list, tuple)):
                    for y in x:
                        achatar(y)
            achatar(c)
            if not pts:
                raise ValueError(f"feição {i + 1}: geometria vazia")
            lo = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
            la = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2
        else:
            raise ValueError(f"feição {i + 1}: geometria {g.get('type')} não suportada")
        r.append(_validar({**(f.get("properties") or {}), "lat": la, "lon": lo}, f"feição {i + 1}"))
    return r


# ═══════════════ Serviço guardado no hub ═══════════════

class ResiduosGis:
    """Destinos de resíduos em volta do lugar, guardados no banco do hub (tabela gis_cache)."""

    CHAVE_MANUAL = "residuos_manual"

    def __init__(self, base, buscar=buscar_overpass):
        self.b, self.buscar = base, buscar

    def importar(self, pontos: list[dict], substituir_fonte: bool = True) -> dict:
        """Guarda os pontos importados; reimportar a mesma fonte substitui os dela."""
        atuais = self.b._guardado(self.CHAVE_MANUAL) or []
        fontes = {p["fonte"] for p in pontos}
        if substituir_fonte:
            atuais = [p for p in atuais if p.get("fonte") not in fontes]
        self.b._guardar(self.CHAVE_MANUAL, atuais + pontos)
        return {"ok": True, "importados": len(pontos), "total": len(atuais) + len(pontos)}

    def consultar(self, lat: float, lon: float, raio_km: float = RAIO_PADRAO) -> dict:
        if not (-35.0 <= lat <= 6.0 and -75.0 <= lon <= -28.0):
            return {"ok": False, "erro": "coordenadas fora do Brasil"}
        raio = max(1.0, min(float(raio_km or RAIO_PADRAO), RAIO_MAX))
        # chave por ~1 km e raio arredondado para cima a 5 km: vizinhos e raios menores usam a mesma busca
        rb = min(RAIO_MAX, math.ceil(raio / 5) * 5)
        la, lo = round(lat, 2), round(lon, 2)
        chave, chave_falha = f"residuos:{la}:{lo}:{rb:g}", f"residuos_falha:{la}:{lo}:{rb:g}"
        g, agora, avisos = self.b._guardado(chave), self.b.hub.relogio(), []
        # uma busca guardada com raio maior também serve
        if g is None:
            for r2 in range(int(rb) + 5, int(RAIO_MAX) + 1, 5):
                g = self.b._guardado(f"residuos:{la}:{lo}:{r2:g}")
                if g is not None:
                    break
        velho = g is None or agora - g.get("quando", 0) > VALIDADE
        falha = self.b._guardado(chave_falha)
        if velho and falha and agora - falha.get("quando", 0) < ESPERA_FALHA:
            avisos.append("OpenStreetMap indisponível há pouco; o servidor tenta de novo depois de uma hora")
        elif velho:
            try:
                pts = ler_overpass(self.buscar(consulta_overpass(la, lo, rb + 1.5)))
                g = {"quando": agora, "pontos": pts}
                self.b._guardar(chave, g)
            except urllib.error.HTTPError as exc:
                self.b._guardar(chave_falha, {"quando": agora})
                avisos.append("Overpass ocupada (limite de uso); o servidor tenta de novo depois de uma hora"
                              if exc.code in (429, 503, 504) else f"OpenStreetMap indisponível agora ({exc})")
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                self.b._guardar(chave_falha, {"quando": agora})
                avisos.append(f"OpenStreetMap indisponível agora; o servidor tenta de novo depois de uma hora ({exc})")
        manuais = self.b._guardado(self.CHAVE_MANUAL) or []
        if g is None and not manuais:
            return {"ok": False, "lat": lat, "lon": lon, "raio_km": raio, "pontos": [], "grupos": {}, "avisos": avisos}
        ag = agrupar((g or {}).get("pontos", []) + manuais, lat, lon, raio)
        fontes = (["OpenStreetMap via Overpass API (© colaboradores do OpenStreetMap, ODbL)"] if g else []) + \
            sorted({p["fonte"] for p in manuais if p["fonte"] != "OpenStreetMap"})
        avisos.append("categorias deduzidas das etiquetas e do nome no OpenStreetMap: conferir a licença ambiental "
                      "e o cadastro no SINIR antes de contratar")
        return {"ok": True, "lat": lat, "lon": lon, "raio_km": raio, **ag,
                "categorias": {k: v[0] for k, v in CATEGORIAS.items()},
                "destinos": {d: mais_proximo_para_destino(ag["grupos"], d) for d in CATEGORIAS_POR_DESTINO},
                "atualizado": (g or {}).get("quando"), "fonte": " + ".join(fontes) + "; guardado no servidor",
                "atribuicao": "© colaboradores do OpenStreetMap" if g else None, "avisos": avisos}
