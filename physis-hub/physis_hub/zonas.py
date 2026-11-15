"""Zonas do lugar: bioma, clima, vegetação, relevo (IBGE) e classificação climática de Köppen.

Fontes abertas, buscadas uma vez por lugar e guardadas no banco do hub (tabela gis_cache):
- IBGE (geoserviços, WFS): Biomas do Brasil 1:5.000.000 (CREN:biomas_5000), Clima do Brasil 1:5.000.000
  (CREN:clima_5000), Vegetação 1:250.000 (BDIA:vege_area: fitofisionomia original e uso atual) e
  Geomorfologia 1:250.000 (BDIA:geom_area: domínio, região e unidade de relevo). A pedologia (classe de solo)
  já vem em gis.GisExtra.solo.
- Köppen-Geiger calculado aqui a partir das normais mensais de temperatura e chuva da NASA POWER
  (critérios de Köppen como descritos por Peel, Finlayson e McMahon, 2007).

A zona bioclimática da NBR 15220-3 é definida por município na própria norma: não é calculada aqui
(o sistema mostra onde conferir).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

WFS = ("https://geoservicos.ibge.gov.br/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature&typeName={camada}"
       "&outputFormat=application/json&maxFeatures=1&CQL_FILTER=INTERSECTS({geo},POINT({lon}%20{lat})){props}")
# camada -> (coluna de geometria, campos que interessam)
CAMADAS = {
    "bioma": ("CREN:biomas_5000", "the_geom", ["cod_bioma", "nom_bioma"]),
    "clima": ("CREN:clima_5000", "the_geom", ["zona", "tp_umidade", "distr_umid", "temperatur", "desc_compl"]),
    "vegetacao": ("BDIA:vege_area", "geom", ["nm_pretet", "legenda_1", "legenda_2", "leg_sup", "nm_uantr"]),
    "relevo": ("BDIA:geom_area", "geom", ["nm_dominio", "nm_regiao", "nm_unidade", "categoria", "forma", "compartimento"]),
}
DIAS = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
NOMES_KOPPEN = {
    "Af": "Tropical úmido (sem estação seca)", "Am": "Tropical de monção", "Aw": "Tropical com inverno seco",
    "As": "Tropical com verão seco", "BWh": "Desértico quente", "BWk": "Desértico frio",
    "BSh": "Semiárido quente", "BSk": "Semiárido frio",
    "Cfa": "Subtropical úmido, verão quente", "Cfb": "Temperado úmido, verão ameno", "Cfc": "Temperado úmido, verão curto",
    "Cwa": "Subtropical de inverno seco, verão quente", "Cwb": "Subtropical de altitude, inverno seco, verão ameno",
    "Cwc": "Subtropical de altitude, inverno seco, verão curto",
    "Csa": "Mediterrâneo, verão quente", "Csb": "Mediterrâneo, verão ameno", "Csc": "Mediterrâneo, verão curto",
}


def texto(b: bytes) -> str:
    """O IBGE às vezes responde em Latin-1; UTF-8 primeiro, Latin-1 se falhar."""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("latin-1")


def buscar_bruto(url: str, timeout: float = 25.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "PhysisHub/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(texto(r.read()))


def ler_feicao(j: dict, campos: list[str]) -> dict | None:
    f = (j.get("features") or [None])[0]
    if not f:
        return None
    p = f.get("properties") or {}
    out = {}
    for k in campos:
        v = p.get(k)
        if isinstance(v, str):
            v = " ".join(v.split())
        if v not in (None, ""):
            out[k] = v
    return out or None


def koppen(temp: list[float], chuva_mm_dia: list[float], hemisferio_sul: bool = True) -> dict:
    """Köppen-Geiger a partir de 12 médias mensais de temperatura (°C) e chuva (mm/dia)."""
    if len(temp) != 12 or len(chuva_mm_dia) != 12 or any(x is None for x in temp + chuva_mm_dia):
        raise ValueError("precisa de 12 meses de temperatura e chuva")
    p = [c * d for c, d in zip(chuva_mm_dia, DIAS)]                  # mm/mês
    tann, pann = sum(temp) / 12, sum(p)
    thot, tcold = max(temp), min(temp)
    # verão = meses mais quentes do semestre (out–mar no hemisfério sul)
    verao = [9, 10, 11, 0, 1, 2] if hemisferio_sul else [3, 4, 5, 6, 7, 8]
    inverno = [i for i in range(12) if i not in verao]
    ps, pw = sum(p[i] for i in verao), sum(p[i] for i in inverno)
    psdry, pwdry = min(p[i] for i in verao), min(p[i] for i in inverno)
    pswet, pwwet = max(p[i] for i in verao), max(p[i] for i in inverno)
    pdry = min(p)
    if ps >= 0.7 * pann:
        pth = 2 * tann + 28
    elif pw >= 0.7 * pann:
        pth = 2 * tann
    else:
        pth = 2 * tann + 14
    if pann < 10 * pth:                                            # B: árido
        cod = ("BW" if pann < 5 * pth else "BS") + ("h" if tann >= 18 else "k")
    elif tcold >= 18:                                              # A: tropical
        if pdry >= 60:
            cod = "Af"
        elif pdry >= 100 - pann / 25:
            cod = "Am"
        else:
            cod = "Aw" if pwdry < psdry else "As"
    elif thot > 10 and tcold > -3:                                 # C: temperado (mês mais frio entre -3 e 18 °C)
        if psdry < 40 and psdry < pwwet / 3:
            seg = "s"
        elif pwdry < pswet / 10:
            seg = "w"
        else:
            seg = "f"
        meses10 = sum(1 for t in temp if t > 10)
        ter = "a" if thot >= 22 else ("b" if meses10 >= 4 else "c")
        cod = "C" + seg + ter
    else:
        cod = "D/E (frio — não ocorre no Brasil)"
    return {"codigo": cod, "nome": NOMES_KOPPEN.get(cod, cod), "temp_media": round(tann, 1), "chuva_anual_mm": round(pann),
            "mes_mais_seco_mm": round(pdry), "meses_secos": sum(1 for x in p if x < 60), "temp_min_mensal": round(tcold, 1),
            "temp_max_mensal": round(thot, 1)}


class Zonas:
    """Zonas do lugar, guardadas no banco do hub (gis_cache), com a mesma base do GIS (gis.Irradiacao)."""

    def __init__(self, base, buscar=buscar_bruto):
        self.b, self.buscar = base, buscar

    def altitude(self, lat: float, lon: float) -> float | None:
        """Altitude do ponto pela grade de relevo já guardada (centro da grade 10 x 10)."""
        try:
            from .gis import GisExtra
            r = GisExtra(self.b).relevo(lat, lon)
            if not r.get("ok"):
                return None
            e, n = r["elev"], r["n"]
            meio = [e[(n // 2 - 1) * n + n // 2 - 1], e[(n // 2 - 1) * n + n // 2], e[(n // 2) * n + n // 2 - 1], e[(n // 2) * n + n // 2]]
            return sum(meio) / 4
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    def consultar(self, lat: float, lon: float) -> dict:
        if not (-35.0 <= lat <= 6.0 and -75.0 <= lon <= -28.0):
            return {"ok": False, "erro": "coordenadas fora do Brasil"}
        la, lo = round(lat, 3), round(lon, 3)
        out, avisos = {}, []
        for nome, (camada, geo, campos) in CAMADAS.items():
            ch = f"zona:{nome}:{la}:{lo}"
            v = self.b._guardado(ch)
            if v is None:
                try:
                    props = "&propertyName=" + ",".join(campos)
                    v = ler_feicao(self.buscar(WFS.format(camada=camada, geo=geo, lat=la, lon=lo, props=props)), campos) or {}
                    self.b._guardar(ch, v)
                except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
                    avisos.append(f"{nome} indisponível agora ({exc})")
                    v = None
            if v:
                out[nome] = v
        # Köppen pelas normais da NASA POWER (as mesmas camadas dos mapas de calor, já guardadas)
        try:
            t = self.b.consultar(lat, lon, "temperatura")
            c = self.b.consultar(lat, lon, "chuva")
            if (t.get("ponto") or {}).get("meses") and (c.get("ponto") or {}).get("meses"):
                temps, ajuste = list(t["ponto"]["meses"]), None
                # a NASA dá a média de uma célula de ~50 km: corrige pela altitude real do lugar (-6,5 °C por km)
                z_nasa = t["ponto"].get("elev")
                z_local = self.altitude(lat, lon)
                if z_nasa is not None and z_local is not None and abs(z_local - z_nasa) > 50:
                    ajuste = round(-0.0065 * (z_local - z_nasa), 1)
                    temps = [x + ajuste for x in temps]
                out["koppen"] = koppen(temps, c["ponto"]["meses"], hemisferio_sul=lat < 0)
                if ajuste is not None:
                    out["koppen"]["ajuste_altitude_c"] = ajuste
                    out["koppen"]["altitude_m"] = round(z_local)
            else:
                avisos.append("Köppen: normais de temperatura e chuva indisponíveis agora")
        except (ValueError, KeyError, TypeError) as exc:
            avisos.append(f"Köppen indisponível ({exc})")
        out["zona_bioclimatica"] = {"definida_por": "NBR 15220-3 (lista de municípios da norma)",
                                    "como": "confira o município na norma vigente e informe no Início; o sistema usa o valor informado"}
        if not any(k in out for k in ("bioma", "clima", "vegetacao", "relevo", "koppen")):
            return {"ok": False, "avisos": avisos or ["zonas indisponíveis agora"]}
        return {"ok": True, "lat": la, "lon": lo, **out, "avisos": avisos,
                "fonte": "IBGE (biomas, clima, vegetação e geomorfologia) e NASA POWER (Köppen), guardados no servidor"}
