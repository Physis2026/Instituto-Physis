"""Indicadores da plataforma (indicadores.py), com séries sintéticas.

Protege:
1. Anomalia sazonal: um pico é achado; numa série limpa com ciclo diário, nenhum alarme falso; pouco dado = "insuficiente".
2. Retorno da equipe: marcar "alarme falso" baixa a nota (e tira o alerta); "real" sobe.
3. Tendência e previsão com inclinação certa; n e confiança informados.
4. Incidentes: o padrão antes do incidente é guardado; padrão parecido depois sugere a causa e a correção.
5. Coleta: pedidos (rota normalizada, 4xx/5xx/429, p95), entradas e senhas erradas, por cliente sem nome e com as
   lacunas de fluxo; lista de melhorias e "virou tarefa". Rotas: papéis, CSRF e sessão.
"""
import json
import math
import os
import random
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from physis_hub import indicadores as ind
from physis_hub import seguranca as seg
from physis_hub.hub import Hub

H0 = 20458 * 24                   # meia-noite de um dia qualquer (época em horas)
EQUIPE = {"usuario": "erick", "papel": "operador"}
DIRECAO = {"usuario": "rafaella", "papel": "administrador"}


def sazonal(dias=14, semente=1, base=100.0, amp=30.0, ruido=2.0):
    r = random.Random(semente)
    return [(H0 + h, base + amp * math.sin(2 * math.pi * (h % 24) / 24) + r.gauss(0, ruido)) for h in range(dias * 24)]


class TestAprendizado(unittest.TestCase):
    def test_pico_e_achado(self):
        s = sazonal()
        hora = H0 + 14 * 24
        normal = 100 + 30 * math.sin(2 * math.pi * (hora % 24) / 24)
        a = ind.anomalia(s, hora, normal + 40)
        self.assertTrue(a["suficiente"])
        self.assertTrue(a["alerta"])
        self.assertEqual(a["modo"], "mesma hora do dia")
        self.assertEqual(a["n_mesma_hora"], 14)
        self.assertGreater(a["z"], ind.LIMIAR)

    def test_sem_alarme_falso_em_serie_limpa_com_ciclo_diario(self):
        s = sazonal(dias=21, semente=7)
        falsos = 0
        for i in range(14 * 24, 21 * 24):           # uma semana de horas novas, cada uma contra o passado
            h, v = s[i]
            falsos += ind.anomalia(s[:i], h, v)["alerta"]
        self.assertEqual(falsos, 0)
        # sem a sazonalidade (comparando com todas as horas) a mesma hora de pico pareceria normal ou anormal
        # de forma errada: o ciclo de ±30 não pode virar alarme

    def test_pouco_dado(self):
        a = ind.anomalia([(H0 + i, 1.0) for i in range(5)], H0 + 5, 50.0)
        self.assertFalse(a["suficiente"])
        self.assertEqual(a["confianca"], "dados insuficientes")
        self.assertFalse(a["alerta"])

    def test_retorno_muda_a_nota(self):
        s = sazonal()
        hora = H0 + 14 * 24
        v = 100 + 30 * math.sin(2 * math.pi * (hora % 24) / 24) + 9.5      # z perto do limiar
        neutro = ind.anomalia(s, hora, v, p_real=0.5)
        falso = ind.anomalia(s, hora, v, p_real=ind.chance_real(0, 6))
        real = ind.anomalia(s, hora, v, p_real=ind.chance_real(6, 0))
        self.assertLess(falso["nota"], neutro["nota"])
        self.assertGreater(real["nota"], neutro["nota"])
        self.assertTrue(real["alerta"])
        self.assertFalse(falso["alerta"])

    def test_tendencia(self):
        s = [(H0 + h, 10 + 2.0 * (h / 24) + (h % 24) * 0.1) for h in range(10 * 24)]
        t = ind.tendencia(s)
        self.assertTrue(t["suficiente"])
        self.assertAlmostEqual(t["inclinacao_dia"], 2.0, places=1)
        self.assertGreater(t["r2"], 0.99)
        self.assertEqual(len(t["previsao"]), 24)
        self.assertEqual(t["n_dias"], 10)
        self.assertFalse(ind.tendencia(s[:30])["suficiente"])

    def test_rota_normalizada(self):
        self.assertEqual(ind.normalizar_rota("/api/emissao/AbCdEf123456789xyz/editar?x=1"), "/api/emissao/:id/editar")
        self.assertEqual(ind.normalizar_rota("/api/central/compra/LJ-TESTE-77/aprovar"), "/api/central/compra/:id/aprovar")
        self.assertEqual(ind.normalizar_rota("/api/robos/suporte"), "/api/robos/suporte")


class Base(unittest.TestCase):
    def setUp(self):
        self.agora = (H0 + 14 * 24) * 3600 + 1800.0
        self.h = Hub(":memory:", relogio=lambda: self.agora)
        self.tmp = tempfile.TemporaryDirectory()
        self.i = ind.Indicadores(self.h, relogio=lambda: self.agora)

    def tearDown(self):
        self.tmp.cleanup()

    def gravar(self, chave, serie):
        with self.h._trava:
            self.h._db.executemany("INSERT OR REPLACE INTO indicador_hora(hora,chave,valor) VALUES(?,?,?)", [(h, chave, v) for h, v in serie])
            self.h._db.commit()


class TestNoHub(Base):
    def test_anomalia_retorno_e_incidente(self):
        hora = H0 + 14 * 24
        s = sazonal(semente=3, base=300, amp=50, ruido=8)
        self.gravar("req.p95_ms", s + [(hora, 300 + 50 * math.sin(2 * math.pi * (hora % 24) / 24) + 400)])
        self.gravar("req.total", sazonal(semente=4) + [(hora, 100 + 30 * math.sin(2 * math.pi * (hora % 24) / 24))])
        an = self.i.anomalias(hora)
        self.assertEqual([a["chave"] for a in an], ["req.p95_ms"])            # só o tempo de resposta, não o total
        self.assertEqual(an[0]["nome"][0], "Tempo de resposta p95 (ms)")
        # incidente: guarda o padrão e depois sugere causa e correção num padrão parecido
        r = self.i.registrar_incidente("Servidor lento", "disco cheio", "limpar /var/log e girar logs", "erick")
        self.assertIn("req.p95_ms+", r["padrao"])
        sug = self.i.sugestoes(hora, {"req.p95_ms+", "req.taxa_5xx+"})
        self.assertEqual(sug["sugestoes"][0]["causa"], "disco cheio")
        self.assertEqual(sug["sugestoes"][0]["correcao"], "limpar /var/log e girar logs")
        self.assertEqual(sug["confianca"], "dados insuficientes")              # 1 incidente só: diz que é pouco
        self.assertEqual(self.i.sugestoes(hora, {"disp.nos_calados+"})["sugestoes"], [])
        # retorno: 5 "alarme falso" → o mesmo pico deixa de ser alerta
        for _ in range(5):
            self.assertTrue(self.i.retorno("req.p95_ms", hora, False, "erick")["ok"])
        an2 = self.i.anomalias(hora, todas=True)
        x = next(a for a in an2 if a["chave"] == "req.p95_ms")
        self.assertLess(x["nota"], an[0]["nota"])
        self.assertEqual(x["retorno"], {"reais": 0, "falsos": 5})
        self.assertTrue(self.h.verificar_cadeia()[0])

    def test_coleta_clientes_e_melhorias(self):
        for k in range(10):
            self.i.requisicao("GET", f"/api/emissao/AbCdEf12345678{k:02d}", 200, 20 + k)
        for _ in range(3):
            self.i.requisicao("POST", "/api/robos/suporte", 500, 3000)
        self.i.requisicao("POST", "/api/conta/entrar", 429, 5)
        self.i.requisicao("PUT", "/api/cliente/estado/abc", 409, 5)
        seg.acesso_registrar(self.h, "ana", "10.0.0.1", "senha errada")
        seg.acesso_registrar(self.h, "ana", "10.0.0.1", "entrou")
        with self.h._trava:
            self.h._db.execute("INSERT INTO instalacao(numero,compra,org,nome,email,modulos,sal,resumo,pacote,criado) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               ("PH-0001", "LJ-1", "fazenda-ana-0001", "Ana Pessoa", "ana@x.com", json.dumps(["certificacoes"]), b"s", b"r", None, self.agora))
            self.h._db.commit()
        v = self.i.coletar()["valores"]
        self.assertEqual(v["req.total"], 15)
        self.assertAlmostEqual(v["req.taxa_5xx"], 3 / 15)
        self.assertEqual((v["req.limite_429"], v["sync.conflitos"]), (1, 1))
        self.assertGreaterEqual(v["req.p95_ms"], 1000)
        self.assertEqual((v["login.ok"], v["login.senha_errada"]), (1, 1))
        rotas = {r[0] for r in self.h._db.execute("SELECT rota FROM indicador_rota")}
        self.assertIn("GET /api/emissao/:id", rotas)
        cli = self.i.clientes()
        self.assertEqual(cli[0]["instalacao"], "PH-0001")
        self.assertIn("carb.inventario", [g["variavel"] for g in cli[0]["lacunas"]])
        self.assertNotIn("Ana", json.dumps(cli))                              # nunca o nome do cliente
        self.assertNotIn("ana@x.com", json.dumps(self.i.painel()))
        # o erro 5xx que se repete vira item da lista de melhorias; "virou tarefa" fica registrado
        b = [x for x in self.i.backlog() if x["tipo"] == "erro"]
        self.assertEqual(b[0]["titulo"], "Erro 5xx que se repete: POST /api/robos/suporte")
        self.assertTrue(self.i.virou_tarefa(b[0]["id"], "rafaella")["ok"])
        self.assertEqual(next(x for x in self.i.backlog() if x["id"] == b[0]["id"])["tarefa_por"], "rafaella")
        self.assertTrue(any(x["tipo"] == "lacuna" for x in self.i.backlog()))

    def test_marcas_de_backup_e_testes_e_retencao(self):
        bk, ts = Path(self.tmp.name) / "ultimo.json", Path(self.tmp.name) / "testes.json"
        bk.write_text(json.dumps({"quando": self.agora - 7200}), encoding="utf-8")
        ts.write_text(json.dumps({"quando": self.agora, "testes": 925, "falhas": 0}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"PHYSIS_BACKUP_MARCA": str(bk), "PHYSIS_TESTES_MARCA": str(ts)}):
            v = self.i.coletar()["valores"]
        self.assertEqual((v["backup.idade_h"], v["testes.falhas"]), (2.0, 0.0))
        self.gravar("req.total", [(H0 - 5000, 1.0)])
        self.assertGreaterEqual(self.i.limpar(dias=100), 1)

    def test_papeis_da_rota(self):
        self.assertEqual(self.i.rota("GET", "/api/indicadores", None)[0], 401)
        self.assertEqual(self.i.rota("GET", "/api/indicadores", {"usuario": "c", "papel": "cliente"})[0], 403)
        cod, p = self.i.rota("GET", "/api/indicadores", EQUIPE)
        self.assertEqual(cod, 200)
        self.assertIn("dados insuficientes", p["amostra"])
        self.assertEqual(self.i.rota("POST", "/api/indicadores/coletar", EQUIPE, "{}")[0], 403)
        self.assertEqual(self.i.rota("POST", "/api/indicadores/coletar", DIRECAO, "{}")[0], 200)
        self.assertEqual(self.i.rota("POST", "/api/indicadores/retorno", EQUIPE, json.dumps({"chave": "req.total", "hora": 5, "real": True}))[0], 200)
        self.assertEqual(self.i.rota("POST", "/api/indicadores/retorno", EQUIPE, json.dumps({"chave": "x y", "hora": "a"}))[0], 400)


class TestServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from physis_hub.servidor import iniciar
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict(os.environ, {"PHYSIS_CLAUDE_CONSUMO": str(Path(cls.tmp.name) / "c.json")})
        cls.env.start()
        for k in ("ANTHROPIC_API_KEY", "PHYSIS_CLAUDE_CHAVE", "PHYSIS_CLAUDE_CHAVE_ARQUIVO"):
            os.environ.pop(k, None)
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": False})
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.env.stop()
        cls.tmp.cleanup()

    def chamar(self, metodo, rota, corpo=None, cookie=None, extra=None):
        h = {"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {}), **(extra or {})}
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", method=metodo, headers=h,
                                     data=json.dumps(corpo).encode() if corpo is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers

    def test_rotas_e_medicao_dos_pedidos(self):
        self.assertEqual(self.chamar("GET", "/api/indicadores")[0], 401)
        _, _, hd = self.chamar("POST", "/api/conta/criar", {"nome": "Rafa", "usuario": "rafa", "senha": "senha-bem-longa-123"})
        ck = hd.get("Set-Cookie").split(";")[0]
        self.assertEqual(self.chamar("POST", "/api/indicadores/coletar", {}, ck, {"X-Physis-CSRF": "errado"})[0], 403)   # CSRF
        st, r, _ = self.chamar("POST", "/api/indicadores/coletar", {}, ck)
        self.assertEqual(st, 200)
        self.assertGreaterEqual(r["valores"]["req.total"], 1)                 # o pedido acima (criar conta) foi medido
        st, p, _ = self.chamar("GET", "/api/indicadores", cookie=ck)
        self.assertEqual(st, 200)
        self.assertIn("backlog", p)
        rotas = {x[0] for x in self.hub._db.execute("SELECT rota FROM indicador_rota")}
        self.assertIn("POST /api/conta/criar", rotas)
        self.assertFalse(any("/api/indicadores" in x for x in rotas))       # a própria tela não entra na conta


if __name__ == "__main__":
    unittest.main()
