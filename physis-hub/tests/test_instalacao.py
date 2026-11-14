"""Montagem automática depois da compra: número, plataforma, código e e-mail de acesso.

Protege:
1. Aprovar uma compra cria a instalação uma vez só (repetir não troca o código).
2. O código só existe no e-mail; o servidor guarda só um resumo com sal e, depois do envio, apaga o código do texto.
3. Código errado não ativa; cinco erros bloqueiam; o certo entrega a plataforma com os módulos comprados.
4. Aprovar exige sessão, mesmo em instalação sem login.
"""
import io
import json
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from physis_hub.hub import Hub
from physis_hub.servidor import iniciar

COMPRA = {"_formato": "physis-compra/1", "modo": "pedido", "numero": "LJ-TESTE-77", "recibo": "RC-TESTE-77", "total": 32590,
          "pagador": {"nome": "Fazenda Boa Água", "doc": "12345678000199", "email": "cliente@exemplo.com", "telefone": "61999990000"},
          "modulos": ["monitoramento", "agua", "inexistente"],
          "cursos": [{"nome": "Monitoramento na prática", "link": "https://cursos.physis.example/c01"}, {"nome": "x", "link": "http://inseguro"}]}


def codigo_do_email(corpo: str) -> str:
    return re.search(r"Código de ativação: ([A-Z0-9-]+)", corpo).group(1)


class InstalacaoNoHub(unittest.TestCase):
    def setUp(self):
        self.h = Hub()
        self.h.central_por("compra", COMPRA["numero"], COMPRA)
        self.tmp = tempfile.TemporaryDirectory()
        self.feitos = []

    def tearDown(self):
        self.tmp.cleanup()

    def fabricar(self, org, modulos, nome, cursos=None):
        self.feitos.append((org, modulos, nome))
        p = Path(self.tmp.name) / f"physis-{org}.zip"
        p.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        return p

    def test_monta_uma_vez(self):
        r = self.h.instalar_compra(COMPRA["numero"], "https://site.physis.example", self.fabricar, "ana")
        self.assertEqual((r["ok"], r["numero"], r["modulos"], r["pacote"]), (True, "PH-0001", ["monitoramento", "agua"], True))
        self.assertEqual(r["link"], "https://site.physis.example/ativar/PH-0001")
        self.assertEqual(self.feitos[0][1], ["monitoramento", "agua"])            # módulo desconhecido não entra
        e = self.h.emails("pendente")
        self.assertEqual(len(e), 1)
        self.assertIn("PH-0001", e[0]["corpo"]); self.assertIn("/ativar/PH-0001", e[0]["corpo"])
        self.assertIn("https://cursos.physis.example/c01", e[0]["corpo"]); self.assertNotIn("http://inseguro", e[0]["corpo"])
        # repetir não cria outra nem troca o código
        cod = codigo_do_email(e[0]["corpo"])
        r2 = self.h.instalar_compra(COMPRA["numero"], "https://x", self.fabricar, "ana")
        self.assertTrue(r2["repetido"]); self.assertEqual(len(self.h.emails()), 1); self.assertEqual(len(self.feitos), 1)
        self.assertTrue(self.h.ativar("PH-0001", cod)["ok"])

    def test_codigo_nao_fica_no_registro(self):
        self.h.instalar_compra(COMPRA["numero"], "https://s", self.fabricar)
        cod = codigo_do_email(self.h.emails()[0]["corpo"])
        conteudo = " ".join(r[0] for r in self.h._db.execute("SELECT conteudo FROM registro"))
        self.assertNotIn(cod, conteudo)
        self.assertNotIn(cod.replace("-", "").encode(), bytes(self.h._db.execute("SELECT resumo FROM instalacao").fetchone()[0]))

    def test_ativacao(self):
        self.h.instalar_compra(COMPRA["numero"], "https://s", self.fabricar)
        cod = codigo_do_email(self.h.emails()[0]["corpo"])
        self.assertFalse(self.h.ativar("PH-0001", "AAAA-BBBB-CCCC")["ok"])
        self.assertFalse(self.h.ativar("PH-9999", cod)["ok"])
        r = self.h.ativar("PH-0001", cod.lower().replace("-", " "))           # aceita minúscula e espaços
        self.assertTrue(r["ok"]); self.assertTrue(r["pacote"].endswith(".zip"))

    def test_bloqueio_por_erros(self):
        self.h.instalar_compra(COMPRA["numero"], "https://s", self.fabricar)
        cod = codigo_do_email(self.h.emails()[0]["corpo"])
        for _ in range(Hub.ATIVAR_ERROS):
            self.h.ativar("PH-0001", "ERRADO")
        r = self.h.ativar("PH-0001", cod)
        self.assertFalse(r["ok"]); self.assertIn("espera", r)

    def test_codigo_sai_do_texto_depois_de_enviado(self):
        self.h.instalar_compra(COMPRA["numero"], "https://s", self.fabricar)
        e = self.h.emails()[0]; cod = codigo_do_email(e["corpo"])
        self.assertTrue(self.h.email_marcar(e["id"], "enviado_a_mao"))
        corpo = self.h.emails()[0]["corpo"]
        self.assertNotIn(cod, corpo); self.assertIn("(enviado ao cliente)", corpo)
        self.assertTrue(self.h.ativar("PH-0001", cod)["ok"])                   # o código continua valendo para o cliente

    def test_compra_sem_email_ou_desconhecida(self):
        self.assertFalse(self.h.instalar_compra("NAO-EXISTE", "https://s", self.fabricar)["ok"])
        self.h.central_por("compra", "LJ-SEM-EMAIL", dict(COMPRA, numero="LJ-SEM-EMAIL", pagador={"nome": "X"}))
        self.assertFalse(self.h.instalar_compra("LJ-SEM-EMAIL", "https://s", self.fabricar)["ok"])

    def test_so_curso_nao_monta_plataforma(self):
        self.h.central_por("compra", "LJ-CURSO", dict(COMPRA, numero="LJ-CURSO", modulos=[]))
        r = self.h.instalar_compra("LJ-CURSO", "https://s", self.fabricar)
        self.assertTrue(r["ok"]); self.assertFalse(r["pacote"]); self.assertEqual(self.feitos, [])
        corpo = [e for e in self.h.emails() if e["ref"] == r["numero"]][0]["corpo"]
        self.assertIn("Seus cursos", corpo); self.assertNotIn("Código de ativação", corpo)


class InstalacaoPelaRede(unittest.TestCase):
    """O fluxo inteiro pela rede, com o montador de verdade: compra -> aprovação -> e-mail -> ativação -> plataforma."""
    PORTA = 8786

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["PHYSIS_ENTREGAS"] = cls.tmp.name
        os.environ.pop("PHYSIS_SMTP_HOST", None)
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, cls.PORTA, endereco="127.0.0.1", instancia={"login": False})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        os.environ.pop("PHYSIS_ENTREGAS", None)
        cls.tmp.cleanup()

    def chamar(self, metodo, rota, corpo=None, cookie=None, bruto=False):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        h = {"Content-Type": "application/json", "Host": "site.physis.example"}
        if cookie:
            h["Cookie"] = cookie
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}{rota}", data=dados, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
                return r.status, (b if bruto else json.loads(b.decode() or "{}")), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}"), e.headers

    def test_fluxo_completo(self):
        self.assertEqual(self.chamar("POST", "/api/central/compra", COMPRA)[0], 200)
        self.assertEqual(self.chamar("POST", "/api/central/compra/LJ-TESTE-77/aprovar", {})[0], 401)   # sem sessão, não
        _, _, hd = self.chamar("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana", "senha": "senha-bem-longa"})
        ck = hd.get("Set-Cookie").split(";")[0]
        st, r, _ = self.chamar("POST", "/api/central/compra/LJ-TESTE-77/aprovar", {}, ck)
        inst = r["instalacao"]
        self.assertEqual((st, inst["ok"], inst["numero"], inst["pacote"], inst["email"]), (200, True, "PH-0001", True, "pendente"))
        self.assertEqual(inst["link"], "http://site.physis.example/ativar/PH-0001")
        # a equipe vê o e-mail na fila; o cliente só sabe o código por ele
        st, j, _ = self.chamar("GET", "/api/central/emails", cookie=ck)
        self.assertFalse(j["configurado"]); cod = codigo_do_email(j["emails"][0]["corpo"])
        self.assertEqual(self.chamar("GET", "/api/central/emails")[0], 401)
        # página de ativação
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}/ativar/PH-0001")
        with urllib.request.urlopen(req, timeout=5) as pg:
            self.assertIn("PH-0001", pg.read().decode())
        self.assertEqual(self.chamar("POST", "/api/ativar/PH-0001", {"codigo": "ERRADO"})[0], 403)
        st, z, hd = self.chamar("POST", "/api/ativar/PH-0001", {"codigo": cod}, bruto=True)
        self.assertEqual((st, hd.get("Content-Type")), (200, "application/zip"))
        with zipfile.ZipFile(io.BytesIO(z)) as arq:
            nomes = arq.namelist()
            inst_json = json.loads(arq.read([n for n in nomes if n.endswith("instancia.json")][0]))
        self.assertEqual(inst_json["modulos"], ["monitoramento", "agua"])
        self.assertEqual(inst_json["nome"], "Fazenda Boa Água")
        self.assertTrue(any(n.endswith("web/painel.html") for n in nomes))
        # marcar como enviado tira o código do texto guardado
        eid = j["emails"][0]["id"]
        self.assertTrue(self.chamar("POST", f"/api/central/emails/{eid}/enviado", {}, ck)[1]["ok"])
        self.assertNotIn(cod, self.chamar("GET", "/api/central/emails", cookie=ck)[1]["emails"][0]["corpo"])


if __name__ == "__main__":
    unittest.main()
