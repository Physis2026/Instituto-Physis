"""Eletrodo de pH: as contas do módulo enviado, com as quatro correções conferidas."""
import unittest
from datetime import datetime, timedelta

from physis_hub import ph_eletrodo as ph

D = datetime(2026, 11, 1)
C = lambda dias, slope, off: ph.Calibracao(D + timedelta(days=dias), "pre", slope, off, [4.01, 7.0, 10.01], 25.0)
REF = D + timedelta(days=35)


class Eletrodo(unittest.TestCase):
    def test_validade_e_compensacao(self):
        self.assertTrue(C(0, 95, 30).valida()); self.assertFalse(C(0, 94.9, 0).valida()); self.assertFalse(C(0, 100, 30.1).valida())
        self.assertAlmostEqual(ph.compensar_temperatura(7.0, 20.0), 7.015); self.assertAlmostEqual(ph.compensar_temperatura(7.0, 25.0), 7.0)

    def test_saude_segue_o_original_quando_a_calibracao_e_boa(self):
        s = ph.EletrodoPH("pre", [C(0, 99, 5), C(30, 98, 6)]).saude(REF)
        self.assertEqual((s["score"], s["status"], s["dias_desde_calibracao"]), (100.0, "saudavel", 5))
        velha = ph.EletrodoPH("pre", [C(0, 99, 20)]).saude(REF)       # 35 dias; offset 20 mV
        self.assertEqual(velha["score"], 100 - 20 - 25); self.assertEqual(velha["status"], "atencao")

    def test_correcao_calibracao_reprovada(self):
        s = ph.EletrodoPH("pre", [C(0, 99, 5), C(30, 88, 6)]).saude(REF)
        self.assertEqual((s["status"], s["score"], s["slope_pct"]), ("calibracao_reprovada", 0, 88))
        self.assertEqual(ph.EletrodoPH("pre", [C(60, 99, 5)]).saude(REF)["status"], "sem_calibracao")

    def test_correcao_vida_util(self):
        v = ph.EletrodoPH("pre", [C(0, 99, 5), C(30, 98, 6)]).vida_util_estimada(REF)
        self.assertEqual(v["dias_restantes"], 90)                    # faltam 3 pontos, a 1/30 por dia
        self.assertEqual(ph.EletrodoPH("pre", [C(0, 99, 5)]).vida_util_estimada(REF)["motivo"], "sem_historico_drift")
        self.assertEqual(ph.EletrodoPH("pre", [C(0, 99, 5), C(30, 99.1, 5)]).vida_util_estimada(REF)["motivo"], "drift_desprezivel")

    def test_drift(self):
        e = ph.EletrodoPH("pre", [C(0, 100, 0), C(2, 98, 0)])
        self.assertAlmostEqual(e.drift()[0]["slope_pct_por_dia"], -1.0); self.assertTrue(e.drift_excede_limite())
        self.assertFalse(ph.EletrodoPH("pre", [C(0, 100, 0), C(30, 99, 3)]).drift_excede_limite())

    def test_correcao_tempo_de_resposta_nos_dois_sentidos(self):
        t0 = datetime(2026, 11, 10, 8)
        sobe = [(t0 + timedelta(seconds=5 * i), 6.0 + (1 - 2.718281828 ** (-i * 5 / 40))) for i in range(80)]
        desce = [(q, 13.0 - v) for q, v in sobe]
        self.assertEqual(ph.tempo_resposta(sobe, t0, 6.0)["tempo_s"], 40.0)
        self.assertEqual(ph.tempo_resposta(desce, t0, 7.0)["tempo_s"], 40.0)
        self.assertTrue(ph.tempo_resposta(desce, t0, 7.0)["ok"])
        self.assertEqual(ph.tempo_resposta([(t0, 6.0), (t0 + timedelta(seconds=5), 6.01)], t0, 6.0)["motivo"], "mudanca_insuficiente")

    def test_redundancia_laboratorio_travamento_ruido(self):
        t0 = datetime(2026, 11, 10, 8)
        r = ph.validar_redundancia_pre_pos([(t0, 6.8, 6.86, False), (t0, 6.8, 6.95, False), (t0, 6.8, 5.9, True)])
        self.assertEqual([x["alerta_redundancia"] for x in r], [False, True])
        lab = ph.comparar_com_laboratorio([(t0, 6.9)], [(t0 + timedelta(minutes=30), 6.7), (t0 + timedelta(hours=5), 6.7)])
        self.assertTrue(lab[0]["alerta_bias"]); self.assertIsNone(lab[1]["ph_comp"])
        parado = [(t0 + timedelta(minutes=5 * i), 6.80) for i in range(20)]
        self.assertTrue(ph.detectar_travamento(parado)[-1]["alerta_travamento"]); self.assertFalse(ph.detectar_travamento(parado)[3]["alerta_travamento"])
        ruidoso = [(t0 + timedelta(seconds=10 * i), 6.8 + (0.6 if i % 2 else -0.6)) for i in range(20)]
        self.assertTrue(ph.diagnosticar_ruido(ruidoso)[-1]["alerta_ruido"]); self.assertFalse(ph.diagnosticar_ruido(parado)[-1]["alerta_ruido"])

    def test_relatorio(self):
        r = ph.relatorio_eletrodos({"pre": ph.EletrodoPH("pre", [C(0, 99, 5), C(30, 98, 6)])}, REF)
        self.assertEqual((r[0]["status"], r[0]["dias_restantes_estimado"]), ("saudavel", 90))


if __name__ == "__main__":
    unittest.main()
