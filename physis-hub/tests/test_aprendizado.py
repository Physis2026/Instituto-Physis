"""Aprendizado no hub (sem internet, dados sintéticos com semente fixa e relógio de mentira).

Protege:
1. Chuva: com histórico, a regressão logística erra menos (Brier) que "sempre a média" e não fica pior que a
   melhor fonte sozinha; com pouco histórico, cai no placar de clima.py; o treino é determinístico.
2. Anomalias: valor fora do normal (z robusto), sensor travado, salto impossível e bateria acabando.
3. Consumo: a regressão acha o efeito do fim de semana e da temperatura e marca o dia de desperdício.
4. Irrigação: velocidade de secagem → hora do limite; chuva provável adia; no limite, irrigar agora.
5. Tabela modelo: versões, estado para a tela e o treino diário.
"""
import json
import math
import random
import unittest
from datetime import datetime, timedelta

from physis_hub import aprendizado as ap
from physis_hub.aprendizado import FUSO
from physis_hub.hub import Hub

AGORA = datetime(2026, 11, 15, 10, 0, tzinfo=FUSO).timestamp()


def dias_para_tras(n: int, fim: str = "2026-11-14") -> list[str]:
    f = datetime.strptime(fim, "%Y-%m-%d")
    return [(f - timedelta(days=n - 1 - i)).strftime("%Y-%m-%d") for i in range(n)]


def chuva_sintetica(n: int, semente: int = 7) -> list[dict]:
    """Chuva mais provável no verão; Open-Meteo acerta ~80%, INMET ~70%, receptor ~60%."""
    rnd = random.Random(semente)
    out = []
    for dia in dias_para_tras(n):
        mes = int(dia[5:7])
        base = 0.55 if mes in (11, 12, 1, 2, 3) else 0.15
        y = int(rnd.random() < base)
        mm = rnd.uniform(2, 30) if y else rnd.choice([0.0, 0.0, 0.4])
        out.append({"dia": dia, "y": y, "mm": mm})
    return out


def apostas(dias: list[dict], semente: int = 11) -> list[tuple]:
    rnd = random.Random(semente)
    linhas = []
    for d in dias:
        for fonte, acerto in (("openmeteo", 0.8), ("inmet", 0.7), ("receptor", 0.6)):
            diz = d["y"] if rnd.random() < acerto else 1 - d["y"]
            mm = (rnd.uniform(3, 20) if diz else rnd.uniform(0, 0.8)) if fonte == "openmeteo" else None
            linhas.append((fonte, d["dia"], diz, mm, AGORA))
    return linhas


def hub_com_chuva(n: int) -> Hub:
    h = Hub(":memory:", relogio=lambda: AGORA)
    a = ap.Aprendizado(h)
    dias = chuva_sintetica(n)
    a._db.executemany("INSERT INTO clima_aposta(fonte,dia,chove,mm,feita) VALUES(?,?,?,?,?)", apostas(dias))
    a._db.executemany("INSERT INTO clima_observado(dia,origem,mm,atualizado) VALUES(?,?,?,?)",
                      [(d["dia"], "cemaden", d["mm"], AGORA) for d in dias])
    h._db.commit()
    return h


def inserir_medicoes(h: Hub, ativo: str, grandeza: str, pontos):
    h._db.executemany("INSERT INTO medicao(leitura,topico,grandeza,ativo,valor,ts,alarme) VALUES(0,'t',?,?,?,?,'ok')",
                      [(grandeza, ativo, v, int(t)) for t, v in pontos])
    h._db.commit()


class TestMatematica(unittest.TestCase):
    def test_reta_e_regressao(self):
        a, b, r2 = ap.reta([0, 1, 2, 3], [1, 3, 5, 7])
        self.assertAlmostEqual(a, 2.0)
        self.assertAlmostEqual(b, 1.0)
        self.assertAlmostEqual(r2, 1.0)
        w = ap.regressao([[1, 0], [1, 1], [1, 2]], [1, 3, 5])
        self.assertAlmostEqual(w[0], 1.0, places=4)
        self.assertAlmostEqual(w[1], 2.0, places=4)

    def test_mediana_mad_logistica(self):
        self.assertEqual(ap.mediana([5, 1, 3]), 3)
        self.assertEqual(ap.mad([1, 2, 3, 4, 100]), 1)
        x = [[1, v] for v in (-2, -1, -0.5, 0.5, 1, 2)]
        w = ap.logistica(x, [0, 0, 0, 1, 1, 1], l2=0.0)
        self.assertGreater(w[1], 0)
        self.assertLess(ap.sigmoide(w[0] + w[1] * -2), 0.2)


class TestChuva(unittest.TestCase):
    def test_modelo_aprende_e_compara(self):
        h = hub_com_chuva(365)        # um ano inteiro: os 30% de teste pegam seca e começo das águas
        amostras = ap.dados_chuva(h._db)
        self.assertEqual(len(amostras), 365)
        m = ap.treinar_chuva(amostras, AGORA)
        met = m["metricas"]
        self.assertEqual(met["modo"], "logistica")
        self.assertLess(met["brier_modelo"], met["brier_sempre_media"])
        self.assertLess(met["brier_modelo"], met["brier_placar"])
        self.assertLessEqual(met["brier_modelo"], min(met["brier_fontes"].values()) + 0.02)
        self.assertTrue(met["calibracao"])
        self.assertIn("brier_placar", met)
        # o Open-Meteo, que acerta mais, pesa mais que o receptor
        w = dict(zip(ap.VARIAVEIS_CHUVA, m["parametros"]["pesos"][1:]))
        self.assertGreater(w["openmeteo_diz"], w["receptor_diz"])
        p_sim = ap.prever_chuva(m, {"dia": "2026-11-16", "fontes": {"openmeteo": {"chove": 1, "mm": 12}, "inmet": {"chove": 1}}})
        p_nao = ap.prever_chuva(m, {"dia": "2026-11-16", "fontes": {"openmeteo": {"chove": 0, "mm": 0}, "inmet": {"chove": 0}}})
        self.assertGreater(p_sim["prob"], 0.7)
        self.assertLess(p_nao["prob"], 0.3)
        self.assertIn("Brier", ap.explicar_chuva(m))
        print(f"\n[chuva] n=365 Brier modelo={met['brier_modelo']} placar={met['brier_placar']} "
              f"fontes={met['brier_fontes']} média={met['brier_sempre_media']} acerto={met['acerto_modelo']}")

    def test_deterministico(self):
        h = hub_com_chuva(120)
        a = ap.treinar_chuva(ap.dados_chuva(h._db), AGORA)
        b = ap.treinar_chuva(ap.dados_chuva(h._db), AGORA)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_pouco_historico_usa_placar(self):
        h = hub_com_chuva(10)
        m = ap.treinar_chuva(ap.dados_chuva(h._db), AGORA)
        self.assertEqual(m["parametros"]["modo"], "placar")
        p = ap.prever_chuva(m, {"dia": "2026-11-16", "fontes": {"openmeteo": {"chove": 1}, "inmet": {"chove": 0}}})
        self.assertEqual(p["modo"], "placar")
        self.assertTrue(0 < p["prob"] < 1)
        self.assertIn("poucos dias", ap.explicar_chuva(m))

    def test_previsao_de_amanha_pelo_hub(self):
        h = hub_com_chuva(60)
        a = ap.Aprendizado(h)
        h._db.execute("INSERT INTO clima_fonte(fonte,dados,consultado) VALUES('openmeteo',?,?)",
                      (json.dumps({"dias": [{"dia": "2026-11-16", "mm": 15.0, "chove": True}]}), AGORA))
        h._db.commit()
        a.treinar()
        r = a.previsao_chuva()
        self.assertEqual(r["dia"], "2026-11-16")
        self.assertGreater(r["prob"], 0.5)
        self.assertEqual(r["modo"], "logistica")


class TestAnomalias(unittest.TestCase):
    def serie(self, n=100, semente=3, base=40.0, ruido=0.5, passo=300):
        rnd = random.Random(semente)
        t0 = AGORA - n * passo
        return [(t0 + i * passo, round(base + rnd.gauss(0, ruido), 2)) for i in range(n)]

    def test_fora_do_normal_salto_e_travado(self):
        s = self.serie()
        normal = ap.detectar_anomalias({"x-no01|umidade_solo": s}, AGORA)
        self.assertEqual(normal, [])
        pico = s + [(AGORA, 99.0)]               # 5 min depois da última leitura
        tipos = {a["tipo"] for a in ap.detectar_anomalias({"x-no01|umidade_solo": pico}, AGORA)}
        self.assertIn("fora_do_normal", tipos)
        self.assertIn("salto_impossivel", tipos)
        travado = s + [(AGORA + i * 300, 41.0) for i in range(1, ap.K_TRAVADO + 1)]
        tipos = {a["tipo"] for a in ap.detectar_anomalias({"x-no01|temperatura": travado}, AGORA)}
        self.assertIn("travado", tipos)

    def test_bateria_acabando(self):
        pts = [(AGORA - (6 - d / 4) * 86400, 3.90 - 0.02 * (6 - (6 - d / 4))) for d in range(25)]
        pts = [(t, 3.90 - 0.02 * ((t - pts[0][0]) / 86400)) for t, _ in pts]
        t = ap.tendencia_bateria(pts, AGORA)
        self.assertAlmostEqual(t["v_por_dia"], -0.02, places=3)
        # 3,78 V hoje, caindo 0,02 V/dia → ~14 dias até 3,5 V
        self.assertAlmostEqual(t["dias_ate_baixa"], 14.0, delta=0.6)
        lista = ap.detectar_anomalias({"x-no02|bateria": pts}, AGORA)
        self.assertTrue(any(a["tipo"] == "bateria_acabando" for a in lista))

    def test_modelo_treinado_e_ponto_novo(self):
        m = ap.treinar_anomalias({"x-no01|umidade_solo": self.serie()}, AGORA)
        self.assertFalse(ap.prever_anomalia(m, {"ativo": "x-no01", "grandeza": "umidade_solo", "valor": 40.3, "ts": AGORA + 300})["anomalo"])
        r = ap.prever_anomalia(m, {"ativo": "x-no01", "grandeza": "umidade_solo", "valor": 75, "ts": AGORA + 300})
        self.assertTrue(r["anomalo"])
        self.assertIn("réguas", ap.explicar_anomalias(m))


class TestConsumo(unittest.TestCase):
    def amostras(self, n=120, semente=5):
        rnd = random.Random(semente)
        out = []
        for dia in dias_para_tras(n):
            d = datetime.strptime(dia, "%Y-%m-%d")
            temp = 24 + 5 * math.sin(d.timetuple().tm_yday / 58.0) + rnd.gauss(0, 1.5)
            valor = 50 + (10 if d.weekday() >= 5 else 0) + 2.0 * (temp - 24) + rnd.gauss(0, 1.5)
            out.append({"dia": dia, "valor": valor, "temp": temp})
        return out

    def test_regressao_e_desperdicio(self):
        am = self.amostras()
        m = ap.treinar_consumo(am, AGORA)
        self.assertEqual(m["parametros"]["modo"], "regressao")
        self.assertGreater(m["metricas"]["r2"], 0.85)
        self.assertLess(m["metricas"]["sigma"], 2.5)
        sab = ap.prever_consumo(m, {"dia": "2026-11-14", "temp": 24.0})     # sábado
        seg = ap.prever_consumo(m, {"dia": "2026-11-16", "temp": 24.0})
        self.assertAlmostEqual(sab["esperado"] - seg["esperado"], 10.0, delta=2.0)
        normal = ap.prever_consumo(m, {"dia": "2026-11-16", "temp": 24.0, "real": seg["esperado"] + 1})
        self.assertFalse(normal["desperdicio"])
        alto = ap.prever_consumo(m, {"dia": "2026-11-16", "temp": 24.0, "real": seg["esperado"] + 15})
        self.assertTrue(alto["desperdicio"])
        self.assertIn("fim de semana", ap.explicar_consumo(m))
        print(f"\n[consumo] n=120 r2={m['metricas']['r2']} sigma={m['metricas']['sigma']} kWh/dia")

    def test_pouco_dado_usa_media(self):
        m = ap.treinar_consumo(self.amostras(5), AGORA)
        self.assertEqual(m["parametros"]["modo"], "media")
        self.assertIn("esperado", ap.prever_consumo(m, {"dia": "2026-11-16"}))


class TestIrrigacao(unittest.TestCase):
    def pontos(self):
        # regou há 20 h (subiu de 28 para 50) e desde então perde 1 ponto por hora
        t0 = AGORA - 20 * 3600
        antes = [(t0 - 3600, 28.0)]
        return antes + [(t0 + h * 3600, 50.0 - h) for h in range(21)]

    def test_hora_do_limite_e_chuva(self):
        m = ap.treinar_irrigacao(self.pontos(), AGORA)
        self.assertAlmostEqual(m["parametros"]["taxa_h"], 1.0, places=3)
        r = ap.prever_irrigacao(m, {"limite": 15, "prob_chuva": 0.1, "agora": AGORA})
        self.assertEqual(r["acao"], "agendar")
        self.assertAlmostEqual(r["horas_ate_limite"], 15.0, places=1)
        r = ap.prever_irrigacao(m, {"limite": 15, "prob_chuva": 0.8, "agora": AGORA})
        self.assertEqual(r["acao"], "aguardar_chuva")
        self.assertIn("chuva", r["texto"])
        r = ap.prever_irrigacao(m, {"limite": 35, "prob_chuva": 0.1, "agora": AGORA})
        self.assertEqual(r["acao"], "irrigar_agora")
        self.assertIn("perde", ap.explicar_irrigacao(m))

    def test_sem_dado(self):
        m = ap.treinar_irrigacao([(AGORA, 40.0)], AGORA)
        self.assertEqual(ap.prever_irrigacao(m, {"limite": 30})["acao"], "sem_dado")


class TestHubCompleto(unittest.TestCase):
    def test_treino_estado_versoes_e_rotina(self):
        relogio = [AGORA]
        h = hub_com_chuva(40)
        h.relogio = lambda: relogio[0]
        a = ap.Aprendizado(h)
        inserir_medicoes(h, "lugar01-no03", "umidade_solo", TestIrrigacao().pontos())
        inserir_medicoes(h, "lugar01-no03", "bateria", [(AGORA - 3 * 86400 + i * 3600, 4.0 - 0.001 * i) for i in range(72)])
        rnd = random.Random(1)
        inserir_medicoes(h, "lugar01-no90", "energia",
                         [(AGORA - d * 86400 + k * 3600, 2.0 + rnd.random()) for d in range(1, 31) for k in range(0, 24, 6)])
        self.assertTrue(ap.precisa_treinar(a))
        r = a.treinar()
        nomes = {m["nome"] for m in r["modelos"]}
        self.assertTrue({"chuva", "anomalias", "consumo:lugar01-no90|energia", "irrigacao:lugar01-no03"} <= nomes)
        self.assertFalse(ap.precisa_treinar(a))
        est = a.estado()
        self.assertTrue(all(m["explicacao"] for m in est["modelos"]))
        relogio[0] = AGORA + 86400 + 3600        # dia seguinte, depois das 3 h
        self.assertTrue(ap.precisa_treinar(a))
        a.treinar()
        self.assertEqual(ap.carregar(h._db, "chuva")["versao"], 2)
        self.assertIn("recomendacoes", a.irrigacao())
        self.assertTrue(a.consumo()["medidores"])
        self.assertIn("anomalias", a.anomalias())
        ok, _ = h.verificar_cadeia()
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
