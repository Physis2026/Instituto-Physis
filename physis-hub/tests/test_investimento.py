import unittest
from physis_hub import investimento


class Investimento(unittest.TestCase):
    def test_sem_inflacao(self):
        r = investimento.analise(12000, 600, 10, 12)
        self.assertAlmostEqual(r["retorno_simples_meses"], 20.0, places=6)
        self.assertAlmostEqual(r["vpl"], 30873, delta=5)
        self.assertGreater(r["retorno_descontado_meses"], 20)        # descontado demora mais que o simples
        self.assertGreater(r["tir_ano_pct"], 12)                     # VPL positivo: a TIR passa da taxa
        # na TIR, o VPL e zero
        z = investimento.analise(12000, 600, 10, r["tir_ano_pct"])
        self.assertAlmostEqual(z["vpl"], 0, delta=1)

    def test_inflacao_melhora_o_retorno_nominal(self):
        a = investimento.analise(12000, 600, 10, 12)
        b = investimento.analise(12000, 600, 10, 12, 5)
        self.assertGreater(b["vpl"], a["vpl"])
        self.assertLess(b["retorno_simples_meses"], a["retorno_simples_meses"])

    def test_dados_incompletos(self):
        self.assertIsNone(investimento.analise(0, 600, 10, 12)["vpl"])
        r = investimento.analise(12000, 600, None, None)
        self.assertEqual((r["retorno_simples_meses"], r["vpl"], r["tir_ano_pct"]), (20.0, None, None))
        self.assertIsNone(investimento.analise(12000, 10, 1, 12)["retorno_simples_meses"])   # nao se paga na vida util
        self.assertLess(investimento.analise(12000, 10, 1, 12)["tir_ano_pct"], 0)             # TIR negativa: perde dinheiro


if __name__ == "__main__":
    unittest.main()
