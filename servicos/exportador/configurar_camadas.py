"""Configura o GeoServer pela API REST a partir de camadas.json (idempotente; só biblioteca padrão).

Roda uma vez (e de novo quando chegarem arquivos novos), com as credenciais só no ambiente do comando:
    set -a; . env/geoserver.env; . env/postgis.env; set +a
    docker compose run --rm -e GEOSERVER_ADMIN_USER -e GEOSERVER_ADMIN_PASSWORD -e GEOSERVER_LEITOR_SENHA \
        exportador python /app/configurar_camadas.py
Cria: espaço "physis"; loja PostGIS (schema geo, papel geoserver_leitor) e as tabelas do hub; uma loja por pasta
de shapefile que EXISTIR em /dados/camadas; GeoTIFF; WFS em cascata (se a URL não estiver marcada [CONFERIR]).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

GS = os.environ.get("GEOSERVER_URL", "http://geoserver:8080/geoserver").rstrip("/")
CAMADAS = Path(os.environ.get("CAMADAS_DIR", "/dados/camadas"))   # caminho visto pelo GeoServer
CONFIG = Path(__file__).with_name("camadas.json")


def pedir(metodo: str, caminho: str, corpo: dict | None = None) -> int:
    u, s = os.environ["GEOSERVER_ADMIN_USER"], os.environ["GEOSERVER_ADMIN_PASSWORD"]
    req = urllib.request.Request(GS + "/rest" + caminho, method=metodo,
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "Authorization": "Basic " + base64.b64encode(f"{u}:{s}".encode()).decode()})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def garantir(caminho_get: str, caminho_post: str, corpo: dict, nome: str) -> None:
    if pedir("GET", caminho_get) == 200:
        print(f"  já existe: {nome}")
        return
    st = pedir("POST", caminho_post, corpo)
    print(f"  {'criado' if st in (200, 201) else f'ERRO {st}'}: {nome}")


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    ws = cfg["espaco"]
    garantir(f"/workspaces/{ws}", "/workspaces", {"workspace": {"name": ws}}, f"espaço {ws}")
    garantir(f"/workspaces/{ws}/datastores/hub", f"/workspaces/{ws}/datastores", {"dataStore": {
        "name": "hub", "connectionParameters": {"entry": [
            {"@key": "dbtype", "$": "postgis"}, {"@key": "host", "$": os.environ.get("PG_HOST", "postgis")},
            {"@key": "port", "$": "5432"}, {"@key": "database", "$": os.environ.get("PG_BANCO", "physis")},
            {"@key": "schema", "$": "geo"}, {"@key": "user", "$": "geoserver_leitor"},
            {"@key": "passwd", "$": os.environ.get("GEOSERVER_LEITOR_SENHA", "")}]}}}, "loja PostGIS hub")
    for c in cfg["camadas"]:
        nome, tipo = c["nome"], c["tipo"]
        if tipo == "postgis":
            garantir(f"/workspaces/{ws}/datastores/hub/featuretypes/{c['tabela']}",
                     f"/workspaces/{ws}/datastores/hub/featuretypes",
                     {"featureType": {"name": c["tabela"], "title": c["titulo"]}}, nome)
        elif tipo == "shapefile":
            pasta = CAMADAS / c["pasta"]
            if not pasta.is_dir() or not any(pasta.glob("*.shp")):
                print(f"  pulado (sem .shp em {pasta}): {nome}")
                continue
            garantir(f"/workspaces/{ws}/datastores/{nome}", f"/workspaces/{ws}/datastores", {"dataStore": {
                "name": nome, "type": "Directory of spatial files (shapefiles)",
                "connectionParameters": {"entry": [{"@key": "url", "$": f"file:{pasta}"},
                                                   {"@key": "charset", "$": "UTF-8"}]}}}, nome)
            for shp in sorted(pasta.glob("*.shp")):
                garantir(f"/workspaces/{ws}/datastores/{nome}/featuretypes/{shp.stem}",
                         f"/workspaces/{ws}/datastores/{nome}/featuretypes",
                         {"featureType": {"name": shp.stem, "title": f"{c['titulo']} ({shp.stem})"}}, f"{nome}/{shp.stem}")
        elif tipo == "geotiff":
            arq = CAMADAS / c["arquivo"]
            if not arq.is_file():
                print(f"  pulado (sem {arq}): {nome}")
                continue
            garantir(f"/workspaces/{ws}/coveragestores/{nome}", f"/workspaces/{ws}/coveragestores", {"coverageStore": {
                "name": nome, "type": "GeoTIFF", "enabled": True, "workspace": ws, "url": f"file:{arq}"}}, nome)
            garantir(f"/workspaces/{ws}/coveragestores/{nome}/coverages/{nome}",
                     f"/workspaces/{ws}/coveragestores/{nome}/coverages",
                     {"coverage": {"name": nome, "nativeCoverageName": arq.stem, "title": c["titulo"]}}, f"{nome} (raster)")
        elif tipo == "wfs_cascata":
            url = c.get("capabilities", "")
            if "[CONFERIR" in url or not url.startswith("https://"):
                print(f"  pulado (URL a conferir): {nome}")
                continue
            garantir(f"/workspaces/{ws}/datastores/{nome}", f"/workspaces/{ws}/datastores", {"dataStore": {
                "name": nome, "type": "Web Feature Server (NG)", "connectionParameters": {"entry": [
                    {"@key": "WFSDataStoreFactory:GET_CAPABILITIES_URL", "$": url},
                    {"@key": "WFSDataStoreFactory:TIMEOUT", "$": "30000"}]}}}, nome)
    return 0


if __name__ == "__main__":
    sys.exit(main())
