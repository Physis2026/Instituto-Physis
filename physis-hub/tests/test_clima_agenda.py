"""Consulta automática da previsão (pedido de 15/11/2026: "monitoramento verde não está atualizado").

Relógio falso e internet falsa: nada sai da máquina. Protege:
1. Ao ligar o hub com local, as fontes do lugar são consultadas sem ninguém clicar em "Consultar agora".
2. Quando o local muda no Início, a previsão do lugar antigo sai e a nova é buscada logo (no próximo passo).
3. Depois, cada fonte no seu ritmo; com erro, a espera dobra (piso e teto), e nunca abaixo do piso da fonte.
4. Sem município/UF, INMET e CEMADEN guardam um erro claro (aparece na tela) em vez de ficar em silêncio.
5. O código IBGE é achado pelo município e UF do Início, uma vez só (sem perguntar ao IBGE a cada consulta).
"""
import json
import unittest
import urllib.error
from datetime import datetime

from physis_hub import clima as clima_mod
from physis_hub.clima import FUSO, Agendador, Clima
from physis_hub.hub import Hub

T0 = datetime(2026, 11, 15, 10, 0, tzinfo=FUSO).timestamp()
OPENMETEO = {"daily": {"time": ["2026-11-15", "2026-11-16"], "precipitation_sum": [0.0, 5.0],
                       "precipitation_probability_max": [10, 80], "temperature_2m_max": [30, 28],
                       "temperature_2m_min": [18, 17], "et0_fao_evapotranspiration": [5, 4]},
             "hourly": {"time": [], "precipitation": []}}
INMET = {"3523602": {"16/11/2026": {"resumo": "Pancadas de chuva", "temp_max": 29, "temp_min": 18}}}
CEMADEN = [{"codibge": 3523602, "cidade": "ITIRAPUÃ", "nomeestacao": "Centro", "datahoraUltimovalor": "15/11/26 12:50",
            "acc1hr": "-", "acc24hr": 1.2, "acc72hr": 3.0}]
IBGE = [{"id": 3523602, "nome": "Itirapuã"}, {"id": 3516200, "nome": "Franca"}]


class InternetFalsa:
    """Responde conforme o endereço; `fora` derruba uma fonte. Guarda cada endereço chamado."""
    def __init__(self):
        self.fora, self.urls = set(), []

    def __call__(self, url):
        self.urls.append(url)
        for chave, resp in (("open-meteo", OPENMETEO), ("apiprevmet3", INMET), ("cemaden", CEMADEN),
                            ("servicodados.ibge", IBGE)):
            if chave in url:
                if chave in self.fora:
                    raise urllib.error.URLError("fora do ar")
                return json.loads(json.dumps(resp))
        raise urllib.error.URLError("endereço inesperado: " + url)

    def quantas(self, chave):
        return sum(1 for u in self.urls if chave in u)


class Base(unittest.TestCase):
    def setUp(self):
        self.t = [T0]
        self.h = Hub(relogio=lambda: self.t[0])
        self.h.instancia = {}                      # sem instancia.json do computador de quem roda os testes
        self.net = InternetFalsa()
        self.c = Clima(self.h, buscar=self.net)
        self.versao = 0

    def inicio(self, **c):
        """Grava o cadastro do Início (physis-perfil.c), como a tela faz."""
        r = self.h.cliente_gravar("physis-perfil", json.dumps({"c": c}), self.versao, "teste")
        self.assertTrue(r["ok"], r)
        self.versao = r["versao"]

    def passo(self, ag, mais_s=0.0):
        self.t[0] += mais_s
        return ag.passo(self.t[0])


class AoLigar(Base):
    def test_com_local_consulta_ao_ligar(self):
        self.inicio(lat=-20.64, lon=-47.22, municipio="Itirapuã", uf="SP", cep="14420-000")
        feitas = self.passo(Agendador(self.c))
        self.assertEqual(feitas, {"openmeteo": "ok", "inmet": "ok", "cemaden": "ok"})   # sem receptor configurado
        e = self.c.estado()["fontes"]
        self.assertTrue(all(e[f]["atual"] for f in ("openmeteo", "inmet", "cemaden")))
        self.assertEqual(self.net.quantas("servicodados.ibge"), 1)        # IBGE achado pelo município, uma vez

    def test_sem_local_erro_claro_e_consulta_quando_o_local_chega(self):
        ag = Agendador(self.c)
        self.assertEqual(self.passo(ag)["openmeteo"], "sem_local")
        self.assertEqual(self.c.estado()["fontes"]["openmeteo"]["erro"], clima_mod.SEM_LOCAL)
        self.assertEqual(self.net.urls, [])
        self.inicio(lat=-20.64, lon=-47.22)                               # só coordenadas, sem município
        feitas = self.passo(ag, 10)
        self.assertEqual(feitas["openmeteo"], "ok")                      # logo depois de gravar o local
        self.assertEqual((feitas["inmet"], feitas["cemaden"]), ("falta_dado", "falta_dado"))
        e = self.c.estado()["fontes"]
        self.assertEqual(e["inmet"]["erro"], "falta município/UF (preencha o CEP no Início)")
        self.assertEqual(e["cemaden"]["erro"], clima_mod.FALTA_MUNICIPIO)
        self.assertIsNone(e["openmeteo"]["erro"])
        # o CEP traz município e UF: INMET e CEMADEN entram no passo seguinte
        self.inicio(lat=-20.64, lon=-47.22, municipio="Itirapua", uf="sp")
        feitas = self.passo(ag, 70)
        self.assertEqual((feitas["inmet"], feitas["cemaden"]), ("ok", "ok"))


class Ritmo(Base):
    def setUp(self):
        super().setUp()
        self.inicio(lat=-20.64, lon=-47.22, municipio="Itirapuã", uf="SP")
        self.ag = Agendador(self.c)
        self.passo(self.ag)

    def test_ritmo_normal(self):
        self.assertEqual(self.passo(self.ag, 10 * 60).get("cemaden"), None)     # 10 min: nada (CEMADEN é a cada 15)
        self.assertEqual(self.passo(self.ag, 5 * 60), {"cemaden": "ok"})        # 15 min
        self.assertNotIn("openmeteo", self.passo(self.ag, 30 * 60))            # 45 min
        self.assertEqual(self.passo(self.ag, 15 * 60).get("openmeteo"), "ok")  # 1 h
        self.assertEqual(self.net.quantas("open-meteo"), 2)

    def test_local_muda_consulta_logo_e_esquece_o_antigo(self):
        self.t[0] += 120
        self.inicio(lat=-22.5, lon=-43.2, municipio="Itirapuã", uf="SP")         # ponto novo no mapa
        feitas = self.passo(self.ag, 10)
        self.assertEqual(feitas.get("openmeteo"), "ok")                       # sem esperar a hora cheia
        self.assertIn("latitude=-22.5", self.net.urls[-3] + self.net.urls[-2] + self.net.urls[-1])

    def test_local_muda_mas_respeita_um_minuto(self):
        self.inicio(lat=-22.5, lon=-43.2, municipio="Itirapuã", uf="SP")
        self.assertEqual(self.passo(self.ag, 20), {})                         # 20 s depois da última ida: ainda não
        self.assertEqual(self.c.estado()["fontes"]["openmeteo"]["dados"], None)   # mas a previsão antiga já saiu
        self.assertEqual(self.passo(self.ag, 45).get("openmeteo"), "ok")

    def test_espera_dobra_com_erro_e_volta_ao_normal(self):
        self.net.fora.add("open-meteo")
        idas = []
        for _ in range(int(14 * 3600 / 60)):                                # 14 h, um passo por minuto
            if self.passo(self.ag, 60).get("openmeteo"):
                idas.append(self.t[0])
        esperas = [round(b - a) for a, b in zip([T0] + idas, idas)]
        self.assertEqual(esperas[0], 3600)                                  # 1ª ida com erro: no ritmo normal
        self.assertEqual(esperas[1:6], [600, 1200, 2400, 4800, 9600])      # 10, 20, 40, 80, 160 min
        self.assertTrue(all(e <= clima_mod.TETO_S["openmeteo"] + 60 for e in esperas))
        self.assertTrue(all(e >= clima_mod.PISO_S["openmeteo"] for e in esperas))
        self.assertIn("fora do ar", self.c.estado()["fontes"]["openmeteo"]["erro"])
        self.assertIsNotNone(self.c.estado()["fontes"]["openmeteo"]["dados"])  # a última previsão boa continua
        self.net.fora.clear()
        for _ in range(int(7 * 3600 / 60)):
            if self.passo(self.ag, 60).get("openmeteo") == "ok":
                break
        self.assertEqual(self.ag.falhas["openmeteo"], 0)

    def test_nunca_abaixo_do_limite_por_hora(self):
        """Mesmo com o local mudando sem parar, no máximo 1 ida por minuto por fonte (Open-Meteo: 600/min, 5.000/h)."""
        for i in range(120):
            self.inicio(lat=-20.0 - i / 100, lon=-47.22, municipio="Itirapuã", uf="SP")
            self.passo(self.ag, 10)
        self.assertLessEqual(self.net.quantas("open-meteo"), 1 + 120 * 10 // 60 + 1)

    def test_piso_vale_depois_de_reiniciar(self):
        """Hub reiniciado logo depois de uma consulta não chama de novo antes do piso (o horário fica no banco)."""
        novo = Agendador(self.c)
        self.assertNotIn("openmeteo", self.passo(novo, 30))
        self.assertEqual(self.passo(novo, 40).get("openmeteo"), "ok")


class Laco(Base):
    def test_rodar_para_e_nao_derruba(self):
        import threading
        self.inicio(lat=-20.64, lon=-47.22, municipio="Itirapuã", uf="SP")
        parar = threading.Event()
        th = threading.Thread(target=clima_mod.rodar, args=(self.c, parar), kwargs={"passo": 0.01}, daemon=True)
        th.start()
        for _ in range(200):
            if self.net.quantas("open-meteo"):
                break
            parar.wait(0.01)
        parar.set()
        th.join(2)
        self.assertFalse(th.is_alive())
        self.assertEqual(self.net.quantas("open-meteo"), 1)                  # relógio parado: uma ida só


if __name__ == "__main__":
    unittest.main()
