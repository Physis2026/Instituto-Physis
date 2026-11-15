"""Carga térmica (sistema/physis-cargatermica.js e o espelho physis_hub/cargatermica.py).

Protege:
1. As tabelas (bloco DADOS) do .js e do .py são idênticas.
2. O módulo de tela não usa internet nem eval, tem um único <h2> e expõe o contrato combinado.
3. Casos conferidos à mão (tolerância de 5 %):

Caso A — só cargas internas, ar externo, infiltração e parede sem sol (lat 0, TBS 32 °C, amplitude 10 °C, w ext = 18 g/kg,
interior 24 °C / 50 %, nível do mar). Ambiente 20 m², pé-direito 3 m, 2 pessoas em escritório (75 W sens. / 55 W lat.),
iluminação 10 W/m², equipamentos 15 W/m², infiltração 0,5 troca/h, ar externo 2,5 L/s·pessoa + 0,3 L/s·m², parede 10 m²,
U = 2, sem sol, sem massa. O pico é às 14 h (fração da amplitude = 0 → T ext = 32 °C, ΔT = 8 K).
   w int: pws(24) = 0,61094·e^(17,625·24/267,04) = 2,978 kPa; pv = 1,489; w = 0,621945·1,489/(101,325−1,489) = 9,276 g/kg
   Δw = 18 − 9,276 = 8,724 g/kg
   parede 2·10·8 = 160 · pessoas 150 S + 110 L · iluminação 200 · equipamentos 300
   infiltração 0,5·60/3,6 = 8,333 L/s → S = 1,23·8,333·8 = 82,0 ; L = 3010·8,333·0,008724 = 218,8
   ar externo 2·2,5 + 20·0,3 = 11 L/s → S = 1,23·11·8 = 108,2 ; L = 3010·11·0,008724 = 288,8
   sensível 1000,2 W · latente 617,6 W · total 1617,9 W · com FS 1,1 → 1779,7 W = 6073 BTU/h = 0,506 TR

Caso B — cobertura escura ao meio-dia no equador, equinócio (março, declinação 0): sen β = 1;
   I_DN = 1186·e^(−0,156) = 1014,7 W/m²; horizontal = 1014,7 + 0,071·1014,7 = 1086,7 W/m²
   T ext(12 h) = 32 − 10·0,13 = 30,7 °C; T sol-ar = 30,7 + 0,9·1086,7/17 − 3,9 = 84,33 °C
   U = 5, A = 20 m², sem massa → Q = 5·20·(84,33 − 24) = 6033 W

Caso C — vidro a leste às 8 h, mesmo dia: H = −60°, sen β = 0,5, azimute 90° (leste), cos θ = cos 30° = 0,866
   I_DN = 1186·e^(−0,156/0,5) = 868,2; direta 751,9; difusa 0,071·868,2·0,5 = 30,8; refletida 0,2·868,2·(0,071+0,5)·0,5 = 49,6
   total 832,3 W/m² × 2 m² × fator solar 0,5 = 832,3 W

Caso D — parede pesada sem sol (U = 2, A = 10, atraso 3 h, amortecimento 0,5), às 17 h:
   média diária da fração da amplitude = 12,87/24 = 0,53625 → T média = 32 − 5,3625 = 26,64 °C
   T ext(17 − 3 = 14 h) = 32 °C → Q = 2·10·[(26,64 − 24) + 0,5·(32 − 26,64)] = 106,4 W

Caso E — psicrometria: TBS 32 / TBU 24 °C ao nível do mar → 15,45 g/kg (carta psicrométrica ≈ 15,4).
"""
import json
import re
import sys
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from physis_hub import cargatermica as ct  # noqa: E402

RAIZ = AQUI.parents[1]
JS = RAIZ / "sistema" / "physis-cargatermica.js"
NO_REPO = JS.is_file()
CLIMA_EQ = {"tbs": 32, "dr": 10, "lat": 0, "alt": 0, "w": 18, "tint": 24, "urint": 50}
OP_EQ = {"mes": 3, "declinacao": 0}


def perto(tc, obtido, esperado, tol=0.05):
    tc.assertLessEqual(abs(obtido - esperado), abs(esperado) * tol, f"{obtido} longe de {esperado}")


class CasosAMao(unittest.TestCase):
    def test_caso_a_cargas_internas(self):
        amb = [{"nome": "A", "area": 20, "pe_direito": 3, "pessoas": 2, "atividade": "escritorio", "uso": "escritorio",
                "iluminacao_wm2": 10, "equipamentos_wm2": 15, "infiltracao_ach": 0.5,
                "superficies": [{"tipo": "parede", "sol": False, "area": 10, "u": 2, "atraso": 0, "amortecimento": 1}]}]
        r = ct.calcular(amb, CLIMA_EQ, dict(OP_EQ, fs=1.1))
        a = r["ambientes"][0]
        self.assertEqual(a["pico"]["h"], 14)
        perto(self, a["pico"]["sens"], 1000.2)
        perto(self, a["pico"]["lat"], 617.6)
        perto(self, a["pico"]["total"], 1617.9)
        perto(self, a["projeto"]["W"], 1779.7)
        perto(self, a["projeto"]["btuh"], 6073)
        perto(self, a["projeto"]["tr"], 0.506)
        perto(self, a["vazao_ar_externo_ls"], 11)

    def test_caso_b_cobertura_ao_sol(self):
        amb = [{"nome": "B", "area": 20, "pessoas": 0, "iluminacao_wm2": 0, "equipamentos_wm2": 0, "infiltracao_ach": 0,
                "superficies": [{"tipo": "cobertura", "area": 20, "u": 5, "atraso": 0, "amortecimento": 1, "absortancia": 0.9}]}]
        r = ct.calcular(amb, CLIMA_EQ, OP_EQ)
        h12 = next(x for x in r["ambientes"][0]["horas"] if x["h"] == 12)
        perto(self, h12["comp"]["envoltoria"], 6033)
        self.assertEqual(r["ambientes"][0]["pico"]["h"], 12)

    def test_caso_c_vidro_leste(self):
        cl = ct.resolver_clima(CLIMA_EQ, OP_EQ)
        perto(self, ct.irradiancia(cl, 8, 90), 832.3)
        amb = [{"nome": "C", "area": 10, "pessoas": 0, "iluminacao_wm2": 0, "equipamentos_wm2": 0, "infiltracao_ach": 0,
                "superficies": [{"tipo": "vidro", "orient": "L", "area": 2, "fs": 0.5, "u": 5.7}]}]
        r = ct.calcular(amb, CLIMA_EQ, OP_EQ)
        h8 = next(x for x in r["ambientes"][0]["horas"] if x["h"] == 8)
        perto(self, h8["comp"]["vidro_solar"], 832.3)

    def test_caso_d_massa_termica(self):
        amb = [{"nome": "D", "area": 10, "pessoas": 0, "iluminacao_wm2": 0, "equipamentos_wm2": 0, "infiltracao_ach": 0,
                "superficies": [{"tipo": "parede", "sol": False, "area": 10, "u": 2, "atraso": 3, "amortecimento": 0.5}]}]
        r = ct.calcular(amb, CLIMA_EQ, OP_EQ)
        h17 = next(x for x in r["ambientes"][0]["horas"] if x["h"] == 17)
        perto(self, h17["comp"]["envoltoria"], 106.4)

    def test_caso_e_psicrometria(self):
        cl = ct.resolver_clima({"tbs": 32, "tbu": 24, "alt": 0}, {})
        perto(self, cl["w_ext"] * 1000, 15.45, 0.01)
        perto(self, cl["w_int"] * 1000, 9.276, 0.01)

    def test_unidades_e_fator(self):
        r = ct.calcular([{"nome": "x", "area": 10, "pessoas": 1}], {"cidade": "Recife"}, {"fs": 1.0})
        p = r["ambientes"][0]["projeto"]
        perto(self, p["btuh"] / p["W"], 3.412142, 0.001)
        perto(self, p["W"] / p["tr"], 3516.853, 0.001)

    def test_pico_simultaneo_nao_passa_da_soma(self):
        base = ct.carregar_base()
        r = ct.calcular([{"nome": "leste", "area": 15, "pessoas": 2, "superficies": [{"tipo": "vidro", "orient": "L", "area": 4, "material": "vidro_simples"}]},
                         {"nome": "oeste", "area": 15, "pessoas": 2, "superficies": [{"tipo": "vidro", "orient": "O", "area": 4, "material": "vidro_simples"}]}],
                        {"cidade": "Brasília"}, {"equipamentos": base})
        self.assertLessEqual(r["total"]["bloco"]["total"], r["total"]["soma_picos"] + 1e-6)
        self.assertNotEqual(r["ambientes"][0]["pico"]["h"], r["ambientes"][1]["pico"]["h"])
        self.assertLess(r["total"]["diversidade"], 1)

    def test_sugestao_de_sistema(self):
        base = ct.carregar_base()
        self.assertIsNotNone(base)
        peq = ct.calcular([{"nome": "q", "area": 12, "pessoas": 2}], {"cidade": "São Paulo"}, {"equipamentos": base, "tarifa": 1.0})
        self.assertEqual(peq["sistema"]["recomendado"], "split")
        self.assertTrue(peq["sistema"]["opcoes"][0]["equipamentos"][0]["id"].startswith("ac-split-hiwall-inv"))
        self.assertIsNotNone(peq["sistema"]["opcoes"][0]["custo_ano"])
        salas = [{"nome": f"s{i}", "area": 60, "pessoas": 8, "equipamentos_wm2": 20} for i in range(8)]
        med = ct.calcular(salas, {"cidade": "Rio de Janeiro"}, {"equipamentos": base})
        self.assertEqual(med["sistema"]["recomendado"], "vrf", med["total"]["projeto"]["tr"])
        grande = ct.calcular([{"nome": f"p{i}", "area": 400, "pessoas": 40, "equipamentos_wm2": 25} for i in range(10)], {"cidade": "Manaus"}, {"equipamentos": base})
        self.assertEqual(grande["sistema"]["recomendado"], "chiller")
        # energia anual: pico simultâneo × horas × fator de carga ÷ eficiência sazonal × auxiliares
        o = peq["sistema"]["opcoes"][0]
        perto(self, o["kwh_ano"], peq["total"]["bloco"]["total"] / 1000 * 2600 * 0.5 / o["sazonal"] * o["aux"], 0.001)
        self.assertIsNone(ct.calcular([{"nome": "q", "area": 12}], {"cidade": "São Paulo"}, {})["sistema"]["opcoes"][0]["custo_ano"])

    def test_cidades_tem_dados(self):
        for c in ct.DADOS["cidades"]:
            for k in ("lat", "alt", "tbs", "tbu", "dr"):
                self.assertIn(k, c)
            self.assertLess(c["tbu"], c["tbs"])
            self.assertTrue(-34 < c["lat"] < 6)


@unittest.skipUnless(NO_REPO, "só no repositório")
class ModuloDaTela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_dados_iguais_no_js_e_no_py(self):
        m = re.search(r"/\*DADOS-INICIO\*/\s*const DADOS = (.*?);\s*/\*DADOS-FIM\*/", self.js, re.S)
        self.assertIsNotNone(m, "bloco DADOS não encontrado no .js")
        self.assertEqual(json.loads(m.group(1)), ct.DADOS)

    def test_sem_internet_nem_eval(self):
        for proibido in (r"https?://", r"\beval\s*\(", r"new\s+Function", r"\bfetch\s*\(", r"XMLHttpRequest", r"\bimport\s*\(", r"</script"):
            self.assertIsNone(re.search(proibido, self.js, re.I), proibido)

    def test_contrato(self):
        self.assertIn("window.CARGA_TERMICA = API", self.js)
        self.assertIn("window.telaCargaTermica = telaCargaTermica", self.js)
        self.assertIn("calcular", self.js)
        self.assertEqual(len(re.findall(r"<h2[\s>]", self.js)), 1, "a sub-aba tem um único <h2>")
        self.assertNotRegex(self.js, r"<h1[\s>]")
        for cor in set(re.findall(r"#[0-9A-Fa-f]{6}\b", self.js)):
            self.assertIn(cor.upper(), (RAIZ / "physis-hub" / "docs" / "PALETA.md").read_text(encoding="utf-8").upper(), f"cor fora da paleta: {cor}")

    def test_mesmas_formulas_no_js(self):
        """Confere que as constantes e expressões centrais do .py aparecem no .js (espelho)."""
        for trecho in ("0.61094 * Math.exp(17.625 * t / (t + 243.04))", "2.25577e-5", "(2501 - 2.326 * tbu)", "Math.exp(-abc[1] / sb)",
                       "K.refletancia_solo * s.idn * (s.C + s.sb) * 0.5", "pr.amort * (interp(tsa, h - pr.atraso) - tm)", "vol / 3.6",
                       "kwBloco * op.horas_ano * op.fator_carga / saz * aux"):
            self.assertIn(trecho, self.js, trecho)


if __name__ == "__main__":
    unittest.main()
