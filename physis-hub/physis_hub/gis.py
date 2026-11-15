"""Base GIS de clima do lugar: o ponto e a grade da região, para os mapas de calor da plataforma.

Fonte aberta: NASA POWER (climatologia de longo prazo). Camadas: irradiação solar, chuva, temperatura
média e máxima, vento e umidade. O hub busca UMA vez por lugar e camada, guarda no banco e entrega sempre
do banco: a tela não chama a internet e, depois da primeira busca, tudo funciona sem internet.
"""
from __future__ import annotations

import json
import math
import os
import struct
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor

from .clima import buscar_json

MESES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
# camada -> (parâmetro NASA POWER, nome, unidade)
CAMADAS = {"irradiacao": ("ALLSKY_SFC_SW_DWN", "Irradiação solar", "kWh/m²·dia"),
           "chuva": ("PRECTOTCORR", "Chuva", "mm/dia"),
           "temperatura": ("T2M", "Temperatura média", "°C"),
           "tmax": ("T2M_MAX", "Temperatura máxima extrema", "°C"),
           "vento": ("WS2M", "Vento a 2 m", "m/s"),
           "umidade": ("RH2M", "Umidade relativa", "%")}
URL_PONTO = ("https://power.larc.nasa.gov/api/temporal/climatology/point?parameters={par}"
             "&community=RE&longitude={lon}&latitude={lat}&format=JSON")
URL_REGIAO = ("https://power.larc.nasa.gov/api/temporal/climatology/regional?parameters={par}"
              "&community=RE&latitude-min={la0}&latitude-max={la1}&longitude-min={lo0}&longitude-max={lo1}&format=JSON")
RAIO = 2.5          # graus em volta do lugar
ESQUEMA = "CREATE TABLE IF NOT EXISTS gis_cache (chave TEXT PRIMARY KEY, dados TEXT NOT NULL, quando REAL NOT NULL);"


def _arred(v: float) -> float:
    return round(float(v) * 4) / 4          # 0,25°: lugares vizinhos usam a mesma busca guardada


def ler_ponto(j: dict, par: str = "ALLSKY_SFC_SW_DWN") -> dict:
    p = ((j.get("properties") or {}).get("parameter") or {}).get(par) or {}
    meses = [p.get(m) for m in MESES]
    if any(v is None or v <= -999 for v in meses):
        raise ValueError("série incompleta")
    c = (j.get("geometry") or {}).get("coordinates") or []
    out = {"meses": meses, "anual": p.get("ANN")}
    if len(c) >= 3 and isinstance(c[2], (int, float)):
        out["elev"] = c[2]          # altitude média da célula da NASA (para corrigir a temperatura pela altitude real)
    return out


def ler_regiao(j: dict, par: str = "ALLSKY_SFC_SW_DWN") -> list[dict]:
    r = []
    for f in j.get("features") or []:
        c = (f.get("geometry") or {}).get("coordinates") or []
        v = (((f.get("properties") or {}).get("parameter") or {}).get(par) or {}).get("ANN")
        if len(c) >= 2 and v is not None and v > -999:
            r.append({"lon": c[0], "lat": c[1], "anual": v})
    return r


class Irradiacao:
    """Clima do lugar por camada (o nome ficou da primeira camada, a irradiação solar)."""

    def __init__(self, hub, buscar=buscar_json):
        self.hub, self.buscar = hub, buscar
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    def _guardado(self, chave: str):
        r = self.hub._db.execute("SELECT dados FROM gis_cache WHERE chave=?", (chave,)).fetchone()
        return json.loads(r[0]) if r else None

    def _guardar(self, chave: str, dados) -> None:
        with self.hub._trava:
            self.hub._db.execute("INSERT INTO gis_cache(chave,dados,quando) VALUES(?,?,?) ON CONFLICT(chave) DO UPDATE SET "
                                 "dados=excluded.dados, quando=excluded.quando", (chave, json.dumps(dados), self.hub.relogio()))
            self.hub._db.commit()

    def consultar(self, lat: float, lon: float, camada: str = "irradiacao") -> dict:
        if camada not in CAMADAS:
            return {"ok": False, "erro": "camada desconhecida"}
        if not (-35.0 <= lat <= 6.0 and -75.0 <= lon <= -28.0):
            return {"ok": False, "erro": "coordenadas fora do Brasil"}
        par, nome, un = CAMADAS[camada]
        la, lo = _arred(lat), _arred(lon)
        pre = "" if camada == "irradiacao" else camada + ":"      # mantém a chave antiga da irradiação
        cp, cr = f"{pre}ponto:{la}:{lo}", f"{pre}regiao:{round(la)}:{round(lo)}"
        ponto, regiao, avisos = self._guardado(cp), self._guardado(cr), []
        if ponto is None:
            try:
                ponto = ler_ponto(self.buscar(os.environ.get("PHYSIS_GIS_PONTO_URL", URL_PONTO).format(par=par, lat=la, lon=lo)), par)
                self._guardar(cp, ponto)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                avisos.append(f"dado do ponto indisponível agora ({exc})")
        if regiao is None:
            try:
                c0, c1 = round(la), round(lo)
                regiao = ler_regiao(self.buscar(os.environ.get("PHYSIS_GIS_REGIAO_URL", URL_REGIAO).format(
                    par=par, la0=c0 - RAIO, la1=c0 + RAIO, lo0=c1 - RAIO, lo1=c1 + RAIO)), par)
                if regiao:
                    self._guardar(cr, regiao)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                avisos.append(f"grade da região indisponível agora ({exc})")
        return {"ok": ponto is not None or bool(regiao), "lat": lat, "lon": lon, "camada": camada, "nome": nome, "unidade": un,
                "ponto": ponto, "regiao": regiao or [], "fonte": f"NASA POWER (climatologia de longo prazo: {nome.lower()}, {un})",
                "avisos": avisos}


# ── Relevo (curvas de nível e declividade), solo e enchente ───────────────────────────────────────
URL_ELEVACAO = "https://api.open-meteo.com/v1/elevation?latitude={lats}&longitude={lons}"          # Copernicus DEM 90 m
URL_SOLO = ("https://rest.isric.org/soilgrids/v2.0/properties/query?lon={lon}&lat={lat}&property=phh2o&property=clay"
            "&property=sand&property=soc&depth=0-5cm&depth=5-15cm&depth=15-30cm&value=mean")                    # SoilGrids (ISRIC)
URL_RIO = "https://flood-api.open-meteo.com/v1/flood?latitude={lat}&longitude={lon}&daily=river_discharge,river_discharge_max&forecast_days=16"
URL_RIO_HIST = "https://flood-api.open-meteo.com/v1/flood?latitude={lat}&longitude={lon}&daily=river_discharge&start_date=2000-01-01&end_date=2024-12-31"
PASSO_RELEVO = 0.002          # ~220 m entre pontos; grade 10 x 10 (~2 km de lado)


def percentil(vals: list[float], p: float) -> float | None:
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * p
    i = int(k)
    return v[i] if i + 1 >= len(v) else v[i] + (v[i + 1] - v[i]) * (k - i)


def buscar_bytes(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "PhysisHub/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ── Solo: duas bases abertas, as duas guardadas no servidor ──
# 1) SoilGrids 250 m (ISRIC) pelo serviço de mapas WCS: responde em ~1 s (o serviço REST antigo leva ~20 s ou cai,
#    e fica só como reserva). Propriedades: pH, argila, areia, silte, carbono orgânico, nitrogênio e CTC, em 3 profundidades.
# 2) Pedologia do Brasil 1:250.000 (IBGE, BDiA): a classe de solo brasileira (SiBCS) do polígono onde o ponto cai.
URL_SOLO_WCS = ("https://maps.isric.org/mapserv?map=/map/{prop}.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage"
                "&COVERAGEID={prop}_{prof}_mean&FORMAT=image/tiff&SUBSET=long({lo0},{lo1})&SUBSET=lat({la0},{la1})"
                "&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326")
URL_SOLO_IBGE = ("https://geoservicos.ibge.gov.br/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=BDIA:pedo_area"
                 "&outputFormat=application/json&maxFeatures=1&propertyName=legenda,ordem,subordem,grande_gru,subgrupos,textura,"
                 "horizonte,relevo,erosao,pedregosid,rochosidad,leg_ordem,legenda_2&CQL_FILTER=INTERSECTS(geom,POINT({lon}%20{lat}))")
# propriedade -> (fator que divide o valor guardado, unidade); conforme a documentação do SoilGrids
SOLO_PROPS = {"phh2o": (10, "pH"), "clay": (10, "%"), "sand": (10, "%"), "silt": (10, "%"), "soc": (10, "g/kg"),
              "nitrogen": (100, "g/kg"), "cec": (10, "cmol(c)/kg")}
SOLO_PROFS = ("0-5cm", "5-15cm", "15-30cm")
VERSAO_SOLO = 2          # muda a chave guardada: lugares buscados na base antiga são buscados de novo


def ler_tiff(b: bytes) -> tuple[int, int, list, float | None]:
    """Leitor mínimo de GeoTIFF (faixas ou blocos, sem compressão ou deflate). Devolve largura, altura, valores e 'sem dado'."""
    bo = "<" if b[:2] == b"II" else ">" if b[:2] == b"MM" else None
    if bo is None or struct.unpack(bo + "H", b[2:4])[0] != 42:
        raise ValueError("não é TIFF")
    tam = {1: 1, 2: 1, 3: 2, 4: 4, 6: 1, 7: 1, 8: 2, 9: 4, 11: 4, 12: 8, 16: 8}
    fmt = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i", 11: "f", 12: "d", 16: "Q"}
    ifd = struct.unpack(bo + "I", b[4:8])[0]
    n, tags = struct.unpack(bo + "H", b[ifd:ifd + 2])[0], {}
    for i in range(n):
        e = ifd + 2 + 12 * i
        tag, tipo, qtd = struct.unpack(bo + "HHI", b[e:e + 8])
        sz = tam.get(tipo, 1) * qtd
        vo = e + 8 if sz <= 4 else struct.unpack(bo + "I", b[e + 8:e + 12])[0]
        if tipo == 2:
            tags[tag] = b[vo:vo + sz].split(b"\0")[0].decode("ascii", "replace")
        elif tipo in fmt:
            tags[tag] = list(struct.unpack(bo + fmt[tipo] * qtd, b[vo:vo + sz]))
    w, h = tags[256][0], tags[257][0]
    bits, comp = tags.get(258, [16])[0], tags.get(259, [1])[0]
    sf, pred = tags.get(339, [1])[0], tags.get(317, [1])[0]
    cod = {(8, 1): "B", (8, 2): "b", (16, 1): "H", (16, 2): "h", (32, 1): "I", (32, 2): "i", (32, 3): "f", (64, 3): "d"}.get((bits, sf))
    if cod is None or comp not in (1, 8, 32946):
        raise ValueError("formato de TIFF não suportado")
    tw, th = (tags[322][0], tags[323][0]) if 324 in tags else (w, tags.get(278, [h])[0])
    offs, cnts = tags.get(324) or tags.get(273), tags.get(325) or tags.get(279)
    grade = [None] * (w * h)
    por_linha = (w + tw - 1) // tw
    for k, (o, c) in enumerate(zip(offs, cnts)):
        bruto = b[o:o + c]
        if comp != 1:
            bruto = zlib.decompress(bruto)
        cw, sz = tw, struct.calcsize(cod)
        m = len(bruto) // sz
        cel = list(struct.unpack(f"{bo}{m}{cod}", bruto[:m * sz]))
        if pred == 2 and cod not in "fd":
            for li in range(len(cel) // cw):
                for x in range(1, cw):
                    cel[li * cw + x] += cel[li * cw + x - 1]
        x0, y0 = ((k % por_linha) * tw, (k // por_linha) * th) if 324 in tags else (0, k * th)
        for i, v in enumerate(cel):
            x, y = x0 + i % cw, y0 + i // cw
            if x < w and y < h:
                grade[y * w + x] = v
    nd = tags.get(42113)
    try:
        nd = float(nd) if nd not in (None, "") else None
    except ValueError:
        nd = None
    return w, h, grade, nd


def valor_tiff(b: bytes) -> float | None:
    """Média dos pixels válidos da pequena janela em volta do ponto."""
    _, _, g, nd = ler_tiff(b)
    # 0 é a máscara do SoilGrids (área urbana, água, rocha): não entra na média
    v = [x for x in g if x is not None and x != nd and x not in (0, -32768) and not (isinstance(x, float) and math.isnan(x))]
    return sum(v) / len(v) if v else None


def ler_pedologia(j: dict) -> dict | None:
    """Classe de solo do IBGE (SiBCS). Área urbana ou corpo d'água vêm sem classe."""
    f = (j.get("features") or [None])[0]
    if not f:
        return None
    p = {k: " ".join(str(v).split()) if isinstance(v, str) and v.strip() else None for k, v in (f.get("properties") or {}).items()}
    tit = lambda s: s.capitalize() if s else None
    return {"classe": tit(p.get("legenda_2") or p.get("legenda")), "ordem": tit(p.get("ordem") or p.get("leg_ordem")),
            "subordem": tit(p.get("subordem")), "grande_grupo": tit(p.get("grande_gru")), "textura": p.get("textura"),
            "horizonte": p.get("horizonte"), "relevo": p.get("relevo"), "erosao": p.get("erosao"),
            "pedregosidade": p.get("pedregosid"), "rochosidade": p.get("rochosidad"), "legenda": p.get("legenda"),
            "urbano_ou_agua": (p.get("leg_ordem") or "").upper() == "OUTROS"}


def ler_solo(j: dict) -> dict:
    """pH, argila e areia (%), carbono orgânico (g/kg) por profundidade; e o que isso diz para as plantas.
    Aceita a resposta do serviço REST do SoilGrids ou o dicionário {propriedade: {profundidade: valor}} já convertido."""
    r = {}
    if "properties" in j:
        for camada in (j.get("properties") or {}).get("layers") or []:
            nome, fator = camada.get("name"), ((camada.get("unit_measure") or {}).get("d_factor") or 1)
            for d in camada.get("depths") or []:
                v = (d.get("values") or {}).get("mean")
                if v is not None:
                    r.setdefault(nome, {})[d.get("label")] = round(v / fator, 2)
    else:
        r = {k: dict(v) for k, v in j.items() if isinstance(v, dict) and v}
    if not r:
        raise ValueError("sem dados de solo")
    ph = (r.get("phh2o") or {}).get("0-5cm")
    argila, areia = (r.get("clay") or {}).get("0-5cm"), (r.get("sand") or {}).get("0-5cm")
    # argila e areia vêm em g/kg÷10 = %, conforme o fator da própria base
    textura = None
    if argila is not None and areia is not None:
        textura = "argiloso" if argila >= 35 else "arenoso" if areia >= 70 else "médio (franco)"
    sup = lambda k: (r.get(k) or {}).get("0-5cm")
    return {"camadas": r, "ph": ph, "acido": ph is not None and ph < 5.5, "argila_pct": argila, "areia_pct": areia,
            "silte_pct": sup("silt"), "carbono_gkg": sup("soc"), "nitrogenio_gkg": sup("nitrogen"), "ctc": sup("cec"),
            "textura": textura}


class GisExtra:
    """Relevo, solo e rio do lugar, guardados no banco do hub (mesma tabela gis_cache)."""

    def __init__(self, base: "Irradiacao", buscar_bytes=buscar_bytes):
        self.b, self.buscar_bytes = base, buscar_bytes

    def _soilgrids(self, lat: float, lon: float) -> dict:
        """As 21 janelas (7 propriedades x 3 profundidades) em paralelo pelo WCS; se o WCS falhar todo, o REST antigo."""
        d = 0.003          # ~300 m: a janela pega o pixel de 250 m do ponto e os vizinhos
        pedidos = [(p, pr) for p in SOLO_PROPS for pr in SOLO_PROFS]

        def um(par):
            p, pr = par
            try:
                v = valor_tiff(self.buscar_bytes(URL_SOLO_WCS.format(prop=p, prof=pr, lo0=lon - d, lo1=lon + d, la0=lat - d, la1=lat + d)))
                return p, pr, None if v is None else round(v / SOLO_PROPS[p][0], 2), True
            except (urllib.error.URLError, OSError, ValueError, KeyError, struct.error, zlib.error):
                return p, pr, None, False
        with ThreadPoolExecutor(max_workers=7) as ex:
            res = list(ex.map(um, pedidos))
        tab = {}
        for p, pr, v, _ in res:
            if v is not None:
                tab.setdefault(p, {})[pr] = v
        if tab:
            return ler_solo(tab)
        if any(ok for *_, ok in res):          # o serviço respondeu, mas o ponto não é mapeado (resposta guardada)
            return {"sem_mapa": True}
        return ler_solo(self.b.buscar(URL_SOLO.format(lat=round(lat, 4), lon=round(lon, 4))))

    def relevo(self, lat: float, lon: float) -> dict:
        la, lo = round(lat, 3), round(lon, 3)
        chave = f"relevo:{la}:{lo}"
        g = self.b._guardado(chave)
        if g is None:
            lats = [round(la + (4.5 - i) * PASSO_RELEVO, 5) for i in range(10) for _ in range(10)]
            lons = [round(lo + (j - 4.5) * PASSO_RELEVO, 5) for _ in range(10) for j in range(10)]
            try:
                j = self.b.buscar(URL_ELEVACAO.format(lats=",".join(map(str, lats)), lons=",".join(map(str, lons))))
                elev = j.get("elevation") or []
                if len(elev) != 100:
                    raise ValueError("grade incompleta")
                g = {"n": 10, "passo_graus": PASSO_RELEVO, "lat0": la, "lon0": lo, "elev": elev}
                self.b._guardar(chave, g)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                return {"ok": False, "avisos": [f"relevo indisponível agora ({exc})"]}
        # declividade média e máxima entre vizinhos (m por m), para APP (> 45°) e encosta (> 30%)
        e, n = g["elev"], g["n"]
        dx = PASSO_RELEVO * 111320 * math.cos(math.radians(la)); dy = PASSO_RELEVO * 110540
        decl = []
        for i in range(n):
            for k in range(n):
                if k + 1 < n:
                    decl.append(abs(e[i * n + k + 1] - e[i * n + k]) / dx)
                if i + 1 < n:
                    decl.append(abs(e[(i + 1) * n + k] - e[i * n + k]) / dy)
        return {"ok": True, **g, "min": min(e), "max": max(e), "decl_media_pct": round(sum(decl) / len(decl) * 100, 1),
                "decl_max_pct": round(max(decl) * 100, 1), "fonte": "Copernicus DEM 90 m (via Open-Meteo), guardado no servidor"}

    def solo_grade(self, lat: float, lon: float, prop: str = "phh2o", prof: str = "0-5cm", raio: float = 0.02) -> dict:
        """Mapa de solo da região: grade do SoilGrids (250 m) em volta do ponto, para o mapa de calor."""
        if prop not in SOLO_PROPS or prof not in SOLO_PROFS:
            return {"ok": False, "erro": "propriedade ou profundidade desconhecida"}
        raio = min(max(float(raio), 0.005), 0.05)        # até ~11 km para cada lado
        la, lo = round(lat, 3), round(lon, 3)
        chave = f"solo_grade:{prop}:{prof}:{la}:{lo}:{raio}"
        g = self.b._guardado(chave)
        if g is None:
            try:
                w, h, cel, nd = ler_tiff(self.buscar_bytes(URL_SOLO_WCS.format(prop=prop, prof=prof, lo0=lo - raio, lo1=lo + raio,
                                                                               la0=la - raio, la1=la + raio)))
                fator = SOLO_PROPS[prop][0]
                vals = [None if (x is None or x == nd or x in (0, -32768)) else round(x / fator, 2) for x in cel]
                g = {"largura": w, "altura": h, "valores": vals, "lat0": la + raio, "lon0": lo - raio,
                     "passo_lat": 2 * raio / h, "passo_lon": 2 * raio / w}
                self.b._guardar(chave, g)
            except (urllib.error.URLError, OSError, ValueError, KeyError, struct.error, zlib.error) as exc:
                return {"ok": False, "avisos": [f"mapa de solo indisponível agora ({exc})"]}
        v = [x for x in g["valores"] if x is not None]
        return {"ok": bool(v), **g, "propriedade": prop, "profundidade": prof, "unidade": SOLO_PROPS[prop][1],
                "min": min(v) if v else None, "max": max(v) if v else None,
                "fonte": "SoilGrids 250 m (ISRIC, serviço de mapas), guardado no servidor",
                "avisos": [] if v else ["sem dado de solo nesta região (área urbana, água ou rocha)"]}

    def solo(self, lat: float, lon: float) -> dict:
        """Propriedades (SoilGrids) e classe brasileira (IBGE). Cada parte é guardada à parte: a que vier fica,
        a que falhar é buscada de novo na próxima abertura."""
        la, lo, avisos = round(lat, 3), round(lon, 3), []
        ck_sg, ck_ib = f"solo{VERSAO_SOLO}:{la}:{lo}", f"pedologia:{la}:{lo}"
        s, ped = self.b._guardado(ck_sg), self.b._guardado(ck_ib)
        if s is None:
            try:
                s = self._soilgrids(la, lo)
                self.b._guardar(ck_sg, s)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                avisos.append(f"propriedades do solo (SoilGrids) indisponíveis agora; o servidor tenta de novo na próxima abertura ({exc})")
        if ped is None:
            try:
                ped = ler_pedologia(self.b.buscar(URL_SOLO_IBGE.format(lat=la, lon=lo))) or {}
                self.b._guardar(ck_ib, ped)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                avisos.append(f"classe de solo do IBGE indisponível agora ({exc})")
        if s and s.get("sem_mapa"):
            avisos.append("o SoilGrids não mapeia este ponto (área urbana, água ou rocha): confirme com análise de solo")
            s = None
        if s is None and not ped:
            return {"ok": False, "avisos": avisos or ["solo indisponível agora"]}
        fontes = (["SoilGrids 250 m (ISRIC, serviço de mapas)"] if s else []) + (["Pedologia do Brasil 1:250.000 (IBGE, BDiA)"] if ped else [])
        return {"ok": True, **(s or {}), "pedologia": ped or None, "avisos": avisos,
                "fonte": " + ".join(fontes) + ", guardado no servidor"}

    def rio(self, lat: float, lon: float) -> dict:
        la, lo = round(lat, 2), round(lon, 2)
        hist = self.b._guardado(f"rio_hist:{la}:{lo}")
        avisos = []
        if hist is None:
            try:
                d = (self.b.buscar(URL_RIO_HIST.format(lat=la, lon=lo)).get("daily") or {}).get("river_discharge") or []
                vals = [x for x in d if x is not None]
                if not vals:
                    raise ValueError("sem histórico de vazão")
                hist = {"dias": len(vals), "media": round(sum(vals) / len(vals), 2), "p90": round(percentil(vals, 0.9), 2),
                        "p99": round(percentil(vals, 0.99), 2), "max": max(vals)}
                self.b._guardar(f"rio_hist:{la}:{lo}", hist)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                avisos.append(f"histórico do rio indisponível agora ({exc})")
        # previsão: guardada por 6 horas (muda todo dia)
        prev = self.b._guardado(f"rio_prev:{la}:{lo}")
        agora = self.b.hub.relogio()
        if prev is None or agora - prev.get("quando", 0) > 6 * 3600:
            try:
                d = self.b.buscar(URL_RIO.format(lat=la, lon=lo)).get("daily") or {}
                prev = {"quando": agora, "dias": d.get("time") or [], "vazao": d.get("river_discharge") or [], "vazao_max": d.get("river_discharge_max") or []}
                self.b._guardar(f"rio_prev:{la}:{lo}", prev)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                avisos.append(f"previsão do rio indisponível agora ({exc})")
        nivel = None
        if hist and prev and prev.get("vazao"):
            # o alerta usa a previsão central; o pior cenário (máximo entre os membros) só é mostrado
            pico = max((x for x in prev["vazao"] if x is not None), default=None)
            if pico is not None:
                nivel = "alerta" if pico >= hist["p99"] else "atencao" if pico >= hist["p90"] else "normal"
        return {"ok": bool(hist or prev), "historico": hist, "previsao": prev, "nivel": nivel, "avisos": avisos,
                "fonte": "GloFAS (Copernicus), rio mais próximo em grade de ~5 km, via Open-Meteo; histórico 2000–2024 guardado no servidor"}


# ═══════════════ Hidrografia (rios e nascentes) instalada no servidor (15/11/2026) ═══════════════
# O arquivo GeoJSON fica no servidor (caminho em PHYSIS_HIDROGRAFIA), gerado por ferramentas/hidrografia_servidor.py a
# partir da base oficial que o engenheiro baixa (Base Hidrográfica Ottocodificada da ANA [CONFERIR o produto e o link]).
# Nada é buscado na internet: sem o arquivo, a resposta diz sem_camada e o Planejador segue com o rio digitado.
MAX_BBOX_GRAUS = 0.25        # janela máxima pedida (≈ 27 km): o Planejador pede o lote com folga
MAX_FEICOES = 400            # teto de feições por resposta
MAX_PONTOS = 20000           # teto de vértices por resposta
_HIDRO_CACHE: dict = {}


def _hidro_ler(caminho: str) -> dict | None:
    try:
        st = os.stat(caminho)
    except OSError:
        return None
    c = _HIDRO_CACHE.get(caminho)
    if c and c[0] == st.st_mtime:
        return c[1]
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    _HIDRO_CACHE[caminho] = (st.st_mtime, dados)
    return dados


def _dentro(p, b) -> bool:
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def _recortar_linha(coords: list, b) -> list[list]:
    """Recorta a linha na janela: guarda os trechos com vértice dentro (mais o vértice vizinho, para a linha cruzar a borda)."""
    partes, atual = [], []
    for i, p in enumerate(coords):
        dentro = _dentro(p, b)
        viz = (i > 0 and _dentro(coords[i - 1], b)) or (i + 1 < len(coords) and _dentro(coords[i + 1], b))
        if dentro or viz:
            atual.append([round(float(p[0]), 6), round(float(p[1]), 6)])
        elif atual:
            if len(atual) >= 2:
                partes.append(atual)
            atual = []
    if len(atual) >= 2:
        partes.append(atual)
    return partes


def hidrografia(bbox, caminho: str | None = None) -> dict:
    """Rios (linhas) e nascentes (pontos) dentro de bbox = (lon_min, lat_min, lon_max, lat_max).
    Propriedades lidas: nome (ou name), largura_m (se a base trouxer; o Planejador pede a largura quando falta)."""
    caminho = caminho or os.environ.get("PHYSIS_HIDROGRAFIA", "")
    try:
        b = [float(x) for x in bbox]
    except (TypeError, ValueError):
        return {"ok": False, "erro": "bbox = lon_min,lat_min,lon_max,lat_max"}
    if len(b) != 4 or b[0] >= b[2] or b[1] >= b[3]:
        return {"ok": False, "erro": "bbox = lon_min,lat_min,lon_max,lat_max"}
    if b[2] - b[0] > MAX_BBOX_GRAUS or b[3] - b[1] > MAX_BBOX_GRAUS:
        return {"ok": False, "erro": f"janela grande demais (máximo {MAX_BBOX_GRAUS}° de lado)"}
    if not caminho or not os.path.isfile(caminho):
        return {"ok": False, "sem_camada": True, "erro": "camada de hidrografia não instalada neste servidor"}
    try:
        dados = _hidro_ler(caminho) or {}
    except (OSError, ValueError):
        return {"ok": False, "erro": "arquivo de hidrografia ilegível"}
    feats = dados.get("features") or []
    rios, nascentes, pontos, cortado = [], [], 0, False
    for f in feats:
        g = (f or {}).get("geometry") or {}
        pr = (f or {}).get("properties") or {}
        nome = str(pr.get("nome") or pr.get("name") or "")[:120]
        larg = pr.get("largura_m")
        larg = float(larg) if isinstance(larg, (int, float)) and larg > 0 else None
        if g.get("type") == "Point":
            c = g.get("coordinates") or []
            if len(c) >= 2 and _dentro(c, b):
                nascentes.append({"nome": nome, "lon": round(float(c[0]), 6), "lat": round(float(c[1]), 6)})
        elif g.get("type") in ("LineString", "MultiLineString"):
            linhas = [g.get("coordinates") or []] if g["type"] == "LineString" else (g.get("coordinates") or [])
            for l in linhas:
                for parte in _recortar_linha(l, b):
                    rios.append({"nome": nome, "largura_m": larg, "coords": parte})
                    pontos += len(parte)
        if len(rios) + len(nascentes) >= MAX_FEICOES or pontos >= MAX_PONTOS:
            cortado = True
            break
    return {"ok": True, "rios": rios, "nascentes": nascentes, "cortado": cortado,
            "fonte": str(dados.get("fonte") or "hidrografia instalada no servidor"), "bbox": b}

