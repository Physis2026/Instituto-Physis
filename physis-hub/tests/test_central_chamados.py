"""Central de clientes e caixa de chamados (Gestão interna).

Protege:
1. GET /api/central/clientes junta compras, instalações, pedidos e chamados por organização (pelo e-mail de contato),
   com módulos, número da instalação e chamados (quantos e em que situação). Dado pessoal: só equipe.
2. GET/POST /api/suporte/chamados/<numero>: situação (novo / em atendimento / resolvido), responsável, nota interna e
   resposta por e-mail (fila email_saida). O cliente vê a situação e a resposta em GET /api/suporte, nunca as notas.
"""
import json
import unittest
import urllib.error
import urllib.request

from physis_hub.hub import Hub
from physis_hub.servidor import iniciar

COMPRA = {"_formato": "physis-compra/1", "numero": "LJ-CC-01", "total": 4900, "modulos": ["monitoramento", "agua"],
          "pagador": {"nome": "Fazenda Boa Água", "doc": "12345678000199", "email": "Cliente@Exemplo.com", "telefone": "61999990000"}}
PEDIDO = {"_formato": "physis-pedido/1", "numero": "PP-CC-01", "texto": "Quero solar.", "nome": "Ana", "org": "Sítio Ana",
          "email": "ana@sitio.example", "telefone": "24999990000"}


class CentralNoHub(unittest.TestCase):
    def setUp(self):
        self.h = Hub(org="physis-site")
        self.h.central_por("compra", COMPRA["numero"], COMPRA)
        self.h.central_por("pedido", PEDIDO["numero"], PEDIDO)
        self.h.instalar_compra(COMPRA["numero"], "https://hub.example")
        self.chamado = self.h.suporte_abrir({"assunto": "Sensor parado", "mensagem": "O nó 3 não fala."}, "Fazenda Boa Água",
                                            "suporte@physis.example", "cliente@exemplo.com")["numero"]
        self.h.suporte_abrir({"assunto": "Dúvida", "mensagem": "Como instalo?", "contato": "Ana · ana@sitio.example"}, "Ana",
                             "suporte@physis.example")

    def test_fichas(self):
        fichas = {f["nome"]: f for f in self.h.central_clientes()}
        f = fichas["Fazenda Boa Água"]
        self.assertTrue(f["org"].startswith("fazenda-boa-agua-"))
        self.assertEqual(f["contato"]["email"], "cliente@exemplo.com")
        self.assertEqual(f["modulos"], ["monitoramento", "agua"])
        self.assertEqual(f["instalacoes"][0]["numero"], "PH-0001")
        self.assertEqual(f["compras"][0]["numero"], "LJ-CC-01")
        self.assertEqual((f["chamados"]["total"], f["chamados"]["abertos"], f["chamados"]["novo"]), (1, 1, 1))
        a = fichas["Sítio Ana"]
        self.assertEqual((a["pedidos"][0]["numero"], a["chamados"]["total"]), ("PP-CC-01", 1))

    def test_atualizar_chamado(self):
        r = self.h.suporte_atualizar(self.chamado, {"estado": "em atendimento", "responsavel": "Laura", "nota": "ver bateria"}, "laura@physis")
        self.assertTrue(r["ok"])
        self.assertEqual((r["chamado"]["estado"], r["chamado"]["responsavel"], len(r["chamado"]["notas"])), ("em_atendimento", "Laura", 1))
        r = self.h.suporte_atualizar(self.chamado, {"estado": "resolvido", "resposta": {"texto": "Trocamos a bateria."}}, "laura@physis")
        self.assertEqual((r["ok"], r["ref"]), (True, self.chamado + "-R1"))
        e = [x for x in self.h.emails() if x["ref"] == r["ref"]][0]
        self.assertEqual((e["para"], e["estado"]), ("cliente@exemplo.com", "pendente"))
        self.assertIn("Trocamos a bateria.", e["corpo"]); self.assertIn("situação: resolvido", e["corpo"])
        self.assertNotIn("ver bateria", e["corpo"])                                    # nota interna nunca vai ao cliente
        meus = self.h.suporte_listar("cliente@exemplo.com")
        self.assertEqual((meus[0]["estado"], meus[0]["respostas"][0]["texto"]), ("resolvido", "Trocamos a bateria."))
        self.assertNotIn("notas", meus[0]); self.assertNotIn("responsavel", meus[0])
        self.assertFalse(self.h.suporte_atualizar(self.chamado, {"estado": "fechado"}, "x")["ok"])
        self.assertEqual(self.h.suporte_atualizar("SP-9999", {"estado": "novo"}, "x").get("codigo"), 404)
        self.assertTrue(self.h.suporte_atualizar(self.chamado, {}, "x")["igual"])
        self.assertEqual([h["para"] for h in self.h.suporte_detalhe(self.chamado)["historico"]], ["em_atendimento", "resolvido"])

    def test_resposta_sem_email(self):
        n = self.h.suporte_abrir({"assunto": "x", "mensagem": "y", "contato": "24 99999-0000", "canal": "whatsapp"}, "Zé",
                                 "suporte@physis.example")["numero"]
        r = self.h.suporte_atualizar(n, {"resposta": {"texto": "oi"}}, "laura")
        self.assertFalse(r["ok"]); self.assertIn("WhatsApp", r["erro"])


class CentralPelaRede(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = Hub(org="physis-site")
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": False, "suporte_email": "suporte@physis.example"})
        cls.porta = cls.srv.server_address[1]
        cls.hub.criar_conta("Direção", "dir@physis.example", "frase-longa-da-direcao-1")
        adm = cls.hub.sessao(cls.hub.entrar("dir@physis.example", "frase-longa-da-direcao-1")["token"])
        cls.hub.criar_conta("Laura", "laura@physis.example", "frase-longa-da-laura-1", adm["id"], papel="equipe")
        cls.hub.criar_conta("Cliente", "cliente@exemplo.com", "frase-longa-do-cliente-1", adm["id"], papel="cliente")
        cls.eq = "physis_sessao=" + cls.hub.entrar("laura@physis.example", "frase-longa-da-laura-1")["token"]
        cls.cli = "physis_sessao=" + cls.hub.entrar("cliente@exemplo.com", "frase-longa-do-cliente-1")["token"]
        cls.hub.central_por("compra", COMPRA["numero"], COMPRA)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def c(self, metodo, rota, corpo=None, cookie=None):
        h = {"Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = cookie
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", method=metodo, headers=h,
                                     data=json.dumps(corpo).encode() if corpo is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_fluxo(self):
        # o cliente abre um chamado pela plataforma
        st, j = self.c("POST", "/api/suporte", {"assunto": "Sem leitura", "mensagem": "O painel parou."}, self.cli)
        self.assertEqual(st, 200)
        n = j["numero"]
        # sem sessão ou como cliente: nada da central
        self.assertEqual(self.c("GET", "/api/central/clientes")[0], 401)
        self.assertEqual(self.c("GET", "/api/central/clientes", cookie=self.cli)[0], 403)
        self.assertEqual(self.c("GET", "/api/suporte/chamados/" + n, cookie=self.cli)[0], 403)
        self.assertEqual(self.c("POST", "/api/suporte/chamados/" + n, {"estado": "resolvido"}, self.cli)[0], 403)
        # a equipe vê as fichas e o chamado
        st, j = self.c("GET", "/api/central/clientes", cookie=self.eq)
        f = [x for x in j["clientes"] if x["contato"]["email"] == "cliente@exemplo.com"][0]
        self.assertEqual((st, f["chamados"]["total"], f["compras"][0]["numero"]), (200, 1, "LJ-CC-01"))
        st, j = self.c("GET", "/api/suporte/chamados/" + n, cookie=self.eq)
        self.assertEqual((st, j["chamado"]["estado"], j["chamado"]["email_cliente"]), (200, "novo", "cliente@exemplo.com"))
        self.assertEqual(self.c("GET", "/api/suporte/chamados/SP-9999", cookie=self.eq)[0], 404)
        self.assertEqual(len(self.c("GET", "/api/suporte/chamados", cookie=self.eq)[1]["chamados"]), 1)
        # atualiza, responde e o cliente vê
        st, j = self.c("POST", "/api/suporte/chamados/" + n, {"estado": "em atendimento", "responsavel": "Laura",
                                                               "nota": "interno", "resposta": {"texto": "Já estamos vendo."}}, self.eq)
        self.assertEqual((st, j["chamado"]["estado"], j["email"]), (200, "em_atendimento", "pendente"))
        self.assertEqual(self.c("POST", "/api/suporte/chamados/" + n, {"estado": "x"}, self.eq)[0], 400)
        self.assertEqual(self.c("POST", "/api/suporte/chamados/" + n, {"desconhecido": 1}, self.eq)[0], 400)
        st, j = self.c("GET", "/api/suporte", cookie=self.cli)
        ch = j["chamados"][0]
        self.assertEqual((ch["estado"], ch["respostas"][0]["texto"]), ("em_atendimento", "Já estamos vendo."))
        self.assertNotIn("interno", json.dumps(j, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
