"""Cadastro, senha e sessao da instalacao; rotas protegidas quando a instancia exige login."""
import json
import unittest
import urllib.error
import urllib.request

from physis_hub.hub import Hub
from physis_hub.servidor import iniciar


class Contas(unittest.TestCase):
    def setUp(self):
        self.t = [1_794_600_000.0]
        self.hub = Hub(relogio=lambda: self.t[0])

    def test_primeira_conta_e_administradora(self):
        self.assertFalse(self.hub.tem_conta())
        r = self.hub.criar_conta("Ana", "ana@exemplo.com", "senha-bem-longa")
        self.assertTrue(r["ok"] and r["primeira"])
        self.assertEqual(self.hub.entrar("ANA@exemplo.com", "senha-bem-longa")["papel"], "administrador")

    def test_senha_curta_e_campos_vazios(self):
        self.assertFalse(self.hub.criar_conta("Ana", "ana", "curta")["ok"])
        self.assertFalse(self.hub.criar_conta("", "ana", "senha-bem-longa")["ok"])

    def test_senha_nao_fica_guardada(self):
        self.hub.criar_conta("Ana", "ana", "senha-bem-longa")
        bruto = repr(self.hub._db.execute("SELECT * FROM conta").fetchall())
        self.assertNotIn("senha-bem-longa", bruto)

    def test_senha_errada_e_bloqueio(self):
        self.hub.criar_conta("Ana", "ana", "senha-bem-longa")
        for _ in range(5):
            self.assertFalse(self.hub.entrar("ana", "errada")["ok"])
        self.assertTrue(self.hub.entrar("ana", "senha-bem-longa").get("espera"))
        self.t[0] += 31
        self.assertTrue(self.hub.entrar("ana", "senha-bem-longa")["ok"])

    def test_sessao_expira_e_sair(self):
        self.hub.criar_conta("Ana", "ana", "senha-bem-longa")
        tk = self.hub.entrar("ana", "senha-bem-longa")["token"]
        self.assertEqual(self.hub.sessao(tk)["usuario"], "ana")
        self.hub.sair(tk)
        self.assertIsNone(self.hub.sessao(tk))
        tk2 = self.hub.entrar("ana", "senha-bem-longa")["token"]
        self.t[0] += Hub.SESSAO_S + 1
        self.assertIsNone(self.hub.sessao(tk2))

    def test_segunda_conta_so_por_administrador(self):
        self.hub.criar_conta("Ana", "ana", "senha-bem-longa")
        self.assertFalse(self.hub.criar_conta("Bia", "bia", "outra-senha-longa")["ok"])
        self.assertTrue(self.hub.criar_conta("Bia", "bia", "outra-senha-longa", autor=1)["ok"])
        self.assertEqual(self.hub.entrar("bia", "outra-senha-longa")["papel"], "operador")
        self.assertFalse(self.hub.criar_conta("Caio", "caio", "mais-uma-senha", autor=2)["ok"])


class RotasProtegidas(unittest.TestCase):
    PORTA = 8797

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1",
                          instancia={"login": True, "modulos": ["monitoramento", "sustainkit"], "licenca": "a definir"})
        cls.PORTA = cls.srv.server_address[1]   # porta livre escolhida pelo sistema

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def chamar(self, metodo, rota, corpo=None, cookie=None):
        dados = json.dumps(corpo).encode() if isinstance(corpo, dict) else (corpo.encode() if corpo else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}{rota}", data=dados, method=metodo,
                                     headers={"Cookie": cookie} if cookie else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode() or "{}"), r.headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}"), None

    def test_fluxo_completo(self):
        st, inst, _ = self.chamar("GET", "/api/instancia")
        self.assertEqual((st, inst["exige_login"], inst["tem_conta"], inst["autenticado"]), (200, True, False, False))
        self.assertEqual(inst["modulos"], ["monitoramento", "sustainkit"])
        self.assertEqual(self.chamar("GET", "/api/painel")[0], 401)
        self.assertEqual(self.chamar("POST", "/api/comando", {"comando": "CMD:01:PING"})[0], 401)
        # o receptor continua entregando sem login (rede local; token na F0)
        self.assertEqual(self.chamar("POST", "/api/gateway/webhook", "ID:01,U1:40.0,IR1:0,U2:41.0,IR2:0")[0], 200)
        self.assertEqual(self.chamar("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana", "senha": "curta"})[0], 400)
        st, r, cookie = self.chamar("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana", "senha": "senha-bem-longa"})
        self.assertEqual(st, 200)
        self.assertIn("HttpOnly", cookie)
        ck = cookie.split(";")[0]
        st, p, _ = self.chamar("GET", "/api/painel", cookie=ck)
        self.assertEqual((st, len(p["nos"])), (200, 1))
        self.assertTrue(self.chamar("GET", "/api/instancia", cookie=ck)[1]["autenticado"])
        self.assertEqual(self.chamar("POST", "/api/conta/criar", {"nome": "X", "usuario": "x", "senha": "senha-bem-longa"})[0], 400)
        self.assertEqual(self.chamar("POST", "/api/conta/entrar", {"usuario": "ana", "senha": "errada"})[0], 401)
        self.chamar("POST", "/api/conta/sair", {}, cookie=ck)
        self.assertEqual(self.chamar("GET", "/api/painel", cookie=ck)[0], 401)
        st, _, cookie2 = self.chamar("POST", "/api/conta/entrar", {"usuario": "ana", "senha": "senha-bem-longa"})
        self.assertEqual(st, 200)
        self.assertEqual(self.chamar("GET", "/api/painel", cookie=cookie2.split(";")[0])[0], 200)


if __name__ == "__main__":
    unittest.main()


class CaixaCentral(unittest.TestCase):
    """A loja entrega, a gestao recebe e aprova, a loja fica sabendo: tudo sem copiar e colar."""
    PORTA = 8794

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": True})
        cls.PORTA = cls.srv.server_address[1]   # porta livre escolhida pelo sistema

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    chamar = RotasProtegidas.chamar

    def test_compra_chega_e_aprovacao_volta(self):
        compra = {"_formato": "physis-compra/1", "numero": "LJ-TESTE-01", "recibo": "RC-TESTE-01", "total": 4900}
        self.assertEqual(self.chamar("POST", "/api/central/compra", {"numero": "X"})[0], 400)
        st, r, _ = self.chamar("POST", "/api/central/compra", compra)
        self.assertEqual((st, r["estado"], r["repetido"]), (200, "aguardando", False))
        self.assertTrue(self.chamar("POST", "/api/central/compra", compra)[1]["repetido"])
        self.assertEqual(self.chamar("GET", "/api/central/compra/LJ-TESTE-01")[1]["estado"], "aguardando")
        self.assertEqual(self.chamar("GET", "/api/central/compra/NAO-EXISTE")[0], 404)
        # so quem tem acesso interno le a caixa e aprova
        self.assertEqual(self.chamar("GET", "/api/central/caixa")[0], 401)
        self.assertEqual(self.chamar("POST", "/api/central/compra/LJ-TESTE-01/aprovar", {})[0], 401)
        _, _, cookie = self.chamar("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana", "senha": "senha-bem-longa"})
        ck = cookie.split(";")[0]
        st, caixa, _ = self.chamar("GET", "/api/central/caixa", cookie=ck)
        self.assertEqual([(i["tipo"], i["numero"], i["estado"]) for i in caixa["itens"]], [("compra", "LJ-TESTE-01", "aguardando")])
        self.assertEqual(self.chamar("POST", "/api/central/compra/LJ-TESTE-01/aprovar", {}, cookie=ck)[0], 200)
        self.assertEqual(self.chamar("GET", "/api/central/compra/LJ-TESTE-01")[1]["estado"], "aprovado")

    def test_pedido_de_proposta_chega(self):
        ped = {"_formato": "physis-pedido/1", "numero": "PP-TESTE-01", "texto": "Quero automatizar tres setores."}
        self.assertEqual(self.chamar("POST", "/api/central/pedido", ped)[1]["estado"], "novo")
        self.assertEqual(self.chamar("POST", "/api/central/pedido", dict(ped, _formato="outro"))[0], 400)


class Faturas(unittest.TestCase):
    def test_fatura_em_sequencia(self):
        h = Hub()
        self.assertEqual(h.central_por("compra", "LJ-A", {"total": 1})["fatura"], "0000")
        self.assertEqual(h.central_por("compra", "LJ-B", {"total": 2})["fatura"], "0001")
        self.assertEqual(h.central_por("compra", "LJ-A", {"total": 1})["fatura"], "0000")     # repetir nao gasta numero
        self.assertIsNone(h.central_por("pedido", "PP-A", {"texto": "x"})["fatura"])
        self.assertEqual(h.central_por("compra", "LJ-C", {"total": 3})["fatura"], "0002")


class ArquivosDoPedido(unittest.TestCase):
    """A cliente anexa Excel, PDF ou Word ao pedido; so a area interna lista e baixa."""
    PORTA = 8791

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": True})
        cls.PORTA = cls.srv.server_address[1]   # porta livre escolhida pelo sistema

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    chamar = RotasProtegidas.chamar

    def enviar(self, pedido, nome, dados):
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}/api/central/arquivo?pedido={pedido}&nome={nome}", data=dados, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def test_arquivo_do_pedido(self):
        self.assertEqual(self.enviar("PP-NAO-EXISTE", "conta.pdf", b"%PDF-1.4")[0], 400)
        self.chamar("POST", "/api/central/pedido", {"_formato": "physis-pedido/1", "numero": "PP-ARQ-01", "texto": "x"})
        self.assertEqual(self.enviar("PP-ARQ-01", "virus.exe", b"MZ")[0], 400)
        self.assertEqual(self.enviar("PP-ARQ-01", "../../etc/passwd.pdf", b"%PDF-1.4 conteudo")[1]["nome"], "passwd.pdf")
        st, r = self.enviar("PP-ARQ-01", "conta-de-luz.xlsx", b"PK\x03\x04planilha")
        self.assertEqual((st, r["tamanho"]), (200, 12))
        # sem acesso interno, ninguem lista nem baixa
        self.assertEqual(self.chamar("GET", "/api/central/arquivos?pedido=PP-ARQ-01")[0], 401)
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}/api/central/arquivo/{r['id']}")
        with self.assertRaises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(erro.exception.code, 401)
        _, _, cookie = self.chamar("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana", "senha": "senha-bem-longa"})
        ck = cookie.split(";")[0]
        lista = self.chamar("GET", "/api/central/arquivos?pedido=PP-ARQ-01", cookie=ck)[1]["arquivos"]
        self.assertEqual([a["nome"] for a in lista], ["passwd.pdf", "conta-de-luz.xlsx"])
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}/api/central/arquivo/{r['id']}", headers={"Cookie": ck})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.read(), b"PK\x03\x04planilha")
            self.assertIn("attachment", resp.headers["Content-Disposition"])


class PoliticaDeChamadas(unittest.TestCase):
    """A chamada da aba Reunioes so pode vir do servidor Jitsi da Physis; nada mais abre a politica."""

    def test_sem_servidor_a_politica_fica_fechada(self):
        from physis_hub.servidor import politica
        p = politica(None)
        self.assertIn("frame-src 'self' blob: data:;", p)
        self.assertIn("connect-src 'self';", p)
        self.assertNotIn("https://", p)

    def test_servidor_valido_entra_so_onde_precisa(self):
        from physis_hub.servidor import politica
        p = politica("https://chamada.physis.example/")
        self.assertIn("script-src 'self' 'unsafe-inline' https://chamada.physis.example;", p)
        self.assertIn("frame-src 'self' blob: data: https://chamada.physis.example;", p)
        self.assertIn("wss://chamada.physis.example", p)
        self.assertNotIn("https://chamada.physis.example", p.split("img-src")[1].split(";")[0])

    def test_valores_perigosos_sao_recusados(self):
        from physis_hub.servidor import origem_chamadas
        for ruim in ["http://chamada.physis.example", "https://x.example; script-src *", "https://x.example/sala",
                     "javascript:alert(1)", "https://user:senha@x.example", "https://x.example?a=1", "*", ""]:
            self.assertIsNone(origem_chamadas(ruim), ruim)
        self.assertEqual(origem_chamadas("https://x.example:8443"), "https://x.example:8443")


class CorpoGrande(unittest.TestCase):
    """Corpo grande demais volta 413 legivel, em qualquer sistema operacional (antes, no Windows, a conexao caia)."""
    PORTA = 8789

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1")
        cls.PORTA = cls.srv.server_address[1]   # porta livre escolhida pelo sistema

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def enviar(self, rota, dados):
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}{rota}", data=dados, method="POST",
                                     headers={"Content-Type": "text/plain"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def test_lote_grande_do_receptor_recebe_413(self):
        st, r = self.enviar("/api/gateway/webhook", b"ID:01,U1:1.0\n" * 20000)
        self.assertEqual((st, r["ok"]), (413, False))

    def test_servidor_segue_atendendo_depois_da_recusa(self):
        self.enviar("/api/gateway/webhook", b"x" * (200 * 1024))
        st, r = self.enviar("/api/gateway/webhook", b"ID:01,U1:30.0\n")
        self.assertEqual(st, 200)
