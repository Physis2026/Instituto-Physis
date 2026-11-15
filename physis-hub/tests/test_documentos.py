"""Documento como página para comentários: limpeza do HTML, versões, comentários, permissões e convites com prazo."""
import base64
import json
import os
import unittest
from unittest import mock

from physis_hub import documentos as D
from physis_hub.hub import Hub

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG).decode()
EQUIPE = {"id": 2, "usuario": "ana", "nome": "Ana", "papel": "operador"}
OUTRA = {"id": 3, "usuario": "bia", "nome": "Bia", "papel": "operador"}
DIRECAO = {"id": 1, "usuario": "dir", "nome": "Direção", "papel": "administrador"}
CLIENTE = {"id": 4, "usuario": "cli", "nome": "Cliente", "papel": "cliente"}


def limpar(h, **k):
    return D.sanitizar_html(h, **k)


class TestSanitizar(unittest.TestCase):
    PERIGOS = [
        '<script>alert(1)</script>', '<SCRIPT SRC=//x.y/z.js></SCRIPT>', '<img src=x onerror=alert(1)>',
        '<p onclick="roubar()">t</p>', '<a href="javascript:alert(1)">x</a>', '<a href=" JaVaScRiPt:alert(1)">x</a>',
        '<a href="http://fora.com/">fora</a>', '<iframe src="https://fora.com"></iframe>', '<iframe srcdoc="<script>x</script>"></iframe>',
        '<object data="x.swf"></object>', '<embed src="x">', '<svg onload=alert(1)><script>x</script></svg>',
        '<math><mi xlink:href="javascript:x">y</mi></math>', '<img src="https://fora.com/rastreio.gif">',
        '<img src="data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+">', '<p style="background:url(http://fora.com/x)">s</p>',
        '<style>@import url(http://fora.com/x.css)</style>', '<link rel=stylesheet href="http://fora.com/x.css">',
        '<meta http-equiv="refresh" content="0;url=http://fora.com">', '<base href="http://fora.com/">',
        '<form action="http://fora.com"><input name=senha value="segredo"><button formaction="x">ok</button></form>',
        '<div onmouseover="x()" data-x="1" id="a" class="b">ok</div>', '<video poster="http://fora.com/p.png"></video>',
        '<!-- <script>x</script> -->', '<p>a</p><template><script>x</script></template>', '<noscript><img src=x onerror=y></noscript>',
        '<img src="data:image/png;base64,PHNjcmlwdD4=">',           # diz PNG, não é
    ]

    def test_nada_perigoso_sobra(self):
        for h in self.PERIGOS:
            s = limpar(h)["html"].lower()
            for proibido in ("<script", "javascript:", "onerror", "onload", "onclick", "onmouseover", "<iframe", "<object", "<embed",
                             "<svg", "<math", "http://", "https://", "//fora", "<style", "<link", "<meta", "<base", "<form", "<input",
                             "segredo", "style=", "srcdoc", "<video", "image/svg", "data-x", 'id="a"', 'class="b"', "<template", "<noscript"):
                self.assertNotIn(proibido, s, f"{h!r} -> {s!r}")

    def test_texto_escapado_continua_texto(self):
        r = limpar("<p>&lt;script&gt;alert(1)&lt;/script&gt; &amp; R$ 5</p>")
        self.assertIn("&lt;script&gt;", r["html"])
        self.assertIn("&amp; R$ 5", r["html"])

    def test_imagem_data_png_fica(self):
        r = limpar(f'<figure><img src="{PNG_URI}" alt="gráfico" width="10" height="10" onerror="x"><figcaption>F</figcaption></figure>')
        self.assertIn(f'src="{PNG_URI}"', r["html"])
        self.assertIn('alt="gráfico"', r["html"])
        self.assertNotIn("onerror", r["html"])

    def test_imagem_grande_demais_e_limite_total(self):
        r = limpar(f'<img src="{PNG_URI}" alt="a">', img_max=10)
        self.assertNotIn("data:image", r["html"])
        self.assertIn("[a]", r["html"])
        self.assertTrue(any("grande" in a for a in r["avisos"]))
        r = limpar(f'<img src="{PNG_URI}"><img src="{PNG_URI}">', imgs_max=len(PNG) + 5)
        self.assertEqual(r["html"].count("data:image"), 1)

    def test_link_interno_fica_externo_vira_texto(self):
        r = limpar('<p><a href="#secao-2">ver</a> <a href="https://x.com">site</a></p>')
        self.assertIn('<a href="#secao-2">ver</a>', r["html"])
        self.assertIn("<a>site</a>", r["html"])
        self.assertIn("links para fora do documento viraram texto", r["avisos"])

    def test_ancoras_de_paragrafo(self):
        r = limpar('<h1>Título</h1><p>um</p><p data-paragrafo="meu-id">dois</p><p data-paragrafo="meu-id">três</p>'
                   '<ul><li>a<li>b</ul><table><tr><td>x<td>y</table>')
        self.assertIn('<h2 data-paragrafo="p1">Título</h2>', r["html"])         # h1 do documento vira h2: a página tem o seu h1
        self.assertNotIn("<h1", r["html"])
        ids = list(r["paragrafos"])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("meu-id", ids)
        self.assertEqual(r["paragrafos"]["meu-id"], {"tag": "p", "trecho": "dois"})
        self.assertEqual(sum(1 for p in r["paragrafos"].values() if p["tag"] == "li"), 2)
        self.assertEqual(sum(1 for p in r["paragrafos"].values() if p["tag"] == "tr"), 1)
        self.assertIn("<td>x</td><td>y</td>", r["html"])

    def test_estavel_ao_limpar_de_novo(self):
        a = limpar('<h2>T</h2><p>x<b>y</b></p><ul><li>a<li>b</ul><img src="x"><div><p>u<p>v</div>')
        b = limpar(a["html"], rebaixar_titulos=False)
        self.assertEqual(a["html"], b["html"])
        self.assertEqual(a["paragrafos"], b["paragrafos"])

    def test_etiqueta_desconhecida_some_texto_fica(self):
        self.assertEqual(limpar("<x-coisa>oi</x-coisa>")["html"], "oi")

    def test_grande_demais(self):
        with self.assertRaises(ValueError):
            limpar("a" * (D.HTML_MAX + 1))

    def test_substituir_paragrafo(self):
        a = limpar("<p>velho <b>texto</b></p><p>fica</p>")
        b = limpar(a["html"], rebaixar_titulos=False, substituir={"p1": "novo <texto>"})
        self.assertIn('<p data-paragrafo="p1">novo &lt;texto&gt;</p><p data-paragrafo="p2">fica</p>', b["html"])
        self.assertEqual(b["trocados"], ["p1"])


class BaseDoc(unittest.TestCase):
    def setUp(self):
        self.t = [1_800_000_000.0]
        self.hub = Hub(":memory:", relogio=lambda: self.t[0])
        self.docs = D.Documentos(self.hub)
        self.r = lambda metodo, caminho, conta=None, corpo=None, convite=None, ip="10.0.0.9", consulta=None: self.docs.rota(
            metodo, caminho, conta, json.dumps(corpo) if isinstance(corpo, dict) else corpo, convite=convite, ip=ip,
            base="https://hub.exemplo", consulta=consulta)
        c, j = self.r("POST", "/api/documentos", EQUIPE, {"titulo": "Proposta Água", "origem": "gestao/propostas",
                                                          "html": "<h1>Proposta</h1><p>Primeiro parágrafo.</p><p>Segundo.</p><script>x</script>"})
        self.assertEqual(c, 200, j)
        self.id = j["id"]
        self.base = "/api/documentos/" + self.id


class TestDocumentos(BaseDoc):
    def test_publicar_link_e_listar(self):
        self.assertGreaterEqual(len(self.id), 22)
        c, j = self.r("GET", "/api/documentos", EQUIPE)
        self.assertEqual(j["documentos"][0]["titulo"], "Proposta Água")
        self.assertEqual(j["documentos"][0]["link"], "/documento/" + self.id)
        c, j = self.r("GET", self.base, EQUIPE)
        self.assertEqual(c, 200)
        self.assertNotIn("<script", j["html"])
        self.assertIn("<script> removido", j["avisos"])
        self.assertEqual(j["versao"], 1)
        self.assertTrue(j["eu"]["pode_resolver"])
        # outro documento recebe outro link
        c, j2 = self.r("POST", "/api/documentos", EQUIPE, {"titulo": "B", "html": "<p>b</p>"})
        self.assertNotEqual(j2["id"], self.id)
        self.assertTrue(j2["link"].startswith("https://hub.exemplo/documento/"))

    def test_permissoes_basicas(self):
        self.assertEqual(self.r("GET", "/api/documentos")[0], 401)
        self.assertEqual(self.r("GET", "/api/documentos", CLIENTE)[0], 403)
        self.assertEqual(self.r("POST", "/api/documentos", CLIENTE, {"titulo": "x", "html": "<p>x</p>"})[0], 403)
        self.assertEqual(self.r("GET", self.base)[0], 401)
        self.assertEqual(self.r("GET", self.base, CLIENTE)[0], 403)
        self.assertEqual(self.r("GET", "/api/documentos/curto", EQUIPE)[0], 404)
        self.assertEqual(self.r("GET", "/api/documentos/" + "a" * 22, EQUIPE)[0], 404)
        self.assertEqual(self.r("POST", "/api/documentos", EQUIPE, {"titulo": "", "html": "<p>x</p>"})[0], 400)
        self.assertEqual(self.r("POST", "/api/documentos", EQUIPE, {"titulo": "x", "html": "<script>só isso</script>"})[0], 400)
        self.assertEqual(self.r("POST", "/api/documentos", EQUIPE, "não é json")[0], 400)

    def test_versoes(self):
        c, j = self.r("POST", self.base + "/versoes", EQUIPE, {"html": "<p>Primeiro parágrafo, revisto.</p>", "nota": "revisão"})
        self.assertEqual((c, j["versao"]), (200, 2))
        c, j = self.r("POST", self.base + "/versoes", EQUIPE, {"html": "<p>Primeiro parágrafo, revisto.</p>"})
        self.assertTrue(j["igual"])                                  # sem mudança, sem versão nova
        c, j = self.r("GET", self.base, EQUIPE, consulta={"versao": ["1"]})
        self.assertIn("Segundo", j["html"])
        self.assertEqual([v["versao"] for v in j["versoes"]], [1, 2])
        c, j = self.r("GET", self.base, EQUIPE)
        self.assertEqual(j["versao"], 2)
        self.assertNotIn("Segundo", j["html"])
        self.assertEqual(self.r("GET", self.base, EQUIPE, consulta={"versao": ["9"]})[0], 404)

    def test_comentar_responder_resolver(self):
        c, j = self.r("POST", self.base + "/comentarios", EQUIPE, {"paragrafo": "p2", "texto": "Conferir o valor."})
        self.assertEqual(c, 200, j)
        raiz = j["id"]
        c, j = self.r("POST", self.base + "/comentarios", OUTRA, {"pai": raiz, "texto": "Conferido."})
        resp = j["id"]
        c, j = self.r("POST", self.base + "/comentarios", EQUIPE, {"pai": resp, "texto": "Obrigada."})   # resposta de resposta: mesma conversa
        lista = self.r("GET", self.base + "/comentarios", EQUIPE)[1]["comentarios"]
        self.assertEqual([x["pai"] for x in lista], [None, raiz, raiz])
        self.assertTrue(all(x["paragrafo"] == "p2" for x in lista))
        self.assertTrue(lista[0]["meu"] and not lista[1]["meu"])
        self.assertEqual(self.r("POST", self.base + "/comentarios", EQUIPE, {"paragrafo": "p99", "texto": "x"})[0], 400)
        self.assertEqual(self.r("POST", self.base + "/comentarios", EQUIPE, {"paragrafo": "p2", "texto": "  "})[0], 400)
        self.assertEqual(self.r("POST", self.base + "/comentarios", EQUIPE, {"paragrafo": "geral", "texto": "Geral"})[0], 200)
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{resp}/resolver", EQUIPE, {})[0], 400)    # resolve pela raiz
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{raiz}/resolver", OUTRA, {})[0], 200)
        lista = self.r("GET", self.base + "/comentarios", EQUIPE)[1]["comentarios"]
        self.assertEqual((lista[0]["estado"], lista[0]["resolvido_por"]), ("resolvido", "Bia"))
        self.r("POST", self.base + f"/comentarios/{raiz}/resolver", EQUIPE, {"resolvido": False})
        self.assertEqual(self.r("GET", self.base + "/comentarios", EQUIPE)[1]["comentarios"][0]["estado"], "aberto")
        self.assertEqual(self.r("GET", "/api/documentos", EQUIPE)[1]["documentos"][0]["abertos"], 2)

    def test_editar_e_apagar_so_quem_escreveu(self):
        cid = self.r("POST", self.base + "/comentarios", EQUIPE, {"paragrafo": "p2", "texto": "Original"})[1]["id"]
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{cid}/editar", OUTRA, {"texto": "Hack"})[0], 403)
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{cid}/editar", EQUIPE, {"texto": "Editado"})[0], 200)
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{cid}/apagar", OUTRA, {})[0], 403)
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{cid}/apagar", DIRECAO, {})[0], 200)   # a direção pode
        x = self.r("GET", self.base + "/comentarios", EQUIPE)[1]["comentarios"][0]
        self.assertTrue(x["apagado"])
        self.assertEqual(x["texto"], "")
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{cid}/editar", EQUIPE, {"texto": "volta"})[0], 404)
        self.assertEqual(self.r("POST", self.base + "/comentarios/abc/editar", EQUIPE, {"texto": "x"})[0], 404)

    def test_sugestao_aceita_vira_versao(self):
        c, j = self.r("POST", self.base + "/comentarios", OUTRA, {"paragrafo": "p2", "texto": "Mais claro assim:", "sugestao": "Primeiro parágrafo, mais claro."})
        cid = j["id"]
        self.assertEqual(self.r("POST", self.base + "/comentarios", OUTRA, {"paragrafo": "geral", "texto": "x", "sugestao": "y"})[0], 400)
        c, j = self.r("POST", self.base + f"/comentarios/{cid}/sugestao", EQUIPE, {"aceitar": True})
        self.assertEqual((c, j["versao"]), (200, 2), j)
        doc = self.r("GET", self.base, EQUIPE)[1]
        self.assertIn("Primeiro parágrafo, mais claro.", doc["html"])
        self.assertIn("Segundo.", doc["html"])
        self.assertIn("aceita", doc["versoes"][-1]["nota"])
        x = [k for k in doc["comentarios"] if k["id"] == cid][0]
        self.assertEqual((x["sugestao_estado"], x["estado"]), ("aceita", "resolvido"))
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{cid}/sugestao", EQUIPE, {"aceitar": True})[0], 409)

    def test_sugestao_recusada(self):
        cid = self.r("POST", self.base + "/comentarios", OUTRA, {"paragrafo": "p3", "texto": "t", "sugestao": "s"})[1]["id"]
        c, j = self.r("POST", self.base + f"/comentarios/{cid}/sugestao", EQUIPE, {"aceitar": False})
        self.assertEqual(c, 200)
        self.assertEqual(self.r("GET", self.base, EQUIPE)[1]["versao"], 1)

    def test_arquivar_fecha_comentarios_e_apagar_so_direcao(self):
        self.assertEqual(self.r("POST", self.base + "/arquivar", EQUIPE, {})[0], 200)
        self.assertEqual(self.r("POST", self.base + "/comentarios", EQUIPE, {"paragrafo": "p2", "texto": "x"})[0], 409)
        self.assertFalse(self.r("GET", self.base, EQUIPE)[1]["eu"]["pode_comentar"])
        self.assertEqual(self.r("POST", self.base + "/apagar", EQUIPE, {})[0], 403)
        self.assertEqual(self.r("POST", self.base + "/apagar", DIRECAO, {})[0], 200)
        self.assertEqual(self.r("GET", self.base, EQUIPE)[0], 404)
        for t in ("doc_versao", "doc_comentario", "doc_convite"):
            self.assertEqual(self.hub._db.execute(f"SELECT COUNT(*) FROM {t} WHERE doc_id=?", (self.id,)).fetchone()[0], 0)

    def test_rota_de_fora(self):
        self.assertIsNone(self.r("GET", "/api/outra"))


class TestConvites(BaseDoc):
    def convidar(self, **k):
        c, j = self.r("POST", self.base + "/convites", EQUIPE, dict({"nome": "Revisor Externo", "email": "rev@cliente.com.br", "dias": 2}, **k))
        self.assertEqual(c, 200, j)
        return j

    def test_link_com_codigo_depois_do_jogo_da_velha(self):
        j = self.convidar()
        self.assertEqual(j["link"], f"https://hub.exemplo/documento/{self.id}#convite={j['token']}")
        guardado = self.hub._db.execute("SELECT resumo FROM doc_convite WHERE id=?", (j["id"],)).fetchone()[0]
        self.assertNotEqual(guardado, j["token"])                     # só o resumo fica no banco
        lista = self.r("GET", self.base + "/convites", EQUIPE)[1]["convites"]
        self.assertNotIn("token", lista[0])
        self.assertTrue(lista[0]["ativo"])

    def test_convidado_le_comenta_mas_nao_resolve(self):
        tk = self.convidar()["token"]
        c, j = self.r("GET", self.base, convite=tk)
        self.assertEqual(c, 200)
        self.assertEqual(j["eu"], {"nome": "Revisor Externo", "tipo": "convite", "pode_comentar": True, "pode_resolver": False, "pode_convidar": False})
        self.assertEqual(j["avisos"], [])
        c, j = self.r("POST", self.base + "/comentarios", convite=tk, corpo={"paragrafo": "p2", "texto": "Do cliente."})
        self.assertEqual(c, 200)
        cid = j["id"]
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{cid}/resolver", convite=tk, corpo={})[0], 403)
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{cid}/sugestao", convite=tk, corpo={"aceitar": True})[0], 403)
        self.assertEqual(self.r("GET", self.base + "/convites", convite=tk)[0], 403)
        self.assertEqual(self.r("POST", self.base + "/convites", convite=tk, corpo={"nome": "x"})[0], 403)
        self.assertEqual(self.r("POST", self.base + "/versoes", convite=tk, corpo={"html": "<p>x</p>"})[0], 403)
        self.assertEqual(self.r("POST", self.base + "/apagar", convite=tk, corpo={})[0], 403)
        self.assertEqual(self.r("POST", self.base + f"/comentarios/{cid}/editar", convite=tk, corpo={"texto": "Editado pelo cliente"})[0], 200)
        x = self.r("GET", self.base + "/comentarios", EQUIPE)[1]["comentarios"][0]
        self.assertEqual((x["autor"], x["autor_tipo"], x["meu"]), ("Revisor Externo", "convite", False))
        self.assertNotIn("email", json.dumps(self.r("GET", self.base, convite=tk)[1]))
        self.assertEqual(self.r("GET", "/api/documentos", convite=tk)[0], 401)     # lista de documentos: só equipe

    def test_convite_de_um_documento_nao_abre_outro(self):
        tk = self.convidar()["token"]
        outro = self.r("POST", "/api/documentos", EQUIPE, {"titulo": "Outro", "html": "<p>o</p>"})[1]["id"]
        self.assertEqual(self.r("GET", "/api/documentos/" + outro, convite=tk)[0], 403)

    def test_somente_leitura(self):
        tk = self.convidar(pode_comentar=False)["token"]
        self.assertFalse(self.r("GET", self.base, convite=tk)[1]["eu"]["pode_comentar"])
        self.assertEqual(self.r("POST", self.base + "/comentarios", convite=tk, corpo={"paragrafo": "p2", "texto": "x"})[0], 403)

    def test_vence_no_prazo(self):
        tk = self.convidar(dias=1)["token"]
        self.t[0] += 86400 - 5
        self.assertEqual(self.r("GET", self.base, convite=tk)[0], 200)
        self.t[0] += 10
        c, j = self.r("GET", self.base, convite=tk)
        self.assertEqual(c, 403)
        self.assertIn("não vale mais", j["erro"])
        self.assertFalse(self.r("GET", self.base + "/convites", EQUIPE)[1]["convites"][0]["ativo"])

    def test_prazo_maximo_30_dias(self):
        j = self.convidar(dias=365)
        self.assertAlmostEqual(j["expira"] - self.t[0], 30 * 86400)

    def test_revogar(self):
        j = self.convidar()
        self.assertEqual(self.r("POST", self.base + f"/convites/{j['id']}/revogar", EQUIPE, {})[0], 200)
        self.assertEqual(self.r("GET", self.base, convite=j["token"])[0], 403)
        self.assertEqual(self.r("POST", self.base + f"/convites/{j['id']}/revogar", EQUIPE, {})[0], 404)

    def test_arquivado_derruba_convite(self):
        tk = self.convidar()["token"]
        self.r("POST", self.base + "/arquivar", EQUIPE, {})
        self.assertEqual(self.r("GET", self.base, convite=tk)[0], 403)

    def test_codigo_errado_e_limite_por_ip(self):
        with mock.patch.dict(os.environ, {"PHYSIS_LIMITE_CONVITE_ERRO": "3/600", "PHYSIS_LIMITE_CONVITE": "5/600"}):
            docs = D.Documentos(self.hub)
        tk = self.convidar()["token"]
        rota = lambda conv, ip: docs.rota("GET", self.base, None, None, convite=conv, ip=ip)[0]
        self.assertEqual([rota("errado", "1.1.1.1") for _ in range(4)], [403, 403, 403, 429])
        self.assertEqual(rota(tk, "2.2.2.2"), 200)                 # outro IP segue normal
        self.assertEqual([rota(tk, "2.2.2.2") for _ in range(5)][-1], 429)   # limite geral de pedidos com convite
        c, j = docs.rota("GET", self.base, None, None, convite=tk, ip="2.2.2.2")
        self.assertGreaterEqual(j["espera"], 1)

    def test_validacoes(self):
        self.assertEqual(self.r("POST", self.base + "/convites", EQUIPE, {"nome": ""})[0], 400)
        self.assertEqual(self.r("POST", self.base + "/convites", EQUIPE, {"nome": "x", "email": "sem-arroba"})[0], 400)
        self.assertEqual(self.r("POST", self.base + "/convites", EQUIPE, {"nome": "x", "dias": "muitos"})[0], 400)

    def test_lgpd_retencao(self):
        j = self.convidar(dias=1)
        tk = j["token"]
        self.r("POST", self.base + "/comentarios", convite=tk, corpo={"paragrafo": "p2", "texto": "comentário fica"})
        self.t[0] += 86400 * 10
        self.assertEqual(self.docs.retencao(dias=30)["anonimizados"], 0)
        self.t[0] += 86400 * 30
        self.assertEqual(self.docs.retencao(dias=30)["anonimizados"], 1)
        cv = self.r("GET", self.base + "/convites", EQUIPE)[1]["convites"][0]
        self.assertEqual((cv["nome"], cv["email"]), ("Revisor externo", ""))
        x = self.r("GET", self.base + "/comentarios", EQUIPE)[1]["comentarios"][0]
        self.assertEqual((x["autor"], x["texto"]), ("Revisor externo", "comentário fica"))
        self.assertEqual(self.docs.retencao(dias=30)["anonimizados"], 0)


class TestFontes(unittest.TestCase):
    def test_fontes_do_painel(self):
        css = D.fontes_css()
        if not (D.WEB / "painel.html").is_file():
            self.skipTest("painel.html ausente")
        self.assertIn('font-family:"Fraunces"', css)
        self.assertNotIn("http", css.split("base64,")[0])


if __name__ == "__main__":
    unittest.main()
