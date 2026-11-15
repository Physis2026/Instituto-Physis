"""Zonas do lugar (IBGE + Köppen) e mapa de solo da região (SoilGrids em grade).

Protege:
1. Köppen: casos clássicos (Manaus Am, como em Alvares et al. 2013, Brasília Aw, Petrolina BSh, Curitiba Cfb, Santa Maria Cfa, Campos do Jordão Cwb).
2. As camadas do IBGE são lidas, limpas e guardadas; sem internet, vêm do banco; uma fora não derruba as outras.
3. A temperatura da NASA é corrigida pela altitude real do lugar.
4. Grade de solo: valores divididos pelo fator, máscara (0) vira vazio, guardada no banco.
"""
import unittest
import urllib.error

from physis_hub.gis import GisExtra, Irradiacao
from physis_hub.hub import Hub
from physis_hub.zonas import Zonas, koppen, ler_feicao, texto
from tests.test_solo import tiff

MANAUS = ([26.5, 26.4, 26.5, 26.6, 26.8, 26.9, 27.0, 27.6, 28.0, 28.0, 27.6, 27.0],
          [9.0, 10.0, 10.5, 10.0, 8.5, 3.5, 2.6, 1.8, 2.6, 3.6, 6.0, 7.8])
BRASILIA = ([21.6, 21.8, 22.0, 21.4, 20.2, 19.1, 19.1, 21.2, 22.5, 22.1, 21.7, 21.5],
            [7.7, 6.4, 6.6, 4.1, 1.0, 0.3, 0.2, 0.4, 1.7, 5.3, 7.8, 7.7])
PETROLINA = ([27.6, 27.3, 27.0, 26.6, 25.8, 24.6, 24.4, 25.3, 27.1, 28.4, 28.4, 27.9],
             [2.6, 2.8, 4.0, 2.0, 0.4, 0.2, 0.1, 0.1, 0.1, 0.4, 1.8, 2.0])
CURITIBA = ([20.5, 20.8, 19.8, 17.7, 14.9, 13.4, 12.9, 14.1, 15.2, 16.9, 18.4, 19.7],
            [6.3, 5.4, 4.3, 3.0, 3.1, 3.2, 3.3, 2.4, 3.8, 4.3, 4.0, 5.0])
SANTA_MARIA = ([24.6, 24.1, 22.5, 19.1, 16.1, 13.4, 13.3, 14.7, 16.5, 19.3, 21.6, 23.6],
               [4.9, 4.6, 4.9, 4.9, 4.4, 4.4, 4.4, 4.0, 5.1, 5.6, 4.6, 4.8])
CAMPOS_JORDAO = ([17.0, 17.3, 16.7, 14.8, 12.0, 10.4, 10.0, 11.4, 13.2, 14.6, 15.5, 16.4],
                 [9.3, 7.5, 6.3, 2.8, 2.0, 1.2, 0.8, 1.3, 3.0, 4.6, 6.2, 8.5])   # julho ~25 mm (normal do INMET)


class Koppen(unittest.TestCase):
    def test_casos_classicos(self):
        for (t, p), esperado in [(MANAUS, "Am"), (BRASILIA, "Aw"), (PETROLINA, "BSh"), (CURITIBA, "Cfb"),
                                 (SANTA_MARIA, "Cfa"), (CAMPOS_JORDAO, "Cwb")]:
            self.assertEqual(koppen(t, p)["codigo"], esperado, esperado)

    def test_dados_incompletos(self):
        with self.assertRaises(ValueError):
            koppen([20] * 11, [3] * 12)


FEICOES = {
    "biomas_5000": {"features": [{"properties": {"cod_bioma": "MAT", "nom_bioma": "Mata  Atlântica", "ds_bioma": "texto longo"}}]},
    "clima_5000": {"features": [{"properties": {"zona": "Tropical Brasil Central", "tp_umidade": "super-úmido", "distr_umid": "sem seca"}}]},
    "vege_area": {"features": [{"properties": {"nm_pretet": "Floresta Ombrófila Densa", "nm_uantr": None}}]},
    "geom_area": {"features": []},
}


class Fonte:
    def __init__(self):
        self.chamadas, self.fora = 0, set()

    def __call__(self, url):
        self.chamadas += 1
        for k, v in FEICOES.items():
            if k in url:
                if k in self.fora:
                    raise urllib.error.URLError("fora do ar")
                return v
        raise urllib.error.URLError("desconhecida")


class Nasa:
    """Temperatura de uma célula a 300 m e chuva; o relevo diz que o lugar está a 900 m."""

    def __call__(self, url):
        if "elevation" in url:
            return {"elevation": [900.0] * 100}
        par = "T2M" if "T2M" in url else "PRECTOTCORR"
        meses = CURITIBA[0] if par == "T2M" else CURITIBA[1]
        nomes = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        if "/point" in url:
            return {"geometry": {"coordinates": [-43.1, -22.4, 300.0]},
                    "properties": {"parameter": {par: dict(zip(nomes, meses), ANN=sum(meses) / 12)}}}
        return {"features": []}


class ZonasNoHub(unittest.TestCase):
    def test_camadas_guardadas_e_koppen_com_altitude(self):
        f = Fonte(); base = Irradiacao(Hub(), buscar=Nasa()); z = Zonas(base, buscar=f)
        r = z.consultar(-22.4, -43.1)
        self.assertTrue(r["ok"])
        self.assertEqual(r["bioma"], {"cod_bioma": "MAT", "nom_bioma": "Mata Atlântica"})      # espaços limpos, só os campos pedidos
        self.assertEqual(r["clima"]["tp_umidade"], "super-úmido")
        self.assertNotIn("relevo", r)                                                        # sem feição: fica de fora
        self.assertEqual(r["koppen"]["ajuste_altitude_c"], -3.9)                             # 600 m acima: -3,9 °C
        self.assertEqual(r["koppen"]["temp_media"], round(sum(CURITIBA[0]) / 12 - 3.9, 1))
        n = f.chamadas
        f.fora = set(FEICOES)
        r2 = z.consultar(-22.4, -43.1)
        self.assertEqual(f.chamadas, n)                        # tudo do banco, inclusive a camada vazia (guardada como {})
        self.assertEqual(r2["bioma"]["nom_bioma"], "Mata Atlântica")

    def test_uma_fora_e_fora_do_brasil(self):
        f = Fonte(); f.fora = {"clima_5000"}
        r = Zonas(Irradiacao(Hub(), buscar=Nasa()), buscar=f).consultar(-22.4, -43.1)
        self.assertTrue(r["ok"]); self.assertNotIn("clima", r); self.assertTrue(any("clima" in a for a in r["avisos"]))
        self.assertFalse(Zonas(Irradiacao(Hub(), buscar=Nasa()), buscar=f).consultar(40.0, -3.0)["ok"])

    def test_texto_latin1_e_feicao(self):
        self.assertEqual(texto("Atlântica".encode("latin-1")), "Atlântica")
        self.assertEqual(texto("Atlântica".encode("utf-8")), "Atlântica")
        self.assertIsNone(ler_feicao({"features": []}, ["a"]))


class GradeDeSolo(unittest.TestCase):
    def test_grade_guardada(self):
        chamadas = []

        def bytes_(url):
            chamadas.append(url)
            return tiff([300, 0, 310, 320, 330, 0, 280, 290, 300], w=3, h=3)
        g = GisExtra(Irradiacao(Hub(), buscar=Nasa()), buscar_bytes=bytes_)
        r = g.solo_grade(-22.4, -43.1, "clay")
        self.assertTrue(r["ok"]); self.assertEqual((r["largura"], r["altura"]), (3, 3))
        self.assertEqual(r["valores"], [30.0, None, 31.0, 32.0, 33.0, None, 28.0, 29.0, 30.0])
        self.assertEqual((r["min"], r["max"], r["unidade"]), (28.0, 33.0, "%"))
        g.solo_grade(-22.4, -43.1, "clay"); self.assertEqual(len(chamadas), 1)
        self.assertFalse(g.solo_grade(-22.4, -43.1, "ouro")["ok"])


if __name__ == "__main__":
    unittest.main()
