"""Editais, eventos e e-mails escritos na Gestão (editais.py). Tudo sem internet: a rede é trocada por uma falsa.

Protege:
1. RSS, Atom e HTML viram itens com título, link, datas-chave (com rótulo) e prazo de envio; nada de prazo inventado.
2. Relevância por regra simples das áreas da Physis (sem IA externa).
3. Fonte fora do ar não derruba as outras; o resultado fica guardado (cache) e vale por um tempo.
4. Fonte acrescentada pela equipe só pode ser endereço público (nada de rede interna).
5. Editais: só Rafaella, Erick Lopes e Marzia (ou quem estiver em PHYSIS_EDITAIS_ACESSO); sem sessão, 401.
6. E-mail escrito na Gestão entra na fila de saída existente (email_saida), pendente, e só sai pelo servidor de e-mail se configurado.
"""
import json
import os
import tempfile
import unittest

from physis_hub import editais as E
from physis_hub.hub import Hub

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Fomento</title>
<item><title>Chamada Pública Energia Solar no Campo</title><link>https://exemplo.gov.br/chamada-1</link>
<description>Submissão de propostas até 15/03/2027. Resultado em 30 de abril de 2027.</description><pubDate>Mon, 10 Nov 2026</pubDate></item>
<item><title>Edital de cultura popular</title><link>https://exemplo.gov.br/chamada-2</link><description>Inscrições abertas.</description></item>
<item><title>Sem link</title></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Call for proposals: climate adaptation water</title>
<link href="https://example.eu/call-9"/><summary>Deadline: January 20, 2027</summary></entry></feed>"""

HTML = """<html><body><ul>
<li><a href="/chamadas/123">Chamada Pública MCTI/FINEP Inovação em Saneamento e Água</a> Prazo para envio: 05/02/2027</li>
<li><a href="/noticias/1">Notícia qualquer sobre a empresa</a></li>
<li><a href="javascript:void(0)">Edital com link quebrado de propósito</a></li>
<li><a href="https://outro.org/edital-x">Edital Agro sustentável e bioeconomia</a></li>
<li><a href="/x">curto</a></li>
</ul></body></html>"""


class Interpretacao(unittest.TestCase):
    def test_rss_com_datas_e_prazo(self):
        f = E.Fonte("t", "Teste", "https://exemplo.gov.br/rss", "rss")
        itens = E.ler_rss(RSS, f)
        self.assertEqual([i["link"] for i in itens], ["https://exemplo.gov.br/chamada-1", "https://exemplo.gov.br/chamada-2"])
        a = itens[0]
        self.assertEqual(a["prazo"], "2027-03-15")
        self.assertIn({"rotulo": "Resultado", "data": "2027-04-30", "envio": False}, a["datas"])
        self.assertIn("energia", a["areas"])
        self.assertEqual(itens[1]["prazo"], "")          # sem data, sem prazo inventado
        self.assertEqual(itens[1]["areas"], [])

    def test_atom_em_ingles(self):
        it = E.ler_rss(ATOM, E.Fonte("eu", "UE", "https://example.eu/feed", "rss", pais="UE"))
        self.assertEqual(len(it), 1)
        self.assertEqual(it[0]["link"], "https://example.eu/call-9")
        self.assertEqual(it[0]["prazo"], "2027-01-20")
        self.assertTrue({"clima", "agua"} <= set(it[0]["areas"]))

    def test_rss_quebrado_nao_derruba(self):
        self.assertEqual(E.ler_rss("<rss><item>", E.Fonte("x", "x", "https://x.org", "rss")), [])

    def test_html_links_que_parecem_edital(self):
        f = E.Fonte("finep", "FINEP", "https://www.finep.gov.br/chamadas-publicas", "html")
        itens = E.ler_html(HTML, f)
        links = [i["link"] for i in itens]
        self.assertEqual(links, ["https://www.finep.gov.br/chamadas/123", "https://outro.org/edital-x"])
        self.assertEqual(itens[0]["prazo"], "2027-02-05")
        self.assertIn("agua", itens[0]["areas"])

    def test_filtro_da_fonte(self):
        f = E.Fonte("finep", "FINEP", "https://www.finep.gov.br/", "html", filtro=r"/chamadas/")
        self.assertEqual([i["link"] for i in E.ler_html(HTML, f)], ["https://www.finep.gov.br/chamadas/123"])

    def test_eventos_usam_outras_marcas(self):
        h = '<a href="/e/1">Congresso Brasileiro de Energia Solar 2027</a> 12/05/2027 <a href="/e/2">Edital de bolsas qualquer</a>'
        it = E.ler_html(h, E.Fonte("s", "Agenda", "https://agenda.org/", "html", tipo="evento"))
        self.assertEqual([i["titulo"] for i in it], ["Congresso Brasileiro de Energia Solar 2027"])
        self.assertEqual(it[0]["tipo"], "evento")

    def test_datas_invalidas_e_rotulos(self):
        d = E.extrair_datas("Inscrições até 31/02/2027. Abertura 01/12/2026. Recursos: 10/01/27.")
        self.assertEqual([(x["rotulo"], x["data"]) for x in d], [("Abertura", "2026-12-01"), ("Recursos", "2027-01-10")])

    def test_relevancia_regra_simples(self):
        hoje = "2026-11-15"
        self.assertEqual(E.relevancia({"areas": [], "prazo": "2027-01-01"}, hoje), 0)
        self.assertEqual(E.relevancia({"areas": ["agua", "clima"], "prazo": "2027-01-01"}, hoje), 25)
        self.assertEqual(E.relevancia({"areas": ["agua"], "prazo": "2026-01-01"}, hoje), 0)
        self.assertEqual(E.relevancia({"areas": ["agua"], "prazo": ""}, hoje), 10)


class Coleta(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.pedidos = []
        self.agora = [1_800_000_000.0]
        self.fontes = [E.Fonte("a", "A", "https://a.gov.br/rss", "rss"), E.Fonte("b", "B", "https://b.gov.br/", "html"),
                       E.Fonte("c", "C fora do ar", "https://c.gov.br/", "html")]

        def abrir(url):
            self.pedidos.append(url)
            if "c.gov.br" in url:
                raise OSError("sem resposta")
            return RSS if url.endswith("rss") else HTML
        self.col = E.Coletor(self.pasta, fontes=self.fontes, abrir=abrir, relogio=lambda: self.agora[0])

    def test_busca_junta_fontes_e_isola_falha(self):
        r = self.col.buscar()
        est = {f["id"]: f for f in r["fontes"]}
        self.assertTrue(est["a"]["ok"] and est["b"]["ok"])
        self.assertFalse(est["c"]["ok"])
        self.assertIn("sem resposta", est["c"]["erro"])
        self.assertEqual(len(r["itens"]), 4)
        self.assertTrue(all(i["novo"] for i in r["itens"]))
        self.assertGreaterEqual(r["itens"][0]["relevancia"], r["itens"][-1]["relevancia"])   # mais relevante primeiro

    def test_cache_vale_por_um_tempo(self):
        self.col.buscar()
        n = len(self.pedidos)
        r = self.col.buscar()
        self.assertTrue(r["do_cache"])
        self.assertEqual(len(self.pedidos), n)                      # não foi à rede de novo
        self.agora[0] += E.VALIDADE_S + 1
        r = self.col.buscar()
        self.assertFalse(r["do_cache"])
        self.assertFalse(any(i["novo"] for i in r["itens"]))        # já vistos antes
        with open(os.path.join(self.pasta, "editais-cache.json"), encoding="utf-8") as f:
            self.assertTrue(json.load(f)["itens"])

    def test_forcar_busca(self):
        self.col.buscar()
        n = len(self.pedidos)
        self.col.buscar(forcar=True)
        self.assertEqual(len(self.pedidos), 2 * n)

    def test_fontes_acrescentadas_so_publicas(self):
        for ruim in ("http://localhost/x", "http://192.168.0.10/edital", "file:///etc/passwd", "https://intranet.local/a", "http://10.0.0.1"):
            self.assertFalse(self.col.acrescentar_fonte({"nome": "X", "url": ruim})["ok"], ruim)
        self.assertFalse(self.col.acrescentar_fonte({"nome": "X", "url": "https://fap.org.br/editais", "formato": "pdf"})["ok"])
        r = self.col.acrescentar_fonte({"nome": "FAP nova", "url": "https://fap.org.br/editais"})
        self.assertTrue(r["ok"])
        self.assertIn(r["id"], [f.id for f in self.col.fontes()])
        self.assertFalse(self.col.acrescentar_fonte({"nome": "FAP nova", "url": "https://fap.org.br/editais"})["ok"])   # repetida
        self.assertFalse(self.col.remover_fonte("a")["ok"])        # fonte padrão não sai
        self.assertTrue(self.col.remover_fonte(r["id"])["ok"])

    def test_interprete_novo_plugavel(self):
        E.registrar_interprete("json-teste", lambda texto, f: [E._item(f, "Chamada Água Limpa", "https://j.org/1", "")])
        try:
            col = E.Coletor(self.pasta, tipo="evento", fontes=[E.Fonte("j", "J", "https://j.org/api", "json-teste", tipo="evento")],
                            abrir=lambda u: "{}")
            self.assertEqual(col.buscar()["itens"][0]["titulo"], "Chamada Água Limpa")
        finally:
            E.INTERPRETES.pop("json-teste", None)

    def test_fontes_padrao_cobrem_o_pedido(self):
        grupos = {f.grupo for f in E.FONTES_EDITAIS}
        self.assertTrue({"FINEP", "BNDES", "CNPq", "FAPs", "Prosas", "Fundo Clima", "Internacional"} <= grupos)
        self.assertTrue(all(f.url.startswith(("http://", "https://")) and f.formato in E.INTERPRETES for f in E.FONTES_EDITAIS + E.FONTES_EVENTOS))
        self.assertEqual(len({f.id for f in E.FONTES_EDITAIS}), len(E.FONTES_EDITAIS))


class CorreioFalso:
    def __init__(self, ligado):
        self.ligado, self.filas = ligado, []

    def configurado(self):
        return self.ligado

    def enviar_fila(self, hub, ref=None):
        self.filas.append(ref)
        return 0


class Rotas(unittest.TestCase):
    def setUp(self):
        p = tempfile.mkdtemp()
        self.ed = E.Coletor(p, abrir=lambda u: RSS, fontes=[E.Fonte("a", "A", "https://a.gov.br/rss", "rss")])
        self.ev = E.Coletor(p, tipo="evento", abrir=lambda u: HTML, fontes=[])
        self.hub = Hub()
        self.raf = {"usuario": "rafaella@physis.example", "pessoa": "rafaella", "papel": "administrador"}
        self.laura = {"usuario": "laura@physis.example", "pessoa": "laura", "papel": "operador"}

    def r(self, metodo, caminho, conta, corpo=None, correio=None):
        return E.rota(metodo, caminho, conta, json.dumps(corpo) if corpo is not None else None, self.ed, self.ev, self.hub, correio)

    def test_rota_alheia_devolve_none(self):
        self.assertIsNone(self.r("GET", "/api/central/emails", self.raf))
        self.assertIsNone(self.r("GET", "/api/editaisx", self.raf))

    def test_acesso_aos_editais(self):
        self.assertEqual(self.r("GET", "/api/editais", None)[0], 401)
        self.assertEqual(self.r("GET", "/api/editais", self.laura)[0], 403)
        self.assertEqual(self.r("GET", "/api/editais", self.raf)[0], 200)
        self.assertEqual(self.r("GET", "/api/eventos", self.laura)[0], 200)          # eventos: toda a equipe
        for p in ("ericklopes", "marzia"):
            self.assertEqual(self.r("GET", "/api/editais", {"pessoa": p})[0], 200)
        os.environ["PHYSIS_EDITAIS_ACESSO"] = "laura"
        try:
            self.assertEqual(self.r("GET", "/api/editais", self.laura)[0], 200)
            self.assertEqual(self.r("GET", "/api/editais", self.raf)[0], 403)
        finally:
            os.environ.pop("PHYSIS_EDITAIS_ACESSO")

    def test_buscar_e_fontes_pela_rota(self):
        c, j = self.r("POST", "/api/editais/buscar", self.raf, {"forcar": True})
        self.assertEqual(c, 200)
        self.assertEqual(len(j["itens"]), 2)
        c, j = self.r("POST", "/api/editais/fontes", self.raf, {"nome": "Nova", "url": "https://nova.org/rss", "formato": "rss"})
        self.assertEqual(c, 200)
        self.assertEqual(self.r("POST", "/api/editais/fontes", self.raf, {"remover": j["id"]})[0], 200)
        self.assertEqual(self.r("GET", "/api/editais/nada", self.raf)[0], 404)
        self.assertEqual(E.rota("POST", "/api/editais/buscar", self.raf, "", self.ed, self.ev)[0], 200)      # corpo vazio vale
        self.assertEqual(E.rota("POST", "/api/editais/buscar", self.raf, None, self.ed, self.ev)[0], 413)    # corpo acima do limite
        self.assertEqual(E.rota("POST", "/api/editais/buscar", self.raf, "{x", self.ed, self.ev)[0], 400)

    def test_email_entra_na_fila_existente(self):
        c, j = self.r("POST", "/api/gestao/correio", self.raf, {"para": "cliente@exemplo.com, outro@exemplo.com", "assunto": "Proposta\nPP-1", "corpo": "Olá"})
        self.assertEqual(c, 200)
        self.assertFalse(j["servidor_email"])
        e = [x for x in self.hub.emails() if x["id"] == j["id"]][0]
        self.assertEqual((e["estado"], e["para"], e["assunto"], e["ref"]), ("pendente", "cliente@exemplo.com, outro@exemplo.com", "Proposta PP-1", j["ref"]))
        self.assertTrue(self.hub.email_marcar(j["id"], "enviado_a_mao"))       # o fluxo existente continua valendo

    def test_email_com_servidor_de_email(self):
        cf = CorreioFalso(True)
        c, j = self.r("POST", "/api/gestao/correio", self.raf, {"para": "a@b.com", "assunto": "Oi", "corpo": "Texto"}, cf)
        self.assertTrue(j["servidor_email"])
        import time as _t
        for _ in range(50):
            if cf.filas:
                break
            _t.sleep(0.01)
        self.assertEqual(cf.filas, [j["ref"]])                  # envia só este, não a fila inteira

    def test_email_recusado(self):
        for corpo in ({"para": "sem-arroba", "assunto": "a", "corpo": "b"}, {"para": "a@b.com", "assunto": "", "corpo": "b"},
                      {"para": "a@b.com", "assunto": "a", "corpo": " "}, {"para": "a@b.com", "assunto": "a", "corpo": "x" * 20001},
                      {"para": ",".join(f"p{i}@b.com" for i in range(11)), "assunto": "a", "corpo": "b"}):
            self.assertEqual(self.r("POST", "/api/gestao/correio", self.raf, corpo)[0], 400, corpo)
        self.assertEqual(self.r("GET", "/api/gestao/correio", self.raf)[0], 405)
        self.assertEqual(self.r("POST", "/api/gestao/correio", None, {})[0], 401)
        self.assertEqual(self.hub.emails(), [])


if __name__ == "__main__":
    unittest.main()
