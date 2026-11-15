"""Base GIS de clima do lugar: o ponto e a grade da região, para os mapas de calor da plataforma.

Fonte aberta: NASA POWER (climatologia de longo prazo). Camadas: irradiação solar, chuva, temperatura
média e máxima, vento e umidade. O hub busca UMA vez por lugar e camada, guarda no banco e entrega sempre
do banco: a tela não chama a internet e, depois da primeira busca, tudo funciona sem internet.
"""
from __future__ import annotations

import json
import math
import os
import urllib.error

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
    return {"meses": meses, "anual": p.get("ANN")}


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


def ler_solo(j: dict) -> dict:
    """pH, argila e areia (%), carbono orgânico (g/kg) por profundidade; e o que isso diz para as plantas."""
    r = {}
    for camada in (j.get("properties") or {}).get("layers") or []:
        nome, fator = camada.get("name"), ((camada.get("unit_measure") or {}).get("d_factor") or 1)
        for d in camada.get("depths") or []:
            v = (d.get("values") or {}).get("mean")
            if v is not None:
                r.setdefault(nome, {})[d.get("label")] = round(v / fator, 2)
    if not r:
        raise ValueError("sem dados de solo")
    ph = (r.get("phh2o") or {}).get("0-5cm")
    argila, areia = (r.get("clay") or {}).get("0-5cm"), (r.get("sand") or {}).get("0-5cm")
    # argila e areia vêm em g/kg÷10 = %, conforme o fator da própria base
    textura = None
    if argila is not None and areia is not None:
        textura = "argiloso" if argila >= 35 else "arenoso" if areia >= 70 else "médio (franco)"
    return {"camadas": r, "ph": ph, "acido": ph is not None and ph < 5.5, "argila_pct": argila, "areia_pct": areia, "textura": textura}


class GisExtra:
    """Relevo, solo e rio do lugar, guardados no banco do hub (mesma tabela gis_cache)."""

    def __init__(self, base: "Irradiacao"):
        self.b = base

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

    def solo(self, lat: float, lon: float) -> dict:
        chave = f"solo:{round(lat, 3)}:{round(lon, 3)}"
        s = self.b._guardado(chave)
        if s is None:
            try:
                s = ler_solo(self.b.buscar(URL_SOLO.format(lat=round(lat, 4), lon=round(lon, 4))))
                self.b._guardar(chave, s)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                return {"ok": False, "avisos": [f"solo indisponível agora; o servidor tenta de novo na próxima abertura ({exc})"]}
        return {"ok": True, **s, "fonte": "SoilGrids 250 m (ISRIC), guardado no servidor"}

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
