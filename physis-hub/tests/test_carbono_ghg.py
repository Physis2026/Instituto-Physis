"""Carbono (inventario GHG Protocol): contas de mesa, base de fatores e tela.

Protege:
1. Casos calculados a mao (diesel, rede, R-410A, gado, aterro) batem com physis_hub/carbono.py em ±1%.
2. A base sistema/physis-fatores-emissao.json tem fonte em cada bloco, fatores coerentes e o fator da rede
   do nucleo igual ao de sistema/physis-premissas.json.
3. O formato antigo salvo em "physis-carbono" ({kwh, diesel, glp, gn, solar_kwh, medidas}) continua lido.
4. sistema/physis-carbono.js define a tela inteira, usa um so ouvinte guardado, nao busca nada na internet
   e nao cita parceiros.
"""
import json
import re
import sys
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from physis_hub import carbono as cb  # noqa: E402

RAIZ = AQUI.parents[1]
BASE = RAIZ / "sistema" / "physis-fatores-emissao.json"
JS = RAIZ / "sistema" / "physis-carbono.js"
PREMISSAS = RAIZ / "sistema" / "physis-premissas.json"
NO_REPO = BASE.is_file()


def perto(tc, a, b, tol=0.01):
    tc.assertTrue(abs(a - b) <= tol * max(abs(b), 1e-9), f"{a} difere de {b} em mais de {tol:.0%}")


@unittest.skipUnless(NO_REPO, "só no repositório")
class ContasDeMesa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.F = cb.carregar(BASE)
        cls.ar5 = cb.gwp_de(cls.F, "AR5")
        cls.ar6 = cb.gwp_de(cls.F, "AR6")

    def test_1000_litros_diesel_puro_gerador(self):
        # 1000 L x 35,5 MJ/L = 0,0355 TJ; CO2 74.100 kg/TJ; CH4 10 e N2O 0,6 kg/TJ (estacionária comercial)
        tj = 1000 * 35.5 / 1e6
        mao = (tj * 74100 + tj * 10 * 28 + tj * 0.6 * 265) / 1000
        g, bio = cb.combustao(self.F, "diesel", 1000, "estacionaria")
        perto(self, cb.tco2e(g, self.ar5), mao)
        perto(self, mao, 2.646)
        self.assertEqual(bio, 0)

    def test_1000_litros_diesel_b15_frota(self):
        # 850 L de diesel fóssil + 150 L de biodiesel (CO2 biogênico fica à parte)
        tjf, tjb = 850 * 35.5 / 1e6, 150 * 32.9 / 1e6
        mao = (tjf * 74100 + (tjf + tjb) * 3.9 * 28 + (tjf + tjb) * 3.9 * 265) / 1000
        g, bio = cb.combustao(self.F, "diesel_b", 1000, "movel")
        perto(self, cb.tco2e(g, self.ar5), mao)
        perto(self, bio / 1000, tjb * 70800 / 1000)

    def test_12_mwh_rede(self):
        perto(self, cb.rede_localizacao(12000, 0.0385), 0.462)
        perto(self, cb.rede_mensal([1000] * 12, [0.0385] * 12), 0.462)

    def test_escolha_de_compra_com_irec(self):
        # 12 MWh, 5 MWh com I-REC (fator 0), resto no fator médio
        perto(self, cb.rede_mercado(12000, 0.0385, irec_mwh=5), 7 * 0.0385)
        perto(self, cb.rede_mercado(12000, 0.0385, irec_mwh=0, contratos=[(12, 0)]), 0.0, tol=1)

    def test_2_kg_r410a(self):
        g, quioto = cb.refrigerante(self.F, "R-410A", 2)
        self.assertTrue(quioto)
        perto(self, cb.tco2e(g, self.ar5), 2 * (0.5 * 677 + 0.5 * 3170) / 1000)   # 3,847 t
        perto(self, cb.tco2e(g, self.ar6), 2 * (0.5 * 771 + 0.5 * 3740) / 1000)   # 4,511 t
        g2, _ = cb.refrigerante_carga(self.F, "R-410A", 40, 0.05)
        perto(self, cb.tco2e(g2, self.ar5), 3.847)

    def test_r22_fica_fora_de_quioto(self):
        _, quioto = cb.refrigerante(self.F, "R-22", 1)
        self.assertFalse(quioto)
        r = cb.calcular({"v": 2, "refrig": [{"gas": "R-22", "modo": "recarga", "kg": "1"}]}, {}, self.F)
        self.assertEqual(r["e1"], 0)
        perto(self, r["fora_quioto_t"], 1.76)

    def test_50_cabecas_gado_de_corte(self):
        # entérica 56 + dejetos 1 kg CH4/cabeça; N no pasto: 0,36 kg N/1000 kg/dia x 305 kg x 365
        ch4 = 50 * (56 + 1)
        nex = 0.36 * 305 / 1000 * 365 * 50
        n2o = nex * (0.02 + 0.2 * 0.01 + 0.3 * 0.0075) * 44 / 28
        mao = (ch4 * 28 + n2o * 265) / 1000
        perto(self, cb.tco2e(cb.rebanho(self.F, "gado_corte", 50), self.ar5), mao)
        perto(self, mao, 100.04)

    def test_10_t_rejeito_no_aterro(self):
        ch4_t = 10 * 0.15 * 0.5 * 1.0 * 0.5 * 16 / 12 * (1 - 0) * (1 - 0.1)   # 0,45 t CH4
        perto(self, cb.tco2e(cb.residuo(self.F, "rejeito", 10, "aterro"), self.ar5), ch4_t * 28)   # 12,6 t
        perto(self, cb.tco2e(cb.residuo(self.F, "rejeito", 10, "aterro"), self.ar6), ch4_t * 27.0)
        self.assertEqual(cb.residuo(self.F, "vidro", 10, "aterro").get("CH4_bio", 0), 0)

    def test_compostagem_e_reciclagem(self):
        perto(self, cb.tco2e(cb.residuo(self.F, "alimentos", 1, "compostagem"), self.ar5), 4 * 28 / 1000 + 0.24 * 265 / 1000)
        perto(self, cb.tco2e(cb.residuo(self.F, "papel", 10, "reciclagem"), self.ar5), 0.21)

    def test_fertilizante_ureia_calcario(self):
        # 100 kg de ureia: CO2 = 100 x 0,20 x 44/12; N = 46 kg -> N2O direto + indireto
        g = cb.fertilizante(self.F, kg_ureia=100, kg_calcario=1000)
        perto(self, g["CO2"], 100 * 0.2 * 44 / 12 + 1000 * 0.12 * 44 / 12)
        perto(self, g["N2O"], 46 * (0.01 + 0.1 * 0.01 + 0.3 * 0.0075) * 44 / 28)

    def test_remocoes_por_bioma_e_idade(self):
        perto(self, cb.remocoes(self.F, 2, "mata_atlantica", 5), 18)
        perto(self, cb.remocoes(self.F, 2, "mata_atlantica", 25), 18 * 0.3)

    def test_trajetoria_e_net_zero(self):
        t = cb.trajetoria(100, 2025, 2030, 4.2)
        perto(self, t[-1][1], 100 * (1 - 0.042 * 5))
        self.assertEqual(cb.ano_net_zero(100, 2025, 4.2), 2025 + 22)   # 90% com 4,2% ao ano: 21,4 -> 22 anos

    def test_limites_sbce(self):
        self.assertEqual(cb.sbce(self.F, 9000), "voluntario")
        self.assertEqual(cb.sbce(self.F, 12000), "relato")
        self.assertEqual(cb.sbce(self.F, 30000), "obrigacao")

    def test_numero_brasileiro(self):
        self.assertEqual(cb.num("1.234,5"), 1234.5)
        self.assertEqual(cb.num("0.0385"), 0.0385)
        self.assertEqual(cb.num("1.000"), 1000)
        self.assertIsNone(cb.num("abc"))

    def test_inventario_completo_soma_por_escopo(self):
        estado = {"v": 2, "gwp": "AR5", "kwh": "12000", "rede": {"fator": "2023"},
                  "estac": [{"comb": "diesel", "qtd": "1000", "q": "medido"}],
                  "refrig": [{"gas": "R-410A", "modo": "recarga", "kg": "2"}],
                  "rebanho": [{"tipo": "gado_corte", "cab": "50"}],
                  "e3": {"cats": [5], "residuos": [{"tipo": "rejeito", "t": "10", "destino": "aterro"}]},
                  "solar_kwh": "6000"}
        r = cb.calcular(estado, {}, self.F)
        perto(self, r["e1"], 2.646 + 3.847 + 100.04)
        perto(self, r["e2_loc"], 0.462)
        perto(self, r["e3"], 12.6)
        perto(self, r["total"], r["e1"] + r["e2_loc"] + r["e3"], tol=1e-9)
        perto(self, r["evitadas"]["solar"], 6 * 0.0385)          # evitada: à parte, não abate
        self.assertEqual(r["sbce"], "voluntario")
        self.assertTrue(0 < r["incerteza"] < 1)
        soma_gases = sum(r["por_gas"].values())
        perto(self, soma_gases, r["total"])

    def test_campos_da_tela(self):
        # carga × taxa típica do equipamento (split 5%), taxa digitada em %, teor bio digitado em %
        r = cb.calcular({"v": 2, "refrig": [{"gas": "R-410A", "modo": "carga", "carga": "40", "equip": "split", "taxa_pct": ""},
                                            {"gas": "R-410A", "modo": "carga", "carga": "20", "equip": "split", "taxa_pct": "10"}],
                         "movel": [{"comb": "diesel_b", "qtd": "1000", "teor_pct": "0"}]}, {}, self.F)
        g, _ = cb.combustao(self.F, "diesel", 1000, "movel")
        perto(self, r["e1"], 3.847 * 2 + cb.tco2e(g, self.ar5))

    def test_fatores_mensais(self):
        estado = {"v": 2, "rede": {"usar_mensal": True, "mensal": ["0,05"] * 6 + ["0,03"] * 6}}
        r = cb.calcular(estado, {"kwh_ano": 12000, "kwh_mes": [1000] * 12}, self.F)
        perto(self, r["e2_loc"], 6 * 0.05 + 6 * 0.03)

    def test_residuos_da_economia_circular(self):
        rc = [{"tipo": "rejeito", "qtd": "1", "un": "t_mes", "rota": "aterro"},         # 12 t/ano para fora: escopo 3
              {"tipo": "alimentos", "qtd": "100", "un": "kg_mes", "rota": "compostagem"}]  # no lugar: escopo 1
        r = cb.calcular({"v": 2}, {"rc": rc}, self.F)
        perto(self, r["e3"], 12 * 0.045 * 28)
        perto(self, r["e1"], 1.2 * (0.004 * 28 + 0.00024 * 265))


@unittest.skipUnless(NO_REPO, "só no repositório")
class FormatoAntigo(unittest.TestCase):
    def test_migra_sem_perder_dados(self):
        velho = {"kwh": "24000", "diesel": "1200", "glp": "156", "gn": "", "solar_kwh": "9000", "medidas": [{"n": "bomba de calor", "t": "1,2"}]}
        novo = cb.migrar(velho)
        self.assertEqual(novo["v"], 2)
        self.assertEqual(novo["kwh"], "24000")
        self.assertEqual(novo["solar_kwh"], "9000")
        self.assertEqual([x["comb"] for x in novo["estac"]], ["diesel_b", "glp"])
        self.assertEqual(novo["metas"]["medidas"][0]["n"], "bomba de calor")
        r = cb.calcular(velho)
        self.assertGreater(r["e1"], 3)    # 1200 L de diesel B + 156 kg de GLP
        perto(self, r["e2_loc"], 24 * 0.0289)

    def test_js_le_o_formato_antigo(self):
        js = JS.read_text(encoding="utf-8")
        for campo in ('"diesel"', '"glp"', '"gn"', "solar_kwh", "medidas"):
            self.assertIn(campo, js)


@unittest.skipUnless(NO_REPO, "só no repositório")
class BaseDeFatores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.F = json.loads(BASE.read_text(encoding="utf-8"))

    def test_blocos_com_fonte(self):
        for k in ("combustiveis", "misturas", "refrigerantes", "vazamento", "agro", "uso_solo", "remocoes", "residuos", "sbce"):
            self.assertIn("_fonte", self.F[k], k)
        for k, g in self.F["escopo3"].items():
            self.assertIn("_fonte", g, k)
        for v in ("AR5", "AR6"):
            self.assertIn("fonte", self.F["gwp"][v])
        self.assertIn(self.F["gwp"]["padrao"], ("AR5", "AR6"))

    def test_combustiveis(self):
        for k, c in self.F["combustiveis"].items():
            if k.startswith("_") or not isinstance(c, dict):
                continue
            for campo in ("nome", "unidade", "mj", "co2", "co2_bio", "estacionaria", "movel"):
                self.assertIn(campo, c, f"{k}.{campo}")
            self.assertGreater(c["mj"], 0)
            self.assertTrue(c["co2"] == 0 or c["co2_bio"] == 0, f"{k}: fóssil ou biogênico, não os dois")
        for k, m in self.F["misturas"].items():
            if k.startswith("_") or not isinstance(m, dict):
                continue
            self.assertIn(m["fossil"], self.F["combustiveis"])
            self.assertTrue(0 <= m["teor_bio"] < 1)

    def test_refrigerantes_somam_um_e_tem_gwp(self):
        for k, r in self.F["refrigerantes"].items():
            if k.startswith("_"):
                continue
            self.assertAlmostEqual(sum(r["gases"].values()), 1.0, places=6, msg=k)
            for g in r["gases"]:
                for v in ("AR5", "AR6"):
                    self.assertIn(g, self.F["gwp"][v], f"{k}: {g} sem GWP {v}")

    def test_rede(self):
        A = self.F["rede"]["anual"]
        self.assertIn(self.F["rede"]["padrao"], A)
        for k, x in A.items():
            self.assertTrue(0 < x["valor"] < 0.3, k)
            self.assertTrue(x.get("fonte"), k)

    def test_rede_igual_premissas(self):
        if not PREMISSAS.is_file():
            self.skipTest("sem premissas")
        p = {x["id"]: x for x in json.loads(PREMISSAS.read_text(encoding="utf-8"))["premissas"]}
        self.assertAlmostEqual(self.F["rede"]["anual"]["nucleo"]["valor"], p["rede.fator_emissao"]["valor_padrao"])

    def test_numeros_nao_negativos(self):
        def anda(o, cam=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    anda(v, cam + "." + k)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    anda(v, f"{cam}[{i}]")
            elif isinstance(o, (int, float)) and not isinstance(o, bool):
                self.assertGreaterEqual(o, 0, cam)
        anda(self.F)

    def test_sbce_limites(self):
        self.assertEqual(self.F["sbce"]["limite_relato_t"], 10000)
        self.assertEqual(self.F["sbce"]["limite_obrigacao_t"], 25000)


@unittest.skipUnless(JS.is_file(), "sem o módulo")
class TelaCarbono(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_contrato(self):
        self.assertIn("window.telaCarbono", self.js)
        self.assertIn("window.PhysisCarbono", self.js)
        self.assertEqual(self.js.count("<h1>"), 1, "uma única <h1> na aba")
        for sub in ("Inventário", "Escopo 1", "Escopo 2", "Escopo 3", "Remoções e evitadas", "Metas e net zero", "SBCE e créditos"):
            self.assertIn(sub, self.js)
        self.assertIn('"physis-carbono"', self.js)
        self.assertIn("base-fatores-emissao", self.js)

    def test_um_ouvinte_guardado(self):
        self.assertIn("__carbEventos", self.js)
        self.assertEqual(len(re.findall(r"document\.addEventListener\(", self.js)), 2)   # change e click, dentro da guarda

    def test_tabelas_com_legenda(self):
        self.assertGreaterEqual(self.js.count("<caption"), self.js.count("<table") - 1)

    def test_sem_internet_e_sem_parceiros(self):
        for arq in (JS, BASE, RAIZ / "sistema" / "physis-relatorio-esg.js"):
            if not arq.is_file():
                continue
            t = arq.read_text(encoding="utf-8")
            self.assertNotRegex(t, r"https?://", arq.name)
            self.assertNotRegex(t, r"\bGIZ\b|INTEGRATION environment|PREEEP", arq.name)


@unittest.skipUnless(NO_REPO, "só no repositório")
class EsgotoEMateriais(unittest.TestCase):
    """Parte Esgoto e biogás (Economia circular) e materiais da obra (physis-calc-materiais)."""
    @classmethod
    def setUpClass(cls):
        cls.F = cb.carregar(BASE)

    def test_materiais_da_obra_categoria_1(self):
        mat = {"composicoes": [{"id": "a", "nome": "Parede", "area_m2": "120", "kgco2e_m2": 45},
                               {"id": "b", "nome": "Cobertura", "area_m2": 80, "kgco2e_m2": None}], "zona": 3}
        r = cb.calcular({"v": 2}, {"materiais": mat}, self.F)
        perto(self, r["e3"], 120 * 45 / 1000)               # 5,4 tCO2e; a cobertura sem valor por m² fica [MARCADOR]
        self.assertEqual(r["mat_falta"], ["Cobertura"])
        r2 = cb.calcular({"v": 2, "e3": {"cats": [1], "mat_auto": False}}, {"materiais": mat}, self.F)
        self.assertEqual(r2["e3"], 0)

    def test_esgoto_sem_fator_fica_marcador(self):
        r = cb.calcular({"v": 2}, {"esgoto": {"pessoas": 5, "tratamento": "fossa_filtro", "reuso_m3_dia": 0.65}}, self.F)
        self.assertEqual(r["e1"], 0)
        self.assertTrue(r["esgoto"]["marcador"])
        self.assertTrue(r["reuso_marcador"] or "agua_fornecida" in self.F)
        perto(self, r["reuso_m3"], 0.65 * 365)

    def test_esgoto_com_fator_entra_no_escopo_1(self):
        F = dict(self.F, efluentes={"dbo_kg_pessoa_dia": 0.05, "bo_kg_ch4_kg_dbo": 0.6, "mcf": {"fossa_filtro": 0.5}})   # valores de teste, não de base
        r = cb.calcular({"v": 2, "gwp": "AR5"}, {"esgoto": {"pessoas": 4, "tratamento": "fossa_filtro"}}, F)
        kg = 4 * 0.05 * 365 * 0.6 * 0.5
        perto(self, r["e1"], kg * 28 / 1000)
        self.assertFalse(r["esgoto"]["marcador"])

    def test_js_le_esgoto_biogas_e_materiais(self):
        js = JS.read_text(encoding="utf-8")
        for trecho in ("ebAtual", "physis-calc-esgoto", "physis-calc-biogas", "physis-calc-materiais", "esgoto_no_lugar", "materiais_obra",
                       "mat_auto", "[MARCADOR: fator de metano do tratamento de esgoto", "substitui a soma do plano de resíduos"):
            self.assertIn(trecho, js)
        # sem contar duas vezes: o biogás do registro substitui a soma do plano de resíduos
        self.assertRegex(js, r"biogM3 = bioR \? num\(bioR\.biogas_m3_dia\) \* 365 :")


if __name__ == "__main__":
    unittest.main()
