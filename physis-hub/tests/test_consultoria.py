"""Página pública de consultoria e textos editáveis do site.

Regras que estes testes protegem:
1. /consultoria é pública (mesmo em instalação que exige login), como a loja.
2. Ler os textos do site é público; gravar exige sessão.
3. Só texto puro é guardado (HTML é retirado); 4000 caracteres por bloco, 200 blocos, página ^[a-z0-9-]{1,40}$.
4. O formulário da página manda um pedido que /api/central/pedido aceita.
"""
import json
import re
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from physis_hub.hub import Hub
from physis_hub.servidor import iniciar

PAGINA = Path(__file__).resolve().parent.parent / "web" / "consultoria.html"


class TextosNoHub(unittest.TestCase):
    def setUp(self):
        self.h = Hub()

    def test_gravar_ler_e_apagar(self):
        self.assertEqual(self.h.site_textos("consultoria")["textos"], {})
        r = self.h.site_gravar("consultoria", {"heroi.titulo": "Novo título"}, "ana")
        self.assertTrue(r["ok"])
        self.assertEqual(self.h.site_textos("consultoria")["textos"], {"heroi.titulo": "Novo título"})
        self.h.site_gravar("consultoria", {"heroi.titulo": ""}, "ana")      # vazio volta ao original
        self.assertEqual(self.h.site_textos("consultoria")["textos"], {})

    def test_html_retirado(self):
        self.h.site_gravar("consultoria", {"a": "<b>Olá</b> <script>alert(1)</script>mundo<img src=x onerror=y>"}, "ana")
        t = self.h.site_textos("consultoria")["textos"]["a"]
        self.assertNotIn("<", t)
        self.assertNotIn(">", t)
        self.assertEqual(t, "Olá alert(1)mundo")

    def test_limites(self):
        self.assertFalse(self.h.site_gravar("Consultoria!", {"a": "x"}, "ana")["ok"])
        self.assertFalse(self.h.site_gravar("x" * 41, {"a": "x"}, "ana")["ok"])
        self.assertFalse(self.h.site_gravar("consultoria", {"a": "x" * 4001}, "ana")["ok"])
        self.assertTrue(self.h.site_gravar("consultoria", {"a": "x" * 4000}, "ana")["ok"])
        self.assertFalse(self.h.site_gravar("consultoria", {f"k{i}": "x" for i in range(201)}, "ana")["ok"])
        self.assertFalse(self.h.site_gravar("consultoria", {"A B": "x"}, "ana")["ok"])
        self.assertFalse(self.h.site_gravar("consultoria", {"a": 3}, "ana")["ok"])
        self.assertFalse(self.h.site_gravar("consultoria", ["a"], "ana")["ok"])
        # o total guardado por página também respeita 200 blocos
        self.assertTrue(self.h.site_gravar("consultoria", {f"k{i}": "x" for i in range(199)}, "ana")["ok"])
        self.assertFalse(self.h.site_gravar("consultoria", {"z1": "x", "z2": "x"}, "ana")["ok"])
        self.assertTrue(self.h.site_gravar("consultoria", {"z1": "x", "k0": ""}, "ana")["ok"])

    def test_paginas_separadas(self):
        self.h.site_gravar("consultoria", {"a": "um"}, "ana")
        self.h.site_gravar("outra-pagina", {"a": "dois"}, "ana")
        self.assertEqual(self.h.site_textos("consultoria")["textos"]["a"], "um")
        self.assertEqual(self.h.site_textos("outra-pagina")["textos"]["a"], "dois")


class PaginaNoServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        # instalação que exige login: a página e a leitura dos textos continuam públicas
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": True, "modulos": ["monitoramento"]})
        cls.PORTA = cls.srv.server_address[1]
        st, j, ck = cls.chamar(None, "POST", "/api/conta/criar",
                               {"nome": "Ana", "usuario": "ana@physis.eng.br", "senha": "senha-bem-longa"})
        assert st == 200 and ck, (st, j)
        cls.cookie = ck.split(";", 1)[0]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    @classmethod
    def chamar(cls, _self, metodo, rota, corpo=None, cookie=None, bruto=False):
        dados = json.dumps(corpo).encode() if isinstance(corpo, (dict, list)) else (corpo.encode() if isinstance(corpo, str) else corpo)
        cab = {"Content-Type": "application/json"}
        if cookie:
            cab["Cookie"] = cookie
        req = urllib.request.Request(f"http://127.0.0.1:{cls.PORTA}{rota}", data=dados, method=metodo, headers=cab)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                corpo_r = r.read()
                if bruto:
                    return r.status, corpo_r.decode("utf-8"), r.headers
                return r.status, json.loads(corpo_r.decode() or "{}"), r.headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            corpo_r = e.read()
            if bruto:
                return e.code, corpo_r.decode("utf-8", "replace"), e.headers
            return e.code, json.loads(corpo_r.decode() or "{}"), None

    def c(self, *a, **k):
        return self.chamar(None, *a, **k)

    def test_pagina_publica(self):
        for rota in ("/consultoria", "/consultoria/"):
            st, html, cab = self.c("GET", rota, bruto=True)
            self.assertEqual(st, 200, rota)
            self.assertIn("text/html", cab.get("Content-Type"))
            self.assertIn("Content-Security-Policy", cab)
            self.assertIn('data-chave="heroi.titulo"', html)
            self.assertIn("/api/central/pedido", html)
            self.assertIn("/api/site/textos/consultoria", html)

    def test_pagina_sem_recurso_externo(self):
        html = PAGINA.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"<h1[\s>]", html)), 1)              # um título só
        self.assertNotRegex(html, r'<script[^>]+src=')
        self.assertNotRegex(html, r'<link[^>]+stylesheet')
        self.assertNotRegex(html, r'(src|href)="https?://')
        self.assertNotIn("@import", html)
        # todo campo do formulário tem rótulo
        for ident in re.findall(r'<(?:input|textarea)[^>]*\bid="([^"]+)"', html):
            if ident != "f-lgpd":                       # este fica dentro do próprio <label>
                self.assertIn(f'for="{ident}"', html)
        chaves = re.findall(r'data-chave="([^"]+)"', html)
        self.assertEqual(len(chaves), len(set(chaves)))
        self.assertLessEqual(len(chaves), Hub.SITE_BLOCOS_MAX)
        for k in chaves:
            self.assertRegex(k, Hub.SITE_CHAVE.pattern)

    def test_ler_textos_publico(self):
        st, j, _ = self.c("GET", "/api/site/textos/consultoria")
        self.assertEqual(st, 200)
        self.assertTrue(j["ok"])
        self.assertIsInstance(j["textos"], dict)
        st, j, _ = self.c("GET", "/api/site/textos/Nao_Vale")
        self.assertEqual(st, 404)

    def test_gravar_exige_sessao(self):
        st, j, _ = self.c("POST", "/api/site/textos/consultoria", {"heroi.titulo": "Invasor"})
        self.assertEqual(st, 401)
        st, j, _ = self.c("POST", "/api/site/textos/consultoria", {"heroi.titulo": "Invasor"}, cookie="physis_sessao=falso")
        self.assertEqual(st, 401)
        self.assertNotEqual(self.c("GET", "/api/site/textos/consultoria")[1]["textos"].get("heroi.titulo"), "Invasor")

    def test_gravar_com_sessao_e_html_retirado(self):
        st, j, _ = self.c("POST", "/api/site/textos/consultoria",
                          {"serv.intro": "Texto <em>novo</em><script>x()</script>\nsegunda linha"}, cookie=self.cookie)
        self.assertEqual(st, 200, j)
        self.assertEqual(j["textos"]["serv.intro"], "Texto novox()\nsegunda linha")
        st, j, _ = self.c("GET", "/api/site/textos/consultoria")
        self.assertEqual(j["textos"]["serv.intro"], "Texto novox()\nsegunda linha")
        # formato {"textos": {...}} também vale
        st, j, _ = self.c("POST", "/api/site/textos/consultoria", {"textos": {"serv.intro": ""}}, cookie=self.cookie)
        self.assertEqual(st, 200, j)
        self.assertNotIn("serv.intro", j["textos"])

    def test_limites_no_servidor(self):
        ck = self.cookie
        self.assertEqual(self.c("POST", "/api/site/textos/consultoria", {"a": "x" * 4001}, cookie=ck)[0], 400)
        self.assertEqual(self.c("POST", "/api/site/textos/consultoria", {f"k{i}": "x" for i in range(201)}, cookie=ck)[0], 400)
        self.assertEqual(self.c("POST", "/api/site/textos/Pagina_Ruim", {"a": "x"}, cookie=ck)[0], 400)
        self.assertEqual(self.c("POST", "/api/site/textos/consultoria", "nao e json", cookie=ck)[0], 400)
        self.assertEqual(self.c("POST", "/api/site/textos/consultoria", "x" * (1024 * 1024 + 10), cookie=ck)[0], 413)

    def test_formulario_aceito_pela_central(self):
        # o mesmo objeto que o script da página monta
        ped = {"_formato": "physis-pedido/1", "numero": "PP-261114-AB2C", "data": "2026-11-14T12:00:00.000Z",
               "origem": "consultoria", "texto": "Quero um diagnóstico energético.", "nome": "Maria Teste", "doc": "",
               "org": "Empresa Exemplo", "email": "maria@exemplo.com", "telefone": "(24) 99999-0000",
               "areas": ["Energia solar", "Qualidade da água"], "itens": [],
               "lgpd": {"aceite": True, "em": "2026-11-14T12:00:00.000Z", "texto": "uso dos dados"}}
        st, j, _ = self.c("POST", "/api/central/pedido", ped)
        self.assertEqual(st, 200, j)
        self.assertTrue(j["ok"])
        self.assertEqual(j["estado"], "novo")
        itens = [i for i in self.hub.central_listar() if i["numero"] == "PP-261114-AB2C"]
        self.assertEqual(len(itens), 1)
        # e a página monta exatamente esse formato
        html = PAGINA.read_text(encoding="utf-8")
        self.assertIn('_formato: "physis-pedido/1"', html)
        for campo in ("numero:", "texto:", "nome:", "org:", "email:", "telefone:", "areas:", "lgpd:"):
            self.assertIn(campo, html)


if __name__ == "__main__":
    unittest.main()
