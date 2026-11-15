"""Mapa da economia circular: destinos de resíduos perto do lugar (OpenStreetMap pela Overpass, guardado no hub).

Protege:
1. Leitura da resposta da Overpass: nós, vias e relações (pelo centro), categoria pelas etiquetas e pelo nome.
2. Distância (haversine) e rumo conferem com a conta à mão; raio filtra; grupos e o mais próximo de cada tipo.
3. Guarda: a segunda consulta não busca de novo; sem internet entrega o guardado; falha espera uma hora.
4. Importação manual (CSV e GeoJSON) com esquema validado; entra na consulta junto com o OpenStreetMap.
5. CO₂ do transporte: por t·km ou por viagens de caminhão, com o diesel da premissa; sem dado, sem número.
6. O módulo da tela (sistema/physis-circular-mapa.js) não chama a internet.
"""
import json
import math
import re
import unittest
import urllib.error
from pathlib import Path

from physis_hub.gis import Irradiacao
from physis_hub.hub import Hub
from physis_hub import residuos_gis as R

LAT, LON = -22.50, -43.20
# 1 km de latitude ≈ 0,008993°
OVERPASS = {"elements": [
    {"type": "way", "id": 1, "center": {"lat": LAT + 0.08993, "lon": LON}, "tags": {"landuse": "landfill", "name": "Aterro Sanitário Exemplo"}},
    {"type": "way", "id": 2, "center": {"lat": LAT - 0.04497, "lon": LON}, "tags": {"landuse": "landfill", "name": "Lixão do Morro"}},
    {"type": "node", "id": 3, "lat": LAT, "lon": LON + 0.02, "tags": {"amenity": "recycling", "recycling_type": "centre", "name": "Cooperativa Recicla Vida",
                                                               "recycling:paper": "yes", "recycling:glass": "yes", "recycling:cans": "no"}},
    {"type": "node", "id": 4, "lat": LAT + 0.01, "lon": LON, "tags": {"amenity": "recycling", "recycling_type": "container", "recycling:glass_bottles": "yes"}},
    {"type": "node", "id": 5, "lat": LAT + 0.02, "lon": LON + 0.01, "tags": {"amenity": "recycling", "name": "Ecoponto Centro"}},
    {"type": "node", "id": 6, "lat": LAT - 0.02, "lon": LON - 0.02, "tags": {"amenity": "recycling", "recycling_type": "centre", "recycling:rubble": "yes"}},
    {"type": "way", "id": 7, "center": {"lat": LAT + 0.03, "lon": LON - 0.03}, "tags": {"man_made": "wastewater_plant", "name": "ETE Norte"}},
    {"type": "node", "id": 8, "lat": LAT + 0.05, "lon": LON + 0.05, "tags": {"amenity": "waste_transfer_station"}},
    {"type": "node", "id": 9, "lat": LAT - 0.05, "lon": LON + 0.05, "tags": {"amenity": "composting", "name": "Pátio de compostagem"}},
    {"type": "node", "id": 10, "lat": LAT + 1.0, "lon": LON, "tags": {"landuse": "landfill"}},               # ~111 km: fora do raio
    {"type": "node", "id": 11, "lat": LAT, "lon": LON, "tags": {"amenity": "bench"}},                       # não é destino
    {"type": "way", "id": 12, "tags": {"landuse": "landfill"}},                                              # sem coordenada
]}


class Overpass:
    def __init__(self):
        self.consultas, self.fora, self.codigo = [], False, None

    def __call__(self, consulta):
        self.consultas.append(consulta)
        if self.codigo:
            raise urllib.error.HTTPError("x", self.codigo, "ocupada", {}, None)
        if self.fora:
            raise urllib.error.URLError("fora do ar")
        return json.loads(json.dumps(OVERPASS))


class Relogio:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class Leitura(unittest.TestCase):
    def test_categorias(self):
        p = {x["id"]: x for x in R.ler_overpass(OVERPASS)}
        self.assertEqual(len(p), 10)                                  # banco e via sem centro ficam de fora
        cat = {k.split("/")[1]: v["categoria"] for k, v in p.items()}
        self.assertEqual(cat, {"1": "aterro", "2": "lixao", "3": "cooperativa", "4": "pev", "5": "ecoponto", "6": "rcc",
                               "7": "ete", "8": "transbordo", "9": "compostagem", "10": "aterro"})
        self.assertEqual(p["osm:node/3"]["materiais"], ["papel", "vidro"])     # "no" não conta
        self.assertEqual(R.classificar({"landuse": "landfill", "name": "Aterro Controlado X"}), "aterro_controlado")
        self.assertEqual(R.classificar({"industrial": "scrap_yard"}), "sucata")
        self.assertIsNone(R.classificar({"shop": "bakery"}))

    def test_consulta_overpass_e_educada(self):
        q = R.consulta_overpass(LAT, LON, 20)
        self.assertIn("around:20000,-22.50000,-43.20000", q); self.assertIn('"landuse"="landfill"', q)
        self.assertIn("[timeout:60]", q); self.assertIn("out center tags", q)
        self.assertEqual(R.AGENTE, "PhysisHub/1.0")


class Distancias(unittest.TestCase):
    def test_haversine_e_rumo(self):
        self.assertAlmostEqual(R.haversine_km(0, 0, 1, 0), 6371.0088 * math.pi / 180, places=6)   # 111,195 km
        self.assertAlmostEqual(R.haversine_km(LAT, LON, LAT + 0.08993, LON), 10.0, delta=0.01)
        # 0,02° de longitude a 22,5° S: 0,02·111,195·cos(22,5°) = 2,0546 km
        self.assertAlmostEqual(R.haversine_km(LAT, LON, LAT, LON + 0.02), 0.02 * 111.195 * math.cos(math.radians(22.5)), delta=0.001)
        self.assertAlmostEqual(R.rumo_graus(LAT, LON, LAT + 0.1, LON), 0, places=6)
        self.assertAlmostEqual(R.rumo_graus(LAT, LON, LAT, LON + 0.1), 90, delta=0.1)
        self.assertAlmostEqual(R.rumo_graus(LAT, LON, LAT - 0.1, LON), 180, places=6)

    def test_grupos_e_mais_proximo(self):
        g = R.agrupar(R.ler_overpass(OVERPASS), LAT, LON, 20)
        self.assertEqual(len(g["pontos"]), 9)                         # o de 111 km fica fora
        ds = [p["dist_km"] for p in g["pontos"]]
        self.assertEqual(ds, sorted(ds))
        self.assertEqual(g["grupos"]["aterro"]["n"], 1)
        self.assertAlmostEqual(g["grupos"]["aterro"]["mais_proximo"]["dist_km"], 10.0, delta=0.01)
        self.assertAlmostEqual(g["grupos"]["lixao"]["mais_proximo"]["dist_km"], 5.0, delta=0.01)
        rec = R.mais_proximo_para_destino(g["grupos"], "reciclagem")
        self.assertEqual(rec["id"], "osm:node/4")                     # PEV a ~1,1 km é o mais perto dos recicláveis
        self.assertEqual(R.mais_proximo_para_destino(g["grupos"], "aterro2")["categoria"], "transbordo")  # ~7,4 km < 10 km
        self.assertIsNone(R.mais_proximo_para_destino({}, "compostagem"))


class Guardado(unittest.TestCase):
    def novo(self):
        rel, f = Relogio(), Overpass()
        return R.ResiduosGis(Irradiacao(Hub(relogio=rel)), buscar=f), f, rel

    def test_busca_uma_vez_e_sem_internet(self):
        s, f, rel = self.novo()
        r = s.consultar(LAT, LON, 20)
        self.assertTrue(r["ok"]); self.assertEqual(len(f.consultas), 1); self.assertEqual(len(r["pontos"]), 9)
        self.assertIn("OpenStreetMap", r["fonte"]); self.assertEqual(r["destinos"]["compostagem"]["categoria"], "compostagem")
        s.consultar(LAT + 0.001, LON, 10)                             # vizinho e raio menor: do banco
        self.assertEqual(len(f.consultas), 1)
        self.assertEqual(len(s.consultar(LAT, LON, 3)["pontos"]), 3)  # PEV 1,1; cooperativa 2,05; ecoponto 2,45 (RCC a 3,03 fica fora)
        f.fora = True; rel.t += R.VALIDADE + 1                        # vencido e sem internet: entrega o velho e avisa
        r = s.consultar(LAT, LON, 20)
        self.assertTrue(r["ok"]); self.assertEqual(len(r["pontos"]), 9); self.assertTrue(any("indisponível" in a for a in r["avisos"]))
        n = len(f.consultas); s.consultar(LAT, LON, 20)
        self.assertEqual(len(f.consultas), n)                         # dentro da hora de espera: não insiste
        rel.t += R.ESPERA_FALHA + 1; f.fora = False; s.consultar(LAT, LON, 20)
        self.assertEqual(len(f.consultas), n + 1)

    def test_ocupada_e_fora_do_brasil(self):
        s, f, _ = self.novo(); f.codigo = 429
        r = s.consultar(LAT, LON, 20)
        self.assertFalse(r["ok"]); self.assertTrue(any("ocupada" in a for a in r["avisos"]))
        self.assertFalse(s.consultar(40.7, -74.0)["ok"])
        self.assertEqual(s.consultar(LAT, LON, 999)["raio_km"], R.RAIO_MAX)

    def test_importacao_manual(self):
        s, f, _ = self.novo(); f.fora = True
        csv = ("nome;categoria;lat;lon;fonte;municipio;uf\n"
               f"Aterro Regional;aterro;{LAT + 0.0899};{LON};SINIR 2024;Exemplo;RJ\n"
               f"Coop. Mãos;cooperativa;{str(LAT + 0.009).replace('.', ',')};{LON};MUNIC 2023;Exemplo;RJ\n")   # vírgula decimal
        pts = R.importar_csv(csv)
        self.assertEqual([p["categoria"] for p in pts], ["aterro", "cooperativa"]); self.assertEqual(pts[0]["uf"], "RJ")
        s.importar(pts)
        r = s.consultar(LAT, LON, 20)
        self.assertTrue(r["ok"]); self.assertEqual(len(r["pontos"]), 2); self.assertIn("SINIR 2024", r["fonte"])
        gj = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [LON, LAT + 0.01]}, "properties": {"categoria": "rcc", "fonte": "INEA"}},
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[LON, LAT], [LON + 0.02, LAT], [LON + 0.02, LAT + 0.02], [LON, LAT]]]},
             "properties": {"categoria": "compostagem", "fonte": "INEA", "nome": "Pátio"}}]}
        g = R.importar_geojson(gj)
        self.assertAlmostEqual(g[1]["lat"], LAT + 0.01); self.assertAlmostEqual(g[1]["lon"], LON + 0.01)
        s.importar(g); s.importar(g)                                  # reimportar a mesma fonte substitui
        self.assertEqual(len(s.consultar(LAT, LON, 20)["pontos"]), 4)
        with self.assertRaises(ValueError):
            R.importar_csv("nome,categoria,lat,lon,fonte\nX,usina,1,2,SINIR\n")
        with self.assertRaises(ValueError):
            R.importar_csv("nome,categoria,lat,lon,fonte\nX,aterro,1,2,\n")
        with self.assertRaises(ValueError):
            R.importar_geojson({"features": [{"geometry": {"type": "Point", "coordinates": ["a", 1]}, "properties": {"categoria": "aterro", "fonte": "x"}}]})


class Transporte(unittest.TestCase):
    def test_co2(self):
        # 2 t/mês a 25 km com 0,1 kgCO2e/t·km: 50 t·km → 5 kg
        r = R.co2_transporte(2000, 25, fator_kg_tkm=0.1)
        self.assertAlmostEqual(r["t_km"], 50); self.assertAlmostEqual(r["kg_co2_mes"], 5.0)
        # por viagens: 2,5 t com caminhão de 1 t → 3 viagens · 25 km · 2 / 5 km/L = 30 L · 2,671 = 80,13 kg
        r = R.co2_transporte(2500, 25, consumo_km_l=5, carga_t=1, diesel_kg_l=2.671)
        self.assertEqual(r["viagens"], 3); self.assertAlmostEqual(r["litros"], 30); self.assertAlmostEqual(r["kg_co2_mes"], 80.13)
        self.assertIsNone(R.co2_transporte(2000, 25)["kg_co2_mes"])   # sem fator: só t·km
        d = R._diesel_premissa()
        if d is not None:
            self.assertAlmostEqual(d, 2.671)


class ModuloDaTela(unittest.TestCase):
    JS = Path(__file__).resolve().parents[2] / "sistema" / "physis-circular-mapa.js"

    @unittest.skipUnless(JS.is_file(), "sistema/physis-circular-mapa.js ausente")
    def test_sem_internet(self):
        s = self.JS.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"https?://", s), "a tela não chama a internet (só /vendor/ e /mapas/ do próprio servidor)")
        self.assertNotIn("</script", s.lower())
        for x in ("window.telaCircularMapa", "physis-residuos-plano", "api/gis/residuos", "<caption", "tabindex=\"0\"", "__rcmEventos",
                  "Fluxo dos resíduos", "Metodologia e normas", "NBR 10004", "NBR 10007", "12.305", "SINIR"):
            self.assertIn(x, s)
        self.assertNotIn("<h1", s)                                    # é uma parte da aba Economia circular


if __name__ == "__main__":
    unittest.main()
