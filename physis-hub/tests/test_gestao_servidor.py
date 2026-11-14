"""Gestão Physis no servidor: contas por e-mail, dados com versão e arquivos.

Protege:
1. Só a direção (administrador) cria, desativa e redefine contas; com PHYSIS_DOMINIO_EMAIL, só e-mails do domínio.
2. Conta desativada não entra e perde as sessões abertas; trocar a senha exige a senha atual.
3. Dados da Gestão: gravar exige a versão em que se baseou; versão velha = conflito com a versão atual (ninguém apaga a mudança de outra pessoa sem saber).
4. Sem sessão, nada: nem dados, nem arquivos, nem a página da Gestão (aparece a página de entrada).
"""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from physis_hub.hub import Hub
from physis_hub import servidor
from physis_hub.servidor import iniciar


class ContasNoHub(unittest.TestCase):
    def setUp(self):
        self.h = Hub()
        self.h.criar_conta("Rafaella", "rafaella@physis.example", "senha-bem-longa")
        self.adm = self.h.sessao(self.h.entrar("rafaella@physis.example", "senha-bem-longa")["token"])

    def test_primeira_e_direcao_e_demais_so_pela_direcao(self):
        self.assertEqual(self.adm["papel"], "administrador")
        self.assertTrue(self.h.criar_conta("Laura", "laura@physis.example", "outra-senha-longa", self.adm["id"], "laura")["ok"])
        laura = self.h.sessao(self.h.entrar("laura@physis.example", "outra-senha-longa")["token"])
        self.assertEqual((laura["papel"], laura["pessoa"]), ("operador", "laura"))
        self.assertFalse(self.h.criar_conta("X", "x@physis.example", "senha-bem-longa", laura["id"])["ok"])
        self.assertFalse(self.h.alterar_conta(laura["id"], "rafaella@physis.example", ativa=False)["ok"])

    def test_dominio_obrigatorio(self):
        os.environ["PHYSIS_DOMINIO_EMAIL"] = "physis.example"
        try:
            self.assertFalse(self.h.criar_conta("Fulano", "fulano@gmail.com", "senha-bem-longa", self.adm["id"])["ok"])
            self.assertTrue(self.h.criar_conta("Arthur", "arthur@physis.example", "senha-bem-longa", self.adm["id"])["ok"])
        finally:
            os.environ.pop("PHYSIS_DOMINIO_EMAIL", None)

    def test_desativar_encerra_sessoes(self):
        self.h.criar_conta("Laura", "laura@physis.example", "outra-senha-longa", self.adm["id"])
        tk = self.h.entrar("laura@physis.example", "outra-senha-longa")["token"]
        self.assertTrue(self.h.alterar_conta(self.adm["id"], "laura@physis.example", ativa=False)["ok"])
        self.assertIsNone(self.h.sessao(tk))
        self.assertFalse(self.h.entrar("laura@physis.example", "outra-senha-longa")["ok"])
        self.assertFalse(self.h.alterar_conta(self.adm["id"], "rafaella@physis.example", ativa=False)["ok"])   # não desativa a si mesma

    def test_trocar_e_redefinir_senha(self):
        self.assertFalse(self.h.trocar_senha(self.adm["id"], "errada", "nova-senha-longa")["ok"])
        self.assertTrue(self.h.trocar_senha(self.adm["id"], "senha-bem-longa", "nova-senha-longa")["ok"])
        self.assertTrue(self.h.entrar("rafaella@physis.example", "nova-senha-longa")["ok"])
        self.h.criar_conta("Laura", "laura@physis.example", "outra-senha-longa", self.adm["id"])
        self.assertTrue(self.h.alterar_conta(self.adm["id"], "laura@physis.example", senha="redefinida-pela-direcao")["ok"])
        self.assertTrue(self.h.entrar("laura@physis.example", "redefinida-pela-direcao")["ok"])


class DadosDaGestao(unittest.TestCase):
    def setUp(self):
        self.h = Hub()

    def test_versao_e_conflito(self):
        k = "gestao-physis:adm-financeiro"
        r1 = self.h.gestao_gravar(k, '{"contratos":[]}', 0, "ana")
        self.assertEqual((r1["ok"], r1["versao"]), (True, 1))
        r2 = self.h.gestao_gravar(k, '{"contratos":[{"id":"c1"}]}', 0, "bia")      # baseada na versão 0: conflito
        self.assertEqual((r2["ok"], r2["conflito"], r2["versao"], r2["valor"]), (False, True, 1, '{"contratos":[]}'))
        self.assertTrue(self.h.gestao_gravar(k, '{"contratos":[{"id":"c1"}]}', 1, "bia")["ok"])
        itens = self.h.gestao_ler()
        self.assertEqual((itens[k]["versao"], itens[k]["por"]), (2, "bia"))
        self.assertEqual(self.h.gestao_ler(desde=itens[k]["atualizado"]), {})

    def test_chaves_e_tamanho(self):
        self.assertFalse(self.h.gestao_gravar("outra-coisa", "x", 0, "a")["ok"])
        self.assertFalse(self.h.gestao_gravar("gestao-physis:../x", "x", 0, "a")["ok"])
        self.assertFalse(self.h.gestao_gravar("gestao-physis:a", "x" * (Hub.GESTAO_VALOR_MAX + 1), 0, "a")["ok"])

    def test_arquivos(self):
        self.assertTrue(self.h.gestao_arquivo_por("arq-reun-1", "ata.pdf", "application/pdf", b"%PDF-1.4 x", "ana")["ok"])
        self.assertEqual(self.h.gestao_arquivo("arq-reun-1")[0:2], ("ata.pdf", "application/pdf"))
        self.assertFalse(self.h.gestao_arquivo_por("../x", "a", "b/c", b"x", "ana")["ok"])
        self.assertTrue(self.h.gestao_arquivo_apagar("arq-reun-1", "ana"))
        self.assertIsNone(self.h.gestao_arquivo("arq-reun-1"))


class GestaoPelaRede(unittest.TestCase):
    PORTA = 8785

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.web_antes = servidor.WEB
        web = Path(cls.tmp.name) / "web"
        web.mkdir()
        (web / "gestao.html").write_text("<!doctype html><title>Gestão Physis</title><p>conteudo interno</p>", encoding="utf-8")
        (web / "painel.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
        servidor.WEB = web
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, cls.PORTA, endereco="127.0.0.1", instancia={"login": False})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        servidor.WEB = cls.web_antes
        cls.tmp.cleanup()

    def chamar(self, metodo, rota, corpo=None, cookie=None, bruto=None, tipo="application/json", extra=None):
        dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
        h = {"Content-Type": tipo}
        if cookie:
            h["Cookie"] = cookie
        h.update(extra or {})
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}{rota}", data=dados, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def test_fluxo(self):
        # sem sessão: página de entrada, nada de dados
        st, corpo, _ = self.chamar("GET", "/gestao/")
        self.assertEqual(st, 200); self.assertIn(b"Entrar", corpo); self.assertNotIn(b"conteudo interno", corpo)
        self.assertEqual(self.chamar("GET", "/api/gestao/estado")[0], 401)
        self.assertEqual(self.chamar("POST", "/api/gestao/estado/gestao-physis:x", {"valor": "1", "versao": 0})[0], 401)
        self.assertEqual(self.chamar("PUT", "/api/gestao/arquivo/arq-1", bruto=b"x", tipo="text/plain")[0], 401)
        # primeira conta (direção) e uma pessoa da equipe
        _, _, hd = self.chamar("POST", "/api/conta/criar", {"nome": "Rafaella", "usuario": "rafaella@physis.example", "senha": "senha-bem-longa"})
        ck = hd.get("Set-Cookie").split(";")[0]
        st, corpo, _ = self.chamar("GET", "/gestao/", cookie=ck)
        self.assertIn(b"conteudo interno", corpo)
        self.assertEqual(self.chamar("POST", "/api/contas", {"nome": "Laura", "usuario": "laura@physis.example", "senha": "outra-senha-longa", "pessoa": "laura"}, ck)[0], 200)
        _, corpo, _ = self.chamar("GET", "/api/contas", cookie=ck)
        self.assertEqual([c["usuario"] for c in json.loads(corpo)["contas"]], ["laura@physis.example", "rafaella@physis.example"])
        _, _, hd = self.chamar("POST", "/api/conta/entrar", {"usuario": "laura@physis.example", "senha": "outra-senha-longa"})
        ck2 = hd.get("Set-Cookie").split(";")[0]
        self.assertEqual(self.chamar("GET", "/api/contas", cookie=ck2)[0], 403)             # equipe não vê as contas
        # dados com versão: a Laura grava, a Rafaella com versão velha recebe conflito
        k = "gestao-physis:reunioes"
        self.assertEqual(self.chamar("POST", "/api/gestao/estado/" + k, {"valor": '[{"id":"r1"}]', "versao": 0}, ck2)[0], 200)
        st, corpo, _ = self.chamar("POST", "/api/gestao/estado/" + k, {"valor": '[{"id":"r2"}]', "versao": 0}, ck)
        self.assertEqual(st, 409); self.assertEqual(json.loads(corpo)["por"], "laura@physis.example")
        _, corpo, _ = self.chamar("GET", "/api/gestao/estado", cookie=ck)
        j = json.loads(corpo)
        self.assertEqual((j["conta"]["usuario"], j["itens"][k]["versao"]), ("rafaella@physis.example", 1))
        # arquivo
        self.assertEqual(self.chamar("PUT", "/api/gestao/arquivo/arq-r1", bruto=b"%PDF-1.4", tipo="application/pdf", cookie=ck2, extra={"X-Nome": "ata%20de%20reuni%C3%A3o.pdf"})[0], 200)
        st, corpo, hd = self.chamar("GET", "/api/gestao/arquivo/arq-r1", cookie=ck)
        self.assertEqual((st, corpo), (200, b"%PDF-1.4")); self.assertIn("ata%20de%20reuni%C3%A3o.pdf", hd.get("Content-Disposition"))
        # troca de senha e desativação
        self.assertEqual(self.chamar("POST", "/api/conta/senha", {"atual": "outra-senha-longa", "nova": "senha-nova-da-laura"}, ck2)[0], 200)
        self.assertEqual(self.chamar("POST", "/api/contas/laura@physis.example", {"ativa": False}, ck)[0], 200)
        self.assertEqual(self.chamar("GET", "/api/gestao/estado", cookie=ck2)[0], 401)


if __name__ == "__main__":
    unittest.main()
