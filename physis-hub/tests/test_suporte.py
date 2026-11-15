"""Suporte ao cliente (Gestão → Suporte Physis): chamado por e-mail e atalho do WhatsApp.

Protege:
1. O chamado precisa de assunto e mensagem e de um e-mail de suporte configurado (nunca no código).
2. Vira registro numerado SP-0001… na central e entra na fila de e-mails para a Physis.
3. Pela rede: exige sessão quando a instalação exige login; o GET devolve os chamados, o e-mail e o WhatsApp
   só com dígitos, vindos da configuração da instalação.
"""
import json
import unittest
import urllib.error
import urllib.request

from physis_hub.hub import Hub
from physis_hub.servidor import iniciar

PARA = "suporte@exemplo.com.br"


class SuporteNoHub(unittest.TestCase):
    def test_abre_numera_e_enfileira(self):
        h = Hub()
        self.assertFalse(h.suporte_abrir({"assunto": "", "mensagem": "x"}, "Ana", PARA)["ok"])
        self.assertFalse(h.suporte_abrir({"assunto": "a", "mensagem": "b"}, "Ana", "")["ok"])
        r1 = h.suporte_abrir({"assunto": "Sensor parado", "mensagem": "Sem leituras desde ontem", "canal": "whatsapp", "contato": "61 9999"}, "Ana", PARA)
        r2 = h.suporte_abrir({"assunto": "Dúvida", "mensagem": "Como baixar o relatório?"}, "Ana", PARA)
        self.assertEqual((r1["numero"], r2["numero"]), ("SP-0001", "SP-0002"))
        lista = h.suporte_listar()
        self.assertEqual([c["numero"] for c in lista], ["SP-0001", "SP-0002"])
        self.assertEqual(lista[0]["canal"], "whatsapp"); self.assertEqual(lista[1]["canal"], "email")
        mails = [e for e in h.emails("pendente") if e["ref"].startswith("SP-")]
        self.assertEqual(len(mails), 2); self.assertEqual(mails[0]["para"], PARA); self.assertIn("Sensor parado", mails[0]["assunto"])


class SuporteNoServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": True, "modulos": [], "suporte_email": PARA,
                                                                        "suporte_whatsapp": "+55 61 90000-0000"})
        cls.PORTA = cls.srv.server_address[1]
        st, j, ck = cls.chamar("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana@exemplo.com.br", "senha": "senha-bem-longa"})
        assert st == 200 and ck, (st, j)
        cls.cookie = ck.split(";", 1)[0]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    @classmethod
    def chamar(cls, metodo, rota, corpo=None, cookie=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        cab = {"Content-Type": "application/json"}
        if cookie:
            cab["Cookie"] = cookie
        req = urllib.request.Request(f"http://127.0.0.1:{cls.PORTA}{rota}", data=dados, method=metodo, headers=cab)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode() or "{}"), r.headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}"), None

    def test_exige_sessao(self):
        st, _, _ = self.chamar("POST", "/api/suporte", {"assunto": "a", "mensagem": "b"})
        self.assertEqual(st, 401)

    def test_abrir_e_listar(self):
        st, j, _ = self.chamar("POST", "/api/suporte", {"assunto": "Teste", "mensagem": "Olá"}, self.cookie)
        self.assertEqual(st, 200, j); self.assertTrue(j["numero"].startswith("SP-"))
        st, j, _ = self.chamar("POST", "/api/suporte", {"assunto": "", "mensagem": "Olá"}, self.cookie)
        self.assertEqual(st, 400)
        st, j, _ = self.chamar("GET", "/api/suporte", None, self.cookie)
        self.assertEqual(st, 200)
        self.assertEqual(j["whatsapp"], "5561900000000"); self.assertEqual(j["email"], PARA)
        self.assertTrue(any(c["assunto"] == "Teste" for c in j["chamados"]))


if __name__ == "__main__":
    unittest.main()
