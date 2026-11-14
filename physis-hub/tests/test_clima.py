"""Previsão do tempo no computador central (sem internet nos testes: as respostas das fontes são gravadas aqui).

Protege:
1. A localização só aceita pontos no Brasil, acha o código IBGE pelo município e é repassada ao receptor.
2. Cada fonte é lida do jeito dela (Open-Meteo por dia, INMET por período, CEMADEN pelo pluviômetro mais próximo,
   receptor pelo /api/estado original) e uma fonte fora do ar não apaga a última previsão boa.
3. O placar compara o que cada fonte disse sobre amanhã com a chuva medida, e a previsão combinada pesa por isso.
4. Pela rede: /api/clima e a gravação da localização exigem login quando a instalação tem login.
"""
import json
import os
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import gzip
from unittest import mock

from physis_hub import clima as clima_mod
from physis_hub.clima import FUSO, Clima, ler_cemaden, ler_inmet, ler_openmeteo, validar_local
from physis_hub.hub import Hub
from physis_hub.servidor import iniciar

AGORA = datetime(2026, 11, 14, 10, 0, tzinfo=FUSO).timestamp()
HOJE = "2026-11-14"
AMANHA = "2026-11-15"

OPENMETEO = {"daily": {"time": [HOJE, AMANHA, "2026-11-16"], "precipitation_sum": [0.0, 12.4, 0.3],
                       "precipitation_probability_max": [10, 85, 20], "temperature_2m_max": [27.1, 23.0, 25.5],
                       "temperature_2m_min": [16.0, 15.2, 14.8], "et0_fao_evapotranspiration": [4.1, 2.2, 3.9]},
             "hourly": {"time": [], "precipitation": []}}
INMET = {"3303906": {"14/11/2026": {"manha": {"resumo": "Muitas nuvens", "temp_max": 26, "temp_min": 16},
                                    "tarde": {"resumo": "Nublado", "temp_max": 27, "temp_min": 17},
                                    "noite": {"resumo": "Encoberto", "temp_max": 22, "temp_min": 16}},
                     "15/11/2026": {"resumo": "Nublado com pancadas de chuva", "temp_max": 23, "temp_min": 15}}}
# formato real do serviço (conferido em 14/11/2026): sem coordenadas, hora em UTC, "-" = não choveu na janela
CEMADEN = [{"idestacao": 3320, "uf": "RJ", "codibge": 3303906, "cidade": "PETRÓPOLIS", "nomeestacao": "Quitandinha",
            "datahoraUltimovalor": "14/11/26 12:50", "acc1hr": "-", "acc24hr": 8.6, "acc72hr": 20.2},
           {"idestacao": 3324, "uf": "RJ", "codibge": 3303906, "cidade": "PETRÓPOLIS", "nomeestacao": "Pedro do Rio",
            "datahoraUltimovalor": "14/11/26 12:40", "acc1hr": "-", "acc24hr": "-", "acc72hr": 3.1},
           {"idestacao": 3314, "uf": "RJ", "codibge": 3303906, "cidade": "PETRÓPOLIS", "nomeestacao": "Parada",
            "datahoraUltimovalor": "16/03/25 05:10", "acc1hr": 0, "acc24hr": 90.0, "acc72hr": 90.0},
           {"idestacao": 9999, "uf": "RJ", "codibge": 3304557, "cidade": "RIO DE JANEIRO", "nomeestacao": "Longe",
            "datahoraUltimovalor": "14/11/26 12:50", "acc1hr": 1.0, "acc24hr": 40.0, "acc72hr": 41.0}]
LOC = {"lat": -22.505, "lon": -43.183, "uf": "RJ", "ibge": "3303906"}
IBGE = [{"id": 3303906, "nome": "Petrópolis"}, {"id": 3304557, "nome": "Rio de Janeiro"}]
RECEPTOR = {"clima": {"chuva": True, "intens": "light", "precip": 0.8, "valido": True, "hora": "09:55"}}


class Fontes:
    """Faz o papel da internet: devolve a resposta gravada conforme o endereço, ou falha."""
    def __init__(self):
        self.fora = set()
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        for chave, resp in (("open-meteo", OPENMETEO), ("apiprevmet3", INMET), ("cemaden", CEMADEN),
                            ("servicodados.ibge", IBGE), ("/api/estado", RECEPTOR)):
            if chave in url:
                if chave in self.fora:
                    raise urllib.error.URLError("fora do ar")
                return json.loads(json.dumps(resp))
        raise urllib.error.URLError("endereço inesperado: " + url)


class Leitores(unittest.TestCase):
    def test_validar_local(self):
        self.assertIsNone(validar_local({"lat": 40.7, "lon": -74.0})[0])           # Nova York: fora do Brasil
        self.assertIsNone(validar_local({"lat": "x", "lon": 1})[0])
        self.assertIsNone(validar_local({"lat": -22.5, "lon": -43.2, "ibge": "12"})[0])
        loc, _ = validar_local({"lat": "-22.505", "lon": -43.183, "uf": "rj"})
        self.assertEqual((loc["lat"], loc["uf"]), (-22.505, "RJ"))

    def test_openmeteo(self):
        d = ler_openmeteo(OPENMETEO)
        amanha = [x for x in d["dias"] if x["dia"] == AMANHA][0]
        self.assertEqual((amanha["mm"], amanha["prob"], amanha["chove"]), (12.4, 85, True))
        self.assertFalse(d["dias"][2]["chove"])                                   # 0,3 mm não conta como "choveu"

    def test_inmet_periodos_e_dia_unico(self):
        d = ler_inmet(INMET, "3303906")
        self.assertEqual([x["dia"] for x in d["dias"]], [HOJE, AMANHA])
        self.assertFalse(d["dias"][0]["chove"]); self.assertTrue(d["dias"][1]["chove"])
        self.assertEqual((d["dias"][0]["tmax"], d["dias"][0]["tmin"]), (27, 16))

    def test_cemaden_por_municipio(self):
        d = ler_cemaden(CEMADEN, LOC, AGORA)                                    # 10 h em Brasília = 13 h UTC
        self.assertEqual((d["estacao"]["nome"], d["mm_24h"], d["ativas"], d["no_municipio"]), ("Quitandinha", 8.6, 2, 3))
        self.assertEqual(d["mm_1h"], 0.0)                                        # "-" de estação ativa = não choveu
        # a estação parada desde 2025 não conta, mesmo com 90 mm; outra cidade não entra
        d2 = ler_cemaden(CEMADEN, dict(LOC, cemaden_estacao="pedro do rio"), AGORA)
        self.assertEqual((d2["estacao"]["nome"], d2["mm_24h"]), ("Pedro do Rio", 0.0))
        self.assertIsNone(ler_cemaden(CEMADEN, dict(LOC, ibge="1302603"), AGORA)["estacao"])   # Manaus: nenhuma


class RespostaCompactada(unittest.TestCase):
    def test_buscar_abre_gzip(self):
        """O IBGE responde compactado mesmo sem pedir; sem abrir, o município nunca era achado."""
        class R:
            headers = {"Content-Encoding": "gzip"}
            def read(self): return gzip.compress(json.dumps(IBGE).encode())
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch.object(clima_mod.urllib.request, "urlopen", return_value=R()):
            self.assertEqual(clima_mod.buscar_json("https://x")[0]["nome"], "Petrópolis")


class ClimaNoHub(unittest.TestCase):
    def setUp(self):
        self.h = Hub(relogio=lambda: AGORA)
        self.f = Fontes()
        self.enviados = []
        self.c = Clima(self.h, buscar=self.f, receptor_url="http://192.168.4.1",
                       enviar_local=lambda lat, lon: (self.enviados.append((lat, lon)) or (True, "ok")))

    def test_local_acha_ibge_e_vai_ao_receptor(self):
        r = self.c.definir_local({"lat": -22.505, "lon": -43.183, "municipio": "Petropolis", "uf": "RJ"}, "ana")
        self.assertTrue(r["ok"]); self.assertEqual(r["local"]["ibge"], "3303906")    # sem acento também acha
        self.assertEqual(self.enviados, [(-22.505, -43.183)]); self.assertTrue(r["receptor"]["ok"])
        self.assertFalse(self.c.definir_local({"lat": 0, "lon": 0})["ok"])          # oceano: fora do Brasil

    def test_consulta_e_fonte_fora_do_ar_mantem_a_ultima(self):
        self.c.definir_local({"lat": -22.505, "lon": -43.183, "municipio": "Petrópolis", "uf": "RJ"})
        self.assertEqual(self.c.consultar_tudo(), {"receptor": True, "openmeteo": True, "inmet": True, "cemaden": True})
        e = self.c.estado()
        self.assertTrue(e["fontes"]["receptor"]["dados"]["chuva"])
        self.assertTrue(all(e["fontes"][k]["atual"] for k in ("receptor", "openmeteo", "inmet", "cemaden")))
        self.f.fora.add("open-meteo")
        self.assertFalse(self.c.consultar("openmeteo"))
        om = self.c.estado()["fontes"]["openmeteo"]
        self.assertEqual(om["dados"]["dias"][1]["mm"], 12.4)                        # a previsão boa continua
        self.assertIn("fora do ar", om["erro"])

    def test_sem_local_so_o_receptor(self):
        r = self.c.consultar_tudo()
        self.assertEqual(r, {"receptor": True, "openmeteo": False, "inmet": False, "cemaden": False})

    def test_placar_e_combinada(self):
        self.c.definir_local({"lat": -22.505, "lon": -43.183, "municipio": "Petrópolis", "uf": "RJ"})
        self.c.consultar("openmeteo"); self.c.consultar("inmet")
        # as apostas para amanhã ficaram guardadas; amanhã choveu 0 mm: as duas erraram
        self.c.observar(AMANHA, "cemaden", 0.0)
        p = self.c.placar()
        self.assertEqual((p["openmeteo"]["dias"], p["openmeteo"]["acertos"]), (1, 0))
        self.assertEqual((p["inmet"]["dias"], p["inmet"]["acertos"]), (1, 0))
        # o pluviômetro da Physis vale mais que o CEMADEN quando os dois mediram
        self.c.observar(AMANHA, "physis", 5.0)
        self.assertEqual(self.c.placar()["openmeteo"]["acertos"], 1)
        comb = self.c.estado()["combinada"]
        self.assertEqual(comb["dia"], AMANHA); self.assertEqual(comb["chance_chuva"], 1.0)

    def test_aposta_nao_e_corrigida_depois(self):
        self.c.definir_local({"lat": -22.505, "lon": -43.183, "municipio": "Petrópolis", "uf": "RJ"})
        self.c.consultar("openmeteo")
        OPENMETEO["daily"]["precipitation_sum"][1] = 0.0
        try:
            self.c.consultar("openmeteo")
        finally:
            OPENMETEO["daily"]["precipitation_sum"][1] = 12.4
        chove = self.h._db.execute("SELECT chove FROM clima_aposta WHERE fonte='openmeteo'").fetchone()[0]
        self.assertEqual(chove, 1)


class ClimaPelaRede(unittest.TestCase):
    PORTA = 0

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub(relogio=lambda: AGORA)
        cls.f = Fontes()
        cls.clima = Clima(cls.hub, buscar=cls.f)
        # porta 0: o sistema escolhe uma livre (não colide com outros testes nem com a plataforma aberta)
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": True}, clima=cls.clima)
        cls.PORTA = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def chamar(self, metodo, rota, corpo=None, cookie=None):
        h = {"Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = cookie
        req = urllib.request.Request(f"http://127.0.0.1:{self.PORTA}{rota}", method=metodo, headers=h,
                                     data=json.dumps(corpo).encode() if corpo is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode() or "{}"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}"), e.headers

    def test_login_e_fluxo(self):
        self.assertEqual(self.chamar("GET", "/api/clima")[0], 401)
        self.assertEqual(self.chamar("POST", "/api/clima/local", {"lat": -22.5, "lon": -43.2})[0], 401)
        _, _, hd = self.chamar("POST", "/api/conta/criar", {"nome": "Ana", "usuario": "ana", "senha": "senha-bem-longa"})
        ck = hd.get("Set-Cookie").split(";")[0]
        st, r, _ = self.chamar("POST", "/api/clima/local", {"lat": -22.505, "lon": -43.183, "municipio": "Petrópolis", "uf": "RJ"}, ck)
        self.assertEqual((st, r["local"]["ibge"], r["receptor"]), (200, "3303906", None))
        st, r, _ = self.chamar("POST", "/api/clima/local", {"lat": 50, "lon": 10}, ck)
        self.assertEqual(st, 400)
        st, r, _ = self.chamar("POST", "/api/clima/atualizar", {}, ck)
        self.assertEqual(st, 200)
        self.assertTrue(r["consultas"]["openmeteo"]); self.assertFalse(r["consultas"]["receptor"])  # sem receptor configurado
        st, e, _ = self.chamar("GET", "/api/clima", cookie=ck)
        self.assertEqual(e["local"]["municipio"], "Petrópolis")
        self.assertEqual(e["fontes"]["receptor"]["erro"], "receptor não configurado")


if __name__ == "__main__":
    unittest.main()
