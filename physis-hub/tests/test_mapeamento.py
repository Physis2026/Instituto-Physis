"""Mapeamento (Fase 1, 15/11/2026): catálogo de camadas, recorte, arquivos do cliente, contexto do lugar, sol nas
superfícies e planta solar.

Protege:
1. Catálogo: as 12 camadas pedidas, cada uma com nome pt/en, finalidade, consumidores, fonte/produto/licença marcados
   [CONFERIR], formato e chave de configuração; estado "instalada" só com o arquivo na pasta PHYSIS_CAMADAS.
2. Recorte: vetor (pontos, linhas e polígonos) recortado na janela; raster .asc lido só na janela, com declividade.
3. Arquivos do cliente: GeoJSON, KML/KMZ e Shapefile (.zip) lidos; projetado e datum estranho recusados; SIRGAS 2000
   aceito com a nota; MultiPatch recusado; índice no SQLite com SHA-256 e integridade conferida.
4. Contexto do lugar: sem camada, "camada não instalada" (nada inventado); com camada, valor e fonte.
5. Sol: sem sombra, telhado horizontal = irradiação horizontal; norte vence sul no hemisfério sul; prédio vizinho faz sombra.
6. Planta solar: curva diária simétrica ao meio-dia solar; sombra entre fileiras no solstício de inverno com passo curto;
   arranjo com contagem, kWp e área; perdas iguais às da aba Solar.
7. A tela (sistema/physis-mapeamento.js) não chama a internet, tem um h1 só, o selo em desenvolvimento e as mesmas
   constantes do espelho.
"""
import io
import json
import math
import re
import sqlite3
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(AQUI.parent))
from physis_hub import mapeamento as M  # noqa: E402

JS = RAIZ / "sistema" / "physis-mapeamento.js"
SOLAR_JS = RAIZ / "sistema" / "physis-solar.js"
LAT = -22.9
HORAS = (9.0, 15.0)          # valores de teste das premissas de hora crítica
H_RJ = [6.0, 6.0, 5.2, 4.5, 3.8, 3.5, 3.7, 4.3, 4.6, 5.2, 5.6, 6.0]      # valores de teste, não de base

FC = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"nome": "Córrego A"}, "geometry": {"type": "LineString", "coordinates": [[-43.30, -22.90], [-43.10, -22.90]]}},
    {"type": "Feature", "properties": {"nome": "Nascente"}, "geometry": {"type": "Point", "coordinates": [-43.1995, -22.9005]}},
    {"type": "Feature", "properties": {"nome": "Longe"}, "geometry": {"type": "Point", "coordinates": [-40.0, -20.0]}},
    {"type": "Feature", "properties": {"classe": "Latossolo"}, "geometry": {"type": "Polygon", "coordinates": [[[-43.3, -23.0], [-43.1, -23.0], [-43.1, -22.8], [-43.3, -22.8], [-43.3, -23.0]]]}}]}
JANELA = [-43.21, -22.91, -43.19, -22.89]


def asc(nc, nr, x0, y0, cs, f):
    linhas = [f"ncols {nc}", f"nrows {nr}", f"xllcorner {x0}", f"yllcorner {y0}", f"cellsize {cs}", "NODATA_value -9999"]
    for r in range(nr):
        y = y0 + (nr - r - 0.5) * cs
        linhas.append(" ".join(str(f(x0 + (c + 0.5) * cs, y)) for c in range(nc)))
    return "\n".join(linhas) + "\n"


def shp_zip(tipo, geoms, campos, registros, prj):
    """Shapefile mínimo em memória (tipos 1, 3 ou 5) para o teste."""
    recs = b""
    for i, g in enumerate(geoms):
        if tipo == 1:
            c = struct.pack("<i2d", 1, *g)
        else:
            partes = g
            pts = [p for parte in partes for p in parte]
            idx, k = [], 0
            for parte in partes:
                idx.append(k)
                k += len(parte)
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            c = struct.pack("<i4d2i", tipo, min(xs), min(ys), max(xs), max(ys), len(partes), len(pts))
            c += struct.pack(f"<{len(idx)}i", *idx) + b"".join(struct.pack("<2d", *p) for p in pts)
        recs += struct.pack(">2i", i + 1, len(c) // 2) + c
    cab = struct.pack(">i5i i", 9994, 0, 0, 0, 0, 0, (100 + len(recs)) // 2) + struct.pack("<2i4d4d", 1000, tipo, 0, 0, 0, 0, 0, 0, 0, 0)
    # .dbf
    nreg, tam = len(registros), 1 + sum(c[2] for c in campos)
    dbf = struct.pack("<4BIHH20x", 3, 126, 11, 15, nreg, 32 + 32 * len(campos) + 1, tam)
    for nome, t, n in campos:
        dbf += nome.encode().ljust(11, b"\x00") + t.encode() + b"\x00" * 4 + bytes([n, 0]) + b"\x00" * 14
    dbf += b"\x0D"
    for r in registros:
        dbf += b" " + b"".join(str(v).encode("latin-1").ljust(n)[:n] for v, (_, _, n) in zip(r, campos))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("camada.shp", cab + recs)
        z.writestr("camada.dbf", dbf)
        if prj is not None:
            z.writestr("camada.prj", prj)
    return buf.getvalue()


WKT_WGS = 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
WKT_SIRGAS = 'GEOGCS["GCS_SIRGAS_2000",DATUM["D_SIRGAS_2000",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
WKT_UTM = 'PROJCS["SIRGAS_2000_UTM_Zone_23S",GEOGCS["GCS_SIRGAS_2000"],PROJECTION["Transverse_Mercator"]]'


class Catalogo(unittest.TestCase):
    def test_doze_camadas_completas_e_marcadas(self):
        ids = [c["id"] for c in M.CAMADAS]
        self.assertEqual(set(ids), {"limites", "relevo", "hidrografia", "uso_solo", "solos", "car", "clima", "risco", "irradiacao", "vento", "rede_eletrica", "osm"})
        for c in M.CAMADAS:
            with self.subTest(c=c["id"]):
                self.assertTrue(c["nome"]["pt"] and c["nome"]["en"] and c["finalidade"]["pt"] and c["consumidores"] and c["chave_config"])
                for k in ("nome", "produto", "licenca"):
                    self.assertIn("[CONFERIR]", c["fonte"][k])
                self.assertIn(c["formato"], ("vetor", "raster", "epw"))
        self.assertEqual(M.POR_ID["hidrografia"]["rota_existente"], "/api/gis/hidrografia")

    def test_estado_segue_a_pasta(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(all(c["status"] == "nao_instalada" for c in M.catalogo(d)))
            Path(d, "osm.geojson").write_text("{}", encoding="utf-8")
            st = {c["id"]: c["status"] for c in M.catalogo(d)}
            self.assertEqual(st["osm"], "instalada")
            self.assertEqual(st["relevo"], "nao_instalada")


class Recorte(unittest.TestCase):
    def test_vetor_recortado_na_janela(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "hidrografia.geojson").write_text(json.dumps(FC), encoding="utf-8")
            r = M.camada("hidrografia", JANELA, d)
            self.assertTrue(r["ok"])
            fs = r["geojson"]["features"]
            tipos = sorted(f["geometry"]["type"] for f in fs)
            self.assertEqual(tipos, ["LineString", "Point", "Polygon"])
            linha = next(f for f in fs if f["geometry"]["type"] == "LineString")["geometry"]["coordinates"]
            self.assertAlmostEqual(linha[0][0], -43.21)
            self.assertAlmostEqual(linha[-1][0], -43.19)
            anel = next(f for f in fs if f["geometry"]["type"] == "Polygon")["geometry"]["coordinates"][0]
            self.assertTrue(all(JANELA[0] - 1e-9 <= p[0] <= JANELA[2] + 1e-9 for p in anel))
            self.assertAlmostEqual(M.area_m2(anel), (0.02 * 111320 * math.cos(math.radians(22.9))) * (0.02 * 110540), delta=500)

    def test_janela_grande_e_camada_ausente(self):
        self.assertFalse(M.camada("osm", [-44, -23, -43, -22], None)["ok"])
        r = M.camada("osm", JANELA, None)
        self.assertTrue(r["sem_camada"])

    def test_raster_asc_e_declividade(self):
        with tempfile.TemporaryDirectory() as d:
            # rampa subindo para o norte: 1 m de altura a cada 10 m (10 %)
            Path(d, "relevo.asc").write_text(asc(40, 40, -43.21, -22.91, 0.0005, lambda x, y: round((y + 22.91) * 110540 / 10, 3)), encoding="ascii")
            r = M.camada("relevo", JANELA, d)
            self.assertTrue(r["ok"], r)
            self.assertAlmostEqual(r["declividade"]["media_pct"], 10.0, delta=0.2)
            self.assertEqual(r["declividade"]["fracao_acima_30pct"], 0)


class ArquivosDoCliente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = sqlite3.connect(":memory:")
        self.up = M.Uploads(self.con, self.tmp.name)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_geojson_guardado_com_hash_e_integridade(self):
        b = json.dumps(FC).encode()
        r = self.up.guardar("rios.geojson", b, "inst1", "ana")
        self.assertTrue(r["ok"])
        self.assertEqual(r["sha256"], M.sha256(b))
        self.assertEqual(r["feicoes"], 4)
        self.assertTrue(self.up.conferir(r["id"])["integro"])
        self.assertTrue(self.up.guardar("rios.geojson", b, "inst1")["repetido"])
        self.assertEqual(len(self.up.listar("inst1")), 1)
        # adulterado no disco: a integridade cai e o arquivo não é entregue
        Path(self.tmp.name, f"{r['id']}.norm.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        self.assertFalse(self.up.conferir(r["id"])["integro"])
        self.assertIsNone(self.up.geojson(r["id"]))
        self.assertTrue(self.up.apagar(r["id"]))

    def test_geojson_crs_e_limites(self):
        sir = dict(FC, crs={"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}})
        r = M.ler_arquivo("a.geojson", json.dumps(sir).encode())
        self.assertEqual(r["crs"], "EPSG:4674")
        self.assertIn("SIRGAS", r["nota_crs"])
        with self.assertRaises(M.ArquivoInvalido):
            M.ler_arquivo("a.geojson", json.dumps(dict(FC, crs={"type": "name", "properties": {"name": "EPSG:31983"}})).encode())
        utm = {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [680000, 7460000]}}
        with self.assertRaisesRegex(M.ArquivoInvalido, "projetado"):
            M.ler_arquivo("a.geojson", json.dumps(utm).encode())
        with self.assertRaises(M.ArquivoInvalido):
            M.ler_arquivo("a.dwg", b"x")
        with self.assertRaisesRegex(M.ArquivoInvalido, "grande"):
            M.ler_arquivo("a.geojson", b" " * (M.MAX_UPLOAD_BYTES + 1))

    def test_kml_e_kmz(self):
        kml = ('<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
               '<Placemark><name>Lote</name><Polygon><outerBoundaryIs><LinearRing><coordinates>-43.2,-22.9,0 -43.19,-22.9,0 -43.19,-22.89,0 -43.2,-22.9,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>'
               '<Placemark><name>Poço</name><Point><coordinates>-43.195,-22.895</coordinates></Point></Placemark></Document></kml>').encode("utf-8")
        r = M.ler_arquivo("lote.kml", kml)
        self.assertEqual([f["geometry"]["type"] for f in r["geojson"]["features"]], ["Polygon", "Point"])
        self.assertEqual(r["geojson"]["features"][1]["properties"]["nome"], "Poço")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("doc.kml", kml)
        self.assertEqual(len(M.ler_arquivo("lote.kmz", buf.getvalue())["geojson"]["features"]), 2)
        with self.assertRaisesRegex(M.ArquivoInvalido, "ENTITY"):
            M.ler_arquivo("x.kml", b'<?xml version="1.0"?><!DOCTYPE k [<!ENTITY a "b">]><kml/>')

    def test_shapefile_pontos_linhas_poligonos(self):
        pts = shp_zip(1, [(-43.2, -22.9), (-43.1, -22.8)], [("NOME", "C", 10), ("VAZAO", "N", 6)], [("Poço A", 12), ("Poço B", 7)], WKT_WGS)
        r = M.ler_arquivo("pocos.zip", pts)
        self.assertEqual(r["formato"], "shapefile")
        self.assertEqual(r["crs"], "EPSG:4326")
        self.assertEqual(r["geojson"]["features"][0]["properties"], {"NOME": "Poço A", "VAZAO": 12})
        lin = shp_zip(3, [[[(-43.2, -22.9), (-43.1, -22.8), (-43.0, -22.8)]]], [("ID", "N", 4)], [(1,)], WKT_SIRGAS)
        r = M.ler_arquivo("rio.zip", lin)
        self.assertEqual(r["geojson"]["features"][0]["geometry"]["type"], "LineString")
        self.assertIn("SIRGAS", r["nota_crs"])
        externo = [(-43.2, -22.9), (-43.2, -22.8), (-43.1, -22.8), (-43.1, -22.9), (-43.2, -22.9)]       # horário
        furo = [(-43.17, -22.87), (-43.13, -22.87), (-43.13, -22.83), (-43.17, -22.83), (-43.17, -22.87)]  # anti-horário
        pol = shp_zip(5, [[externo, furo]], [("ID", "N", 4)], [(1,)], WKT_WGS)
        g = M.ler_arquivo("lote.zip", pol)["geojson"]["features"][0]["geometry"]
        self.assertEqual(g["type"], "Polygon")
        self.assertEqual(len(g["coordinates"]), 2)
        self.assertFalse(M.dentro_geometria((-43.15, -22.85), g))
        self.assertTrue(M.dentro_geometria((-43.19, -22.89), g))

    def test_shapefile_recusas_claras(self):
        with self.assertRaisesRegex(M.ArquivoInvalido, "projetadas"):
            M.ler_arquivo("u.zip", shp_zip(1, [(680000, 7460000)], [("ID", "N", 4)], [(1,)], WKT_UTM))
        with self.assertRaisesRegex(M.ArquivoInvalido, r"\.prj"):
            M.ler_arquivo("u.zip", shp_zip(1, [(-43.2, -22.9)], [("ID", "N", 4)], [(1,)], None))
        mp = bytearray(shp_zip(1, [(-43.2, -22.9)], [("ID", "N", 4)], [(1,)], WKT_WGS))
        z = zipfile.ZipFile(io.BytesIO(bytes(mp)))
        shp = bytearray(z.read("camada.shp"))
        shp[32:36] = struct.pack("<i", 31)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z2:
            for n in z.namelist():
                z2.writestr(n, bytes(shp) if n.endswith(".shp") else z.read(n))
        with self.assertRaisesRegex(M.ArquivoInvalido, "MultiPatch"):
            M.ler_arquivo("m.zip", buf.getvalue())


class Contexto(unittest.TestCase):
    LOCAL = {"lat": -22.9, "lon": -43.2, "municipio": "Teste", "uf": "RJ", "poligono": None, "area_m2": 1200, "fonte": "inicio"}

    def test_sem_camadas_nada_inventado(self):
        c = M.construir_contexto(self.LOCAL, pasta=None)
        self.assertEqual(c["esquema"], M.ESQUEMA_CONTEXTO)
        self.assertEqual(c["campos"]["area_lote_m2"]["valor"], 1200)
        faltam = {f["camada"] for f in c["faltam"]}
        self.assertEqual(faltam, {"relevo", "hidrografia", "uso_solo", "solos", "limites", "car", "risco", "rede_eletrica", "osm", "clima", "irradiacao", "vento"})
        for campo, v in c["campos"].items():
            if v["situacao"] == "camada_nao_instalada":
                self.assertIsNone(v["valor"], campo)
            self.assertTrue(v["fonte"], campo)
        self.assertEqual(len(c["integridade"]["sha256"]), 64)

    def test_sem_localizacao_pede_o_inicio(self):
        c = M.construir_contexto({"fonte": "nao_informado"})
        self.assertTrue(any("Início" in a for a in c["avisos"]))
        self.assertEqual(c["faltam"], [])

    def test_com_camadas_e_base_da_aba_solar(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "hidrografia.geojson").write_text(json.dumps(FC), encoding="utf-8")
            Path(d, "solos.geojson").write_text(json.dumps(FC), encoding="utf-8")
            Path(d, "uso_solo.asc").write_text(asc(40, 40, -43.21, -22.91, 0.0005, lambda x, y: 3 if x < -43.2 else 15), encoding="ascii")
            Path(d, "uso_solo.legenda.json").write_text('{"3": "Formação florestal", "15": "Pastagem"}', encoding="utf-8")
            lote = {"schema": "physis.terreno/1.0", "terreno": {"lat0": -22.9, "lon0": -43.2, "poly": [[-50, -50], [50, -50], [50, 50], [-50, 50]]}}
            c = M.construir_contexto(self.LOCAL, lote, d, irradiacao_solar={"meses": H_RJ, "fonte": "NASA POWER (teste)"})
        self.assertAlmostEqual(c["campos"]["area_lote_m2"]["valor"], 10000, delta=50)
        h = c["campos"]["hidrografia"]["valor"]
        self.assertEqual((h["rios"], h["nascentes"]), (1, 1))
        self.assertLess(h["rio_mais_proximo_m"], 20)
        self.assertEqual(c["campos"]["solos"]["valor"]["classe"], "Latossolo")
        nomes = {x["nome"] for x in c["campos"]["uso_solo"]["valor"]}
        self.assertEqual(nomes, {"Formação florestal", "Pastagem"})
        self.assertAlmostEqual(sum(x["fracao"] for x in c["campos"]["uso_solo"]["valor"]), 1.0)
        self.assertIn("NASA POWER", c["campos"]["irradiacao"]["fonte"])
        self.assertNotIn("irradiacao", {f["camada"] for f in c["faltam"]})

    def test_rotas(self):
        self.assertIsNone(M.rota("GET", "/api/gis/zonas", {}, None))
        cod, r = M.rota("GET", "/api/mapeamento/camadas", {}, None)
        self.assertEqual((cod, len(r["camadas"])), (200, 12))
        con = sqlite3.connect(":memory:")
        with tempfile.TemporaryDirectory() as d:
            up = M.Uploads(con, d)
            cod, r = M.rota("POST", "/api/mapeamento/upload", {}, b"nada", uploads=up, nome_arquivo="x.geojson")
            self.assertEqual(cod, 400)
            cod, r = M.rota("POST", "/api/mapeamento/upload", {}, json.dumps(FC).encode(), uploads=up, nome_arquivo="../../x.geojson")
            self.assertEqual(cod, 200)
            self.assertNotIn("/", r["nome"])
            cod, r = M.rota("GET", "/api/mapeamento/upload", {"id": [r["id"]]}, None, uploads=up)
            self.assertEqual(cod, 200)
        con.close()


class SolNasSuperficies(unittest.TestCase):
    def test_horizontal_sem_sombra_igual_a_base(self):
        r = M.incidencia_superficie(H_RJ, LAT, 0, 0)
        for a, b in zip(r["mensal_kwh_m2_dia"], H_RJ):
            self.assertAlmostEqual(a, b)
        self.assertAlmostEqual(r["fator_anual"], 1.0)

    def test_norte_vence_sul_no_hemisferio_sul(self):
        n = M.incidencia_superficie(H_RJ, LAT, 23, 0)
        s = M.incidencia_superficie(H_RJ, LAT, 23, 180)
        self.assertGreater(n["anual_kwh_m2"], s["anual_kwh_m2"] * 1.1)
        self.assertGreater(n["fator_anual"], 1.0)
        self.assertLess(s["fator_anual"], 1.0)
        # inverno (junho) é onde a face norte mais ganha
        self.assertGreater(n["mensal_kwh_m2_dia"][5] / H_RJ[5], n["mensal_kwh_m2_dia"][0] / H_RJ[0])

    def test_predio_vizinho_ao_norte_faz_sombra(self):
        alvo = {"id": "a", "x": 0, "y": 0, "z": 0.05, "incl": 0, "azim": 0}
        vizinho = [{"id": "v", "x": 0, "y": 12, "w": 30, "d": 8, "rot": 0, "h": 15, "z0": 0}]
        livre = M.incidencia(H_RJ, LAT, [alvo])["superficies"][0]
        com = M.incidencia(H_RJ, LAT, [alvo], caixas=vizinho)["superficies"][0]
        self.assertLess(com["anual_kwh_m2"], livre["anual_kwh_m2"] * 0.9)
        self.assertGreater(com["sombra_pct"], 10)
        hz = M.horizonte(0, 0, 0.05, None, vizinho)
        self.assertGreater(hz[0], math.radians(40))           # norte bloqueado
        self.assertEqual(hz[18], 0.0)                         # sul livre

    def test_terreno_e_fachadas(self):
        nx = ny = 21
        Z = [j * 1.0 for j in range(ny) for _ in range(nx)]   # sobe 1 m por célula para o norte
        g = {"x0": -50, "y0": -50, "cs": 5, "nx": nx, "ny": ny, "Z": Z}
        cel = M.celulas_terreno(g, 50)
        self.assertTrue(cel)
        self.assertAlmostEqual(cel[0]["azim"], 180, delta=1)     # desce para o sul
        self.assertAlmostEqual(cel[0]["incl"], math.degrees(math.atan(0.2)), delta=0.1)
        fa = M.fachadas({"id": "e", "x": 0, "y": 0, "w": 10, "d": 6, "rot": 0, "h": 3})
        self.assertEqual(sorted(round(f["azim"]) % 360 for f in fa), [0, 90, 180, 270])
        pl = M.planos_telhado({"id": "e", "x": 0, "y": 0, "w": 10, "d": 6, "rot": 0, "h": 3, "incl": 20, "azim": 0, "aguas": 2})
        self.assertEqual([p["azim"] for p in pl], [0, 180])


class PlantaSolar(unittest.TestCase):
    def test_curva_diaria_simetrica_ao_meio_dia(self):
        c = M.curva_diaria(5.0, LAT, M.EQUINOCIO_MAR, 20, 0)
        g = [p[1] for p in c["pontos"]]
        for a, b in zip(g, reversed(g)):
            self.assertAlmostEqual(a, b, places=6)
        self.assertAlmostEqual(c["nascer_h"] + c["por_h"], 24)
        self.assertAlmostEqual(c["nascer_h"], 6.0, delta=0.05)          # equinócio: 12 h de sol
        meio = max(c["pontos"], key=lambda p: p[1])
        self.assertAlmostEqual(meio[0], 12, delta=0.2)
        # reescalada para o total do mês (o mesmo da aba Solar)
        t = M.curva_diaria(5.0, LAT, 75, 20, 0, total_plano=5.4)
        self.assertAlmostEqual(t["total_kwh_m2"], 5.4)
        self.assertAlmostEqual(sum(p[1] for p in t["pontos"]) * t["passo_h"] / 1000, 5.4)
        p = M.potencia_ca(t, 10, 25, 45, -0.35)
        self.assertLess(max(x[1] for x in p), 10)

    def test_norte_vence_sul_na_curva_de_inverno(self):
        n = M.curva_diaria(3.5, LAT, M.SOLSTICIO_JUN, 25, 0)
        s = M.curva_diaria(3.5, LAT, M.SOLSTICIO_JUN, 25, 180)
        self.assertGreater(n["total_kwh_m2"], 1.5 * s["total_kwh_m2"])

    def test_sombra_entre_fileiras_no_solsticio_de_inverno(self):
        curto = M.sombra_entre_fileiras(LAT, 25, 0, 2.0, 0.95, 2.5, M.SOLSTICIO_JUN, HORAS)
        self.assertTrue(curto["sombreia"])
        largo = M.sombra_entre_fileiras(LAT, 25, 0, 2.0, 0.95, curto["passo_minimo_m"] + 0.01, M.SOLSTICIO_JUN, HORAS)
        self.assertFalse(largo["sombreia"])
        verao = M.sombra_entre_fileiras(LAT, 25, 0, 2.0, 0.95, 2.5, M.SOLSTICIO_DEZ, HORAS)
        self.assertLess(verao["sombra_max_m"], curto["sombra_max_m"])

    def test_arranjo_no_solo_e_no_telhado(self):
        mod = {"comprimento_m": 2.28, "largura_m": 1.13, "pmax": 550}
        area = [[0, 0], [30, 0], [30, 20], [0, 20]]
        a = M.arranjo(area, mod, orientacao="retrato", empilhados=1, incl=25, azim=0, afastamento_m=1.0, folga_m=0.02, plano="solo", lat=LAT, horas_criticas=HORAS)
        self.assertGreater(a["modulos"], 0)
        self.assertFalse(a["sombra_entre_fileiras"]["sombreia"])
        self.assertAlmostEqual(a["kwp"], a["modulos"] * 0.55)
        self.assertAlmostEqual(a["area_modulos_m2"], a["modulos"] * 2.28 * 1.13)
        apertado = M.arranjo(area, mod, incl=25, azim=0, afastamento_m=1.0, folga_m=0.02, passo_m=2.2, plano="solo", lat=LAT, horas_criticas=HORAS)
        self.assertTrue(apertado["sombra_entre_fileiras"]["sombreia"])
        self.assertGreater(apertado["modulos"], a["modulos"])
        for p in a["posicoes"]:
            self.assertTrue(1.0 <= p["x"] <= 29.0 and 1.0 <= p["y"] <= 19.0)
        casa = [[10, 5], [20, 5], [20, 15], [10, 15]]
        com_casa = M.arranjo(area, mod, incl=25, azim=0, afastamento_m=1.0, folga_m=0.02, plano="solo", lat=LAT, horas_criticas=HORAS, obstaculos=[casa])
        self.assertLess(com_casa["modulos"], a["modulos"])
        self.assertFalse(any(M.dentro_poligono((q["x"], q["y"]), casa) for q in com_casa["posicoes"]))
        tel = M.arranjo([[0, 0], [10, 0], [10, 5], [0, 5]], mod, orientacao="paisagem", afastamento_m=0.3, folga_m=0.02, plano="telhado")
        # paisagem: 2,28 m ao longo da fileira → 4 por fileira em 9,4 m; 1,13 m na água → 3 fileiras em 4,4 m
        self.assertEqual(tel["modulos"], 12)
        self.assertIsNone(tel["sombra_entre_fileiras"])

    def test_carta_solar(self):
        c = M.carta_solar(LAT)
        self.assertEqual(len(c["dias"]), 12)
        jun = c["dias"][5]
        self.assertLess(jun["por_h"] - jun["nascer_h"], 12)          # inverno: dia curto
        self.assertTrue(all(p["altura"] > 0 for d in c["dias"] for p in d["pontos"]))
        meio_dia_jun = next(p for p in jun["pontos"] if p["hora"] == 12)
        self.assertAlmostEqual(meio_dia_jun["azimute"], 0, delta=0.5)   # sol ao norte no inverno do sul
        self.assertAlmostEqual(meio_dia_jun["altura"], 90 - 22.9 - 23.45, delta=0.6)

    @unittest.skipUnless(SOLAR_JS.is_file(), "physis-solar.js fora do pacote")
    def test_perdas_iguais_as_da_aba_solar(self):
        m = re.search(r"const PERDAS_PADRAO = \{([^}]*)\}", SOLAR_JS.read_text(encoding="utf-8"))
        js = {k: float(v) for k, v in re.findall(r"(\w+):([\d.]+)", m.group(1))}
        self.assertEqual(js, {k: float(v) for k, v in M.PERDAS_SOLAR.items()})


class ContratoSimulacaoEExemplos(unittest.TestCase):
    def test_geometria_para_simulacao(self):
        g = {"x0": 0, "y0": 0, "cs": 5, "nx": 2, "ny": 2, "Z": [1, 2, 3, 4]}
        el = [{"id": "c", "tipo": "cisterna", "materiais": [{"id": "concreto_normal", "quantidade": 1, "unidade": "m3"}]}]
        base = {"concreto_normal": {"densidade": 2300, "condutividade": 1.75, "calor_especifico": 1000, "carbono_incorporado": {"valor": 0.13}}}
        d = M.geometria_para_simulacao(-22.9, -43.2, g, [{"id": "e", "x": 0, "y": 0, "w": 1, "d": 1, "h": 3}], [{"id": "s", "incl": 20}], el, base)
        self.assertEqual(d["esquema"], M.ESQUEMA_GEOMETRIA)
        self.assertEqual(d["terreno"]["Z"], [1, 2, 3, 4])
        self.assertEqual(d["elementos_bim"][0]["materiais"][0]["condutividade_w_mk"], 1.75)

    @unittest.skipUnless((RAIZ / "modulos" / "mapeamento" / "exemplos" / "modelo.ifc").is_file(), "exemplos fora do pacote")
    def test_pacote_de_exemplo_marcado_e_legivel(self):
        from physis_hub import ifc
        ex = RAIZ / "modulos" / "mapeamento" / "exemplos"
        for n in ("lote.geojson", "planejador-exemplo.json", "planta-solar.json", "contexto-lugar.json"):
            self.assertIn("FICTÍCIOS", json.loads((ex / n).read_text(encoding="utf-8"))["aviso"], n)
        for n in ("lote.geojson", "pocos.kml", "nascentes-shp.zip"):
            M.ler_arquivo(n, (ex / n).read_bytes())
        r = ifc.ler((ex / "modelo.ifc").read_bytes())
        p = json.loads((ex / "planta-solar.json").read_text(encoding="utf-8"))
        self.assertEqual(r["tipos"]["IFCSOLARDEVICE"], p["total"]["modulos"] + len(p["aguas"]))


@unittest.skipUnless(JS.is_file(), "sistema/physis-mapeamento.js ausente")
class ModuloDaTela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = JS.read_text(encoding="utf-8")

    def test_sem_internet_um_h1_e_selo(self):
        self.assertIsNone(re.search(r"https?://", self.s))
        self.assertEqual(len(re.findall(r"<h1[ >]", self.s)), 1)
        self.assertIn("Em desenvolvimento", self.s)
        self.assertIn("window.telaMapeamentoModulo", self.s)
        self.assertIn("camada não instalada", self.s)

    def test_mesmas_constantes_do_espelho(self):
        self.assertIn(f"PASSOS_DIA = {M.PASSOS_DIA}", self.s)
        self.assertIn(f"SETORES = {M.SETORES}", self.s)
        self.assertIn("DIA_REP=" + json.dumps(M.DIA_REP).replace(" ", ""), self.s.replace(" ", ""))
        self.assertIn("DIA_21=" + json.dumps(M.DIA_21).replace(" ", ""), self.s.replace(" ", ""))
        self.assertIn("eletrica.fator_potencia_padrao", self.s)
        for k in ("S.tCelula", "S.fTemp", "window.SOLAR", "S.calcular(", "PERDAS_PADRAO", "pc.potencias", "potenciasHtml", "PhysisCalc"):
            self.assertIn(k, self.s)

    def test_i18n_valido(self):
        m = re.search(r"window\.MAPEAMENTO_I18N = (\{.*?\});", self.s, re.S)
        d = json.loads(m.group(1))
        self.assertIn("Mapeamento", d)
        self.assertEqual(d["Em desenvolvimento"], "In development")
        rx = re.search(r"window\.MAPEAMENTO_I18N_RX = (\[.*?\]);", self.s, re.S)
        for a, _ in json.loads(rx.group(1)):
            re.compile(a)


if __name__ == "__main__":
    unittest.main()
