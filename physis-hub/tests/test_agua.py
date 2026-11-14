import unittest
from physis_hub import agua


class Agua(unittest.TestCase):
    def test_atraso_de_mistura(self):
        # trecho de 20 m com 50 mm de diametro tem 39,27 L; a 120 L/min a agua leva 19,6 s
        self.assertAlmostEqual(agua.atraso_de_mistura_s(20, 50, 120), 19.63, places=1)
        self.assertEqual(agua.atraso_de_mistura_s(None, 50, 120, atraso_fixo_s=45), 45)
        self.assertEqual(agua.atraso_de_mistura_s(20, 50, 0, atraso_fixo_s=45), 45)       # sem vazao, vale o fixo
        self.assertIsNone(agua.atraso_de_mistura_s(None, None, None))

    def test_delta_ph_usa_o_antes_atrasado(self):
        pre = [(0, 6.80), (20, 6.90), (40, 7.00)]
        pos = [(40, 6.10)]
        self.assertAlmostEqual(agua.delta_ph(pos, pre, 20)[0]["delta"], 6.10 - 6.90)      # compara com t = 20 s
        self.assertAlmostEqual(agua.delta_ph(pos, pre, None)[0]["delta"], 6.10 - 7.00)    # sem atraso, mesmo instante
        self.assertEqual(agua.delta_ph([(500, 6.0)], pre, 20), [])                        # sem 'antes' proximo, nao compara

    def test_vazao_noturna(self):
        noite = [(22.5, 4.0), (23.0, 5.0), (2.0, 6.0), (12.0, 150.0)]
        r = agua.vazao_noturna(noite, 22, 5, 2.0)
        self.assertEqual((r["n"], r["mediana"], r["alerta"]), (3, 5.0, True))
        self.assertFalse(agua.vazao_noturna(noite, 22, 5, 10.0)["alerta"])
        self.assertFalse(agua.vazao_noturna(noite, 22, 5, None)["alerta"])                # sem limite definido, nao alerta
        self.assertTrue(agua.vazao_noturna(noite[:2], 22, 5, 2.0)["falta"])

    def test_filtro_pede_dois_sinais(self):
        self.assertFalse(agua.sinais_filtro(0.9, 0.8, 3, 5, 2, 7)["limpar"])
        self.assertTrue(agua.sinais_filtro(0.9, 0.8, 6, 5, 2, 7)["limpar"])
        self.assertEqual(agua.sinais_filtro(0.9, None, 6, None, 9, None)["n"], 0)         # sem limite, sem sinal

    def test_bomba(self):
        self.assertEqual(agua.protecao_bomba(12, 220, 100, 4, 10, 190), ["corrente_alta"])
        self.assertEqual(agua.protecao_bomba(8, 170, 0, 4, 10, 190), ["tensao_baixa", "sem_fluxo"])
        self.assertEqual(agua.protecao_bomba(0, 220, 0, 4, 10, 190), [])                   # desligada nao e bomba seca
        self.assertEqual(agua.protecao_bomba(8, 220, 100, None, None, None), [])



class ModoEQueda(unittest.TestCase):
    def test_modo_automatico(self):
        self.assertEqual(agua.resolver_modo("obra", 10, 50, 30, 10)[0], "obra")          # manual prevalece
        self.assertEqual(agua.resolver_modo("auto", 18, 50, 30, 10)[0], "seca")          # seca antes de chuva
        self.assertEqual(agua.resolver_modo("auto", 60, 25, 30, 10)[0], "chuva")
        self.assertEqual(agua.resolver_modo("auto", 60, 2, 30, 10)[0], "normal")
        self.assertEqual(agua.resolver_modo("auto", 18, None, None, None)[0], "normal")  # sem limite, nao muda

    def test_queda_de_energia_nos_dois_cenarios(self):
        r = agua.queda_de_energia(4, 2, 6, 3)
        self.assertAlmostEqual(r["bomba_desliga"]["horas_de_irrigacao_perdidas_mes"], 2.0)
        self.assertEqual(r["bomba_continua"]["horas_de_irrigacao_perdidas_mes"], 0.0)
        self.assertAlmostEqual(r["bomba_continua"]["energia_das_baterias_kwh"], 6.0)


if __name__ == "__main__":
    unittest.main()
