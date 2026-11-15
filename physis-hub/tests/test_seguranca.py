"""Servidor exposto à internet (docs/SEGURANCA.md). Um bloco por item da auditoria:

1. Cookie Secure e HSTS só por HTTPS (PHYSIS_HTTPS=1 ou X-Forwarded-Proto de proxy confiável); cabeçalhos extras.
2. Dados pessoais (caixa, chamados, anexos, e-mails, gestão) sempre com sessão; sem login, a telemetria é aberta
   só para a rede local.
3. Aparelhos: chave por dispositivo (resumo no banco, revogável, presa ao nó); sem chave só da rede local
   ou com PHYSIS_ACEITAR_SEM_CHAVE=1; PHYSIS_TOKEN comparado em tempo constante.
4. Papéis: direção x equipe x cliente nas rotas sensíveis.
5. Limite por IP (429 + Retry-After, lendo o corpo antes) nos formulários públicos, anexos e login.
6. Sessão guardada só como resumo SHA-256; migração descarta as sessões antigas em texto.
7. LGPD: Meus dados, Apagar meus dados e retenção.
8. Erro interno nunca devolve o rastro.
Segunda parte: senha esquecida, confirmação do e-mail, convite, consentimento, política de senha, 2FA (TOTP),
ociosidade e vida da sessão, reautenticação, CSRF, JSON/arquivos validados, security.txt, eventos na cadeia.
"""
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from physis_hub import seguranca as seg
from physis_hub.hub import Hub
from physis_hub.servidor import iniciar

SENHA = "senha-bem-longa"


def chamar(porta, metodo, rota, corpo=None, cab=None, cookie=None):
    if isinstance(corpo, (dict, list)):
        dados = json.dumps(corpo).encode()
    elif isinstance(corpo, str):
        dados = corpo.encode()
    else:
        dados = corpo
    h = dict(cab or {})
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(f"http://127.0.0.1:{porta}{rota}", data=dados, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            b = r.read()
            return r.status, (json.loads(b.decode() or "{}") if "json" in (r.headers.get("Content-Type") or "") else b), r.headers
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b.decode() or "{}"), e.headers
        except ValueError:
            return e.code, b, e.headers


class Servidor(unittest.TestCase):
    """Base: um servidor por classe, criado com as variáveis de ambiente de AMBIENTE."""
    AMBIENTE: dict = {}
    INSTANCIA = {"login": True}

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        with mock.patch.dict(os.environ, cls.AMBIENTE):
            cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia=dict(cls.INSTANCIA))
        cls.PORTA = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def c(self, *a, **k):
        return chamar(self.PORTA, *a, **k)

    def conta(self, nome, usuario, papel=None, admin_ck=None):
        """Cria (a primeira vira direção) e devolve o cookie da sessão."""
        if admin_ck:
            st, j, _ = self.c("POST", "/api/contas", {"nome": nome, "usuario": usuario, "senha": SENHA, "papel": papel}, cookie=admin_ck)
            self.assertEqual(st, 200, j)
            st, j, h = self.c("POST", "/api/conta/entrar", {"usuario": usuario, "senha": SENHA})
        else:
            st, j, h = self.c("POST", "/api/conta/criar", {"nome": nome, "usuario": usuario, "senha": SENHA})
        self.assertEqual(st, 200, j)
        return h["Set-Cookie"].split(";")[0]


# ── 1. Secure, HSTS e cabeçalhos ─────────────────────────────────────────────
class HttpsDireto(Servidor):
    def test_sem_https_sem_secure_nem_hsts(self):
        st, _, h = self.c("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana@x.com", "senha": SENHA})
        self.assertEqual(st, 200)
        self.assertNotIn("Secure", h["Set-Cookie"])
        self.assertIsNone(h["Strict-Transport-Security"])
        # X-Forwarded-Proto de quem não é proxy confiável não vale
        st, _, h = self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA}, cab={"X-Forwarded-Proto": "https"})
        self.assertNotIn("Secure", h["Set-Cookie"])
        # PHYSIS_HTTPS=1: o servidor só é alcançado por HTTPS
        with mock.patch.dict(os.environ, {"PHYSIS_HTTPS": "1"}):
            st, _, h = self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA})
        self.assertIn("; Secure", h["Set-Cookie"])
        self.assertIn("max-age=", h["Strict-Transport-Security"])

    def test_cabecalhos_extra_e_sem_versao_do_python(self):
        st, _, h = self.c("GET", "/api/instancia")
        self.assertEqual(st, 200)
        self.assertIn("default-src 'self'", h["Content-Security-Policy"])
        self.assertIn("geolocation=(self)", h["Permissions-Policy"])
        self.assertIn("payment=()", h["Permissions-Policy"])
        self.assertEqual(h["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(h["X-Frame-Options"], "SAMEORIGIN")
        self.assertNotIn("Python", h["Server"])


class HttpsPorProxy(Servidor):
    AMBIENTE = {"PHYSIS_PROXY_CONFIAVEL": "127.0.0.1,::1"}

    def test_proxy_confiavel_https(self):
        st, _, h = self.c("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana@x.com", "senha": SENHA},
                          cab={"X-Forwarded-Proto": "https", "X-Forwarded-For": "192.168.0.10"})
        self.assertEqual(st, 200)
        self.assertIn("; Secure", h["Set-Cookie"])
        self.assertTrue(h["Strict-Transport-Security"])
        st, _, h = self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA},
                          cab={"X-Forwarded-Proto": "http", "X-Forwarded-For": "192.168.0.10"})
        self.assertNotIn("Secure", h["Set-Cookie"])

    def test_primeira_conta_de_fora_e_recusada(self):
        h = Hub()
        with mock.patch.dict(os.environ, self.AMBIENTE):
            srv = iniciar(h, 0, endereco="127.0.0.1", instancia={"login": True})
        try:
            p = srv.server_address[1]
            st, j, _ = chamar(p, "POST", "/api/conta/criar", {"nome": "X", "usuario": "x@x.com", "senha": SENHA},
                              cab={"X-Forwarded-For": "203.0.113.9"})
            self.assertEqual(st, 403)
            self.assertFalse(h.tem_conta())
        finally:
            srv.shutdown()


class Rede(unittest.TestCase):
    def test_ip_do_cliente(self):
        px = seg.proxies_confiaveis("127.0.0.1, 10.0.0.0/8")
        self.assertEqual(seg.ip_do_cliente("203.0.113.5", {"X-Forwarded-For": "1.2.3.4"}, px), "203.0.113.5")   # não confiável: ignora
        self.assertEqual(seg.ip_do_cliente("127.0.0.1", {"X-Forwarded-For": "1.2.3.4, 10.1.1.1"}, px), "1.2.3.4")
        self.assertEqual(seg.ip_do_cliente("127.0.0.1", {"X-Forwarded-For": "9.9.9.9, 1.2.3.4"}, px), "1.2.3.4")  # forjado à esquerda
        self.assertEqual(seg.ip_do_cliente("127.0.0.1", {}, px), "desconhecido")
        self.assertEqual(seg.ip_do_cliente("127.0.0.1", {"X-Forwarded-For": "1.2.3.4"}, []), "127.0.0.1")
        self.assertFalse(seg.eh_rede_local("desconhecido"))
        self.assertTrue(seg.eh_rede_local("192.168.4.20"))
        self.assertTrue(seg.eh_rede_local("::ffff:10.0.0.3"))
        self.assertFalse(seg.eh_rede_local("8.8.8.8"))
        self.assertFalse(seg.eh_rede_local("203.0.113.7"))          # faixa de documentação: is_private do Python diria True
        with mock.patch.dict(os.environ, {"PHYSIS_REDE_LOCAL": "100.64.0.0/10"}):
            self.assertTrue(seg.eh_rede_local("100.64.1.1"))
        with mock.patch.dict(os.environ, {"PHYSIS_EXPOSTO": "1"}):
            self.assertFalse(seg.eh_rede_local("127.0.0.1"))


# ── 2. Dados pessoais sempre com sessão; sem login, telemetria só na rede local ──
class SemLogin(Servidor):
    INSTANCIA = {"login": False, "suporte_email": "suporte@exemplo.com.br", "suporte_whatsapp": "+55 61 90000-0000"}
    AMBIENTE = {"PHYSIS_PROXY_CONFIAVEL": "127.0.0.1"}

    def test_dados_pessoais_pedem_sessao(self):
        self.c("POST", "/api/central/compra", {"_formato": "physis-compra/1", "numero": "LJ-1", "email": "pagador@x.com", "cpf": "123"},
               cab={"X-Forwarded-For": "192.168.0.5"})
        lan = {"X-Forwarded-For": "192.168.0.5"}
        for rota in ("/api/central/caixa", "/api/central/arquivos?pedido=X", "/api/central/arquivo/abc",
                     "/api/central/emails", "/api/central/instalacoes", "/api/gestao/estado", "/api/conta/meus-dados"):
            st, j, _ = self.c("GET", rota, cab=lan)
            self.assertEqual(st, 401, rota)
        # suporte: contatos públicos, chamados não
        self.c("POST", "/api/suporte", {"assunto": "a", "mensagem": "meu telefone 9999", "contato": "61 9999"}, cab=lan)
        st, j, _ = self.c("GET", "/api/suporte", cab=lan)
        self.assertEqual((st, j["chamados"], j["whatsapp"]), (200, [], "5561900000000"))

    def test_telemetria_aberta_so_na_rede_local(self):
        self.assertEqual(self.c("GET", "/api/painel", cab={"X-Forwarded-For": "192.168.0.5"})[0], 200)
        self.assertEqual(self.c("GET", "/api/leituras", cab={"X-Forwarded-For": "192.168.0.5"})[0], 200)
        for rota in ("/api/painel", "/api/leituras", "/api/serie?ativo=a&grandeza=b"):
            self.assertEqual(self.c("GET", rota, cab={"X-Forwarded-For": "203.0.113.7"})[0], 401, rota)
        self.assertEqual(self.c("POST", "/api/comando", {"comando": "CMD:01:PING"}, cab={"X-Forwarded-For": "203.0.113.7"})[0], 401)
        self.assertEqual(self.c("POST", "/api/clima/atualizar", {}, cab={"X-Forwarded-For": "203.0.113.7"})[0], 401)
        with mock.patch.dict(os.environ, {"PHYSIS_EXPOSTO": "1"}):
            self.assertEqual(self.c("GET", "/api/painel", cab={"X-Forwarded-For": "192.168.0.5"})[0], 401)


# ── 3. Chaves por dispositivo ────────────────────────────────────────────────
class ChavesNoHub(unittest.TestCase):
    def test_criar_conferir_revogar(self):
        h = Hub()
        r = seg.chave_criar(h, 7, "caixinha da horta", "ana")
        self.assertTrue(r["ok"] and r["chave"].startswith("phk_"))
        bruto = repr(h._db.execute("SELECT * FROM dispositivo_chave").fetchall())
        self.assertNotIn(r["chave"], bruto)
        self.assertIn(hashlib.sha256(r["chave"].encode()).hexdigest(), bruto)
        self.assertEqual(seg.chave_conferir(h, r["chave"]), {"id": r["id"], "no": 7})
        self.assertIsNone(seg.chave_conferir(h, r["chave"] + "x"))
        self.assertNotIn("chave", seg.chave_listar(h)[0])
        self.assertTrue(seg.chave_revogar(h, r["id"], "ana"))
        self.assertIsNone(seg.chave_conferir(h, r["chave"]))
        self.assertFalse(seg.chave_criar(h, "abc", "", "ana")["ok"])
        self.assertEqual(seg.filtrar_do_no("ID:7,U1:1\nID:8,U1:2\n", 7), ("ID:7,U1:1", 1))
        self.assertTrue(h.verificar_cadeia()[0])


class ChavesNoServidor(Servidor):
    AMBIENTE = {"PHYSIS_ACEITAR_SEM_CHAVE": "0"}          # mesmo da rede local, só com chave

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        st, j, h = chamar(cls.PORTA, "POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana@x.com", "senha": SENHA})
        cls.adm = h["Set-Cookie"].split(";")[0]

    def test_rotas_de_admin_e_entrega(self):
        linha = "ID:01,U1:40.0,IR1:0,U2:41.0,IR2:0"
        self.assertEqual(self.c("POST", "/api/gateway/webhook", linha)[0], 401)          # sem chave: recusado
        self.assertEqual(self.c("POST", "/api/dispositivos/chaves", {"rotulo": "rx"})[0], 401)
        op = self.conta("Bia", "bia@x.com", "equipe", self.adm)
        self.assertEqual(self.c("POST", "/api/dispositivos/chaves", {"rotulo": "rx"}, cookie=op)[0], 403)
        self.assertEqual(self.c("GET", "/api/dispositivos/chaves", cookie=op)[0], 403)
        st, rx, _ = self.c("POST", "/api/dispositivos/chaves", {"rotulo": "receptor"}, cookie=self.adm)
        self.assertEqual(st, 200)
        st, so7, _ = self.c("POST", "/api/dispositivos/chaves", {"rotulo": "caixinha", "no": 7}, cookie=self.adm)
        lista = self.c("GET", "/api/dispositivos/chaves", cookie=self.adm)[1]["chaves"]
        self.assertEqual([c["rotulo"] for c in lista], ["receptor", "caixinha"])
        self.assertNotIn(rx["chave"], json.dumps(lista))
        st, r, _ = self.c("POST", "/api/gateway/webhook", linha, cab={"Authorization": "Bearer " + rx["chave"]})
        self.assertEqual((st, r["aceitas"]), (200, 1))
        st, r, _ = self.c("POST", "/api/v6/linha", "ID:07,U1:1.0\n" + linha, cab={"X-Physis-Chave": so7["chave"]})
        self.assertEqual((st, r["recusadas_outro_no"]), (200, 1))       # a chave do nó 7 não fala pelo nó 1
        self.assertEqual(self.c("POST", "/api/gateway/webhook", linha, cab={"X-Physis-Chave": "phk_errada"})[0], 401)
        self.assertEqual(self.c("POST", f"/api/dispositivos/chaves/{rx['id']}/revogar", {}, cookie=self.adm)[0], 200)
        self.assertEqual(self.c("POST", "/api/gateway/webhook", linha, cab={"Authorization": "Bearer " + rx["chave"]})[0], 401)


class SemChaveSoNaRedeLocal(Servidor):
    INSTANCIA = {"login": False}
    AMBIENTE = {"PHYSIS_PROXY_CONFIAVEL": "127.0.0.1"}

    def test_padrao(self):
        linha = "ID:02,U1:40.0"
        lan = {"X-Forwarded-For": "192.168.4.1"}
        self.assertEqual(self.c("POST", "/api/gateway/webhook", linha, cab=lan)[0], 200)    # da rede local (receptor atual)
        # do próprio proxy sem X-Forwarded-For: origem desconhecida, tratada como de fora
        self.assertEqual(self.c("POST", "/api/gateway/webhook", linha)[0], 401)
        self.assertEqual(self.c("POST", "/api/gateway/webhook", linha, cab={"X-Forwarded-For": "203.0.113.4"})[0], 401)
        self.assertEqual(self.c("POST", "/api/saude/linha", "ID:31,TIPO:MED,EVT:TOMADO,TS:1",
                                cab={"X-Forwarded-For": "203.0.113.4"})[0], 401)
        with mock.patch.dict(os.environ, {"PHYSIS_EXPOSTO": "1"}):
            self.assertEqual(self.c("POST", "/api/v6/linha", linha, cab=lan)[0], 401)
        with mock.patch.dict(os.environ, {"PHYSIS_ACEITAR_SEM_CHAVE": "1"}):     # lido na criação do servidor: aqui não muda
            self.assertEqual(self.c("POST", "/api/v6/linha", linha, cab={"X-Forwarded-For": "203.0.113.4"})[0], 401)


class TokenAntigo(Servidor):
    INSTANCIA = {"login": False}
    AMBIENTE = {"PHYSIS_ACEITAR_SEM_CHAVE": "0"}

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()
        with mock.patch.dict(os.environ, cls.AMBIENTE):
            cls.srv = iniciar(cls.hub, 0, token="segredo-antigo", endereco="127.0.0.1", instancia={"login": False})
        cls.PORTA = cls.srv.server_address[1]

    def test_token_vale_e_compara_certo(self):
        self.assertEqual(self.c("POST", "/api/gateway/webhook", "ID:03,U1:1.0", cab={"X-Physis-Token": "segredo-antigo"})[0], 200)
        self.assertEqual(self.c("POST", "/api/gateway/webhook", "ID:03,U1:1.0", cab={"X-Physis-Token": "segredo-antigX"})[0], 401)
        self.assertEqual(self.c("POST", "/api/comando", {"comando": "CMD:01:PING"}, cab={"X-Physis-Token": "errado"})[0], 401)
        self.assertTrue(seg.iguais("a", "a") and not seg.iguais("a", "b") and not seg.iguais(None, "a"))


# ── 4. Papéis ────────────────────────────────────────────────────────────────
class Papeis(Servidor):
    INSTANCIA = {"login": False}

    def test_normalizar(self):
        self.assertEqual(seg.normalizar_papel("Direção"), "administrador")
        self.assertEqual(seg.normalizar_papel("equipe"), "operador")
        self.assertEqual(seg.normalizar_papel("cliente"), "cliente")
        self.assertIsNone(seg.normalizar_papel("dono"))
        self.assertTrue(seg.pode({"papel": "administrador"}, "equipe"))
        self.assertFalse(seg.pode({"papel": "cliente"}, "equipe"))
        self.assertFalse(seg.pode(None, "cliente"))

    def test_direcao_equipe_cliente(self):
        adm = self.conta("Ana", "ana@x.com")
        eq = self.conta("Bia", "bia@x.com", "equipe", adm)
        cli = self.conta("Caio", "caio@x.com", "cliente", adm)
        self.assertEqual({c["usuario"]: c["papel"] for c in self.c("GET", "/api/contas", cookie=adm)[1]["contas"]},
                         {"ana@x.com": "administrador", "bia@x.com": "operador", "caio@x.com": "cliente"})
        self.c("POST", "/api/central/compra", {"_formato": "physis-compra/1", "numero": "LJ-P1", "total": 10})
        # aprovar compra: só a direção
        self.assertEqual(self.c("POST", "/api/central/compra/LJ-P1/aprovar", {}, cookie=eq)[0], 403)
        self.assertEqual(self.c("POST", "/api/central/compra/LJ-P1/aprovar", {}, cookie=cli)[0], 403)
        self.assertEqual(self.c("POST", "/api/central/compra/LJ-P1/aprovar", {}, cookie=adm)[0], 200)
        # loja: equipe grava e revisa; publicar, só a direção
        self.assertEqual(self.c("POST", "/api/loja/item/campo", {"st": "func", "preco": 1}, cookie=eq)[0], 200)
        self.assertEqual(self.c("POST", "/api/loja/item/campo/revisar", {}, cookie=eq)[0], 200)
        self.assertEqual(self.c("POST", "/api/loja/item/campo/publicar", {}, cookie=eq)[0], 403)
        self.assertEqual(self.c("POST", "/api/loja/item/campo", {"st": "func"}, cookie=cli)[0], 403)
        self.assertEqual(self.c("POST", "/api/loja/item/campo/publicar", {}, cookie=adm)[0], 200)
        # textos do site: só a direção
        self.assertEqual(self.c("POST", "/api/site/textos/consultoria", {"heroi.titulo": "X"}, cookie=eq)[0], 403)
        self.assertEqual(self.c("POST", "/api/site/textos/consultoria", {"heroi.titulo": "X"}, cookie=adm)[0], 200)
        # contas: só a direção (antes o hub recusava com 400; agora o servidor barra antes, com 403)
        self.assertEqual(self.c("POST", "/api/contas", {"nome": "D", "usuario": "d@x.com", "senha": SENHA}, cookie=eq)[0], 403)
        self.assertEqual(self.c("GET", "/api/contas", cookie=eq)[0], 403)
        # fontes dos editais/eventos: só a direção; cliente fora da área interna
        self.assertEqual(self.c("POST", "/api/eventos/fontes", {"remover": "x"}, cookie=eq)[0], 403)
        self.assertEqual(self.c("GET", "/api/eventos", cookie=cli)[0], 403)
        # dados pessoais: equipe sim, cliente não
        self.assertEqual(self.c("GET", "/api/central/caixa", cookie=eq)[0], 200)
        for rota in ("/api/central/caixa", "/api/gestao/estado", "/api/central/emails", "/api/loja/catalogo/interno"):
            self.assertEqual(self.c("GET", rota, cookie=cli)[0], 403, rota)
        # suporte: cliente vê só os próprios chamados
        with mock.patch.dict(os.environ, {"PHYSIS_SUPORTE_EMAIL": "s@x.com"}):
            self.c("POST", "/api/suporte", {"assunto": "do cliente", "mensagem": "m"}, cookie=cli)
            self.c("POST", "/api/suporte", {"assunto": "da equipe", "mensagem": "m"}, cookie=eq)
            self.assertEqual([c["assunto"] for c in self.c("GET", "/api/suporte", cookie=cli)[1]["chamados"]], ["do cliente"])
            self.assertEqual(len(self.c("GET", "/api/suporte", cookie=eq)[1]["chamados"]), 2)


# ── 5. Limites por IP ────────────────────────────────────────────────────────
class Limitador(unittest.TestCase):
    def test_balde(self):
        t = [0.0]
        lim = seg.Limitador(2, 60, relogio=lambda: t[0])
        self.assertEqual((lim.tentar("a"), lim.tentar("a")), (0.0, 0.0))
        self.assertAlmostEqual(lim.tentar("a"), 30.0)
        self.assertEqual(lim.tentar("b"), 0.0)          # outro IP, outro balde
        t[0] += 30
        self.assertEqual(lim.tentar("a"), 0.0)
        self.assertEqual(seg.ler_limite("5/10", "1/1"), (5.0, 10.0))
        self.assertIsNone(seg.ler_limite("0", "1/1"))
        self.assertEqual(seg.ler_limite("lixo", "3/9"), (3.0, 9.0))


class LimitesNoServidor(Servidor):
    INSTANCIA = {"login": False}
    AMBIENTE = {"PHYSIS_LIMITE_PUBLICO": "2/600", "PHYSIS_LIMITE_ARQUIVO": "1/600", "PHYSIS_LIMITE_ENTRAR": "3/600"}

    def test_formulario_publico(self):
        for i in range(2):
            self.assertEqual(self.c("POST", "/api/central/pedido", {"_formato": "physis-pedido/1", "numero": f"PP-L{i}", "texto": "x"})[0], 200)
        st, j, h = self.c("POST", "/api/central/pedido", {"_formato": "physis-pedido/1", "numero": "PP-L9", "texto": "x"})
        self.assertEqual(st, 429)
        self.assertGreater(int(h["Retry-After"]), 0)
        self.assertGreater(j["espera"], 0)

    def test_anexo_grande_recebe_429_legivel(self):
        self.hub.central_por("pedido", "PP-ARQ", {"texto": "x"})          # direto no hub: não gasta ficha do formulário
        st, _, _ = self.c("POST", "/api/central/arquivo?pedido=PP-ARQ&nome=a.pdf", b"%PDF-1.4 x")
        self.assertEqual(st, 200)
        st, j, h = self.c("POST", "/api/central/arquivo?pedido=PP-ARQ&nome=b.pdf", b"x" * (2 * 1024 * 1024))
        self.assertEqual((st, j["ok"]), (429, False))           # corpo lido antes de responder: sem RST
        self.assertEqual(self.c("GET", "/api/instancia")[0], 200)

    def test_login_por_ip(self):
        for i in range(3):
            self.assertEqual(self.c("POST", "/api/conta/entrar", {"usuario": f"u{i}@x.com", "senha": "errada-123"})[0], 401)
        st, _, h = self.c("POST", "/api/conta/entrar", {"usuario": "outro@x.com", "senha": "errada-123"})
        self.assertEqual(st, 429)
        self.assertTrue(h["Retry-After"])


# ── 6. Sessão guardada só como resumo ────────────────────────────────────────
class SessaoComResumo(unittest.TestCase):
    def test_token_nao_fica_no_banco(self):
        h = Hub()
        h.criar_conta("Ana", "ana@x.com", SENHA)
        tk = h.entrar("ana@x.com", SENHA, "192.168.0.2", "Teste/1")["token"]
        bruto = repr(h._db.execute("SELECT * FROM sessao").fetchall())
        self.assertNotIn(tk, bruto)
        self.assertIn(hashlib.sha256(tk.encode()).hexdigest(), bruto)
        self.assertEqual(h.sessao(tk)["usuario"], "ana@x.com")
        self.assertIsNone(h.sessao(hashlib.sha256(tk.encode()).hexdigest()))       # o resumo não serve de token
        h.sair(tk)
        self.assertIsNone(h.sessao(tk))

    def test_migracao_descarta_sessoes_antigas(self):
        with tempfile.TemporaryDirectory() as d:
            arq = str(Path(d) / "velho.db")
            db = sqlite3.connect(arq)
            db.executescript("CREATE TABLE sessao (token TEXT PRIMARY KEY, conta INTEGER NOT NULL, expira REAL NOT NULL);"
                             "INSERT INTO sessao VALUES ('token-velho-em-texto', 1, 9e12);")
            db.commit(); db.close()
            h = Hub(arq)
            cols = {r[1] for r in h._db.execute("PRAGMA table_info(sessao)")}
            self.assertIn("resumo", cols); self.assertNotIn("token", cols)
            self.assertEqual(h._db.execute("SELECT COUNT(*) FROM sessao").fetchone()[0], 0)
            self.assertIsNone(h.sessao("token-velho-em-texto"))
            h.fechar()


# ── 7. LGPD: Meus dados, Apagar e retenção ───────────────────────────────────
class MeusDados(Servidor):
    INSTANCIA = {"login": True, "suporte_email": "suporte@exemplo.com.br"}

    def test_exportar_e_apagar(self):
        adm = self.conta("Ana", "ana@x.com")
        bia = self.conta("Bia", "bia@x.com", "cliente", adm)
        self.c("POST", "/api/central/pedido", {"_formato": "physis-pedido/1", "numero": "PP-BIA", "texto": "orçamento",
                                               "email": "bia@x.com", "telefone": "61 9999"})
        self.c("POST", "/api/central/compra", {"_formato": "physis-compra/1", "numero": "LJ-BIA", "total": 4900,
                                               "pagador": {"nome": "Bia", "email": "bia@x.com", "cpf": "111.222.333-44"},
                                               "itens": [{"nome": "Kit", "preco": 4900}]})
        self.c("POST", "/api/central/pedido", {"_formato": "physis-pedido/1", "numero": "PP-OUTRO", "texto": "x", "email": "outra@x.com"})
        self.c("POST", "/api/suporte", {"assunto": "Ajuda", "mensagem": "m"}, cookie=bia)
        st, j, _ = self.c("GET", "/api/conta/meus-dados", cookie=bia)
        self.assertEqual(st, 200)
        self.assertEqual(j["conta"]["usuario"], "bia@x.com")
        self.assertNotIn("sal", json.dumps(j["conta"]))
        self.assertEqual(sorted(x["numero"] for x in j["central"]), ["LJ-BIA", "PP-BIA", "SP-0001"])
        self.assertTrue(j["sessoes"] and j["acessos"])
        self.assertTrue(any(a["evento"] == "entrou" for a in j["acessos"]))
        # apagar: senha errada não; última direção não
        self.assertEqual(self.c("POST", "/api/conta/apagar", {"senha": "errada"}, cookie=bia)[0], 403)
        self.assertEqual(self.c("POST", "/api/conta/apagar", {"senha": SENHA}, cookie=adm)[0], 409)
        st, r, h = self.c("POST", "/api/conta/apagar", {"senha": SENHA}, cookie=bia)
        self.assertEqual(st, 200, r)
        self.assertIn("Max-Age=0", h["Set-Cookie"])
        self.assertEqual(self.c("GET", "/api/conta/meus-dados", cookie=bia)[0], 401)
        self.assertEqual(self.c("POST", "/api/conta/entrar", {"usuario": "bia@x.com", "senha": SENHA})[0], 401)
        caixa = {i["numero"]: i for i in self.c("GET", "/api/central/caixa", cookie=adm)[1]["itens"]}
        compra = caixa["LJ-BIA"]["dados"]
        self.assertEqual((compra["total"], compra["fatura"], compra["itens"][0]["nome"]), (4900, "0000", "Kit"))   # fiscal fica
        self.assertNotIn("bia@x.com", json.dumps(caixa["LJ-BIA"]))
        self.assertNotIn("111.222", json.dumps(caixa["LJ-BIA"]))
        self.assertNotIn("61 9999", json.dumps(caixa["PP-BIA"]))
        self.assertIn("outra@x.com", json.dumps(caixa["PP-OUTRO"]))        # de outra pessoa: intocado
        self.assertTrue(self.hub.verificar_cadeia()[0])
        ult = self.hub._db.execute("SELECT tipo, conteudo FROM registro WHERE tipo='lgpd' ORDER BY seq DESC LIMIT 1").fetchone()
        self.assertIn("apagados a pedido do titular", ult[1])
        self.assertNotIn("bia@x.com", ult[1])


class Retencao(unittest.TestCase):
    def test_politica(self):
        t = [1_800_000_000.0]
        h = Hub(relogio=lambda: t[0])
        dia = 86400
        h.criar_conta("Ana", "ana@x.com", SENHA)
        h.entrar("ana@x.com", SENHA)
        seg.acesso_registrar(h, "ana@x.com", "1.2.3.4", "entrou")
        h._db.execute("INSERT INTO email_saida(para,assunto,corpo,estado,ref,criado) VALUES('a@x.com','s','c','pendente','r',?)", (t[0],))
        h._db.execute("INSERT INTO email_saida(para,assunto,corpo,estado,ref,criado) VALUES('a@x.com','s','c','enviado','r2',?)", (t[0],))
        h.central_por("pedido", "PP-V", {"texto": "x", "email": "v@x.com"})
        h._db.commit()
        t[0] += 40 * dia                      # 40 dias depois
        n = seg.aplicar_retencao(h, {"PEDIDO": 30})
        self.assertEqual((n["emails_pendentes"], n.get("acessos"), n["pedido"], n["sessoes"]), (1, 0, 1, 1))   # sessão de 30 dias venceu
        self.assertNotIn("v@x.com", h._db.execute("SELECT dados FROM central WHERE numero='PP-V'").fetchone()[0])
        t[0] += 150 * dia                     # 190 dias: passou dos 6 meses do Marco Civil
        n = seg.aplicar_retencao(h, {})
        self.assertEqual((n["acessos"], n["sessoes"]), (1, 0))
        t[0] += 400 * dia
        self.assertEqual(seg.aplicar_retencao(h, {})["emails_enviados"], 1)
        self.assertTrue(h.verificar_cadeia()[0])
        with mock.patch.dict(os.environ, {"PHYSIS_RETENCAO_DIAS_ACESSO": "90", "PHYSIS_RETENCAO_DIAS_EMAIL_PENDENTE": "x"}):
            cfg = seg.retencao_config()
        self.assertEqual((cfg["ACESSO"], cfg["EMAIL_PENDENTE"]), (90, 30))


# ── 8. Erro interno sem rastro ───────────────────────────────────────────────
class ErroSemRastro(Servidor):
    INSTANCIA = {"login": False}

    def test_500_generico(self):
        def explode():
            raise RuntimeError("segredo interno /caminho/do/servidor")
        with mock.patch.object(self.hub, "painel", explode), contextlib.redirect_stderr(io.StringIO()) as err:
            st, j, _ = self.c("GET", "/api/painel")
        self.assertEqual((st, j), (500, {"ok": False, "erro": "erro interno"}))
        self.assertIn("RuntimeError", err.getvalue())             # o rastro fica no console do servidor
        self.assertEqual(self.c("GET", "/api/instancia")[0], 200)


# ════════════════════════════════════════════════════════════════════════════
# Segunda parte: contas por e-mail, consentimento, senha, 2FA, sessão, CSRF, validação, arquivos
# ════════════════════════════════════════════════════════════════════════════
import base64
import re
import time

URL = "https://hub.exemplo.com.br"


def token_do_email(hub, ref_prefixo):
    e = [x for x in hub.emails() if x["ref"].startswith(ref_prefixo)][-1]
    return re.search(r"#t=([A-Za-z0-9_-]+)", e["corpo"]).group(1)


class PoliticaDeSenha(unittest.TestCase):
    def test_regras(self):
        for ruim in ("curta", "123456789012", "senha12345678", "Password1234", "aaaaaaaaaaaaaa", "abcdefghijklm",
                     "qwertyuiop!!", "Flamengo2024!"):
            self.assertIsNotNone(seg.senha_fraca(ruim), ruim)
        self.assertIsNotNone(seg.senha_fraca("mariana12345", "mariana@x.com"))      # quase o próprio usuário
        for boa in ("senha-bem-longa", "minha horta de alfaces", "senha-nova-da-laura"):
            self.assertIsNone(seg.senha_fraca(boa, "laura@x.com"), boa)
        h = Hub()
        self.assertIn("comum", h.criar_conta("Ana", "ana@x.com", "password1234")["erro"])


class Totp(unittest.TestCase):
    def test_vetor_da_rfc_6238_e_reuso(self):
        s = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(seg.totp_codigo(s, 59), "287082")
        self.assertEqual(seg.totp_codigo(s, 1111111109), "081804")
        p = seg.totp_conferir(s, "081804", 1111111109)
        self.assertIsNotNone(p)
        self.assertIsNone(seg.totp_conferir(s, "081804", 1111111109, ultimo=p))      # o mesmo código não entra duas vezes
        self.assertIsNone(seg.totp_conferir(s, "000000", 1111111109))
        self.assertTrue(seg.totp_uri(s, "ana@x.com").startswith("otpauth://totp/"))


class SessaoTempo(unittest.TestCase):
    def test_ociosa_e_vida_maxima(self):
        t = [1_800_000_000.0]
        h = Hub(relogio=lambda: t[0])
        h.criar_conta("Ana", "ana@x.com", SENHA)
        tk = h.entrar("ana@x.com", SENHA)["token"]
        t[0] += 11 * 3600
        self.assertIsNotNone(h.sessao(tk))                 # 11 h parada: ainda vale (padrão 12 h)
        t[0] += 12 * 3600 + 1
        self.assertIsNone(h.sessao(tk))                    # passou de 12 h sem uso: caiu
        with mock.patch.dict(os.environ, {"PHYSIS_SESSAO_OCIOSA_MIN": "0", "PHYSIS_SESSAO_DIAS": "2"}):
            h2 = Hub(relogio=lambda: t[0])
            h2.criar_conta("Ana", "ana@x.com", SENHA)
            tk = h2.entrar("ana@x.com", SENHA)["token"]
            t[0] += 2 * 86400 - 10
            self.assertIsNotNone(h2.sessao(tk))
            t[0] += 20
            self.assertIsNone(h2.sessao(tk))               # vida máxima, mesmo em uso


class FluxosDeConta(Servidor):
    AMBIENTE = {"PHYSIS_URL_PUBLICA": URL, "PHYSIS_LIMITE_ENTRAR": "200/60"}     # muitos fluxos de conta do mesmo IP

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        st, j, h = chamar(cls.PORTA, "POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana@x.com", "senha": SENHA})
        cls.adm = h["Set-Cookie"].split(";")[0]

    def test_esqueci_e_nova_senha(self):
        ck = self.conta("Bia", "bia@x.com", "equipe", self.adm)
        st, j1, _ = self.c("POST", "/api/conta/esqueci", {"usuario": "bia@x.com"})
        st2, j2, _ = self.c("POST", "/api/conta/esqueci", {"usuario": "ninguem@x.com"})
        self.assertEqual((st, st2, j1), (200, 200, j2))             # mesma resposta, exista ou não a conta
        tk = token_do_email(self.hub, "conta-senha-")
        self.assertIn(URL + "/conta/nova-senha#t=", [e for e in self.hub.emails() if e["ref"].startswith("conta-senha-")][-1]["corpo"])
        self.assertNotIn(seg.resumo(tk), repr([e["corpo"] for e in self.hub.emails()]))
        bruto = repr(self.hub._db.execute("SELECT * FROM conta_token").fetchall())
        self.assertNotIn(tk, bruto)                                  # no banco, só o resumo
        self.assertEqual(self.c("POST", "/api/conta/nova-senha", {"token": tk, "senha": "123456789012"})[0], 400)
        self.assertEqual(self.c("POST", "/api/conta/nova-senha", {"token": tk, "senha": "outra frase bem minha"})[0], 200)
        self.assertEqual(self.c("POST", "/api/conta/nova-senha", {"token": tk, "senha": "mais uma frase minha"})[0], 400)   # uso único
        self.assertEqual(self.c("GET", "/api/gestao/estado", cookie=ck)[0], 401)                 # sessões derrubadas
        self.assertEqual(self.c("POST", "/api/conta/entrar", {"usuario": "bia@x.com", "senha": "outra frase bem minha"})[0], 200)
        # vencido (30 min)
        self.c("POST", "/api/conta/esqueci", {"usuario": "bia@x.com"})
        self.hub._db.execute("UPDATE conta_token SET criado=criado-120 WHERE tipo='senha'")
        self.c("POST", "/api/conta/esqueci", {"usuario": "bia@x.com"})
        tk2 = token_do_email(self.hub, "conta-senha-")
        self.hub._db.execute("UPDATE conta_token SET expira=? WHERE resumo=?", (time.time() - 1, seg.resumo(tk2)))
        self.assertEqual(self.c("POST", "/api/conta/nova-senha", {"token": tk2, "senha": "frase nova e longa"})[0], 400)
        # a fila da Gestão não mostra e-mails com link de conta
        fila = self.c("GET", "/api/central/emails", cookie=self.adm)[1]
        self.assertFalse(any(e["ref"].startswith("conta-") for e in fila["emails"]))
        self.assertGreater(fila["conta_ocultos"], 0)

    def test_convite(self):
        eq = self.conta("Caio", "caio@x.com", "equipe", self.adm)
        self.assertEqual(self.c("POST", "/api/convites", {"email": "dani@x.com"}, cookie=eq)[0], 403)
        self.assertEqual(self.c("POST", "/api/convites", {"email": "dani@x.com", "extra": 1}, cookie=self.adm)[0], 400)   # campo desconhecido
        st, j, _ = self.c("POST", "/api/convites", {"email": "dani@x.com", "papel": "equipe", "pessoa": "dani"}, cookie=self.adm)
        self.assertEqual((st, j["papel"]), (200, "operador"))
        self.assertNotIn("ref", j)
        tk = token_do_email(self.hub, "conta-convite-")
        st, v, _ = self.c("POST", "/api/conta/convite/ver", {"token": tk})
        self.assertEqual((st, v["email"]), (200, "dani@x.com"))
        with mock.patch.dict(os.environ, {"PHYSIS_TERMOS_VERSAO": "T-1"}):
            st, r, _ = self.c("POST", "/api/conta/convite/aceitar", {"token": tk, "nome": "Dani", "senha": "dani tem uma frase"})
            self.assertEqual((st, r.get("consentimento")), (400, True))
            st, r, h = self.c("POST", "/api/conta/convite/aceitar", {"token": tk, "nome": "Dani", "senha": "dani tem uma frase",
                                                                       "consentimento": {"versao": "T-1", "aceito": True}})
            self.assertEqual(st, 200, r)
            ck = h["Set-Cookie"].split(";")[0]
            inst = self.c("GET", "/api/instancia", cookie=ck)[1]
            self.assertFalse(inst["consentimento_pendente"])
            self.assertTrue(inst["email_confirmado"])
        self.assertEqual(self.c("GET", "/api/central/caixa", cookie=ck)[0], 200)        # equipe já confirmada pelo convite
        self.assertEqual(self.c("POST", "/api/conta/convite/aceitar", {"token": tk, "nome": "X", "senha": "outra frase longa"})[0], 400)
        # revogar
        self.c("POST", "/api/convites", {"email": "edu@x.com"}, cookie=self.adm)
        tk3 = token_do_email(self.hub, "conta-convite-")
        cid = [c for c in self.c("GET", "/api/convites", cookie=self.adm)[1]["convites"] if c["email"] == "edu@x.com"][0]["id"]
        self.assertEqual(self.c("POST", f"/api/convites/{cid}/revogar", {}, cookie=self.adm)[0], 200)
        self.assertEqual(self.c("POST", "/api/conta/convite/ver", {"token": tk3})[0], 404)
        # convite para a direção pede a senha de novo (reautenticação)
        self.hub._db.execute("UPDATE sessao SET reauth=0")
        st, j, _ = self.c("POST", "/api/convites", {"email": "fer@x.com", "papel": "direção"}, cookie=self.adm)
        self.assertEqual((st, j.get("reautenticar")), (403, True))
        self.assertEqual(self.c("POST", "/api/conta/reautenticar", {"senha": SENHA}, cookie=self.adm)[0], 200)
        self.assertEqual(self.c("POST", "/api/convites", {"email": "fer@x.com", "papel": "direção"}, cookie=self.adm)[0], 200)

    def test_confirmacao_de_email(self):
        with mock.patch.dict(os.environ, {"PHYSIS_CONFIRMAR_EMAIL": "1"}):
            ck = self.conta("Gil", "gil@x.com", "equipe", self.adm)
            st, j, _ = self.c("GET", "/api/central/caixa", cookie=ck)
            self.assertEqual((st, j.get("confirmar_email")), (403, True))            # sem confirmar, vale como cliente
            self.assertFalse(self.c("GET", "/api/instancia", cookie=ck)[1]["email_confirmado"])
            tk = token_do_email(self.hub, "conta-confirmar-")
            self.assertEqual(self.c("POST", "/api/conta/confirmar", {"token": tk})[0], 200)
            self.assertEqual(self.c("GET", "/api/central/caixa", cookie=ck)[0], 200)
            self.assertEqual(self.c("POST", "/api/conta/confirmar", {"token": tk})[0], 400)

    def test_consentimento(self):
        ck = self.conta("Hel", "hel@x.com", "equipe", self.adm)
        with mock.patch.dict(os.environ, {"PHYSIS_TERMOS_VERSAO": "T-2"}):
            self.assertTrue(self.c("GET", "/api/instancia", cookie=ck)[1]["consentimento_pendente"])
            with mock.patch.dict(os.environ, {"PHYSIS_CONSENTIMENTO_ESTRITO": "1"}):
                self.assertEqual(self.c("GET", "/api/central/caixa", cookie=ck)[1].get("consentimento"), True)
                self.assertEqual(self.c("POST", "/api/conta/consentimento", {"versao": "T-1", "aceito": True}, cookie=ck)[0], 409)
                self.assertEqual(self.c("POST", "/api/conta/consentimento", {"versao": "T-2", "aceito": True}, cookie=ck)[0], 200)
                self.assertEqual(self.c("GET", "/api/central/caixa", cookie=ck)[0], 200)
                self.assertEqual(self.c("POST", "/api/conta/consentimento", {"aceito": False}, cookie=ck)[0], 200)     # retirar
                self.assertEqual(self.c("GET", "/api/central/caixa", cookie=ck)[0], 403)
            hist = self.c("GET", "/api/conta/meus-dados", cookie=ck)[1]["consentimentos"]
            self.assertEqual([(x["versao"], x["aceito"]) for x in hist], [("T-2", True), ("T-2", False)])

    def test_termos_lidos_do_juridico(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "physis-juridico.js"
            arq.write_bytes(b'window.JUR = {\n "versao": "14/11/2026",\n "termos": "..."};\n')
            self.assertEqual(seg.termos_versao(str(arq)), "14/11/2026")


class DoisFatoresPelaRede(Servidor):
    def test_ligar_entrar_recuperar_desligar(self):
        adm = self.conta("Ana", "ana@x.com")
        st, j, _ = self.c("POST", "/api/conta/2fa/iniciar", {}, cookie=adm)
        self.assertEqual(st, 200)
        segredo = j["segredo"]
        self.assertEqual(self.c("POST", "/api/conta/2fa/ativar", {"codigo": "000000"}, cookie=adm)[0], 400)
        st, j, _ = self.c("POST", "/api/conta/2fa/ativar", {"codigo": seg.totp_codigo(segredo, time.time())}, cookie=adm)
        self.assertEqual((st, len(j["recuperacao"])), (200, 10))
        rec = j["recuperacao"]
        self.assertTrue(self.c("GET", "/api/instancia", cookie=adm)[1]["dois_fatores"])
        st, j, _ = self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA})
        self.assertEqual((st, j.get("precisa_2fa")), (401, True))
        st, j, _ = self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": "errada-mas-longa", "codigo": "123456"})
        self.assertNotIn("precisa_2fa", j)                                  # senha errada não revela o 2FA
        st, _, h = self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA, "codigo": rec[0]})
        self.assertEqual(st, 200)
        self.assertEqual(self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA, "codigo": rec[0]})[0], 401)  # gasto
        ck = h["Set-Cookie"].split(";")[0]
        st, _, _ = self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA,
                                                         "codigo": seg.totp_codigo(segredo, time.time() + 30)})
        self.assertEqual(st, 200)
        self.assertEqual(self.c("POST", "/api/conta/2fa/desativar", {"codigo": rec[1]}, cookie=ck)[0], 200)
        self.assertEqual(self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA})[0], 200)


class Reautenticacao(Servidor):
    def test_acao_sensivel_pede_senha(self):
        adm = self.conta("Ana", "ana@x.com")
        self.c("POST", "/api/central/compra", {"_formato": "physis-compra/1", "numero": "LJ-R1", "total": 1})
        self.hub._db.execute("UPDATE sessao SET reauth=0")             # o login foi há muito tempo
        st, j, _ = self.c("POST", "/api/central/compra/LJ-R1/aprovar", {}, cookie=adm)
        self.assertEqual((st, j.get("reautenticar")), (403, True))
        self.assertEqual(self.c("POST", "/api/conta/reautenticar", {"senha": "errada-mas-longa"}, cookie=adm)[0], 403)
        self.assertEqual(self.c("POST", "/api/conta/reautenticar", {"senha": SENHA}, cookie=adm)[0], 200)
        self.assertEqual(self.c("POST", "/api/central/compra/LJ-R1/aprovar", {}, cookie=adm)[0], 200)
        self.c("POST", "/api/contas", {"nome": "Bia", "usuario": "bia@x.com", "senha": SENHA, "papel": "equipe"}, cookie=adm)
        self.hub._db.execute("UPDATE sessao SET reauth=0")
        self.assertEqual(self.c("POST", "/api/contas/bia@x.com", {"papel": "direção"}, cookie=adm)[0], 403)


class Csrf(Servidor):
    def test_origem_e_token(self):
        st, j, h = self.c("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana@x.com", "senha": SENHA})
        ck, tk = h["Set-Cookie"].split(";")[0], j["csrf"]
        self.assertEqual(self.c("GET", "/api/instancia", cookie=ck)[1]["csrf"], tk)
        mal = {"Origin": "https://site-mal.example"}
        self.assertEqual(self.c("POST", "/api/loja/item/x", {"st": "func"}, cab=mal, cookie=ck)[1].get("csrf"), True)
        self.assertEqual(self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA}, cab=mal)[0], 403)
        self.assertEqual(self.c("POST", "/api/loja/item/x", {"st": "func"}, cab={"Origin": "null"}, cookie=ck)[0], 403)
        self.assertEqual(self.c("POST", "/api/loja/item/x", {"st": "func"}, cab={"Referer": "https://site-mal.example/a"}, cookie=ck)[0], 403)
        # formulário público sem sessão, vindo de outro site: não há o que forjar
        self.assertEqual(self.c("POST", "/api/central/pedido", {"_formato": "physis-pedido/1", "numero": "PP-C", "texto": "x"}, cab=mal)[0], 200)
        mesmo = {"Origin": f"http://127.0.0.1:{self.PORTA}"}
        self.assertEqual(self.c("POST", "/api/loja/item/x", {"st": "func"}, cab=mesmo, cookie=ck)[0], 200)
        self.assertEqual(self.c("POST", "/api/loja/item/x", {"st": "func"}, cab={"X-Physis-CSRF": "errado"}, cookie=ck)[0], 403)
        self.assertEqual(self.c("POST", "/api/loja/item/x", {"st": "func"}, cab={"X-Physis-CSRF": tk}, cookie=ck)[0], 200)
        with mock.patch.dict(os.environ, {"PHYSIS_CSRF_ESTRITO": "1"}):
            self.assertEqual(self.c("POST", "/api/loja/item/x", {"st": "func"}, cookie=ck)[0], 403)
            self.assertEqual(self.c("POST", "/api/loja/item/x", {"st": "func"}, cab={"X-Physis-CSRF": tk}, cookie=ck)[0], 200)
            self.assertEqual(self.c("PUT", "/api/gestao/arquivo/arq-1", b"%PDF-1.4", cookie=ck)[0], 403)
            self.assertEqual(self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": SENHA}, cookie=ck)[0], 200)


class ValidacaoEArquivos(Servidor):
    INSTANCIA = {"login": False}

    def test_json(self):
        for ruim in ('{"a": NaN}', '{"a": Infinity}', "[" * 50 + "]" * 50, '{"a": 1' + "0" * 40 + "}"):
            with self.assertRaises(ValueError):
                seg.carregar_json(ruim)
        self.assertEqual(seg.validar({"a": 1}, {"a": (str, 5, True)}), "campo a com tipo errado")
        self.assertEqual(seg.validar({"a": True}, {"a": (int, 5, True)}), "campo a com tipo errado")
        self.assertIsNone(seg.validar({"a": "x", "b": 1}, {"a": (str, 5, True)}, estrito=False))
        self.assertEqual(self.c("POST", "/api/central/pedido", '{"_formato": "physis-pedido/1", "numero": "P", "v": NaN}')[0], 400)
        self.assertEqual(self.c("POST", "/api/conta/entrar", {"usuario": ["lista"], "senha": SENHA})[0], 400)

    def test_anexos(self):
        self.hub.central_por("pedido", "PP-F", {"texto": "x"})
        enviar = lambda nome, dados: self.c("POST", f"/api/central/arquivo?pedido=PP-F&nome={nome}", dados)[0]
        self.assertEqual(enviar("planilha.xlsx", b"MZ\x90\x00"), 400)          # executável com nome de planilha
        self.assertEqual(enviar("conta.pdf", b"<html>oi</html>"), 400)        # conteúdo não é PDF
        self.assertEqual(enviar("dados.csv", b"a;b\n1;2\n"), 200)
        self.assertEqual(enviar("conta.pdf", b"%PDF-1.7 ok"), 200)
        h = self.hub
        self.assertFalse(h.gestao_arquivo_por("arq-x1", "a.pdf", "application/pdf", b"\x7fELF...", "ana")["ok"])
        self.assertTrue(h.gestao_arquivo_por("arq-x2", "pagina.html", "text/html", b"<script>alert(1)</script>", "ana")["ok"])
        self.assertEqual(h.gestao_arquivo("arq-x2")[1], "application/octet-stream")      # nunca volta como HTML

    def test_security_txt_e_paginas(self):
        with mock.patch.dict(os.environ, {"PHYSIS_SEGURANCA_CONTATO": "seguranca@exemplo.com.br"}):
            st, corpo, h = self.c("GET", "/.well-known/security.txt")
        self.assertEqual(st, 200)
        self.assertIn(b"Contact: mailto:seguranca@exemplo.com.br", corpo)
        self.assertIn(b"Expires: ", corpo)
        for rota in ("/conta/esqueci", "/conta/nova-senha", "/conta/confirmar", "/conta/convite"):
            st, corpo, _ = self.c("GET", rota)
            self.assertEqual(st, 200)
            self.assertIn(b"/api/conta/", corpo)


class EventosNaCadeia(Servidor):
    def test_eventos_sem_email(self):
        self.conta("Ana", "ana@x.com")
        self.c("POST", "/api/conta/entrar", {"usuario": "ana@x.com", "senha": "errada-mas-longa"})
        ev = [json.loads(c) for t, c in self.hub._db.execute("SELECT tipo, conteudo FROM registro WHERE tipo='seguranca'")]
        self.assertTrue({"entrou", "senha errada"} <= {e["o_que"] for e in ev})
        self.assertFalse(any("ana@x.com" in json.dumps(e) for e in ev))
        self.assertTrue(all(e["ref"] == seg.pseudonimo(self.hub, "ana@x.com") for e in ev if e["o_que"] in ("entrou", "senha errada")))
        self.assertTrue(self.hub.verificar_cadeia()[0])


if __name__ == "__main__":
    unittest.main()
