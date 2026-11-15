"""Gera o pacote de EXEMPLO do Mapeamento (dados fictícios) para conferir os visualizadores.

    python modulos/mapeamento/exemplos/gerar_exemplos.py

Tudo aqui é inventado para teste (lote, relevo, rio, poços, irradiação): nada vem de base oficial nem de cliente.
Saídas nesta pasta: lote.geojson, planejador-exemplo.json, camadas-exemplo/ (relevo.asc, hidrografia.geojson),
pocos.kml, nascentes-shp.zip, planta-solar.json, modelo.ifc, ifc-resumo.json e contexto-lugar.json.
A página ferramentas/testes-navegador/conferir-modelos.html abre tudo isso nos visualizadores do módulo.
"""
from __future__ import annotations

import io
import json
import math
import struct
import sys
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
sys.path.insert(0, str(RAIZ / "physis-hub"))
from physis_hub import ifc, mapeamento as M  # noqa: E402

AVISO = "EXEMPLO / DADOS FICTÍCIOS — só para conferir os visualizadores; não usar em projeto"
LAT0, LON0 = -22.5, -43.2
H_FICTICIO = [5.8, 5.9, 5.0, 4.4, 3.7, 3.4, 3.6, 4.2, 4.5, 5.0, 5.4, 5.8]     # kWh/m²·dia, inventado
K = 111320 * math.cos(math.radians(LAT0))
POLY = [[-40, -30], [40, -30], [40, 30], [-40, 30]]                           # lote 80 × 60 m (metros locais)
CASA = {"id": "casa", "nome": "Casa exemplo", "tipo": "residencia", "x": 0.0, "y": 0.0, "w": 12.0, "d": 8.0, "rot": 0, "pav": 1,
        "h": 3.0, "incl": 20, "azim": 0, "aguas": 2}
MODULO = {"id": "fv-perc-144", "comprimento_m": 2.28, "largura_m": 1.13, "pmax": 550}
REGRAS = {"afastamento_m": 0.3, "folga_m": 0.02}                              # valores de teste das premissas [CONFERIR]


def ll(x, y):
    return [round(LON0 + x / K, 7), round(LAT0 + y / 110540, 7)]


def z(x, y):
    return round(2.0 + 0.05 * (y + 30), 3)                                    # sobe 5 % para o norte (fictício)


def escrever(nome, obj):
    (AQUI / nome).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def shp_pontos(pts, nomes) -> bytes:
    recs = b""
    for i, p in enumerate(pts):
        c = struct.pack("<i2d", 1, *p)
        recs += struct.pack(">2i", i + 1, len(c) // 2) + c
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cab = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(recs)) // 2) + struct.pack("<2i4d4d", 1000, 1, min(xs), min(ys), max(xs), max(ys), 0, 0, 0, 0)
    shx = b""
    dbf = struct.pack("<4BIHH20x", 3, 126, 11, 15, len(nomes), 32 + 32 + 1, 1 + 30)
    dbf += b"NOME".ljust(11, b"\x00") + b"C" + b"\x00" * 4 + bytes([30, 0]) + b"\x00" * 14 + b"\x0D"
    for n in nomes:
        dbf += b" " + n.encode("latin-1").ljust(30)[:30]
    prj = 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zz:
        zz.writestr("nascentes.shp", cab + recs)
        zz.writestr("nascentes.dbf", dbf)
        zz.writestr("nascentes.prj", prj)
        zz.writestr("LEIA-ME.txt", AVISO + "\n")
    del shx
    return buf.getvalue()


def main():
    anel = [ll(*p) for p in POLY] + [ll(*POLY[0])]
    escrever("lote.geojson", {"type": "FeatureCollection", "aviso": AVISO, "features": [
        {"type": "Feature", "properties": {"nome": "Lote exemplo", "aviso": AVISO}, "geometry": {"type": "Polygon", "coordinates": [anel]}}]})
    pontos = [[x, y, z(x, y)] for x in range(-40, 41, 10) for y in range(-30, 31, 10)]
    planejador = {"schema": "physis.terreno/1.0", "aviso": AVISO, "meta": {"nome": "Projeto exemplo", "criado": "exemplo-mapeamento", "municipio": "[exemplo]", "uf": "RJ"},
                  "terreno": {"fonte": "exemplo", "crs": "EPSG:4326", "lat0": LAT0, "lon0": LON0, "poly": POLY, "pontos": pontos, "grade": None},
                  "itens": [CASA], "hidro": {"rios": [], "nascentes": []}, "log": []}
    escrever("planejador-exemplo.json", planejador)
    # camadas fictícias "instaladas" para o contexto
    cam = AQUI / "camadas-exemplo"
    cam.mkdir(exist_ok=True)
    cs, nc, nr = 0.0002, 60, 60
    x0, y0 = LON0 - nc * cs / 2, LAT0 - nr * cs / 2
    linhas = [f"ncols {nc}", f"nrows {nr}", f"xllcorner {x0}", f"yllcorner {y0}", f"cellsize {cs}", "NODATA_value -9999"]
    for r in range(nr):
        lat = y0 + (nr - r - 0.5) * cs
        linhas.append(" ".join(f"{z(0, (lat - LAT0) * 110540):.3f}" for _ in range(nc)))
    (cam / "relevo.asc").write_text("\n".join(linhas) + "\n", encoding="ascii")
    (cam / "hidrografia.geojson").write_text(json.dumps({"type": "FeatureCollection", "fonte": AVISO, "features": [
        {"type": "Feature", "properties": {"nome": "Córrego exemplo"}, "geometry": {"type": "LineString", "coordinates": [ll(-60, -45), ll(60, -40)]}},
        {"type": "Feature", "properties": {"nome": "Nascente exemplo"}, "geometry": {"type": "Point", "coordinates": ll(-50, -42)}}]}, ensure_ascii=False), encoding="utf-8")
    # arquivos do cliente (caminho do envio)
    kml = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>' + AVISO + '</name>'
           + "".join(f'<Placemark><name>Poço {i + 1} (exemplo)</name><Point><coordinates>{p[0]},{p[1]},0</coordinates></Point></Placemark>'
                     for i, p in enumerate([ll(-30, 20), ll(25, -20)]))
           + f'<Placemark><name>Lote (exemplo)</name><Polygon><outerBoundaryIs><LinearRing><coordinates>{" ".join(f"{a},{b},0" for a, b in anel)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>'
           + "</Document></kml>")
    (AQUI / "pocos.kml").write_text(kml, encoding="utf-8")
    (AQUI / "nascentes-shp.zip").write_bytes(shp_pontos([ll(-35, -25), ll(35, 25)], ["Nascente A (exemplo)", "Nascente B (exemplo)"]))
    for nome in ("pocos.kml", "nascentes-shp.zip", "lote.geojson"):
        M.ler_arquivo(nome, (AQUI / nome).read_bytes())          # confere que o leitor aceita
    # planta solar nas duas águas do telhado
    planos = M.planos_telhado(dict(CASA, z0=z(0, 0)))
    planta = {"aviso": AVISO, "lat": LAT0, "H": H_FICTICIO, "modulo": MODULO, "regras_teste": REGRAS, "aguas": []}
    elementos = []
    for p in planos:
        larg, comp = CASA["w"], CASA["d"] / 2 / math.cos(math.radians(p["incl"]))
        a = M.arranjo([[0, 0], [larg, 0], [larg, comp], [0, comp]], MODULO, orientacao="retrato", plano="telhado", **REGRAS)
        inc = M.incidencia_superficie(H_FICTICIO, LAT0, p["incl"], p["azim"])
        cv = M.curva_diaria(H_FICTICIO[5], LAT0, M.SOLSTICIO_JUN, p["incl"], p["azim"], total_plano=None)
        planta["aguas"].append({"id": p["id"], "incl": p["incl"], "azim": p["azim"], "modulos": a["modulos"], "kwp": a["kwp"],
                                "area_modulos_m2": a["area_modulos_m2"], "anual_kwh_m2": inc["anual_kwh_m2"], "curva_junho_total_kwh_m2": cv["total_kwh_m2"]})
        elementos.append({"id": "pv-" + p["id"], "tipo": "pv", "nome": "Arranjo " + p["id"] + " (exemplo)", "pavimento": "cobertura",
                          "posicao": {"x": -larg / 2, "y": 0 if p["azim"] == 0 else -CASA["d"] / 2, "z": 0.1}, "caixa": {"dx": larg, "dy": CASA["d"] / 2, "dz": 0.05},
                          "propriedades": {"modulos": a["modulos"], "kwp": a["kwp"], "incl_graus": p["incl"], "azim_graus": p["azim"], "passo_fileiras_m": a["passo_m"],
                                           "inversor": "inv-string-mono-3-6"},
                          "modulos": [{"x": q["x"] - larg / 2, "y": q["y"], "z": 0.1} for q in a["posicoes"]]})
    planta["total"] = {"modulos": sum(x["modulos"] for x in planta["aguas"]), "kwp": sum(x["kwp"] for x in planta["aguas"])}
    escrever("planta-solar.json", planta)
    elementos.append({"id": "inv1", "tipo": "inversor", "nome": "Inversor (exemplo)", "propriedades": {"potencia_kw": 5}})
    elementos.append({"id": "cist", "tipo": "cisterna", "nome": "Cisterna (exemplo)", "propriedades": {"volume_m3": 5},
                      "materiais": [{"id": "concreto_normal", "quantidade": 0.8, "unidade": "m3"}]})
    texto = ifc.escrever({"projeto": {"id": "exemplo-mapeamento", "nome": "Projeto exemplo (dados ficticios)"},
                          "site": {"nome": "Lote exemplo", "lat": LAT0, "lon": LON0, "altitude_m": 2},
                          "edificacoes": [{"id": "casa", "nome": "Casa exemplo", "pavimentos": [{"id": "terreo", "nome": "Térreo", "elevacao_m": 0},
                                                                                                 {"id": "cobertura", "nome": "Cobertura", "elevacao_m": 3.0}]}],
                          "elementos": elementos}, agora=1794700000)
    (AQUI / "modelo.ifc").write_text(texto, encoding="utf-8", newline="\n")
    escrever("ifc-resumo.json", {"aviso": AVISO, **{k: v for k, v in ifc.ler(texto.encode()).items() if k != "tipos"}})
    local = {"lat": LAT0, "lon": LON0, "municipio": "[exemplo]", "uf": "RJ", "poligono": None, "area_m2": None, "fonte": "exemplo"}
    ctx = M.construir_contexto(local, planejador, cam, irradiacao_solar={"meses": H_FICTICIO, "fonte": AVISO}, instalacao="exemplo", agora=1794700000)
    ctx["aviso"] = AVISO
    escrever("contexto-lugar.json", ctx)
    print("exemplos gerados em", AQUI)


if __name__ == "__main__":
    main()
