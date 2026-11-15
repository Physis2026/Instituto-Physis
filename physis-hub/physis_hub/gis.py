"""Base GIS de irradiação solar: o ponto do lugar e a grade da região, para o mapa de calor da Energia solar.

Fonte aberta: NASA POWER (climatologia de irradiação global horizontal, ALLSKY_SFC_SW_DWN, kWh/m²·dia,
média de longo prazo). O hub busca UMA vez por lugar, guarda no banco e entrega sempre do banco: a tela
não chama a internet e, depois da primeira busca, tudo funciona sem internet.
"""
from __future__ import annotations

import json
import os
import urllib.error

from .clima import buscar_json

MESES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
URL_PONTO = ("https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=ALLSKY_SFC_SW_DWN"
             "&community=RE&longitude={lon}&latitude={lat}&format=JSON")
URL_REGIAO = ("https://power.larc.nasa.gov/api/temporal/climatology/regional?parameters=ALLSKY_SFC_SW_DWN"
              "&community=RE&latitude-min={la0}&latitude-max={la1}&longitude-min={lo0}&longitude-max={lo1}&format=JSON")
RAIO = 2.5          # graus em volta do lugar (a grade da NASA POWER tem cerca de 0,5° a 1°)
ESQUEMA = "CREATE TABLE IF NOT EXISTS gis_cache (chave TEXT PRIMARY KEY, dados TEXT NOT NULL, quando REAL NOT NULL);"


def _arred(v: float) -> float:
    return round(float(v) * 4) / 4          # 0,25°: lugares vizinhos usam a mesma busca guardada


def ler_ponto(j: dict) -> dict:
    p = ((j.get("properties") or {}).get("parameter") or {}).get("ALLSKY_SFC_SW_DWN") or {}
    meses = [p.get(m) for m in MESES]
    if any(v is None or v < 0 for v in meses):
        raise ValueError("série incompleta")
    return {"meses": meses, "anual": p.get("ANN")}


def ler_regiao(j: dict) -> list[dict]:
    r = []
    for f in j.get("features") or []:
        c = (f.get("geometry") or {}).get("coordinates") or []
        v = (((f.get("properties") or {}).get("parameter") or {}).get("ALLSKY_SFC_SW_DWN") or {}).get("ANN")
        if len(c) >= 2 and v is not None and v >= 0:
            r.append({"lon": c[0], "lat": c[1], "anual": v})
    return r


class Irradiacao:
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

    def consultar(self, lat: float, lon: float) -> dict:
        if not (-35.0 <= lat <= 6.0 and -75.0 <= lon <= -28.0):
            return {"ok": False, "erro": "coordenadas fora do Brasil"}
        la, lo = _arred(lat), _arred(lon)
        cp, cr = f"ponto:{la}:{lo}", f"regiao:{round(la)}:{round(lo)}"
        ponto, regiao, avisos = self._guardado(cp), self._guardado(cr), []
        if ponto is None:
            try:
                ponto = ler_ponto(self.buscar(os.environ.get("PHYSIS_GIS_PONTO_URL", URL_PONTO).format(lat=la, lon=lo)))
                self._guardar(cp, ponto)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                avisos.append(f"irradiação do ponto indisponível agora ({exc})")
        if regiao is None:
            try:
                c0, c1 = round(la), round(lo)
                regiao = ler_regiao(self.buscar(os.environ.get("PHYSIS_GIS_REGIAO_URL", URL_REGIAO).format(
                    la0=c0 - RAIO, la1=c0 + RAIO, lo0=c1 - RAIO, lo1=c1 + RAIO)))
                if regiao:
                    self._guardar(cr, regiao)
            except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                avisos.append(f"grade da região indisponível agora ({exc})")
        return {"ok": ponto is not None or bool(regiao), "lat": lat, "lon": lon, "ponto": ponto, "regiao": regiao or [],
                "fonte": "NASA POWER (climatologia de irradiação global horizontal, kWh/m²·dia)", "avisos": avisos}
