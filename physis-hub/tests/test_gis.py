"""Base GIS de irradiação (Energia solar): busca uma vez, guarda no banco e entrega sem internet.

Protege:
1. O ponto vem com os 12 meses e a média anual; a região vem como grade de pontos.
2. A segunda consulta (e lugares vizinhos, arredondados a 0,25°) não buscam de novo.
3. Fonte fora do ar não derruba nada: responde o que tiver e avisa.
4. Pela rede: a rota exige lat/lon e recusa fora do Brasil.
"""
import json
import unittest
import urllib.error
import urllib.request

from physis_hub.gis import Irradiacao
from physis_hub.hub import Hub
from physis_hub.servidor import iniciar

MESES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
PONTO = {"properties": {"parameter": {"ALLSKY_SFC_SW_DWN": dict(zip(MESES, [5.78, 5.97, 5.14, 4.52, 3.68, 3.46, 3.64, 4.26, 4.57, 5.0, 5.05, 5.56]), ANN=4.71)}}}
REGIAO = {"features": [{"geometry": {"coordinates": [-44.5, -23.5, 66]}, "properties": {"parameter": {"ALLSKY_SFC_SW_DWN": {"ANN": 4.8}}}},
                       {"geometry": {"coordinates": [-43.5, -22.5, 900]}, "properties": {"parameter": {"ALLSKY_SFC_SW_DWN": {"ANN": 4.7}}}},
                       {"geometry": {"coordinates": [-42.5, -21.5, 300]}, "properties": {"parameter": {"ALLSKY_SFC_SW_DWN": {"ANN": -999}}}}]}


class Fonte:
    def __init__(self):
        self.chamadas, self.fora = [], False

    def __call__(self, url):
        self.chamadas.append(url)
        if self.fora:
            raise urllib.error.URLError("fora do ar")
        return json.loads(json.dumps(PONTO if "/point" in url else REGIAO))


class IrradiacaoNoHub(unittest.TestCase):
    def test_busca_uma_vez_e_guarda(self):
        f = Fonte(); g = Irradiacao(Hub(), buscar=f)
        r = g.consultar(-22.505, -43.183)
        self.assertTrue(r["ok"]); self.assertEqual(len(r["ponto"]["meses"]), 12); self.assertEqual(r["ponto"]["anual"], 4.71)
        self.assertEqual(len(r["regiao"]), 2)                       # o -999 (sem dado) fica de fora
        self.assertEqual(len(f.chamadas), 2)
        g.consultar(-22.51, -43.19)                                 # vizinho: mesma busca guardada
        self.assertEqual(len(f.chamadas), 2)
        f.fora = True
        self.assertTrue(g.consultar(-22.5, -43.2)["ok"])             # sem internet, do banco

    def test_fora_do_ar_e_fora_do_brasil(self):
        f = Fonte(); f.fora = True; g = Irradiacao(Hub(), buscar=f)
        r = g.consultar(-15.8, -47.9)
        self.assertFalse(r["ok"]); self.assertEqual(len(r["avisos"]), 2)
        self.assertFalse(g.consultar(40.7, -74.0)["ok"])


class IrradiacaoPelaRede(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": False}, irradiacao=Irradiacao(cls.hub, buscar=Fonte()))
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, rota):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}{rota}", timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_rota(self):
        st, j = self.get("/api/gis/irradiacao?lat=-22.5&lon=-43.18")
        self.assertEqual((st, j["ok"], j["ponto"]["anual"]), (200, True, 4.71))
        self.assertEqual(self.get("/api/gis/irradiacao?lat=x")[0], 400)
        self.assertEqual(self.get("/api/gis/irradiacao?lat=40&lon=-74")[0], 400)


if __name__ == "__main__":
    unittest.main()
