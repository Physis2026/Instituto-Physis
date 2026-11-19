"""Comunidade aberta do Instituto (docs/COMUNIDADE.md), pelo servidor de verdade.

Protege (decisões de 19/11/2026):
1. Leitura aberta: sem conta, a pessoa lê o fórum e as peças publicadas do Physis 3D; não vê o que espera moderação.
2. Cadastro próprio: só com "cadastro_aberto"; vira participante (papel cliente), com aceite LGPD; sem aceite, recusado.
3. Menor de 18: precisa do responsável; navega, mas só publica depois da autorização registrada pela equipe.
4. Moderação prévia: tópico, resposta e peça 3D só aparecem depois que a equipe aprova; recusa pede motivo.
5. InovaSTEM Delas: só com autodeclaração (ou equipe); a autodeclaração não aparece para ninguém além da pessoa.
6. LGPD: apagar a conta tira o nome público, o responsável e a autodeclaração.
7. Sem "cadastro_aberto" (instalação da Physis), o cadastro público fica fechado.
"""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from physis_hub import seguranca as seg
from physis_hub import servidor
from physis_hub.hub import Hub

SENHA = "frase-longa-da-direcao-1"
SENHA_P = "senha-longa-da-participante-9"
ACEITE = {"aceito": True, "versao": "1"}


class Comunidade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.antes = {k: os.environ.get(k) for k in ("PHYSIS_EXPOSTO", "PHYSIS_3D_PASTA", "PHYSIS_CONFIRMAR_EMAIL", "PHYSIS_LIMITE_ENTRAR")}
        for k in cls.antes:
            os.environ.pop(k, None)
        os.environ["PHYSIS_LIMITE_ENTRAR"] = "0"     # muitos cadastros seguidos no teste; o limite tem teste próprio (test_rotas_novas)
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["PHYSIS_3D_PASTA"] = str(Path(cls.tmp.name) / "3d")
        cls.h = Hub(org="instituto-teste")
        cls.srv = servidor.iniciar(cls.h, 0, endereco="127.0.0.1",
                                   instancia={"login": True, "cadastro_aberto": True, "moderacao_previa": True, "instalacao": "instituto"})
        cls.porta = cls.srv.server_address[1]
        cls.h.criar_conta("Direção", "dir@inst.example", SENHA)
        cls.dir = cls.sessao("dir@inst.example", SENHA)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()
        for k, v in cls.antes.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    @classmethod
    def sessao(cls, usuario, senha):
        tk = cls.h.entrar(usuario, senha)["token"]
        return ("physis_sessao=" + tk, seg.csrf_de(cls.h, tk))

    @classmethod
    def pedir(cls, metodo, rota, corpo=None, s=None):
        cab = {"Content-Type": "application/json"}
        if s:
            cab.update({"Cookie": s[0], "X-Physis-CSRF": s[1]})
        req = urllib.request.Request(f"http://127.0.0.1:{cls.porta}{rota}", method=metodo, headers=cab,
                                     data=json.dumps(corpo).encode() if corpo is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (json.loads(b) if b.strip().startswith(b"{") else {})

    def cadastro(self, usuario, **kw):
        d = {"nome": kw.pop("nome", "Pessoa Teste"), "usuario": usuario, "senha": SENHA_P, "nome_publico": kw.pop("nome_publico", "Pessoa"),
             "maior_de_idade": kw.pop("maior", True), "consentimento": kw.pop("consentimento", ACEITE), **kw}
        return self.pedir("POST", "/api/publico/cadastro", d)

    # 2. cadastro aberto, LGPD
    def test_1_cadastro_aberto_vira_participante(self):
        st, r = self.cadastro("ana@ex.example", consentimento={"aceito": False, "versao": "1"})
        self.assertEqual(st, 400, r)
        st, r = self.cadastro("ana@ex.example", nome_publico="Ana")
        self.assertEqual(st, 200, r)
        conta = next(c for c in self.h.contas() if c["usuario"] == "ana@ex.example")
        self.assertEqual(conta["papel"], seg.CLIENTE)
        st, r = self.cadastro("ana@ex.example")
        self.assertEqual(st, 400, "mesma conta duas vezes")
        s = self.sessao("ana@ex.example", SENHA_P)
        st, eu = self.pedir("GET", "/api/comunidade/eu", s=s)
        self.assertTrue(eu["pode_publicar"])
        self.assertEqual(eu["participante"]["nome_publico"], "Ana")

    # 3. menor de 18
    def test_2_menor_precisa_do_responsavel(self):
        st, r = self.cadastro("bia@ex.example", maior=False)
        self.assertEqual(st, 400, "sem responsável")
        st, r = self.cadastro("bia@ex.example", maior=False, responsavel_nome="Mãe da Bia", responsavel_email="mae@ex.example")
        self.assertEqual(st, 200, r)
        self.assertFalse(r["pode_publicar"])
        s = self.sessao("bia@ex.example", SENHA_P)
        st, r = self.pedir("POST", "/api/comunidade/forum", {"categoria": "geral", "titulo": "Olá", "texto": "Oi"}, s)
        self.assertEqual(st, 400)
        self.assertIn("responsável", r["erro"])
        st, fila = self.pedir("GET", "/api/comunidade/moderacao", s=self.dir)
        menor = [x for x in fila["itens"] if x["tipo"] == "menor"]
        self.assertEqual(len(menor), 1)
        self.assertEqual(menor[0]["responsavel_email"], "mae@ex.example")
        st, r = self.pedir("POST", "/api/comunidade/moderar", {"tipo": "menor", "id": menor[0]["id"], "decisao": "aprovar"}, self.dir)
        self.assertEqual(st, 200, r)
        st, r = self.pedir("POST", "/api/comunidade/forum", {"categoria": "geral", "titulo": "Olá de novo", "texto": "Oi"}, s)
        self.assertEqual(st, 200, r)

    # 1 e 4. leitura aberta e moderação prévia
    def test_3_moderacao_previa_e_leitura_aberta(self):
        self.cadastro("caio@ex.example", nome_publico="Caio")
        s = self.sessao("caio@ex.example", SENHA_P)
        st, r = self.pedir("POST", "/api/comunidade/forum", {"categoria": "inovastem", "titulo": "Trilha T1", "texto": "Quando abre?"}, s)
        self.assertEqual((st, r["estado"]), (200, "pendente"))
        tid = r["id"]
        st, pub = self.pedir("GET", "/api/publico/comunidade/forum?categoria=inovastem")
        self.assertEqual(st, 200)
        self.assertNotIn(tid, [t["id"] for t in pub["topicos"]], "pendente não aparece para o público")
        st, meu = self.pedir("GET", "/api/comunidade/forum?categoria=inovastem", s=s)
        self.assertIn(tid, [t["id"] for t in meu["topicos"]], "o autor vê o próprio pendente")
        st, r = self.pedir("POST", "/api/comunidade/moderar", {"tipo": "topico", "id": tid, "decisao": "recusar"}, self.dir)
        self.assertEqual(st, 400, "recusa pede motivo")
        st, r = self.pedir("POST", "/api/comunidade/moderar", {"tipo": "topico", "id": tid, "decisao": "aprovar"}, self.dir)
        self.assertEqual(st, 200, r)
        st, pub = self.pedir("GET", "/api/publico/comunidade/forum?categoria=inovastem")
        self.assertIn(tid, [t["id"] for t in pub["topicos"]])
        st, msgs = self.pedir("GET", f"/api/publico/comunidade/forum/{tid}")
        self.assertEqual([m["texto"] for m in msgs["mensagens"]], ["Quando abre?"])
        self.assertNotIn("autor", msgs["mensagens"][0], "o usuário (e-mail) nunca sai")
        # resposta também espera
        st, r = self.pedir("POST", f"/api/comunidade/forum/{tid}", {"texto": "Em 2027."}, s)
        self.assertEqual(r["estado"], "pendente")
        st, msgs = self.pedir("GET", f"/api/publico/comunidade/forum/{tid}")
        self.assertEqual(len(msgs["mensagens"]), 1)
        # participante não modera; público não escreve
        st, _ = self.pedir("GET", "/api/comunidade/moderacao", s=s)
        self.assertEqual(st, 403)
        st, _ = self.pedir("POST", "/api/comunidade/forum", {"categoria": "geral", "titulo": "x" * 5, "texto": "y"})
        self.assertEqual(st, 401)
        st, _ = self.pedir("POST", "/api/publico/comunidade/forum", {"categoria": "geral", "titulo": "xxxxx", "texto": "y"})
        self.assertIn(st, (404, 405))

    # 5. Delas
    def test_4_delas_por_autodeclaracao(self):
        self.cadastro("duda@ex.example", nome_publico="Duda", delas=True)
        self.cadastro("edu@ex.example", nome_publico="Edu")
        sd, se = self.sessao("duda@ex.example", SENHA_P), self.sessao("edu@ex.example", SENHA_P)
        st, r = self.pedir("GET", "/api/publico/comunidade/forum?categoria=delas")
        self.assertEqual(st, 403)
        st, r = self.pedir("GET", "/api/comunidade/forum?categoria=delas", s=se)
        self.assertEqual(st, 403)
        st, r = self.pedir("POST", "/api/comunidade/forum", {"categoria": "delas", "titulo": "Roda de conversa", "texto": "Quinta?"}, sd)
        self.assertEqual(st, 200, r)
        st, r = self.pedir("GET", "/api/comunidade/forum?categoria=delas", s=sd)
        self.assertEqual(st, 200)
        # a autodeclaração não aparece na fila nem no registro
        st, fila = self.pedir("GET", "/api/comunidade/moderacao", s=self.dir)
        self.assertNotIn("delas", json.dumps([x for x in fila["itens"] if x["tipo"] != "topico"]))
        regs = [r[0] for r in self.h._db.execute("SELECT conteudo FROM registro WHERE tipo='comunidade'")]
        self.assertTrue(regs)
        self.assertFalse(any('"delas":' in c for c in regs), "a autodeclaração não vai para o registro encadeado")
        # a pessoa pode retirar
        st, r = self.pedir("POST", "/api/comunidade/delas", {"autodeclaro": False}, sd)
        self.assertEqual(st, 200)
        st, r = self.pedir("GET", "/api/comunidade/forum?categoria=delas", s=sd)
        self.assertEqual(st, 403)

    # 1 e 4. Physis 3D aberto para leitura, com moderação prévia
    def test_5_physis_3d_leitura_aberta_e_moderacao(self):
        self.cadastro("fer@ex.example", nome_publico="Fer")
        s = self.sessao("fer@ex.example", SENHA_P)
        st, r = self.pedir("POST", "/api/3d/participante", {"nome_publico": "Fer", "consentimento": True}, s)
        self.assertEqual(st, 200, r)
        st, r = self.pedir("POST", "/api/3d/pecas", {"nome": "Suporte de vaso", "material": ""}, s)
        pid = r["id"]
        stl = (b"\0" * 80) + (1).to_bytes(4, "little") + (b"\0" * 12) + b"".join(
            v.to_bytes(4, "little") for v in [0, 0, 0, 0x3F800000, 0, 0, 0, 0x3F800000, 0]) + b"\0\0"
        import base64
        st, r = self.pedir("POST", f"/api/3d/pecas/{pid}/revisao", {"arquivo_b64": base64.b64encode(stl).decode(), "arquivo_nome": "s.stl",
                                                                    "nota": "primeira"}, s)
        self.assertEqual(st, 200, r)
        st, r = self.pedir("POST", f"/api/3d/pecas/{pid}/publicar", {"licenca": "CC-BY-4.0", "consentimento": True}, s)
        self.assertEqual(st, 200, r)
        st, pub = self.pedir("GET", "/api/publico/3d/pecas")
        self.assertNotIn(pid, [p["id"] for p in pub["pecas"]], "peça à espera da moderação")
        st, fila = self.pedir("GET", "/api/comunidade/moderacao", s=self.dir)
        self.assertIn(("p3d_peca", pid), [(x["tipo"], x["id"]) for x in fila["itens"]])
        st, r = self.pedir("POST", "/api/comunidade/moderar", {"tipo": "p3d_peca", "id": pid, "decisao": "aprovar"}, self.dir)
        self.assertEqual(st, 200, r)
        st, pub = self.pedir("GET", "/api/publico/3d/pecas")
        self.assertIn(pid, [p["id"] for p in pub["pecas"]])
        st, peca = self.pedir("GET", f"/api/publico/3d/pecas/{pid}")
        self.assertEqual(st, 200)
        self.assertNotIn("autor", peca["peca"], "o usuário (e-mail) do autor nunca sai")
        st, memo = self.pedir("GET", f"/api/publico/3d/pecas/{pid}/memorial")
        self.assertIn("Memorial de desenvolvimento", memo["texto"])
        # fórum 3D: pendente até aprovar
        st, r = self.pedir("POST", "/api/3d/forum", {"titulo": "Dúvida de infill", "texto": "Quanto usar?"}, s)
        self.assertTrue(r.get("pendente"))
        st, pub = self.pedir("GET", "/api/publico/3d/forum")
        self.assertEqual(pub["topicos"], [])
        self.pedir("POST", "/api/comunidade/moderar", {"tipo": "p3d_topico", "id": r["id"], "decisao": "aprovar"}, self.dir)
        st, pub = self.pedir("GET", "/api/publico/3d/forum")
        self.assertEqual([t["titulo"] for t in pub["topicos"]], ["Dúvida de infill"])
        # o público só lê
        st, _ = self.pedir("POST", "/api/publico/3d/pecas", {"nome": "x"})
        self.assertIn(st, (404, 405))

    # 6. LGPD
    def test_6_apagar_conta_tira_dados_da_comunidade(self):
        self.cadastro("gil@ex.example", nome_publico="Gil", delas=True)
        s = self.sessao("gil@ex.example", SENHA_P)
        st, r = self.pedir("POST", "/api/conta/apagar", {"senha": SENHA_P}, s)
        self.assertEqual(st, 200, r)
        row = self.h._db.execute("SELECT nome_publico, delas, removido FROM com_participante WHERE usuario='gil@ex.example'").fetchone()
        self.assertEqual(tuple(row), ("Participante removido", 0, 1))


class CadastroFechado(unittest.TestCase):
    """7. Instalação sem "cadastro_aberto" (Physis): o cadastro público responde 403."""
    def test_sem_cadastro_aberto(self):
        h = Hub(org="sem-cadastro")
        srv = servidor.iniciar(h, 0, endereco="127.0.0.1", instancia={"login": True})
        try:
            h.criar_conta("Direção", "d@x.example", SENHA)
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/publico/cadastro", method="POST",
                                         headers={"Content-Type": "application/json"},
                                         data=json.dumps({"nome": "X", "usuario": "x@x.example", "senha": SENHA_P, "nome_publico": "X",
                                                          "maior_de_idade": True, "consentimento": ACEITE}).encode())
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req, timeout=30)
            self.assertEqual(e.exception.code, 403)
            self.assertFalse(any(c["usuario"] == "x@x.example" for c in h.contas()))
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
