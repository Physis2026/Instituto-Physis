#!/usr/bin/env python3
"""Prepara a camada de hidrografia do servidor (rios e nascentes) a partir da base oficial que o engenheiro baixa.

Fonte indicada: Base Hidrográfica Ottocodificada (BHO) da ANA — trechos de drenagem [CONFERIR o produto exato, a
versão e o link no portal de metadados da ANA antes de usar]. Nenhum dado vem copiado neste repositório: a pessoa baixa
a base, converte para GeoJSON (por exemplo no QGIS, "Exportar → Salvar feições como… GeoJSON", ou com
`ogr2ogr -f GeoJSON trechos.geojson <arquivo da BHO>`) e roda este script para recortar a região e padronizar os campos.

    python ferramentas/hidrografia_servidor.py trechos.geojson saida.geojson --bbox -43.4,-22.6,-43.0,-22.3 [--nascentes nascentes.geojson]

Depois, no servidor: PHYSIS_HIDROGRAFIA=/caminho/saida.geojson (GET /api/gis/hidrografia?bbox=… passa a responder).

Campos de saída por feição: nome (do campo de nome da base, se houver) e largura_m (só se a base trouxer; quase nunca traz:
o Planejador pede a largura do rio antes de desenhar a faixa de APP). Linhas viram rios; pontos (arquivo de nascentes,
opcional) viram nascentes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CAMPOS_NOME = ("nome", "name", "noriocomp", "nocurso", "NORIOCOMP", "NOME", "NM_RIO")   # [CONFERIR] nomes de campo da BHO
CAMPOS_LARGURA = ("largura_m", "largura", "LARGURA")


def _toca(coords, b) -> bool:
    return any(b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] for p in coords)


def _prop(pr: dict, campos) -> object:
    for c in campos:
        if pr.get(c) not in (None, ""):
            return pr[c]
    return None


def converter(origem: dict, bbox, nascentes: dict | None = None, fonte: str = "") -> dict:
    """GeoJSON de entrada → GeoJSON padronizado do servidor, só com o que toca a janela."""
    b = [float(x) for x in bbox]
    saida = []
    for f in (origem.get("features") or []):
        g = f.get("geometry") or {}
        pr = f.get("properties") or {}
        if g.get("type") not in ("LineString", "MultiLineString"):
            continue
        linhas = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        if not any(_toca(l, b) for l in linhas):
            continue
        larg = _prop(pr, CAMPOS_LARGURA)
        try:
            larg = float(larg) if larg is not None else None
        except (TypeError, ValueError):
            larg = None
        saida.append({"type": "Feature", "geometry": g, "properties": {"nome": str(_prop(pr, CAMPOS_NOME) or ""), "largura_m": larg}})
    for f in ((nascentes or {}).get("features") or []):
        g = f.get("geometry") or {}
        if g.get("type") == "Point" and _toca([g.get("coordinates") or [999, 999]], b):
            saida.append({"type": "Feature", "geometry": g, "properties": {"nome": str(_prop(f.get("properties") or {}, CAMPOS_NOME) or "")}})
    return {"type": "FeatureCollection", "fonte": fonte or "Base Hidrográfica Ottocodificada (ANA) [CONFERIR versão]", "features": saida}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description="Recorta e padroniza a hidrografia para o servidor Physis")
    a.add_argument("entrada"); a.add_argument("saida")
    a.add_argument("--bbox", required=True, help="lon_min,lat_min,lon_max,lat_max da região do servidor")
    a.add_argument("--nascentes", help="GeoJSON de pontos de nascentes (opcional)")
    a.add_argument("--fonte", default="", help="texto da fonte com versão e data de download")
    op = a.parse_args(argv)
    ent = json.loads(Path(op.entrada).read_text(encoding="utf-8"))
    nas = json.loads(Path(op.nascentes).read_text(encoding="utf-8")) if op.nascentes else None
    r = converter(ent, op.bbox.split(","), nas, op.fonte)
    Path(op.saida).write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    print(f"{len(r['features'])} feições gravadas em {op.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
