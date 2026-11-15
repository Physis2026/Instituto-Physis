import copy
import unittest

from physis_hub import integridade as ig


def reg(i, valor=21.5, qualidade="valido"):
    return {"id": i, "grandeza": "umidade_solo", "valor": valor, "unidade": "%", "quando": "2026-11-15T08:00:00Z",
            "origem": {"aparelho": "v6-0007", "local": "setor-3", "firmware": "6.2"},
            "metodo": {"metodologia": "2026.11", "calibracao": "2026-10-01"}, "qualidade": qualidade}


def fechar(regs, **kw):
    return ig.fechar_lote(regs, lote_id="L1", periodo=("2026-11-01", "2026-11-15"), responsavel="arthur",
                          dicionario="physis/2", **kw)


class Integridade(unittest.TestCase):
    def test_fecha_e_confere(self):
        lote = fechar([reg("b"), reg("a")])
        self.assertEqual([r["id"] for r in lote["registros"]], ["a", "b"])
        self.assertEqual(len(lote["resumo_lote"]), 64)
        self.assertEqual(ig.conferir_lote(lote), (True, []))

    def test_resumo_igual_em_qualquer_ordem(self):
        a, b = fechar([reg("a"), reg("b")]), fechar([reg("b"), reg("a")])
        self.assertEqual(a["resumo_lote"], b["resumo_lote"])

    def test_mudanca_depois_de_fechar_aparece(self):
        lote = fechar([reg("a"), reg("b")])
        mexido = copy.deepcopy(lote)
        mexido["registros"][0]["valor"] = 99
        ok, problemas = ig.conferir_lote(mexido)
        self.assertFalse(ok)
        self.assertTrue(any("a:" in p for p in problemas))

    def test_recusa_incompleto_repetido_e_suspeito(self):
        sem_origem = reg("a"); sem_origem.pop("origem")
        with self.assertRaises(ValueError):
            fechar([sem_origem])
        with self.assertRaises(ValueError):
            fechar([reg("a"), reg("a")])
        with self.assertRaises(ValueError):
            fechar([reg("a", qualidade="suspeito")])
        self.assertTrue(fechar([reg("a", qualidade="suspeito")], aceitar_suspeitos=True))
        with self.assertRaises(ValueError):
            fechar([])

    def test_correcao_nao_apaga(self):
        lote = fechar([reg("a")])
        c = ig.corrigir(lote["registros"][0], 22.0, novo_id="a-c1", quem="arthur", motivo="sensor recalibrado",
                        quando="2026-11-16T09:00:00Z")
        self.assertEqual(c["corrige"]["id"], "a")
        self.assertEqual(c["corrige"]["valor_anterior"], 21.5)
        self.assertEqual(c["corrige"]["resumo_anterior"], lote["registros"][0]["resumo"])
        self.assertEqual(ig.conferir_lote(fechar([c])), (True, []))
        with self.assertRaises(ValueError):
            ig.corrigir(lote["registros"][0], 1, novo_id="x", quem="a", motivo=" ", quando="2026-11-16")


if __name__ == "__main__":
    unittest.main()
