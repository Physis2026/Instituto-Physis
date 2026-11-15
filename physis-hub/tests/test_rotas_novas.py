"""Rotas ligadas no servidor.py em 15/11/2026: documento para comentários e PDF/A, painel municipal, evidências,
parceiros, download do app, pegada do servidor, demonstrações públicas e textos jurídicos.

Protege, pela rede (servidor de verdade numa porta livre):
1. Código de cada rota e o acesso: sem sessão = 401, papel baixo = 403, o papel certo = 200; páginas públicas abertas.
2. CSRF: com sessão, token errado = 403; sem token, 403 no modo estrito (PHYSIS_CSRF_ESTRITO=1), como as outras rotas.
3. Todo corpo JSON passa pelo seg.ESQUEMAS (estrito): campo desconhecido ou tipo errado = 400.
4. Limite por IP nas rotas públicas (429), cabeçalhos de segurança nas demos e o 'unsafe-eval' só no Planejador.
5. APK: SHA-256 calculado do arquivo servido; nada fora da lista sai da pasta de download.
"""
import base64
import contextlib
import hashlib
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from physis_hub import documentos as documentos_mod
from physis_hub import evidencias as evidencias_mod
from physis_hub import seguranca as seg
from physis_hub import servidor
from physis_hub.hub import Hub

RAIZ = Path(__file__).resolve().parent.parent
SENHAS = {"dir": "frase-longa-da-direcao-1", "eq": "frase-longa-da-equipe-1", "cli": "frase-longa-do-cliente-1"}


def cpf_valido(base9: str) -> str:
    d = [int(x) for x in base9]
    for n in (10, 11):
        s = sum(v * p for v, p in zip(d, range(n, 1, -1)))
        d.append(0 if s % 11 < 2 else 11 - s % 11)
    return "".join(map(str, d))


class Base(unittest.TestCase):
    instancia = {"login": False}

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub(org="rotas-novas")
        cls.srv = servidor.iniciar(cls.hub, 0, endereco="127.0.0.1", instancia=cls.instancia)
        cls.porta = cls.srv.server_address[1]
        h = cls.hub
        h.criar_conta("Direção", "dir@physis.example", SENHAS["dir"])
        adm = h.sessao(h.entrar("dir@physis.example", SENHAS["dir"])["token"])
        h.criar_conta("Equipe", "eq@physis.example", SENHAS["eq"], adm["id"], papel="operador")
        h.criar_conta("Cliente", "cli@fazenda.example", SENHAS["cli"], adm["id"], papel="cliente")
        cls.s = {}
        for k, u in (("dir", "dir@physis.example"), ("eq", "eq@physis.example"), ("cli", "cli@fazenda.example")):
            tk = h.entrar(u, SENHAS[k])["token"]
            cls.s[k] = ("physis_sessao=" + tk, seg.csrf_de(h, tk))

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def c(self, metodo, rota, corpo=None, quem=None, csrf=True, extra=None, bruto=None, tipo="application/json"):
        """(status, json ou bytes, cabeçalhos). quem = "dir" | "eq" | "cli" | None; csrf: True (certo), False (sem) ou texto."""
        h = {"Content-Type": tipo}
        if quem:
            ck, tk = self.s[quem]
            h["Cookie"] = ck
            if csrf is True:
                h["X-Physis-CSRF"] = tk
            elif csrf:
                h["X-Physis-CSRF"] = csrf
        h.update(extra or {})
        dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", data=dados, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                b = r.read()
                return r.status, self._dec(b, r.headers), r.headers
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, self._dec(b, e.headers), e.headers

    @staticmethod
    def _dec(b, cab):
        if "json" in (cab.get("Content-Type") or ""):
            return json.loads(b or b"{}")
        return b

    @contextlib.contextmanager
    def estrito(self):
        """PHYSIS_CSRF_ESTRITO=1: com sessão, sem o cabeçalho X-Physis-CSRF é recusado."""
        antes = os.environ.get("PHYSIS_CSRF_ESTRITO")
        os.environ["PHYSIS_CSRF_ESTRITO"] = "1"
        try:
            yield
        finally:
            if antes is None:
                os.environ.pop("PHYSIS_CSRF_ESTRITO", None)
            else:
                os.environ["PHYSIS_CSRF_ESTRITO"] = antes

    def csrf_recusado(self, rota, corpo, quem="eq"):
        st, j, _ = self.c("POST", rota, corpo, quem, csrf="token-errado")
        self.assertEqual((st, j.get("csrf")), (403, True), rota)
        with self.estrito():
            st, j, _ = self.c("POST", rota, corpo, quem, csrf=False)
        self.assertEqual((st, j.get("csrf")), (403, True), rota)

    def esquema_recusado(self, rota, corpo, quem="eq"):
        st, j, _ = self.c("POST", rota, dict(corpo, campo_estranho=1), quem)
        self.assertEqual(st, 400, rota)
        self.assertIn("campo desconhecido", j["erro"])


class Documento(Base):
    def publicar(self):
        st, j, _ = self.c("POST", "/api/documentos", {"titulo": "Proposta", "html": "<p>Um parágrafo.</p>"}, "eq")
        self.assertEqual(st, 200, j)
        return j["id"]

    def test_paginas(self):
        st, b, h = self.c("GET", "/documento/fontes.css")
        self.assertEqual((st, h["Content-Type"]), (200, "text/css; charset=utf-8"))
        for rota in ("/documento", "/documento/", "/documento/" + "a" * 24):
            st, b, h = self.c("GET", rota)
            self.assertEqual(st, 200, rota)
            self.assertIn(b"<h1", b)
            self.assertIn("Content-Security-Policy", h)
        self.assertEqual(self.c("GET", "/documento/curto")[0], 404)
        self.assertEqual(self.c("GET", "/documento/../physis_hub/servidor.py")[0], 404)

    def test_api_acesso(self):
        self.assertEqual(self.c("GET", "/api/documentos")[0], 401)
        self.assertEqual(self.c("GET", "/api/documentos", quem="cli")[0], 403)
        self.assertEqual(self.c("GET", "/api/documentos", quem="eq")[0], 200)
        self.assertEqual(self.c("POST", "/api/documentos", {"titulo": "x", "html": "<p>x</p>"})[0], 401)
        self.assertEqual(self.c("POST", "/api/documentos", {"titulo": "x", "html": "<p>x</p>"}, "cli")[0], 403)
        ident = self.publicar()
        st, j, _ = self.c("GET", "/api/documentos/" + ident, quem="eq")
        self.assertEqual((st, j["documento"]["titulo"] if "documento" in j else j.get("titulo")), (200, "Proposta"))

    def test_csrf_e_esquema(self):
        corpo = {"titulo": "x", "html": "<p>x</p>"}
        self.csrf_recusado("/api/documentos", corpo)
        self.esquema_recusado("/api/documentos", corpo)
        self.assertEqual(self.c("POST", "/api/documentos", {"titulo": 5, "html": "<p>x</p>"}, "eq")[0], 400)
        ident = self.publicar()
        self.esquema_recusado(f"/api/documentos/{ident}/comentarios", {"paragrafo": "geral", "texto": "oi"})
        self.esquema_recusado(f"/api/documentos/{ident}/convites", {"nome": "Revisora", "dias": 2})
        self.esquema_recusado(f"/api/documentos/{ident}/arquivar", {"arquivado": True})
        self.csrf_recusado(f"/api/documentos/{ident}/comentarios", {"paragrafo": "geral", "texto": "oi"})

    def test_convite_sem_sessao(self):
        ident = self.publicar()
        st, j, _ = self.c("POST", f"/api/documentos/{ident}/convites", {"nome": "Revisora", "dias": 2, "pode_comentar": True}, "eq")
        self.assertEqual(st, 200, j)
        tk = j["token"]
        st, j, _ = self.c("POST", f"/api/documentos/{ident}/comentarios", {"paragrafo": "geral", "texto": "Revisado."},
                          extra={"X-Physis-Convite": tk})
        self.assertEqual(st, 200, j)
        self.assertEqual(self.c("GET", f"/api/documentos/{ident}", extra={"X-Physis-Convite": tk})[0], 200)
        self.assertEqual(self.c("GET", f"/api/documentos/{ident}", extra={"X-Physis-Convite": "x" * 30})[0], 403)
        # o revisor externo não publica nem arquiva
        self.assertEqual(self.c("POST", f"/api/documentos/{ident}/arquivar", {"arquivado": True}, extra={"X-Physis-Convite": tk})[0], 403)

    def test_pdfa(self):
        self.assertEqual(self.c("POST", "/api/documentos/pdfa", bruto=b"PK\x03\x04x", tipo=documentos_mod.MIME_ODT)[0], 401)
        st, j, _ = self.c("POST", "/api/documentos/pdfa", quem="cli", csrf="errado", bruto=b"PK\x03\x04x", tipo=documentos_mod.MIME_ODT)
        self.assertEqual(st, 403)
        antes = (documentos_mod.soffice_programa, os.environ.pop("PHYSIS_DOC_URL", None))
        try:
            documentos_mod.soffice_programa = lambda programa=None: None        # sem LibreOffice nem serviço: 501 com orientação
            st, j, _ = self.c("POST", "/api/documentos/pdfa", quem="cli", bruto=b"PK\x03\x04x", tipo=documentos_mod.MIME_ODT)
            self.assertEqual(st, 501)
            self.assertIn("LibreOffice", j["erro"])
            documentos_mod.soffice_programa = lambda programa=None: "soffice-de-teste"
            st, j, _ = self.c("POST", "/api/documentos/pdfa", quem="cli", bruto=b"nao e odt", tipo=documentos_mod.MIME_ODT)
            self.assertEqual(st, 400)
        finally:
            documentos_mod.soffice_programa = antes[0]
            if antes[1] is not None:
                os.environ["PHYSIS_DOC_URL"] = antes[1]


class Municipio(Base):
    CFG = {"ibge": "3303906", "uf": "RJ", "municipio": "Petrópolis", "limiares": {}}

    def test_paginas_e_publico(self):
        st, b, _ = self.c("GET", "/municipio")
        self.assertEqual(st, 200)
        self.assertIn(b"<h1", b)
        self.assertEqual(self.c("GET", "/api/municipio/publico")[0], 200)
        st, b, h = self.c("GET", "/api/municipio/exportar?tipo=chuva")
        self.assertEqual((st, h["Content-Type"]), (200, "text/csv; charset=utf-8"))
        self.assertEqual(self.c("GET", "/api/municipio/exportar?tipo=senhas")[0], 400)

    def test_operador(self):
        self.assertEqual(self.c("GET", "/api/municipio")[0], 401)
        self.assertEqual(self.c("GET", "/api/municipio", quem="cli")[0], 403)
        self.assertEqual(self.c("GET", "/api/municipio", quem="eq")[0], 200)
        self.assertEqual(self.c("POST", "/api/municipio/config", self.CFG)[0], 401)
        self.assertEqual(self.c("POST", "/api/municipio/config", self.CFG, "cli")[0], 403)
        self.assertEqual(self.c("POST", "/api/municipio/atualizar", {}, "cli")[0], 403)
        st, j, _ = self.c("POST", "/api/municipio/config", self.CFG, "eq")
        self.assertEqual(st, 200, j)
        self.csrf_recusado("/api/municipio/config", self.CFG)
        self.esquema_recusado("/api/municipio/config", self.CFG)
        self.assertEqual(self.c("POST", "/api/municipio/config", dict(self.CFG, ibge=3303906), "eq")[0], 400)   # tipo errado
        self.esquema_recusado("/api/municipio/bairro", {"id": "centro", "risco": "R2"})
        self.assertEqual(self.c("POST", "/api/municipio/bairro", {"id": "nao-existe", "risco": "R2"}, "eq")[0], 400)

    def test_importar(self):
        geo = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"nome": "Centro", "risco": "R3"},
                                                          "geometry": {"type": "Point", "coordinates": [-43.18, -22.51]}}]}
        corpo = json.dumps(geo).encode()
        self.assertEqual(self.c("POST", "/api/municipio/bairros/importar", bruto=corpo)[0], 401)
        self.assertEqual(self.c("POST", "/api/municipio/bairros/importar", quem="cli", bruto=corpo)[0], 403)
        self.assertEqual(self.c("POST", "/api/municipio/bairros/importar", quem="eq", csrf="x", bruto=corpo)[0], 403)
        st, j, _ = self.c("POST", "/api/municipio/bairros/importar", quem="eq", bruto=corpo)
        self.assertEqual((st, j["importados"]), (200, 1), j)
        self.assertEqual(self.c("POST", "/api/municipio/bairros/importar", quem="eq", bruto=b"{nada")[0], 400)


class Evidencias(Base):
    def anexo(self):
        cert = evidencias_mod.carregar_certs()[0]
        crit = cert["grupos"][0]["criterios"][0]["id"]
        return {"cert": cert["id"], "criterio": crit, "nome": "Laudo de água", "data": "2026-11-15"}

    def test_dados(self):
        self.assertEqual(self.c("GET", "/api/evidencias/dados")[0], 401)
        st, j, _ = self.c("GET", "/api/evidencias/dados", quem="cli")
        self.assertEqual((st, j["dados"]["arquivos"]), (200, []))            # nomes de arquivos da Gestão: só equipe
        self.assertEqual(self.c("GET", "/api/evidencias/dados", quem="eq")[0], 200)

    def test_anexar_e_remover(self):
        a = self.anexo()
        self.assertEqual(self.c("POST", "/api/evidencias/anexo", a)[0], 401)
        st, j, _ = self.c("POST", "/api/evidencias/anexo", a, "cli")
        self.assertEqual(st, 200, j)
        self.csrf_recusado("/api/evidencias/anexo", a, "cli")
        self.esquema_recusado("/api/evidencias/anexo", a, "cli")
        self.esquema_recusado("/api/evidencias/anexo/remover", {"id": j["id"]}, "cli")
        self.assertEqual(self.c("POST", "/api/evidencias/anexo/remover", {"id": "1"}, "cli")[0], 400)      # tipo errado
        self.assertEqual(self.c("POST", "/api/evidencias/anexo/remover", {"id": j["id"]}, "cli")[:2], (200, {"ok": True}))


class Parceiros(Base):
    def cadastro(self, base9="529982247", **extra):
        return dict({"tipo": "pf", "documento": cpf_valido(base9), "nome": "Ana Instaladora", "conselho": "CREA", "registro": "123456",
                     "registro_uf": "RJ", "email": "ana@exemplo.com", "telefone": "21999998888", "especialidades": ["hidraulica"],
                     "regioes": [{"uf": "RJ"}], "descricao": "Instalações hidráulicas.", "consentimento": True}, **extra)

    def test_vitrine_publica_e_interno(self):
        st, j, _ = self.c("GET", "/api/parceiros?servico=solar&uf=RJ")
        self.assertEqual((st, j["ok"]), (200, True))
        self.assertEqual(self.c("GET", "/api/parceiros/interno")[0], 401)
        self.assertEqual(self.c("GET", "/api/parceiros/interno", quem="cli")[0], 403)
        self.assertEqual(self.c("GET", "/api/parceiros/interno", quem="eq")[0], 200)
        self.assertEqual(self.c("GET", "/api/parceiros/interno?completo=1", quem="dir")[0], 200)     # senha recente (acabou de entrar)

    def test_cadastro_curadoria(self):
        st, j, _ = self.c("POST", "/api/parceiros/cadastro", self.cadastro(consentimento=False))
        self.assertEqual(st, 400)                                                  # LGPD: sem consentimento, nada é gravado
        st, j, _ = self.c("POST", "/api/parceiros/cadastro", self.cadastro())
        self.assertEqual(st, 200, j)
        pid = j["id"]
        self.esquema_recusado("/api/parceiros/cadastro", self.cadastro("111444777"), quem=None)
        self.assertEqual(self.c("POST", f"/api/parceiros/{pid}/conferir", {})[0], 401)
        self.assertEqual(self.c("POST", f"/api/parceiros/{pid}/conferir", {}, "cli")[0], 403)
        self.assertEqual(self.c("POST", f"/api/parceiros/{pid}/conferir", {}, "eq")[:2], (200, {"ok": True}))
        self.csrf_recusado(f"/api/parceiros/{pid}/conferir", {})
        self.assertEqual(self.c("POST", f"/api/parceiros/{pid}/curadoria", {"status": "aprovado"}, "eq")[0], 403)   # só a direção
        st, j, _ = self.c("POST", f"/api/parceiros/{pid}/curadoria", {"status": "aprovado"}, "dir")
        self.assertEqual(st, 400)                                                  # faltam documentos obrigatórios
        self.esquema_recusado(f"/api/parceiros/{pid}/curadoria", {"status": "suspenso", "motivo": "x"}, "dir")
        st, j, _ = self.c("POST", f"/api/parceiros/{pid}/documento", {"tipo": "art_modelo"}, "eq")
        self.assertEqual(st, 200, j)
        self.esquema_recusado(f"/api/parceiros/{pid}/documento", {"tipo": "art_modelo"})
        self.assertEqual(self.c("POST", f"/api/parceiros/{pid}/documento/remover", {"id": j["id"]}, "eq")[:2], (200, {"ok": True}))
        self.esquema_recusado(f"/api/parceiros/{pid}/editar", {"descricao": "nova"})
        self.assertEqual(self.c("POST", f"/api/parceiros/{pid}/avaliacao", {"nota": 5, "pedido": "PQ-1"})[0], 401)
        self.esquema_recusado(f"/api/parceiros/{pid}/avaliacao", {"nota": 5, "pedido": "PQ-1"}, "cli")
        self.assertEqual(self.c("POST", f"/api/parceiros/{pid}/apagar", {}, "eq")[0], 403)
        self.assertEqual(self.c("POST", f"/api/parceiros/{pid}/apagar", {}, "dir")[:2], (200, {"ok": True}))
        self.assertEqual(self.c("POST", "/api/parceiros/1/qualquer", {}, "dir")[0], 404)

    def test_orcamento(self):
        corpo = {"parceiro": 999, "servico": "solar", "municipio": "Petrópolis", "uf": "RJ", "nome": "Bia", "email": "bia@exemplo.com",
                 "descricao": "Quero orçamento de energia solar.", "consentimento": True}
        st, j, _ = self.c("POST", "/api/parceiros/orcamento", corpo)
        self.assertEqual(st, 400)                          # profissional fora da vitrine
        self.esquema_recusado("/api/parceiros/orcamento", corpo, quem=None)
        self.assertEqual(self.c("POST", "/api/parceiros/orcamento", dict(corpo, parceiro=[1]))[0], 400)


class LimitePublico(Base):
    @classmethod
    def setUpClass(cls):
        cls.antes = os.environ.get("PHYSIS_LIMITE_PUBLICO")
        os.environ["PHYSIS_LIMITE_PUBLICO"] = "2/600"
        try:
            super().setUpClass()
        finally:
            if cls.antes is None:
                os.environ.pop("PHYSIS_LIMITE_PUBLICO", None)
            else:
                os.environ["PHYSIS_LIMITE_PUBLICO"] = cls.antes

    def test_cadastro_e_orcamento_limitados(self):
        codigos = [self.c("POST", "/api/parceiros/cadastro", {"consentimento": False})[0] for _ in range(3)]
        self.assertEqual(codigos, [400, 400, 429])
        st, j, h = self.c("POST", "/api/parceiros/orcamento", {"parceiro": 1})
        self.assertEqual(st, 429)
        self.assertTrue(h.get("Retry-After"))


class App(Base):
    def test_pagina_e_apk(self):
        st, b, h = self.c("GET", "/app/baixar")
        self.assertEqual((st, h["Content-Type"]), (200, "text/html; charset=utf-8"))
        self.assertIn("Content-Security-Policy", h)
        with tempfile.TemporaryDirectory() as d:
            antes = os.environ.get("PHYSIS_APP_DOWNLOAD")
            os.environ["PHYSIS_APP_DOWNLOAD"] = d
            try:
                self.assertEqual(self.c("GET", "/app/android.apk")[0], 404)          # ainda não publicado
                self.assertEqual(self.c("GET", "/app/baixar")[0], 404)
                apk = b"PK\x03\x04" + os.urandom(3000)
                (Path(d) / "android.apk").write_bytes(apk)
                (Path(d) / "physis-release.jks").write_bytes(b"chave")               # nunca sai, mesmo se alguém deixar lá
                st, b, h = self.c("GET", "/app/android.apk")
                self.assertEqual((st, b, h["Content-Type"]), (200, apk, servidor.APK_MIME))
                self.assertEqual(h["Digest"], "sha-256=" + base64.b64encode(hashlib.sha256(apk).digest()).decode())
                self.assertIn("attachment", h["Content-Disposition"])
                st, b, _ = self.c("GET", "/app/android.apk.sha256")
                self.assertEqual((st, b.decode()), (200, hashlib.sha256(apk).hexdigest() + "  android.apk\n"))
                for rota in ("/app/physis-release.jks", "/app/../app-download/physis-release.jks", "/app/baixar/../physis-release.jks"):
                    self.assertEqual(self.c("GET", rota)[0], 404, rota)
            finally:
                if antes is None:
                    os.environ.pop("PHYSIS_APP_DOWNLOAD", None)
                else:
                    os.environ["PHYSIS_APP_DOWNLOAD"] = antes


class Pegada(Base):
    def test_acesso_e_detalhe(self):
        self.assertEqual(self.c("GET", "/api/servidor/pegada")[0], 401)
        st, j, _ = self.c("GET", "/api/servidor/pegada", quem="cli")
        self.assertEqual((st, j["ok"]), (200, True))
        self.assertNotIn("clientes", j)                           # cliente: só os totais
        self.assertNotIn("fonte", j["equipamentos"][0])
        st, j, _ = self.c("GET", "/api/servidor/pegada", quem="eq")
        self.assertEqual(st, 200)
        self.assertIn("clientes", j)
        self.assertIn("fonte", j["equipamentos"][0])


class PegadaDesligada(Base):
    @classmethod
    def setUpClass(cls):
        antes = os.environ.get("PHYSIS_PEGADA")
        os.environ["PHYSIS_PEGADA"] = "0"
        try:
            super().setUpClass()
        finally:
            if antes is None:
                os.environ.pop("PHYSIS_PEGADA", None)
            else:
                os.environ["PHYSIS_PEGADA"] = antes

    def test_desligada(self):
        st, j, _ = self.c("GET", "/api/servidor/pegada", quem="cli")
        self.assertEqual((st, j["ok"], j.get("desligada")), (200, False, True))


class Demos(Base):
    def test_rotas_publicas_com_cabecalhos(self):
        for nome, arq in servidor.DEMOS.items():
            for rota in (f"/demo/{nome}/", f"/demo/{nome}"):
                st, b, h = self.c("GET", rota)
                self.assertEqual(st, 200, rota)
                self.assertEqual(len(b), (RAIZ.parent / "demos" / arq).stat().st_size)
                for cab in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"):
                    self.assertIn(cab, h, (rota, cab))
                self.assertEqual("'unsafe-eval'" in h["Content-Security-Policy"], nome == "planejador", rota)
        st, b, _ = self.c("GET", "/demo/")
        self.assertEqual(st, 200)                                  # a demonstração do painel continua em /demo/
        for rota in ("/demo/gestao/", "/demo/../physis_hub/servidor.py", "/demo/sustainkit/x", "/demo/SCADA/"):
            self.assertEqual(self.c("GET", rota)[0], 404, rota)
        self.assertEqual(self.c("POST", "/demo/scada/", {})[0], 404)          # só leitura


class Juridico(Base):
    def test_paginas(self):
        for rota, titulo in (("/termos", b"Termos de uso"), ("/privacidade", "Política de privacidade".encode()),
                             ("/acessibilidade", b"barreira")):
            st, b, h = self.c("GET", rota)
            self.assertEqual(st, 200, rota)
            self.assertIn(titulo, b)
            self.assertEqual(b.count(b"<h1"), 1)
            self.assertIn(b'html[data-tema="escuro"]', b)          # tema escuro (e claro) da barra de preferências
            self.assertIn(b'id="px-idioma"', b)
            self.assertIn(b"Portuguese only", b)                    # em inglês, avisa; não inventa tradução de texto legal
            self.assertIn("Content-Security-Policy", h)
        _, b, _ = self.c("GET", "/conta/esqueci")
        for r in (b'href="/termos"', b'href="/privacidade"', b'href="/acessibilidade"'):
            self.assertIn(r, b)

    def test_markdown_escapado(self):
        h = servidor.md_para_html(["<script>alert(1)</script> **forte**", "- um", "- dois", "| a | b |", "|---|---|", "| 1 | 2 |", "1. x"])
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)
        self.assertIn("<strong>forte</strong>", h)
        self.assertIn("<ul><li>um</li><li>dois</li></ul>", h)
        self.assertIn('<th scope="col">a</th>', h)
        self.assertIn("<td>2</td>", h)
        self.assertIn("<ol><li>x</li></ol>", h)


class Esquemas(unittest.TestCase):
    def test_todos_no_seguranca(self):
        for k, v in servidor.ESQUEMAS_ROTAS.items():
            self.assertIs(seg.ESQUEMAS[k], v)
        self.assertEqual(servidor.esquema_documento("/api/documentos"), "doc_publicar")
        self.assertEqual(servidor.esquema_documento("/api/documentos/abc/comentarios/3/editar"), "doc_texto")
        self.assertEqual(servidor.esquema_documento("/api/documentos/abc/convites/3/revogar"), "vazio")
        self.assertIsNone(servidor.esquema_documento("/api/documentos/abc/outra"))


if __name__ == "__main__":
    unittest.main()
