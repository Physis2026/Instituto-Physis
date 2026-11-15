"""IA Claude para os robôs (sem internet: um servidor HTTP falso no próprio computador faz o papel da Anthropic).

Protege:
1. Sem chave, o Claude fica desligado e nada sai do hub; a chave nunca aparece no repr, no log nem no contador.
2. Resposta normal: cabeçalhos certos (x-api-key, anthropic-version), modelo padrão, sem temperature, custo contado.
3. Erro da API, recusa ou rede fora: devolve None e o robô responde por regras.
4. Teto do mês: acima dele nada é enviado e o robô responde por regras; mês novo zera o contador.
5. Dados pessoais (e-mail, CPF, CNPJ, telefone) saem antes do envio, e o contador anota quantos saíram.
6. Ordem: Claude → IA local → regras; toda resposta de IA vem marcada e com revisão humana.
"""
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from physis_hub import ia_claude, robos

CHAVE = "sk-ant-teste-NAO-E-REAL-123"
BASE = [{"texto": "Para baixar qualquer tela, use o botão Baixar esta tela: ele gera Word, PDF ou Excel com a identidade da Physis.",
         "fonte": "docs/APPS.md", "secao": "Exportar"}]
OK = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "stop_reason": "end_turn",
      "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": "Use o botão Baixar esta tela [1]."}],
      "usage": {"input_tokens": 1000, "output_tokens": 500}}


class Falso(BaseHTTPRequestHandler):
    respostas: list = []          # (status, corpo) por chamada
    recebidos: list = []

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        Falso.recebidos.append({"cabecalhos": dict(self.headers), "corpo": corpo, "caminho": self.path})
        status, saida = Falso.respostas.pop(0) if Falso.respostas else (200, OK)
        dados = json.dumps(saida).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *a):
        pass


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Falso)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}/v1/messages"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        Falso.respostas, Falso.recebidos = [], []
        self.tmp = tempfile.TemporaryDirectory()
        self.consumo = Path(self.tmp.name) / "consumo.json"
        self.agora = datetime(2026, 11, 15, 10, 0).timestamp()

    def tearDown(self):
        self.tmp.cleanup()

    def claude(self, **kw):
        kw.setdefault("chave", CHAVE)
        kw.setdefault("url", self.url)
        kw.setdefault("consumo", self.consumo)
        kw.setdefault("teto_usd", 25)
        kw.setdefault("tempo", 5)
        return ia_claude.IAClaude(relogio=lambda: self.agora, **kw)


class TestIAClaude(Base):
    def test_sem_chave_desligado(self):
        sem = {"PHYSIS_CLAUDE_CHAVE": "", "ANTHROPIC_API_KEY": "", "PHYSIS_CLAUDE_CHAVE_ARQUIVO": ""}
        with mock.patch.dict(os.environ, sem):
            ia = ia_claude.IAClaude(url=self.url, consumo=self.consumo)
        self.assertFalse(ia.ativa)
        self.assertIsNone(ia.gerar("s", "p"))
        self.assertEqual(Falso.recebidos, [])
        self.assertFalse(ia.estado()["configurada"])

    def test_chave_de_arquivo_e_endereco_externo_recusado(self):
        arq = Path(self.tmp.name) / "chave.txt"
        arq.write_text(CHAVE + "\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"PHYSIS_CLAUDE_CHAVE_ARQUIVO": str(arq)}):
            self.assertEqual(ia_claude.ler_chave(), CHAVE)
        ruim = self.claude(url="https://outro-servidor.example.com/v1/messages")
        self.assertFalse(ruim.ativa)
        self.assertIn("api.anthropic.com", ruim.erro)

    def test_resposta_normal(self):
        ia = self.claude()
        with self.assertLogs("physis.ia_claude", "INFO") as logs:
            self.assertEqual(ia.gerar("sistema", "como exportar?", robo="suporte"), "Use o botão Baixar esta tela [1].")
        req = Falso.recebidos[0]
        cab = {k.lower(): v for k, v in req["cabecalhos"].items()}
        self.assertEqual(cab["x-api-key"], CHAVE)
        self.assertEqual(cab["anthropic-version"], ia_claude.VERSAO_API)
        self.assertEqual(cab["anthropic-beta"], ia_claude.BETA_RESERVA)
        corpo = req["corpo"]
        self.assertEqual(corpo["model"], "claude-opus-5-5")
        self.assertEqual(corpo["fallbacks"], "default")
        self.assertEqual(corpo["output_config"], {"effort": "low"})
        self.assertNotIn("temperature", corpo)
        # custo: 1000 × 4 + 500 × 20 por milhão = 0,014 US$
        est = ia.estado()
        self.assertAlmostEqual(est["gasto_usd"], 0.014, places=6)
        self.assertEqual(est["chamadas"], 1)
        self.assertEqual(ia.ultimo["modelo"], "claude-opus-5-5")
        # a chave e o texto não aparecem no log, no repr nem no contador
        guardado = self.consumo.read_text(encoding="utf-8")
        for onde in ("\n".join(logs.output), repr(ia), guardado, json.dumps(est)):
            self.assertNotIn(CHAVE, onde)
        self.assertNotIn("como exportar", guardado)

    def test_erro_da_api_e_recusa(self):
        Falso.respostas = [(529, {"type": "error", "error": {"type": "overloaded_error", "message": "x"}}),
                           (200, dict(OK, stop_reason="refusal", content=[]))]
        ia = self.claude()
        self.assertIsNone(ia.gerar("s", "p"))
        self.assertIn("529", ia.erro)
        self.assertIn("overloaded_error", ia.erro)
        self.assertIsNone(ia.gerar("s", "p"))
        self.assertIn("recusou", ia.erro)
        self.assertEqual(ia.estado()["falhas"], 2)

    def test_rede_fora(self):
        ia = self.claude(url="http://127.0.0.1:9/v1/messages", tempo=1)
        self.assertIsNone(ia.gerar("s", "p"))
        self.assertIn("rede", ia.erro)

    def test_teto_atingido_e_mes_novo(self):
        self.consumo.write_text(json.dumps({"mes": "2026-11", "gasto_usd": 24.95}), encoding="utf-8")
        ia = self.claude(teto_usd=25)
        self.assertIsNone(ia.gerar("s", "p"))
        self.assertIn("teto", ia.erro)
        self.assertEqual(Falso.recebidos, [])
        self.assertEqual(ia.estado()["bloqueadas_teto"], 1)
        self.agora = datetime(2026, 12, 1, 8, 0).timestamp()        # mês novo: contador zera
        self.assertIsNotNone(ia.gerar("s", "p"))
        self.assertEqual(ia.estado()["mes"], "2026-12")
        self.assertFalse(self.claude(teto_usd=0).ativa)               # teto 0 = Claude desligado

    def test_dados_pessoais_saem_e_ficam_anotados(self):
        ia = self.claude()
        ia.gerar("sistema", "Sou Ana Lima, ana.lima@exemplo.com.br, CPF 123.456.789-09, CNPJ 12.345.678/0001-90, "
                            "tel (24) 99876-5432. Quero exportar.", robo="suporte", nomes=["Ana Lima"])
        enviado = json.dumps(Falso.recebidos[0]["corpo"], ensure_ascii=False)
        for s in ("ana.lima@", "123.456.789", "12.345.678/0001", "99876", "Ana Lima"):
            self.assertNotIn(s, enviado)
        for marca in ("[e-mail]", "[CPF]", "[CNPJ]", "[telefone]", "[pessoa]"):
            self.assertIn(marca, enviado)
        nota = json.loads(self.consumo.read_text(encoding="utf-8"))["envios"][-1]
        self.assertEqual(nota["dados_pessoais_removidos"], {"e-mail": 1, "CPF": 1, "CNPJ": 1, "telefone": 1, "pessoa": 1})
        self.assertNotIn("exportar", json.dumps(nota))


class TestOrdemNosRobos(Base):
    def test_claude_primeiro_e_marcado(self):
        cadeia = robos.CadeiaIA([self.claude(), robos.IALocal("")])
        r = robos.Suporte({"base_suporte": BASE}, cadeia).responder({"pergunta": "exportar tela para PDF"})
        self.assertTrue(r["ia"]["usada"])
        self.assertEqual(r["ia"]["tipo"], "claude")
        self.assertTrue(r["gerado_por_ia"])
        self.assertTrue(r["revisao_humana"])
        self.assertIn(robos.AVISO_IA, r["resposta"])

    def test_claude_falha_vai_para_local_depois_regras(self):
        Falso.respostas = [(500, {}), (500, {})]
        local = robos.IALocal("http://localhost:8000", enviar=lambda u, c, t: {"choices": [{"message": {"content": "da IA local"}}]})
        r = robos.Suporte({"base_suporte": BASE}, robos.CadeiaIA([self.claude(), local])).responder({"pergunta": "exportar tela para PDF"})
        self.assertEqual(r["ia"]["tipo"], "openai")
        self.assertTrue(r["resposta"].startswith("da IA local"))
        self.assertTrue(any("claude" in t for t in r["ia"]["tentativas"]))
        r = robos.Suporte({"base_suporte": BASE}, robos.CadeiaIA([self.claude(), robos.IALocal("")])).responder(
            {"pergunta": "exportar tela para PDF"})
        self.assertFalse(r["ia"]["usada"])
        self.assertIn("Baixar esta tela", r["resposta"])          # resposta pronta
        self.assertNotIn(robos.AVISO_IA, r["resposta"])

    def test_teto_robo_responde_por_regras(self):
        self.consumo.write_text(json.dumps({"mes": "2026-11", "gasto_usd": 30.0}), encoding="utf-8")
        r = robos.Suporte({"base_suporte": BASE}, robos.CadeiaIA([self.claude(), robos.IALocal("")])).responder(
            {"pergunta": "exportar tela para PDF"})
        self.assertTrue(r["ok"])
        self.assertFalse(r["ia"]["usada"])
        self.assertIn("teto", r["ia"]["erro"])
        self.assertEqual(Falso.recebidos, [])

    def test_precos_e_editais_viram_sugestao(self):
        cadeia = robos.CadeiaIA([self.claude()])
        r = robos.Precos({}, cadeia).responder({"itens": [{"descricao": "Módulo fotovoltaico 550 W", "preco": 960}],
                                                "historico": [{"descricao": "Módulo fotovoltaico 550 W", "preco": p} for p in (900, 1000)]})
        self.assertTrue(r["revisao_humana"])
        self.assertTrue(r["dados"]["sugestao"])
        self.assertTrue(r["gerado_por_ia"])
        r = robos.Editais({}, cadeia).responder({"editais": [{"id": "b", "titulo": "Chamada energia solar no campo",
                                                             "resumo": "fotovoltaica", "prazo": "2026-12-20"}], "hoje": "2026-11-15"})
        self.assertTrue(r["dados"]["sugestao"])
        self.assertTrue(r["gerado_por_ia"])
        self.assertIn("Perfil:", Falso.recebidos[-1]["corpo"]["messages"][0]["content"])

    def test_ordem_padrao_do_ambiente(self):
        with mock.patch.dict(os.environ, {"PHYSIS_CLAUDE_CHAVE": CHAVE, "PHYSIS_IA_URL": "http://localhost:8000",
                                          "PHYSIS_CLAUDE_CONSUMO": str(self.consumo)}):
            c = robos.ia_do_ambiente()
        self.assertEqual(c.tipo, "claude → openai → regras")
        self.assertNotIn(CHAVE, repr(c.provedores[0]))


if __name__ == "__main__":
    unittest.main()
