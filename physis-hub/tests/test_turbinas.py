"""Turbinas: vento do lugar (NASA POWER a 10 m e 50 m) e as contas eólica e hidráulica (espelho de physis-turbinas.js).

Protege:
1. Vento: busca uma vez, guarda no banco (gis_cache), entrega sem internet; não colide com a camada WS2M do gis.py.
2. Densidade do ar, lei de potência (cisalhamento) e α medido entre 10 m e 50 m conferem com a conta à mão.
3. Weibull: c = v̄/Γ(1+1/k); sem partida, corte nem limite, a energia anual bate com a fórmula fechada
   ½·ρ·A·Cp·c³·Γ(1+3/k)·8760; o Cp nunca passa de Betz; fator de capacidade e mensagem de viabilidade.
4. Hidráulica: a fórmula de sempre (P = 1000·9,81·Q/3600·H·η), perdas por Darcy e Hazen-Williams, sugestão de tipo,
   energia mês a mês com a vazão limitada à de projeto.
5. O módulo da tela (sistema/physis-turbinas.js) não chama a internet e expõe o contrato com a plataforma.
"""
import json
import math
import re
import unittest
import urllib.error
from pathlib import Path

from physis_hub.gis import Irradiacao, MESES
from physis_hub.hub import Hub
from physis_hub import vento as V

RESP = {"geometry": {"coordinates": [-43.25, -22.5, 812.4]},
        "properties": {"parameter": {
            "WS10M": dict(zip(MESES, [3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0, 4.1]), ANN=3.55),
            "WS50M": dict(zip(MESES, [4.0, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 5.0, 5.1]), ANN=4.55),
            "T2M": dict(zip(MESES, [24] * 12), ANN=21.0)}}}
JS = Path(__file__).resolve().parents[2] / "sistema" / "physis-turbinas.js"


class Fonte:
    def __init__(self):
        self.chamadas, self.fora = [], False

    def __call__(self, url):
        self.chamadas.append(url)
        if self.fora:
            raise urllib.error.URLError("fora do ar")
        return json.loads(json.dumps(RESP))


class VentoNoHub(unittest.TestCase):
    def test_busca_uma_vez_guarda_e_funciona_sem_internet(self):
        f = Fonte(); base = Irradiacao(Hub(), buscar=f); v = V.Vento(base)
        r = v.consultar(-22.505, -43.183)
        self.assertTrue(r["ok"]); self.assertEqual(r["ws10"]["anual"], 3.55); self.assertEqual(r["ws50"]["anual"], 4.55)
        self.assertEqual(r["elevacao_m"], 812.4); self.assertIn("WS10M,WS50M", f.chamadas[0])
        self.assertAlmostEqual(r["alfa_medido"], math.log(4.55 / 3.55) / math.log(5), places=3)
        v.consultar(-22.51, -43.19)                 # vizinho (0,25°): do banco
        self.assertEqual(len(f.chamadas), 1)
        f.fora = True
        self.assertTrue(v.consultar(-22.5, -43.2)["ok"])
        self.assertIsNone(base._guardado("vento:ponto:-22.5:-43.25"))      # a camada WS2M do gis.py fica intacta

    def test_fora_do_ar_e_fora_do_brasil(self):
        f = Fonte(); f.fora = True; v = V.Vento(Irradiacao(Hub(), buscar=f))
        r = v.consultar(-15.8, -47.9)
        self.assertFalse(r["ok"]); self.assertEqual(len(r["avisos"]), 1)
        self.assertFalse(v.consultar(40.7, -74.0)["ok"])
        f.fora = False
        self.assertTrue(v.consultar(-15.8, -47.9)["ok"])      # tenta de novo na próxima abertura


class ContasDoVento(unittest.TestCase):
    def test_densidade_do_ar(self):
        self.assertAlmostEqual(V.densidade_ar(0, 15), 1.2250, places=3)          # atmosfera padrão
        # 1000 m e 25 °C, à mão: p = 101325·(1−0,0225577)^5,25588 = 89 875 Pa; ρ = p/(287,05·298,15) = 1,0501
        self.assertAlmostEqual(V.densidade_ar(1000, 25), 1.0501, places=3)

    def test_cisalhamento_e_alfa(self):
        self.assertAlmostEqual(V.cisalhamento(4.0, 10, 30, 0.2), 4.0 * 3 ** 0.2, places=9)   # 4,983 m/s
        self.assertAlmostEqual(V.cisalhamento(4.0, 10, 30, 0.2), 4.9829, places=3)
        self.assertAlmostEqual(V.alfa_medido(4.0, 4.0 * 5 ** 0.143), 0.143, places=6)
        self.assertIsNone(V.alfa_medido(0, 5))
        r = V.eolica({"diametro": 3, "v_ref": 4.0, "h_ref": 10, "altura_cubo": 30, "terreno": "rural"})
        self.assertAlmostEqual(r["alfa"], 0.20); self.assertAlmostEqual(r["v_cubo"], 4.9829, places=3)

    def test_weibull_e_energia_contra_a_formula_fechada(self):
        k, vm = 2.0, 5.0
        c = V.weibull_c(vm, k)
        self.assertAlmostEqual(c, 5.0 / (math.sqrt(math.pi) / 2), places=9)      # Γ(1,5) = √π/2 → c = 5,6419
        self.assertAlmostEqual(c, 5.6419, places=3)
        # a densidade integra 1 e tem a média v̄
        dv = 0.01; s = m = 0.0
        for i in range(6000):
            v = (i + 0.5) * dv; f = V.weibull_pdf(v, k, c); s += f * dv; m += v * f * dv
        self.assertAlmostEqual(s, 1.0, places=4); self.assertAlmostEqual(m, vm, places=3)
        # turbina ideal (sem partida, corte nem limite): kWh = ½ρA·Cp·c³·Γ(1+3/k)·8760/1000
        t = V.turbina_eolica(4.0, 0.35, rho=1.225)
        aep = V.energia_weibull(t, k, c, v_max=60)
        mao = 0.5 * 1.225 * (math.pi * 4) * 0.35 * c ** 3 * math.gamma(2.5) * 8760 / 1000
        self.assertAlmostEqual(aep / mao, 1.0, places=3)
        # à mão: 0,6125 · 12,566 · 0,35 · 179,59 · 1,32934 = 643,2 W médios → 5 634 kWh/ano
        self.assertAlmostEqual(mao, 5634, delta=2)

    def test_curva_de_potencia_e_betz(self):
        t = V.turbina_eolica(3.0, 0.9, v_in=3, v_nom=11, v_out=25)
        self.assertAlmostEqual(t["cp"], 16 / 27)                                    # limitado a Betz
        t = V.turbina_eolica(3.0, 0.30, v_in=3, v_nom=11, v_out=25, p_nom=1.0)
        self.assertEqual(V.potencia_vento(2.9, t), 0.0)
        self.assertAlmostEqual(V.potencia_vento(5, t), 0.5 * 1.225 * math.pi * 2.25 * 125 * 0.30 / 1000)
        self.assertEqual(V.potencia_vento(12, t), 1.0); self.assertEqual(V.potencia_vento(25, t), 0.0)
        # sem potência nominal: sai da velocidade nominal
        t2 = V.turbina_eolica(3.0, 0.30, v_in=3, v_nom=10, v_out=25)
        self.assertAlmostEqual(t2["p_nom"], 0.5 * 1.225 * math.pi * 2.25 * 1000 * 0.30 / 1000)

    def test_eolica_viabilidade_mensal_e_fc(self):
        base = {"diametro": 3.0, "cp": 0.30, "v_in": 3, "v_nom": 11, "v_out": 25, "p_nom": 1.0, "altura_cubo": 10, "h_ref": 10,
                "terreno": "aberto", "altitude": 0, "temperatura": 15}
        fraco = V.eolica({**base, "v_ref": 3.5})
        self.assertEqual(fraco["viabilidade"], "pouco_viavel"); self.assertLess(fraco["fc"], 0.10)
        bom = V.eolica({**base, "v_ref": 6.5, "custo": 30000, "tarifa": 0.9})
        self.assertEqual(bom["viabilidade"], "viavel"); self.assertGreater(bom["aep_kwh"], fraco["aep_kwh"])
        self.assertAlmostEqual(bom["fc"], bom["aep_kwh"] / 8760, places=9)
        self.assertIsNotNone(bom["invest"]["retorno_simples_meses"])
        m = V.eolica({**base, "v_ref": 5.0, "meses_ref": [5.0] * 12})
        self.assertEqual(len(m["meses"]), 12)
        anual = V.eolica({**base, "v_ref": 5.0})
        self.assertAlmostEqual(m["aep_kwh"], anual["aep_kwh"], delta=anual["aep_kwh"] * 1e-9)   # 365 dias = 8760 h
        com_perdas = V.eolica({**base, "v_ref": 5.0, "perdas": 10})
        self.assertAlmostEqual(com_perdas["aep_kwh"], anual["aep_kwh"] * 0.9, places=6)


class ContasDaAgua(unittest.TestCase):
    def test_formula_de_sempre(self):
        # 12 m³/h, 25 m, η 0,6: 1000·9,81·(12/3600)·25·0,6/1000 = 0,4905 kW
        self.assertAlmostEqual(V.potencia_hidraulica(12, 25, 0.6), 0.4905, places=6)
        r = V.hidraulica({"vazao": 12, "queda": 25, "eta": 0.6, "horas": 12, "n": 1})
        self.assertAlmostEqual(r["kw"], 0.4905, places=6)
        self.assertAlmostEqual(r["kwh_ano"], 0.4905 * 12 * 365, places=4)
        self.assertAlmostEqual(V.hidraulica({"vazao": 12, "queda": 2, "un": "bar", "eta": 0.6})["queda_bruta"], 20.4)

    def test_perdas_darcy_e_hazen(self):
        # 36 m³/h (0,01 m³/s) em 100 mm, 100 m de PVC: v = 1,273 m/s; Re ≈ 126 800
        d = V.perda_darcy(36, 100, 100, 0.0015)
        self.assertAlmostEqual(d["v"], 0.01 / (math.pi * 0.01 / 4), places=6)
        f = 0.25 / math.log10(0.0015e-3 / 0.37 + 5.74 / d["re"] ** 0.9) ** 2
        self.assertAlmostEqual(d["f"], f, places=9)
        self.assertAlmostEqual(d["hf"], f * 1000 * d["v"] ** 2 / (2 * 9.81), places=9)    # ~1,4 m
        self.assertTrue(1.2 < d["hf"] < 1.6)
        h = V.perda_hazen(36, 100, 100, 150)
        self.assertAlmostEqual(h["hf"], 10.67 * 100 * 0.01 ** 1.852 / (150 ** 1.852 * 0.1 ** 4.87), places=9)
        self.assertTrue(1.0 < h["hf"] < 1.6)
        self.assertEqual(V.perda_darcy(0, 100, 100, 0.0015)["hf"], 0.0)
        self.assertAlmostEqual(V.perda_darcy(0.05, 100, 1, 0.0015)["f"], 64 / V.perda_darcy(0.05, 100, 1, 0.0015)["re"])  # laminar

    def test_queda_liquida_mensal_e_tipos(self):
        p = {"vazao": 36, "queda": 30, "eta": 0.7, "horas": 24, "n": 1,
             "tubo": {"material": "pvc", "diametro_mm": 100, "comprimento_m": 100, "metodo": "darcy"},
             "vazoes_mes": [50, 50, 40, 36, 30, 20, 10, 10, 15, 25, 36, 45]}
        r = V.hidraulica(p)
        self.assertAlmostEqual(r["queda_liquida"], 30 - r["perda_m"], places=9)
        self.assertEqual(r["meses"][0]["vazao"], 36)                 # acima da de projeto: o resto passa pelo vertedouro
        self.assertEqual(r["meses"][6]["vazao"], 10)
        self.assertAlmostEqual(r["kwh_ano"], sum(m["kwh"] for m in r["meses"]))
        self.assertLess(r["kwh_ano"], r["kw"] * 24 * 365)
        din = V.hidraulica({**p, "pressao_dinamica": True})
        self.assertEqual(din["perda_m"], 0.0)
        alta = V.sugerir_tipos(200, 36)                               # 200 m, 0,01 m³/s
        self.assertEqual(alta[0]["id"], "pelton"); self.assertTrue(alta[0]["dentro"])
        baixa = V.sugerir_tipos(3, 3600)                              # 3 m, 1 m³/s
        self.assertIn(baixa[0]["id"], ("kaplan", "banki")); self.assertNotIn("pelton", [t["id"] for t in baixa if t["dentro"]])
        self.assertIn("pat", [t["id"] for t in V.sugerir_tipos(30, 36) if t["dentro"]])
        self.assertEqual(V.sugerir_tipos(0, 10), [])
        self.assertTrue(any("10%" in a for a in V.hidraulica({**p, "tubo": {**p["tubo"], "diametro_mm": 50}})["avisos"]))


@unittest.skipUnless(JS.is_file(), "sistema/physis-turbinas.js ausente")
class ModuloDaTela(unittest.TestCase):
    def test_sem_internet_e_contrato(self):
        s = JS.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"https?://", s), "a tela não chama a internet")
        self.assertNotIn("</script", s.lower())
        for x in ("window.TURBINAS", "window.telaTurbinas", "hidraulica", "eolica", "aria-pressed", "__turbEventos",
                  "<h1>Turbinas</h1>", "api/gis/vento", "Metodologia e normas", "IEC 61400-2", "IEC 61400-12-1",
                  "NBR 10151", "NBR 12214", "IEC 61116", "14.300", "1.059/2023"):
            self.assertIn(x, s)
        self.assertEqual(s.count("<h1>"), 1)
        # mesmas constantes da conta do servidor
        for x in ("16 / 27", "2.25577e-5", "5.25588", "287.05", "10.67", "1.852", "4.87", "5.74", "1.004e-6"):
            self.assertIn(x, s)


if __name__ == "__main__":
    unittest.main()
