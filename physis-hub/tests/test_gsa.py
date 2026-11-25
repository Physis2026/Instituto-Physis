"""GSA · gestão interna (gsa.py): só convidados ou pedido aceito pela direção; documentos base só com conta."""
import json, os, tempfile, unittest
from pathlib import Path
from physis_hub.hub import Hub
from physis_hub import gsa as g

DIR = {"usuario": "dir@x.org", "papel": "administrador"}
EQ = {"usuario": "eq@x.org", "papel": "operador"}

class GSA(unittest.TestCase):
    def setUp(self):
        self.h = Hub(org="gsa"); self.g = g.GSA(self.h, "")

    def test_pedido_e_aprovacao(self):
        self.assertFalse(self.g.pedir({"nome": "Ana", "email": "ana@x.org", "aceite": False})["ok"])
        self.assertTrue(self.g.pedir({"nome": "Ana", "email": "ana@x.org", "organizacao": "ONG", "aceite": True})["pendente"])
        self.assertTrue(self.g.pedir({"nome": "Ana", "email": "ana@x.org", "aceite": True})["pendente"])   # não duplica
        self.assertEqual(len(self.g.pedidos(DIR)["itens"]), 1)
        self.assertEqual(self.g.pedidos(EQ).get("codigo"), 403)
        pid = self.g.pedidos(DIR)["itens"][0]["id"]
        self.assertEqual(self.g.decidir({"id": pid, "decisao": "aprovar"}, EQ).get("codigo"), 403)
        r = self.g.decidir({"id": pid, "decisao": "aprovar"}, DIR)
        self.assertTrue(r["ok"], r); self.assertIn("/conta/convite", r["texto_convite"])
        self.assertEqual(self.g.decidir({"id": pid, "decisao": "aprovar"}, DIR).get("codigo"), 409)

    def test_recusa_pede_motivo(self):
        self.g.pedir({"nome": "Bia", "email": "bia@x.org", "aceite": True})
        pid = self.g.pedidos(DIR)["itens"][0]["id"]
        self.assertFalse(self.g.decidir({"id": pid, "decisao": "recusar"}, DIR)["ok"])
        self.assertEqual(self.g.decidir({"id": pid, "decisao": "recusar", "motivo": "fora do escopo"}, DIR)["estado"], "recusado")

    def test_documentos_base_sem_sair_da_pasta(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Estatuto.pdf").write_bytes(b"%PDF-1.4")
            (Path(d) / "x.exe").write_bytes(b"MZ")
            os.environ["PHYSIS_GSA_DOCS"] = d
            try:
                self.assertEqual([x["nome"] for x in self.g.documentos(EQ)["itens"]], ["Estatuto.pdf"])
                self.assertIsNotNone(self.g.arquivo("Estatuto.pdf"))
                self.assertIsNone(self.g.arquivo("../" + Path(d).name + "/x.exe"))
                self.assertIsNone(self.g.arquivo("../../etc/passwd"))
            finally:
                os.environ.pop("PHYSIS_GSA_DOCS")

    def test_pagina(self):
        h = (Path(__file__).resolve().parents[1] / "web" / "gsa.html").read_text(encoding="utf-8")
        for k in ("/api/publico/gsa/pedido", "/api/gsa/decidir", "/api/gsa/documentos", "/api/gsa/itens", "/api/gsa/indicadores", "/api/gsa/membros",
                  "Membros", "Projetos", "Tarefas", "Financeiro", "Propostas e editais", "Mapa de parceiros", "Painel de indicadores", "Marketing"):
            self.assertIn(k, h)
        self.assertEqual(h.count("<h1"), 1)
        self.assertNotIn("/gestao/", h, "versão básica: sem a Gestão da Physis")

    def test_itens_alertas_e_financeiro(self):
        self.assertFalse(self.g.salvar({"tipo": "tarefa", "dados": {}}, EQ)["ok"])
        self.assertFalse(self.g.salvar({"tipo": "tarefa", "dados": {"titulo": "x", "prazo": "25/11/2026"}}, EQ)["ok"])
        self.assertTrue(self.g.salvar({"tipo": "tarefa", "dados": {"titulo": "Relatório", "prazo": "2026-11-20", "situacao": "a fazer"}}, EQ)["ok"])
        self.assertTrue(self.g.salvar({"tipo": "edital", "dados": {"titulo": "Chamada X", "prazo": "2026-12-10", "link": "https://exemplo.org"}}, EQ)["ok"])
        self.assertEqual(self.g.salvar({"tipo": "financeiro", "dados": {"descricao": "Doação", "tipo_lancamento": "entrada", "valor": "1.500,00"}}, EQ).get("codigo"), 403)
        self.assertTrue(self.g.salvar({"tipo": "financeiro", "dados": {"descricao": "Doação", "tipo_lancamento": "entrada", "valor": "1.500,00"}}, DIR)["ok"])
        self.assertTrue(self.g.salvar({"tipo": "parceiro", "dados": {"nome": "ONG Sul", "lat": "-22,5", "lon": "-43,2"}}, EQ)["ok"])
        i = self.g.indicadores("2026-11-25")
        self.assertEqual(i["financeiro"]["saldo"], 1500.0)
        self.assertEqual(i["tarefas"]["atrasadas"], 1)
        self.assertTrue(any("Edital fecha" in a for a in i["alertas"]))
        pid = self.g.itens("parceiro")["itens"][0]["id"]
        self.assertTrue(self.g.apagar({"id": pid}, EQ)["ok"]); self.assertEqual(self.g.itens("parceiro")["itens"], [])

if __name__ == "__main__":
    unittest.main()
