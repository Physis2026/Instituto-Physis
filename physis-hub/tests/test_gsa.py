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
        for k in ("/api/publico/gsa/pedido", "/api/gsa/decidir", "/api/gsa/documentos", "/gestao/", "/plataforma/", "Mapa de parceiros", "Marketing"):
            self.assertIn(k, h)
        self.assertEqual(h.count("<h1"), 1)

if __name__ == "__main__":
    unittest.main()
