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


class BancoDeLeitura(unittest.TestCase):
    def setUp(self):
        import sqlite3
        self.con = sqlite3.connect(":memory:")
        ig.preparar(self.con)
        self.lote = fechar([reg("a"), reg("b", 30.0)])
        ig.guardar_lote(self.con, self.lote)

    def test_le_do_banco_sem_blockchain(self):
        lido = ig.ler_lote(self.con, "L1")
        self.assertEqual(lido["resumo_lote"], self.lote["resumo_lote"])
        self.assertEqual(ig.conferir_lote(lido), (True, []))
        self.assertEqual(ig.listar_lotes(self.con)[0]["ancoragens"], [])
        self.assertIsNone(ig.ler_lote(self.con, "nao-existe"))

    def test_banco_so_acrescenta(self):
        import sqlite3
        for sql in ("UPDATE integridade_registro SET valor='99'", "DELETE FROM integridade_registro",
                    "UPDATE integridade_lote SET quantidade=9", "DELETE FROM integridade_lote"):
            with self.assertRaises(sqlite3.DatabaseError, msg=sql):
                self.con.execute(sql)
        with self.assertRaises(sqlite3.IntegrityError):
            ig.guardar_lote(self.con, self.lote)       # o mesmo lote não entra duas vezes

    def test_recusa_lote_adulterado(self):
        mexido = copy.deepcopy(fechar([reg("c")]))
        mexido["registros"][0]["valor"] = 1
        with self.assertRaises(ValueError):
            ig.guardar_lote(self.con, mexido)

    def test_blockchain_e_ancoragem_adicional(self):
        with self.assertRaises(ValueError):
            ig.registrar_ancoragem(self.con, "L-nao-guardado", "blockchain", "tx-1")
        ig.registrar_ancoragem(self.con, "L1", "blockchain", "tx-123", "2026-11-15T10:00:00+00:00")
        self.assertEqual(ig.listar_lotes(self.con)[0]["ancoragens"][0]["referencia"], "tx-123")
        self.assertEqual(ig.conferir_lote(ig.ler_lote(self.con, "L1")), (True, []))   # a ancoragem não muda o lote

    def test_exporta_arquivo_so_leitura(self):
        import os, sqlite3, tempfile
        pasta = tempfile.mkdtemp()
        self.con.execute("CREATE TABLE conta (senha TEXT)")       # nada além da integridade vai no arquivo
        arq = ig.exportar_banco_leitura(self.con, os.path.join(pasta, "leitura.db"))
        ro = ig.abrir_leitura(arq)
        try:
            tabelas = {n for (n,) in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("conta", tabelas)
            self.assertIn("leia_me", tabelas)
            self.assertEqual(ro.execute("SELECT count(*) FROM integridade_leitura").fetchone()[0], 2)
            self.assertEqual(ig.conferir_lote(ig.ler_lote(ro, "L1")), (True, []))
            with self.assertRaises(sqlite3.OperationalError):
                ro.execute("INSERT INTO leia_me VALUES ('x')")
        finally:
            ro.close()


if __name__ == "__main__":
    unittest.main()
