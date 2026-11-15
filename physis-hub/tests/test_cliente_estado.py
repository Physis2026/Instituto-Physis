"""Dados da plataforma do cliente no servidor (perfil_cliente.py, /api/cliente/estado, sistema/physis-ponte-cliente.js).

Protege:
1. Só as chaves da lista entram; valor é texto com limite por chave e por organização.
2. Versão e conflito: gravar com a versão velha devolve 409 com o valor atual e quem gravou (a ponte decide pela mais nova).
3. Pela rede: sempre com sessão (cliente para cima), mesmo em instalação sem login; ETag e If-None-Match (304); If-Match.
4. O "aprendido" (atividades do negócio) é calculado no servidor com as MESMAS regras da tela (espelho de web/painel.html)
   e os alertas de clima usam essas atividades quando a assinatura não escolheu nenhuma.
5. A ponte do navegador usa a mesma lista de chaves do servidor.
"""
import json
import re
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from physis_hub import perfil_cliente
from physis_hub.hub import Hub
from physis_hub.servidor import iniciar
from physis_hub import alertas_clima as al

RAIZ = Path(__file__).resolve().parent.parent
PONTE = RAIZ.parent / "sistema" / "physis-ponte-cliente.js"
PAINEL = RAIZ / "web" / "painel.html"


class ArmarioNoHub(unittest.TestCase):
    def setUp(self):
        self.h = Hub(org="fazenda-teste")

    def test_chaves_da_lista(self):
        for k in ("physis-perfil", "physis.terreno.v1", "physis-calc-solar", "physis-curso-c01:progresso"):
            self.assertTrue(perfil_cliente.chave_valida(k), k)
        for k in ("gestao-physis:x", "physis-calc-", "physis-calc-../x", "physis-perfil2", "", "physis-curso-" + "x" * 61):
            self.assertFalse(perfil_cliente.chave_valida(k), k)
        self.assertFalse(self.h.cliente_gravar("outra", "x", 0, "ana")["ok"])
        self.assertFalse(self.h.cliente_gravar("physis-perfil", {"a": 1}, 0, "ana")["ok"])        # só texto

    def test_versao_conflito_e_tamanho(self):
        r1 = self.h.cliente_gravar("physis-perfil", '{"c":{}}', 0, "ana")
        self.assertEqual((r1["ok"], r1["versao"]), (True, 1))
        r2 = self.h.cliente_gravar("physis-perfil", '{"c":{"x":1}}', 0, "bia")
        self.assertEqual((r2["ok"], r2["conflito"], r2["versao"], r2["valor"], r2["por"]), (False, True, 1, '{"c":{}}', "ana"))
        self.assertTrue(self.h.cliente_gravar("physis-perfil", '{"c":{"x":1}}', 1, "bia")["ok"])
        self.assertTrue(self.h.cliente_gravar("physis-perfil", '{"c":{"x":1}}', 2, "bia")["igual"])     # igual: não sobe versão
        itens = self.h.cliente_ler()
        self.assertEqual((itens["physis-perfil"]["versao"], itens["physis-perfil"]["por"]), (2, "bia"))
        self.assertEqual(self.h.cliente_ler(desde=itens["physis-perfil"]["atualizado"]), {})
        self.assertEqual(self.h.cliente_ler(org="outra-org"), {})                                      # por organização
        grande = self.h.cliente_gravar("physis-sbn", "x" * (perfil_cliente.VALOR_MAX + 1), 0, "ana")
        self.assertEqual((grande["ok"], grande.get("grande")), (False, True))

    def test_total_da_organizacao(self):
        antes = perfil_cliente.TOTAL_MAX
        perfil_cliente.TOTAL_MAX = 100
        try:
            self.assertTrue(self.h.cliente_gravar("physis-calc-a", "x" * 60, 0, "ana")["ok"])
            self.assertFalse(self.h.cliente_gravar("physis-calc-b", "x" * 60, 0, "ana")["ok"])
            self.assertTrue(self.h.cliente_gravar("physis-calc-a", "y" * 90, 1, "ana")["ok"])         # trocar a própria cabe
        finally:
            perfil_cliente.TOTAL_MAX = antes


class Aprendido(unittest.TestCase):
    def test_regras(self):
        self.assertEqual(perfil_cliente.achar_atividades("Fazenda de café e gado de leite com irrigação por gotejamento"),
                         ["cafe", "gado_leite", "irrigacao"])
        self.assertEqual(perfil_cliente.achar_atividades("Criação de gado de corte"), ["gado"])
        self.assertEqual(perfil_cliente.achar_atividades("POUSADA na serra"), ["hospedagem"])
        a = perfil_cliente.aprendido_do_perfil(json.dumps({"c": {"descricao": "Plantamos café"}, "aprendido": {"atividades": ["gado"]}}))
        self.assertEqual((a["atividades"], a["fonte"], a["nomes"]), (["cafe"], "descricao", ["Cafeicultura"]))   # a descrição manda
        self.assertIn("resiliencia", a["modulos"])
        a = perfil_cliente.aprendido_do_perfil(json.dumps({"c": {}, "aprendido": {"atividades": ["graos", "xyz"]}}))
        self.assertEqual((a["atividades"], a["fonte"]), (["graos"], "tela"))
        self.assertEqual(perfil_cliente.aprendido_do_perfil("não é json")["atividades"], [])

    def test_espelho_da_tela(self):
        """As regras de ATIVIDADES em web/painel.html e em perfil_cliente.py são as mesmas (id, expressão, módulos)."""
        if not PAINEL.exists():
            self.skipTest("painel.html ausente")
        html = PAINEL.read_text(encoding="utf-8")
        tela = re.findall(r'\{ id:"([a-z_]+)", re:/(.+?)/i, nome:"([^"]+)".*?mods:\[([^\]]*)\] \}', html)
        self.assertEqual(len(tela), len(perfil_cliente.ATIVIDADES))
        for (i, rx, nome, mods), (pi, prx, pnome, _, pmods) in zip(tela, perfil_cliente.ATIVIDADES):
            self.assertEqual((i, rx, nome), (pi, prx, pnome))
            self.assertEqual([m.strip().strip('"') for m in mods.split(",")], list(pmods))

    def test_alertas_usam_o_perfil(self):
        h = Hub()
        a = al.AlertasClima(h, whatsapp=None)
        self.assertEqual(a.atividades_do_perfil(), [])
        h.cliente_gravar("physis-perfil", json.dumps({"c": {"descricao": "Cafezal e hotel fazenda"}}), 0, "ana")
        self.assertEqual(a.atividades_do_perfil(), ["cafe", "hospedagem"])


class PelaRede(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = Hub(org="fazenda-teste")
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": False})
        cls.porta = cls.srv.server_address[1]
        cls.hub.criar_conta("Direção", "dir@physis.example", "frase-longa-da-direcao-1")
        adm = cls.hub.sessao(cls.hub.entrar("dir@physis.example", "frase-longa-da-direcao-1")["token"])
        cls.hub.criar_conta("Cliente", "cli@fazenda.example", "frase-longa-do-cliente-1", adm["id"], papel="cliente")
        cls.hub.criar_conta("Outra", "outra@fazenda.example", "frase-longa-da-outra-1", adm["id"], papel="cliente")
        cls.ck = "physis_sessao=" + cls.hub.entrar("cli@fazenda.example", "frase-longa-do-cliente-1")["token"]
        cls.ck2 = "physis_sessao=" + cls.hub.entrar("outra@fazenda.example", "frase-longa-da-outra-1")["token"]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def c(self, metodo, rota, corpo=None, cookie=None, extra=None):
        h = {"Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = cookie
        h.update(extra or {})
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", data=dados, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}"), r.headers
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (json.loads(b) if b else {}), e.headers

    def test_sem_sessao_nada(self):
        self.assertEqual(self.c("GET", "/api/cliente/estado")[0], 401)               # mesmo sem login e da rede local
        self.assertEqual(self.c("GET", "/api/cliente/estado/physis-perfil")[0], 401)
        self.assertEqual(self.c("PUT", "/api/cliente/estado/physis-perfil", {"valor": "x", "versao": 0})[0], 401)
        self.assertEqual(self.c("GET", "/api/cliente/perfil")[0], 401)

    def test_ida_e_volta_conflito_e_etag(self):
        k = "/api/cliente/estado/physis-calc-solar"
        st, j, h = self.c("GET", k, cookie=self.ck)
        self.assertEqual((st, j["versao"]), (404, 0))
        st, j, h = self.c("PUT", k, {"valor": '{"kwp":10}', "versao": 0}, self.ck)
        self.assertEqual((st, j["versao"], h.get("ETag")), (200, 1, '"v1"'))
        st, j, h = self.c("GET", k, cookie=self.ck2)                                     # outra pessoa da mesma organização
        self.assertEqual((st, j["valor"], j["por"], h.get("ETag")), (200, '{"kwp":10}', "cli@fazenda.example", '"v1"'))
        self.assertEqual(self.c("GET", k, cookie=self.ck2, extra={"If-None-Match": '"v1"'})[0], 304)
        # a outra grava em cima da versão 1; quem ainda está na versão 0 recebe 409 com o valor atual
        self.assertEqual(self.c("PUT", k, {"valor": '{"kwp":12}', "versao": 1}, self.ck2)[0], 200)
        st, j, h = self.c("PUT", k, {"valor": '{"kwp":11}', "versao": 0}, self.ck)
        self.assertEqual((st, j["conflito"], j["versao"], j["valor"], j["por"], h.get("ETag")),
                         (409, True, 2, '{"kwp":12}', "outra@fazenda.example", '"v2"'))
        # a mais nova vence: a ponte regrava com a versão do servidor (aqui pelo If-Match)
        st, j, _ = self.c("PUT", k, {"valor": '{"kwp":11}'}, self.ck, extra={"If-Match": '"v2"'})
        self.assertEqual((st, j["versao"]), (200, 3))
        st, j, _ = self.c("GET", "/api/cliente/estado", cookie=self.ck)
        self.assertEqual((st, j["org"], j["itens"]["physis-calc-solar"]["valor"]), (200, "fazenda-teste", '{"kwp":11}'))
        self.assertIn("physis-perfil", j["chaves"])

    def test_recusas(self):
        self.assertEqual(self.c("PUT", "/api/cliente/estado/gestao-physis:x", {"valor": "1", "versao": 0}, self.ck)[0], 400)
        self.assertEqual(self.c("PUT", "/api/cliente/estado/physis-sbn", {"valor": 1, "versao": 0}, self.ck)[0], 400)
        self.assertEqual(self.c("PUT", "/api/cliente/estado/physis-sbn", {"valor": "1", "versao": -1}, self.ck)[0], 400)
        self.assertEqual(self.c("PUT", "/api/cliente/estado/physis-sbn", {"valor": "1", "versao": 0, "x": 1}, self.ck)[0], 400)
        # CSRF: token errado com sessão = 403
        st, j, _ = self.c("PUT", "/api/cliente/estado/physis-sbn", {"valor": "1", "versao": 0}, self.ck, extra={"X-Physis-CSRF": "errado"})
        self.assertEqual((st, j.get("csrf")), (403, True))
        # grande demais: 413
        st, _, _ = self.c("PUT", "/api/cliente/estado/physis-sbn", {"valor": "x" * (perfil_cliente.VALOR_MAX + 10), "versao": 0}, self.ck)
        self.assertEqual(st, 413)

    def test_perfil_aprendido(self):
        r = self.c("GET", "/api/cliente/estado/physis-perfil", cookie=self.ck)
        v = r[1].get("versao", 0)
        self.assertEqual(self.c("PUT", "/api/cliente/estado/physis-perfil",
                                {"valor": json.dumps({"c": {"descricao": "Produzimos soja e milho"}}), "versao": v}, self.ck)[0], 200)
        st, j, _ = self.c("GET", "/api/cliente/perfil", cookie=self.ck)
        self.assertEqual((st, j["aprendido"]["atividades"]), (200, ["graos"]))


class PonteDoNavegador(unittest.TestCase):
    def test_mesma_lista_de_chaves(self):
        js = PONTE.read_text(encoding="utf-8")
        chaves = json.loads(re.search(r"var CHAVES = (\[[^\]]*\])", js).group(1))
        prefixos = json.loads(re.search(r"var PREFIXOS = (\[[^\]]*\])", js).group(1))
        self.assertEqual((chaves, prefixos), (list(perfil_cliente.CHAVES), list(perfil_cliente.PREFIXOS)))
        for rota in ("/api/cliente/estado", "X-Physis-CSRF", '"PUT"', "keepalive"):
            self.assertIn(rota, js)
        self.assertNotIn("\r\n", js)


if __name__ == "__main__":
    unittest.main()
