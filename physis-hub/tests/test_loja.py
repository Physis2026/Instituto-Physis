"""Catálogo da loja: o servidor é quem diz o que o cliente vê.

Regras que estes testes protegem:
1. Tudo nasce interno; o público só vê item revisado, em funcionamento e publicado.
2. Item em desenvolvimento, simulação ou parceria nunca vai ao público.
3. Mudar preço, situação ou texto depois da revisão desfaz a revisão e tira do público.
4. Alterar, revisar e publicar exigem sessão, mesmo em instalação sem login.
"""
import json
import unittest
import urllib.error
import urllib.request

from physis_hub.hub import Hub
from physis_hub.servidor import iniciar


class CatalogoNoHub(unittest.TestCase):
    def setUp(self):
        self.h = Hub()

    def test_tudo_nasce_interno(self):
        self.h.loja_gravar("campo", {"st": "func", "preco": 3700}, "ana")
        self.assertEqual(self.h.loja_catalogo()["itens"], {})
        self.assertIn("campo", self.h.loja_catalogo(interno=True)["itens"])

    def test_publicar_exige_revisao(self):
        self.h.loja_gravar("campo", {"st": "func", "preco": 3700}, "ana")
        r = self.h.loja_publicar("campo", "ana")
        self.assertFalse(r["ok"])
        self.assertIn("revisao", r["erro"])
        self.h.loja_revisar("campo", "ana")
        self.assertTrue(self.h.loja_publicar("campo", "ana")["ok"])
        pub = self.h.loja_catalogo()["itens"]
        self.assertEqual(pub["campo"]["preco"], 3700)
        self.assertNotIn("revisado", pub["campo"])          # quem revisou não sai para o público

    def test_em_desenvolvimento_nunca_vai_ao_publico(self):
        for st in ("dev", "sim", "par"):
            self.h.loja_gravar("P5", {"st": st}, "ana")
            self.h.loja_revisar("P5", "ana")
            r = self.h.loja_publicar("P5", "ana")
            self.assertFalse(r["ok"], st)
        self.assertEqual(self.h.loja_catalogo()["itens"], {})

    def test_mudar_preco_tira_do_publico(self):
        self.h.loja_gravar("campo", {"st": "func", "preco": 3700}, "ana")
        self.h.loja_revisar("campo", "ana")
        self.h.loja_publicar("campo", "ana")
        r = self.h.loja_gravar("campo", {"preco": 3900}, "bia")
        self.assertTrue(r["revisao_desfeita"])
        self.assertEqual(self.h.loja_catalogo()["itens"], {})
        # gravar o mesmo valor não desfaz nada
        self.h.loja_revisar("campo", "ana"); self.h.loja_publicar("campo", "ana")
        self.assertFalse(self.h.loja_gravar("campo", {"preco": 3900}, "bia")["revisao_desfeita"])
        self.assertIn("campo", self.h.loja_catalogo()["itens"])

    def test_desfazer_revisao_tira_do_publico(self):
        self.h.loja_gravar("campo", {"st": "func"}, "ana"); self.h.loja_revisar("campo", "ana"); self.h.loja_publicar("campo", "ana")
        self.h.loja_revisar("campo", "ana", revisado=False)
        self.assertEqual(self.h.loja_catalogo()["itens"], {})

    def test_curso_novo(self):
        r = self.h.loja_gravar("curso-solar", {"novo": True, "categ": "cursos", "nome": "Energia solar na fazenda", "carga": "20 h",
                                               "modalidade": "On-line", "link": "https://cursos.physis.example/solar", "st": "func", "preco": None}, "ana")
        self.assertTrue(r["ok"])
        self.h.loja_revisar("curso-solar", "ana"); self.h.loja_publicar("curso-solar", "ana")
        c = self.h.loja_catalogo()["itens"]["curso-solar"]
        self.assertEqual((c["categ"], c["carga"], c["preco"]), ("cursos", "20 h", None))

    def test_valores_invalidos(self):
        ruins = [("x y", {"st": "func"}), ("ok", {"st": "pronto"}), ("ok", {"preco": -1}), ("ok", {"preco": "10"}),
                 ("ok", {"preco": True}), ("ok", {"categ": "outra"}), ("ok", {"nome": "x" * 500}),
                 ("ok", {"link": "http://inseguro.example"}), ("ok", {"novo": True})]
        for ident, campos in ruins:
            self.assertFalse(self.h.loja_gravar(ident, campos, "ana")["ok"], (ident, campos))

    def test_cada_mudanca_fica_no_registro(self):
        antes = self.h.verificar_cadeia()[1]
        self.h.loja_gravar("campo", {"st": "func"}, "ana"); self.h.loja_revisar("campo", "ana"); self.h.loja_publicar("campo", "ana")
        integra, depois = self.h.verificar_cadeia()
        self.assertTrue(integra)
        self.assertEqual(depois - antes, 3)


class CatalogoPelaRede(unittest.TestCase):
    PORTA = 8787

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, cls.PORTA, endereco="127.0.0.1", instancia={"login": False})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def chamar(self, metodo, rota, corpo=None, cookie=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        h = {"Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = cookie
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}{rota}", data=dados, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode() or "{}"), r.headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}"), None

    def test_fluxo_completo(self):
        # sem sessão: nada interno, mesmo com a instalação sem login
        self.assertEqual(self.chamar("POST", "/api/loja/item/campo", {"st": "func"})[0], 401)
        self.assertEqual(self.chamar("GET", "/api/loja/catalogo/interno")[0], 401)
        self.assertEqual(self.chamar("GET", "/api/loja/catalogo")[1]["itens"], {})
        _, _, ck = self.chamar("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana", "senha": "senha-bem-longa"})
        ck = ck.split(";")[0]
        self.assertEqual(self.chamar("POST", "/api/loja/item/campo", {"st": "func", "preco": 3700}, ck)[0], 200)
        self.assertEqual(self.chamar("POST", "/api/loja/item/campo/publicar", {}, ck)[0], 400)
        self.assertEqual(self.chamar("POST", "/api/loja/item/campo/revisar", {}, ck)[0], 200)
        self.assertEqual(self.chamar("POST", "/api/loja/item/campo/publicar", {}, ck)[0], 200)
        self.assertEqual(self.chamar("GET", "/api/loja/catalogo")[1]["itens"]["campo"]["preco"], 3700)
        self.assertEqual(self.chamar("POST", "/api/loja/item/campo/apagar", {}, ck)[0], 404)
        self.assertEqual(self.chamar("POST", "/api/loja/item/a/b/c", {}, ck)[0], 404)

    def test_paginas_servidas(self):
        for rota in ("/loja/", "/loja/interna/"):
            req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}{rota}")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertIn(b"<html", r.read(400).lower())


if __name__ == "__main__":
    unittest.main()
