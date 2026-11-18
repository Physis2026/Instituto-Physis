"""Frota e combustível (em desenvolvimento; docs/FROTA.md): physis_hub/frota.py e sistema/physis-frota.js.

Protege:
1. Contas: haversine, distância (com salto de GPS e odômetro), litros pela vazão, horas de motor, marcha lenta e consumo.
2. Detector de consumo acima do normal (z robusto com mediana e MAD, EWMA): nenhum alarme falso em dados limpos,
   alarme no valor fora, diz o tamanho da amostra, não decide com poucas amostras nem com MAD zero.
3. Cerca: ponto no polígono (também côncavo) e eventos de saída; queda de nível com o veículo parado.
4. Linha V6 TIPO:VEI (faixas físicas, binários, grandezas physis/1) e o caminho até a frota pelo hub; ponte MQTT.
5. Importação CSV (rastreador e cartão): validada, tudo ou nada, resumo SHA-256 igual com ; ou , e com CRLF ou LF.
6. Paridade com o Carbono: o CO₂e da frota é o do carbono.calcular (combustão móvel), e o medido substitui o digitado.
7. Rotas: sessão, papéis (cliente lê; equipe grava; direção apaga e muda a retenção), CSRF, esquema estrito, comprovante,
   exportação sem o motorista.
8. A tela: contrato com a plataforma, mesmas premissas e constantes do Python, sem internet, aba com selo no painel.
"""
import json
import math
import os
import random
import re
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from physis_hub import adaptador, carbono, frota, mqtt, nucleo, protocolo
from physis_hub import seguranca as seg
from physis_hub import servidor
from physis_hub.clima import FUSO
from physis_hub.hub import Hub

RAIZ = Path(__file__).resolve().parents[2]
JS = RAIZ / "sistema" / "physis-frota.js"
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
T0 = datetime(2026, 11, 10, 8, 0, tzinfo=FUSO).timestamp()


def reta(n, passo_s=60, lat0=-22.5, lon0=-43.18, kmh=36.0, **extra):
    """n pontos andando para o norte a kmh."""
    dlat = kmh * passo_s / 3600 / 110.574
    return [dict({"ts": T0 + i * passo_s, "lat": lat0 + i * dlat, "lon": lon0, "vel": kmh}, **extra) for i in range(n)]


class Contas(unittest.TestCase):
    def test_haversine(self):
        self.assertAlmostEqual(frota.haversine_km(0, 0, 0, 1), 111.195, places=2)          # 1° no equador
        la1, lo1, la2, lo2 = (math.radians(x) for x in (-22.9068, -43.1729, -23.5505, -46.6333))   # Rio–SP pela lei dos cossenos
        cos = math.sin(la1) * math.sin(la2) + math.cos(la1) * math.cos(la2) * math.cos(lo2 - lo1)
        self.assertAlmostEqual(frota.haversine_km(-22.9068, -43.1729, -23.5505, -46.6333), frota.R_TERRA_KM * math.acos(cos), places=6)
        self.assertEqual(frota.haversine_km(-22.5, -43.2, -22.5, -43.2), 0.0)

    def test_distancia_salto_e_odometro(self):
        ps = reta(61)                                        # 1 h a 36 km/h
        d = frota.distancia(ps, 200)
        self.assertAlmostEqual(d["km"], 36.0, delta=0.5)                 # 110,574 km por grau × esfera de 6.371 km
        self.assertEqual((d["fonte"], d["descartados"]), ("gps", 0))
        ruim = [dict(p) for p in ps]
        ruim[30]["lat"] += 1.0                               # salto de 110 km em 1 min
        d2 = frota.distancia(ruim, 200)
        self.assertEqual(d2["descartados"], 1)
        self.assertAlmostEqual(d2["km"], d["km"], delta=0.02)
        com_odo = [dict(p, odo=1000 + i * 0.6) for i, p in enumerate(ps)]
        d3 = frota.distancia(com_odo, 200)
        self.assertEqual(d3["fonte"], "odometro")
        self.assertAlmostEqual(d3["km"], 36.0, places=6)

    def test_vazao_horas_e_consumo(self):
        ps = reta(61, flx=10.0, ign=1)
        self.assertAlmostEqual(frota.litros_do_fluxo(ps), 10.0, places=6)    # 10 L/h por 1 h
        buraco = ps[:30] + [dict(p, ts=p["ts"] + 3600) for p in ps[30:]]     # 1 h sem leitura não entra
        self.assertAlmostEqual(frota.litros_do_fluxo(buraco), 10.0 * 59 / 60, places=6)
        self.assertIsNone(frota.litros_do_fluxo(reta(5)))
        self.assertAlmostEqual(frota.horas_motor(ps), 1.0, places=6)
        self.assertAlmostEqual(frota.horas_motor([dict(p, hor=100 + i / 60) for i, p in enumerate(ps)]), 1.0, places=6)
        c = frota.consumo(10.0, 36.0, 1.0)
        self.assertAlmostEqual(c["l_100km"], 27.777, places=2)
        self.assertAlmostEqual(c["l_h"], 10.0)
        self.assertAlmostEqual(c["km_l"], 3.6)
        self.assertEqual(frota.consumo(None, 0, 0), {"l_100km": None, "l_h": None, "km_l": None})
        # consumo do dia: litros e km dos MESMOS trechos (o trecho sem vazão não entra nos dois)
        sem_vazao = [dict(p, flx=None) for p in reta(31, lat0=-22.4)]
        dia = ps + [dict(p, ts=p["ts"] + 7200) for p in sem_vazao]
        tv = frota.trechos_com_vazao(dia, 200)
        self.assertAlmostEqual(tv["litros"], 10.0, places=6)
        self.assertAlmostEqual(tv["km"], frota.distancia(ps, 200)["km"], places=6)
        self.assertAlmostEqual(tv["horas"], 1.0, places=6)
        d = frota.por_dia(dia, 200, 3.0, 20.0)[frota.dia_de(T0)]
        self.assertAlmostEqual(d["l_100km"], 10.0 / tv["km"] * 100, places=6)
        self.assertGreater(d["km"], tv["km"])                       # a distância do dia mostra tudo

    def test_marcha_lenta(self):
        parado = [{"ts": T0 + i * 60, "lat": -22.5, "lon": -43.18, "vel": 0.0, "flx": 2.0} for i in range(31)]
        andando = reta(10, kmh=40, flx=12.0)
        ml = frota.marcha_lenta(andando + [dict(p, ts=p["ts"] + 600) for p in parado], 3.0, 20.0)
        self.assertAlmostEqual(ml["horas"], 0.5, places=6)
        self.assertEqual(len(ml["eventos"]), 1)
        self.assertAlmostEqual(ml["eventos"][0]["min"], 30.0)
        desligado = [dict(p, flx=0.0) for p in parado]
        self.assertEqual(frota.marcha_lenta(desligado, 3.0, 20.0)["horas"], 0.0)
        curto = parado[:11]                                   # 10 min: soma horas, mas não alerta
        r = frota.marcha_lenta(curto, 3.0, 20.0)
        self.assertEqual(len(r["eventos"]), 0)
        self.assertAlmostEqual(r["horas"], 10 / 60)


class Detector(unittest.TestCase):
    def test_sem_alarme_falso_em_dados_limpos(self):
        for semente in range(20):
            rnd = random.Random(semente)
            amostras = [30 + rnd.gauss(0, 1.0) for _ in range(90)]
            falsos = [i for i in range(8, len(amostras))
                      if frota.anomalia_consumo(amostras[i], amostras[:i], 3.5, 8, 0.3, 15.0)["anomalo"]]
            self.assertEqual(falsos, [], f"semente {semente}")

    def test_alarme_no_valor_fora_e_amostra_dita(self):
        rnd = random.Random(7)
        hist = [30 + rnd.gauss(0, 1.0) for _ in range(20)]
        r = frota.anomalia_consumo(45.0, hist, 3.5, 8, 0.3, 15.0)
        self.assertTrue(r["anomalo"])
        self.assertFalse(frota.anomalia_consumo(33.8, hist, 3.5, 8, 0.3, 15.0)["anomalo"])   # z alto, mas menos de 15 % acima
        self.assertEqual(r["n"], 20)
        self.assertGreater(r["z"], 3.5)
        self.assertAlmostEqual(r["mediana"], sorted(hist)[9] / 2 + sorted(hist)[10] / 2)
        self.assertIsNotNone(r["ewma"])
        self.assertFalse(frota.anomalia_consumo(20.0, hist, 3.5, 8, 0.3)["anomalo"])     # abaixo do normal não alerta

    def test_aprendendo_e_mad_zero(self):
        r = frota.anomalia_consumo(90.0, [30.0] * 5, 3.5, 8, 0.3)
        self.assertFalse(r["anomalo"])
        self.assertIn("5 de 8", r["motivo"])
        r = frota.anomalia_consumo(90.0, [30.0] * 12, 3.5, 8, 0.3)
        self.assertFalse(r["anomalo"])
        self.assertIn("MAD zero", r["motivo"])

    def test_ewma(self):
        self.assertAlmostEqual(frota.normal_aprendido([10, 20], 0.3)["ewma"], 13.0)


class CercaEQueda(unittest.TestCase):
    QUAD = [[-22.51, -43.19], [-22.51, -43.17], [-22.49, -43.17], [-22.49, -43.19]]

    def test_ponto_no_poligono(self):
        self.assertTrue(frota.ponto_no_poligono(-22.50, -43.18, self.QUAD))
        self.assertFalse(frota.ponto_no_poligono(-22.52, -43.18, self.QUAD))
        self.assertFalse(frota.ponto_no_poligono(-22.50, -43.16, self.QUAD))
        U = [[0, 0], [0, 3], [3, 3], [3, 2], [1, 2], [1, 1], [3, 1], [3, 0]]          # "C" côncavo: o vão fica fora
        self.assertTrue(frota.ponto_no_poligono(0.5, 1.5, U))
        self.assertFalse(frota.ponto_no_poligono(1.5, 2.0 - 0.5, U))
        self.assertFalse(frota.ponto_no_poligono(0, 0, [[0, 0], [1, 1]]))

    def test_saida_da_cerca(self):
        ps = reta(40, lat0=-22.505, kmh=60)                   # sai pelo norte (-22.49)
        cerca = {"id": 3, "nome": "Sede", "poligono": self.QUAD, "veiculos": [], "ativa": True}
        ev = frota.saidas_da_cerca(ps, [cerca], 1)
        self.assertEqual(len(ev), 1)
        self.assertGreater(ev[0]["lat"], -22.49)
        self.assertEqual(frota.saidas_da_cerca(ps, [dict(cerca, ativa=False)], 1), [])
        self.assertEqual(frota.saidas_da_cerca(ps, [dict(cerca, veiculos=[2])], 1), [])

    def test_queda_de_nivel_parado(self):
        base = {"lat": -22.5, "lon": -43.18, "vel": 0.0}
        caindo = [dict(base, ts=T0 + i * 300, niv=60 - i * 1.0) for i in range(10)]          # 9 % em 45 min, sem vazão
        ev = frota.quedas_sem_andar(caindo, 5.0, 0.2, 3.0, 300)
        self.assertEqual(len(ev), 1)
        self.assertAlmostEqual(ev[0]["queda_pct"], 9.0)                 # um evento só, a janela inteira
        self.assertAlmostEqual(ev[0]["litros"], 27.0)
        # o mesmo nível caindo, mas a vazão mediu o gasto (motor ligado parado): não é furto
        com_vazao = [dict(p, flx=24.0) for p in caindo]       # 24 L/h × 5 min = 2 L = 0,67 % por passo
        self.assertEqual(frota.quedas_sem_andar(com_vazao, 5.0, 0.2, 3.0, 300), [])
        andando = [dict(p, lat=p["lat"] + i * 0.002) for i, p in enumerate(caindo)]   # andou: consumo normal
        self.assertEqual(frota.quedas_sem_andar(andando, 5.0, 0.2, 3.0, 300), [])
        estavel = [dict(base, ts=T0 + i * 300, niv=60 + (i % 2) * 0.3) for i in range(30)]
        self.assertEqual(frota.quedas_sem_andar(estavel, 5.0, 0.2, 3.0, 300), [])


class V6(unittest.TestCase):
    LINHA = "ID:61,TIPO:VEI,LAT:-22.50512,LON:-43.17845,VEL:42.5,RUMO:183,FLX:12.40,NIV:63.5,HOR:1234.5,ODO:45678.9,IGN:1,GPS:1,BAT:3.95,TS:1794600000"

    def test_linha_vei(self):
        self.assertLessEqual(len(self.LINHA + ",RSSI:-80.0,SNR:7.5,SIM:SIMULADO/teste"), protocolo.LINHA_MAX)
        ok, motivo, c = protocolo.validar_telemetria(self.LINHA)
        self.assertTrue(ok, motivo)
        self.assertNotIn("_FORA", c)
        e = adaptador.interpretar(c)
        self.assertEqual((e["tipo"], e["lat"], e["vel"], e["rumo"], e["flx"], e["niv"], e["hor"], e["odo"], e["ign"], e["gps"]),
                         ("VEI", -22.50512, 42.5, 183.0, 12.4, 63.5, 1234.5, 45678.9, True, True))
        g = {m["grandeza"]: m for m in adaptador.adaptar(c, "org-teste", "l")}
        for k in ("latitude", "longitude", "velocidade", "rumo", "vazao_combustivel", "nivel_combustivel", "horimetro", "odometro"):
            self.assertIn(k, g)
            self.assertIn(k, nucleo.FAIXAS)
        self.assertEqual(g["vazao_combustivel"]["unidade"], "L/h")
        self.assertIn("VEI", adaptador.TIPOS)

    def test_faixas_fisicas_e_binarios(self):
        ok, _, c = protocolo.validar_telemetria("ID:61,TIPO:VEI,LAT:-95,LON:-43.1,VEL:-3,RUMO:361,NIV:101,FLX:-1,IGN:2,GPS:1,TS:1794600000")
        self.assertTrue(ok)
        self.assertEqual(set(c["_FORA"].split(",")), {"LAT", "VEL", "RUMO", "NIV", "FLX", "IGN"})
        self.assertEqual(c["LON"], "-43.1")
        ok, _, c = protocolo.validar_telemetria("ID:61,TIPO:VEI,LAT:-22.5,LON:-43.1,GPS:0,TS:1794600000")
        g = {m["grandeza"] for m in adaptador.adaptar(c, "org-teste", "l")}
        self.assertNotIn("latitude", g)                       # GPS:0 = posição não confiável
        # fora do VEI as chaves do veículo não ganham faixa (NIV do comedouro segue igual)
        ok, _, c = protocolo.validar_telemetria("ID:05,TIPO:COM,NIV:150,PORC:1,TS:1794600000")
        self.assertNotIn("_FORA", c)

    def test_hub_entrega_a_frota(self):
        h = Hub(relogio=lambda: 1794600100)
        f = frota.Frota(h, fatores=carbono.carregar())
        h.frota_receptor = f.receber_v6
        h.receber_lote(self.LINHA + ",SIM:SIMULADO/teste")
        self.assertEqual(f._db.execute("SELECT no, veiculo, origem FROM frota_ponto").fetchall(), [(61, None, "v6-simulado")])
        self.assertEqual(f.gravar_veiculo({"tipo": "caminhao", "placa": "abc1d23", "combustivel": "diesel_b", "no": 61}, "eq")["ok"], True)
        self.assertEqual(f._db.execute("SELECT veiculo FROM frota_ponto").fetchone()[0], 1)      # pontos antigos passam ao veículo
        h.receber_lote(self.LINHA.replace("TS:1794600000", "TS:1794600060"))
        self.assertEqual(f._db.execute("SELECT COUNT(*) FROM frota_ponto WHERE veiculo=1").fetchone()[0], 2)
        e = f.estado()
        self.assertEqual(e["veiculos"][0]["placa"], "ABC1D23")
        self.assertAlmostEqual(e["veiculos"][0]["analise"]["ultima"]["lat"], -22.50512)
        self.assertEqual(f.gravar_veiculo({"tipo": "carro", "placa": "X", "combustivel": "gasolina_c", "no": 61}, "eq")["ok"], False)

    def test_ponte_mqtt(self):
        p = mqtt.Ponte([{"no": "trator-1", "id": 61, "tipo": "veiculo", "lat": "latitude", "lon": "longitude", "niv": "nivel",
                         "ign": "ignicao"}, {"no": "obd", "id": 62, "tipo": "veiculo", "json": "dados"}], relogio=lambda: 1794600000)
        self.assertEqual(p.mensagem("trator-1/sensor/latitude/state", "-22.5"), ([], []))       # espera a longitude
        self.assertEqual(p.mensagem("trator-1/binary_sensor/ignicao/state", "ON"), ([], []))
        linhas, pub = p.mensagem("trator-1/sensor/longitude/state", "-43.18")
        self.assertEqual(pub, [])
        ok, _, c = protocolo.validar_telemetria(linhas[0])
        self.assertTrue(ok)
        self.assertEqual((c["TIPO"], c["IGN"], c["LAT"]), ("VEI", "1", "-22.500000"))
        linhas, _ = p.mensagem("obd/sensor/dados/state", '{"lat": -22.4, "lon": -43.1, "vel": 30, "flx": 9.5, "odo": 1200}')
        self.assertIn("FLX:9.50", linhas[0])
        self.assertEqual(p.mensagem("obd/sensor/dados/state", "não é json"), ([], []))
        self.assertEqual(p.comando("CMD:61:IRR1:1"), [])                                          # só leitura
        with self.assertRaises(ValueError):
            mqtt.Ponte([{"no": "x", "id": 63, "tipo": "veiculo"}])


class Banco(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.agora = datetime(2026, 11, 18, 12, 0, tzinfo=FUSO).timestamp()
        self.h = Hub(relogio=lambda: self.agora)
        self.f = frota.Frota(self.h, pasta=self.dir.name, fatores=carbono.carregar())
        self.v = self.f.gravar_veiculo({"tipo": "trator", "placa": "TR-02", "combustivel": "diesel_b", "tanque_l": 120}, "eq")["id"]

    def tearDown(self):
        self.dir.cleanup()

    CSV = ("data_hora;lat;lon;vel;flx;niv\n2026-11-17 08:00;-22,5000;-43,1800;6,0;9,0;80\n"
           "2026-11-17 08:01;-22,5008;-43,1800;6,0;9,5;79,9\n2026-11-17 08:02;-22,5016;-43,1800;6,0;9,2;79,8\n")

    def test_importar_rastreador_tudo_ou_nada(self):
        r = self.f.importar({"veiculo": self.v, "tipo": "rastreador", "csv": self.CSV, "simular": True}, "eq")
        self.assertTrue(r["ok"] and r["simulado"])
        self.assertEqual(r["linhas"], 3)
        self.assertEqual(self.f._db.execute("SELECT COUNT(*) FROM frota_ponto").fetchone()[0], 0)
        virgula = self.CSV.replace(",", ".").replace(";", ",").replace("\n", "\r\n")
        self.assertEqual(self.f.importar({"veiculo": self.v, "tipo": "rastreador", "csv": virgula, "simular": True}, "eq")["resumo"], r["resumo"])
        ruim = self.CSV + "2026-11-17 08:03;-95;-43,18;6;9;79\n"
        r2 = self.f.importar({"veiculo": self.v, "tipo": "rastreador", "csv": ruim}, "eq")
        self.assertFalse(r2["ok"])
        self.assertIn("linha 5", r2["erros"][0])
        self.assertEqual(self.f._db.execute("SELECT COUNT(*) FROM frota_ponto").fetchone()[0], 0)        # nada gravado
        r3 = self.f.importar({"veiculo": self.v, "tipo": "rastreador", "csv": self.CSV, "nome": "rastreador.csv"}, "eq")
        self.assertEqual((r3["ok"], r3["novas"]), (True, 3))
        self.assertEqual(self.f.importar({"veiculo": self.v, "tipo": "rastreador", "csv": self.CSV}, "eq")["novas"], 0)  # sem duplicar
        self.assertEqual(len(r3["arquivo_sha256"]), 64)
        for csv_ruim, trecho in (("lat;lon\n1;2\n", "faltam"), ("data_hora;lat;lon;x\n", "desconhecidas"), ("", "vazio"),
                                 ("data_hora;lat;lon\n2026-13-01 08:00;1;2\n", "linha 2")):
            r = self.f.importar({"veiculo": self.v, "tipo": "rastreador", "csv": csv_ruim}, "eq")
            self.assertFalse(r["ok"])
            self.assertIn(trecho, " ".join(r["erros"]))

    def test_importar_cartao(self):
        txt = "data;litros;preco_l;horimetro;motorista\n2026-11-01;80,5;6,19;1500;M03\n2026-11-08;75;;1510;\n"
        r = self.f.importar({"veiculo": self.v, "tipo": "cartao", "csv": txt}, "eq")
        self.assertTrue(r["ok"], r)
        ab = self.f.abastecimentos()
        self.assertEqual([(a["litros"], a["preco_fonte"]) for a in sorted(ab, key=lambda a: a["data"])], [(80.5, "cartao"), (75.0, "")])
        futuro = "data;litros\n2027-01-01;10\n"
        self.assertFalse(self.f.importar({"veiculo": self.v, "tipo": "cartao", "csv": futuro}, "eq")["ok"])
        nome = "data;litros;motorista\n2026-11-02;10;João da Silva\n"
        self.assertFalse(self.f.importar({"veiculo": self.v, "tipo": "cartao", "csv": nome}, "eq")["ok"])     # só código

    def test_abastecimento_preco_com_fonte_e_aviso_do_tanque(self):
        self.assertFalse(self.f.abastecer({"veiculo": self.v, "data": "2026-11-17", "litros": 50, "preco_l": 6.0}, "eq")["ok"])
        r = self.f.abastecer({"veiculo": self.v, "data": "2026-11-17", "litros": 150, "preco_l": 6.0, "preco_fonte": "nota"}, "eq")
        self.assertTrue(r["ok"])
        self.assertTrue(r["avisos"])
        self.assertEqual(frota.custos_por_mes(self.f.abastecimentos()), {"2026-11": {"litros": 150.0, "custo": 900.0, "sem_preco": 0}})

    def test_retencao_e_lgpd(self):
        self.f.abastecer({"veiculo": self.v, "data": "2026-11-17", "litros": 50, "motorista": "M03"}, "eq")
        for d in (400, 10):
            self.f._db.execute("INSERT INTO frota_ponto(chave,veiculo,ts,lat,lon,origem) VALUES(?,?,?,?,?,?)",
                               (f"v{self.v}", self.v, self.agora - d * 86400, -22.5, -43.18, "v6"))
        r = self.f.configurar({"retencao_dias": 365}, "dir")
        self.assertEqual(r["pontos_apagados"], 1)
        self.assertEqual(self.f.estado()["abastecimentos"][0]["motorista"], "")
        self.assertEqual(self.f.estado(completo=True)["abastecimentos"][0]["motorista"], "M03")
        txt, _ = self.f.exportar_csv("abastecimentos")
        self.assertNotIn("M03", txt)
        self.assertIn("M03", self.f.exportar_csv("abastecimentos", com_motorista=True)[0])
        self.assertIn("LGPD", self.f.estado()["aviso_lgpd"])

    def test_comprovante(self):
        pdf = b"%PDF-1.4\n" + b"x" * 100
        r = self.f.comprovante_por(self.v, "nota.pdf", pdf, "eq")
        self.assertTrue(r["ok"])
        self.assertEqual(self.f.comprovante(r["id"])[2], pdf)
        self.assertFalse(self.f.comprovante_por(self.v, "nota.pdf", b"MZ\x90\x00" + b"x" * 50, "eq")["ok"])
        self.assertFalse(self.f.comprovante_por(self.v, "nota.png", pdf, "eq")["ok"])
        self.assertFalse(self.f.comprovante_por(self.v, "a.pdf", b"%PDF-" + b"x" * frota.ARQ_MAX, "eq")["ok"])
        (Path(self.dir.name) / self.f._db.execute("SELECT arquivo FROM frota_arquivo").fetchone()[0]).write_bytes(b"%PDF-mexido")
        self.assertIsNone(self.f.comprovante(r["id"]))         # mexido no disco: não entrega


class ParidadeCarbono(unittest.TestCase):
    def setUp(self):
        self.F = carbono.carregar()

    def test_mesmo_caminho_do_carbono(self):
        for comb in frota.COMBUSTIVEIS:
            with self.subTest(comb=comb):
                e = frota.co2e(comb, 1000.0, self.F)
                R = carbono.calcular({"v": 2, "movel": [{"comb": comb, "qtd": "1000"}]}, {}, self.F)
                t = sum(l["t"] for l in R["linhas"] if l["fonte"] == "movel")
                self.assertAlmostEqual(e["t"], t, places=12)
                self.assertAlmostEqual(e["bio_t"], sum(l["bio_t"] for l in R["linhas"] if l["fonte"] == "movel"), places=12)
                self.assertIn(comb, {**self.F["combustiveis"], **self.F["misturas"]})

    def test_medido_substitui_o_digitado(self):
        vs = [{"id": 1, "combustivel": "diesel_b"}, {"id": 2, "combustivel": "gasolina_c"}, {"id": 3, "combustivel": "diesel_b"}]
        ab = [{"veiculo": 1, "data": "2026-03-01", "litros": 100.0}, {"veiculo": 1, "data": "2025-12-30", "litros": 999.0},
              {"veiculo": 2, "data": "2026-05-01", "litros": 40.0}]
        linhas = frota.para_carbono(vs, ab, "2026", {3: 55.0, 2: 10.0})       # 3 sem abastecimento: entra pela vazão
        self.assertEqual([(x["comb"], x["qtd"], x["q"]) for x in linhas], [("diesel_b", 155.0, "medido"), ("gasolina_c", 40.0, "medido")])
        self.assertIn("1 abastecimento de 2026", linhas[0]["fonte"])
        self.assertIn("55 L pela vazão", linhas[0]["fonte"])
        digitado = {"v": 2, "movel": [{"comb": "diesel_b", "qtd": "5000", "q": "estimado"}]}
        R = carbono.calcular(digitado, {"frota_movel": linhas}, self.F)
        movel = [l for l in R["linhas"] if l["fonte"] == "movel"]
        self.assertEqual(len(movel), 2)
        self.assertTrue(all(l["q"] == "medido" for l in movel))
        esperado = frota.co2e("diesel_b", 155.0, self.F)["t"] + frota.co2e("gasolina_c", 40.0, self.F)["t"]
        self.assertAlmostEqual(sum(l["t"] for l in movel), esperado, places=12)
        R2 = carbono.calcular(dict(digitado, movel_auto=False), {"frota_movel": linhas}, self.F)     # a caixa desmarcada: o digitado
        self.assertAlmostEqual(sum(l["t"] for l in R2["linhas"] if l["fonte"] == "movel"), frota.co2e("diesel_b", 5000.0, self.F)["t"])
        R3 = carbono.calcular(digitado, {}, self.F)                                                     # sem frota: o digitado
        self.assertAlmostEqual(R3["e1"], R2["e1"])

    def test_simulado_nao_entra(self):
        h = Hub(relogio=lambda: datetime(2026, 11, 18, 12, 0, tzinfo=FUSO).timestamp())
        f = frota.Frota(h, fatores=self.F)
        v = f.gravar_veiculo({"tipo": "caminhao", "placa": "SIM", "combustivel": "diesel_b", "no": 70}, "eq")["id"]
        t = datetime(2026, 11, 17, 8, 0, tzinfo=FUSO).timestamp()
        for i in range(30):
            f._db.execute("INSERT INTO frota_ponto(chave,veiculo,ts,lat,lon,flx,origem) VALUES(?,?,?,?,?,?,?)",
                          (f"v{v}", v, t + i * 60, -22.5, -43.18, 20.0, "v6-simulado"))
        self.assertEqual(f.estado()["para_carbono"], [])

    def test_js_usa_o_mesmo_caminho(self):
        cjs = (RAIZ / "sistema" / "physis-carbono.js").read_text(encoding="utf-8")
        self.assertIn("ctx.frota_movel", cjs)
        self.assertIn("c.movel_auto !== false", cjs)
        self.assertIn("FROTA.paraCarbono(ano)", cjs)
        self.assertIn('"biodiesel","diesel"]', cjs)
        fjs = JS.read_text(encoding="utf-8")
        self.assertIn("PhysisCarbono", fjs)
        self.assertIn('movel:[{ comb, qtd: String(litros || 0), q:"medido" }]', fjs)
        self.assertIn("ctx[\"frota_movel\"] if med_frota", (RAIZ / "physis-hub" / "physis_hub" / "carbono.py").read_text(encoding="utf-8"))


class Rotas(unittest.TestCase):
    SENHAS = {"dir": "frase-longa-da-direcao-1", "eq": "frase-longa-da-equipe-1", "cli": "frase-longa-do-cliente-1"}

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        os.environ["PHYSIS_FROTA_PASTA"] = cls.dir.name
        cls.hub = Hub(org="frota-rotas")
        cls.srv = servidor.iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": False})
        cls.porta = cls.srv.server_address[1]
        h = cls.hub
        h.criar_conta("Direção", "dir@physis.example", cls.SENHAS["dir"])
        adm = h.sessao(h.entrar("dir@physis.example", cls.SENHAS["dir"])["token"])
        h.criar_conta("Equipe", "eq@physis.example", cls.SENHAS["eq"], adm["id"], papel="operador")
        h.criar_conta("Cliente", "cli@fazenda.example", cls.SENHAS["cli"], adm["id"], papel="cliente")
        cls.s = {}
        for k, u in (("dir", "dir@physis.example"), ("eq", "eq@physis.example"), ("cli", "cli@fazenda.example")):
            tk = h.entrar(u, cls.SENHAS[k])["token"]
            cls.s[k] = ("physis_sessao=" + tk, seg.csrf_de(h, tk))

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        os.environ.pop("PHYSIS_FROTA_PASTA", None)
        cls.dir.cleanup()

    def c(self, metodo, rota, corpo=None, quem=None, csrf=True, bruto=None, tipo="application/json"):
        h = {"Content-Type": tipo}
        if quem:
            h["Cookie"] = self.s[quem][0]
            if csrf is True:
                h["X-Physis-CSRF"] = self.s[quem][1]
            elif csrf:
                h["X-Physis-CSRF"] = csrf
        dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", data=dados, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                b = r.read()
                return r.status, (json.loads(b or b"{}") if "json" in (r.headers.get("Content-Type") or "") else b)
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (json.loads(b or b"{}") if "json" in (e.headers.get("Content-Type") or "") else b)

    def test_papeis_csrf_e_esquema(self):
        V = {"tipo": "carro", "placa": "RTA1B22", "combustivel": "gasolina_c", "tanque_l": 50, "motorista": "M07"}
        self.assertEqual(self.c("GET", "/api/frota/estado")[0], 401)
        self.assertEqual(self.c("POST", "/api/frota/veiculo", V, "cli")[0], 403)                 # cliente só lê
        st, j = self.c("POST", "/api/frota/veiculo", V, "eq", csrf="token-errado")
        self.assertEqual((st, j.get("csrf")), (403, True))
        self.assertEqual(self.c("POST", "/api/frota/veiculo", dict(V, campo_estranho=1), "eq")[0], 400)
        st, j = self.c("POST", "/api/frota/veiculo", V, "eq")
        self.assertEqual(st, 200, j)
        vid = j["id"]
        st, j = self.c("POST", "/api/frota/abastecimento", {"veiculo": vid, "data": "2026-11-01", "litros": 30.5,
                                                          "preco_l": 6.29, "preco_fonte": "nota", "motorista": "M07"}, "eq")
        self.assertEqual(st, 200, j)
        st, j = self.c("GET", "/api/frota/estado", quem="cli")
        self.assertEqual(st, 200)
        self.assertEqual(j["veiculos"][0]["motorista"], "")                                       # LGPD: sem o código
        self.assertEqual(j["abastecimentos"][0]["motorista"], "")
        self.assertEqual(self.c("GET", "/api/frota/estado?motoristas=1", quem="dir")[1]["abastecimentos"][0]["motorista"], "M07")
        self.assertEqual(self.c("GET", "/api/frota/exportar?tipo=abastecimentos", quem="cli")[0], 403)
        st, b = self.c("GET", "/api/frota/exportar?tipo=abastecimentos", quem="eq")
        self.assertEqual(st, 200)
        self.assertNotIn(b"M07", b)
        self.assertEqual(self.c("GET", "/api/frota/exportar?tipo=abastecimentos&motoristas=1", quem="eq")[0], 403)
        self.assertEqual(self.c("POST", "/api/frota/config", {"retencao_dias": 90}, "eq")[0], 403)     # só a direção
        self.assertEqual(self.c("POST", "/api/frota/config", {"retencao_dias": 90}, "dir")[0], 200)
        self.assertEqual(self.c("POST", "/api/frota/veiculo/remover", {"id": vid}, "eq")[0], 403)
        st, j = self.c("POST", "/api/frota/cerca", {"nome": "Sede", "poligono": [[-22.51, -43.19], [-22.51, -43.17], [-22.49, -43.17]]}, "eq")
        self.assertEqual(st, 200, j)
        self.assertEqual(self.c("POST", "/api/frota/cerca", {"nome": "Ruim", "poligono": [[0, 0], [1, 1]]}, "eq")[0], 400)
        st, j = self.c("GET", f"/api/frota/rota?veiculo={vid}&dia=2026-11-01", quem="cli")
        self.assertEqual((st, j["pontos"]), (200, []))
        st, j = self.c("POST", f"/api/frota/comprovante?veiculo={vid}&nome=nota.pdf", None, "eq", bruto=b"%PDF-1.4 teste", tipo="application/pdf")
        self.assertEqual(st, 200, j)
        self.assertEqual(self.c("GET", f"/api/frota/comprovante/{j['id']}", quem="cli")[0], 403)      # só a equipe
        self.assertEqual(self.c("GET", f"/api/frota/comprovante/{j['id']}", quem="eq")[1], b"%PDF-1.4 teste")
        st, j = self.c("POST", "/api/frota/importar", {"veiculo": vid, "tipo": "rastreador", "csv": "data_hora;lat;lon\n2026-11-01 08:00;-22,5;-43,18\n"}, "eq")
        self.assertEqual((st, j.get("novas")), (200, 1))
        self.assertEqual(self.c("GET", "/api/frota/nada", quem="eq")[0], 404)

    def test_linha_vei_chega_pela_rota_dos_aparelhos(self):
        st, j = self.c("POST", "/api/frota/veiculo", {"tipo": "trator", "placa": "TR-9", "combustivel": "diesel_b", "no": 77}, "eq")
        self.assertEqual(st, 200, j)
        st, _ = self.c("POST", "/api/v6/linha", None, bruto=V6.LINHA.replace("ID:61", "ID:77").encode(), tipo="text/plain")
        self.assertEqual(st, 200)
        est = self.c("GET", "/api/frota/estado", quem="cli")[1]
        v = next(x for x in est["veiculos"] if x["placa"] == "TR-9")
        self.assertEqual(v["analise"]["ultima"]["niv"], 63.5)


@unittest.skipUnless(JS.is_file(), "sistema/physis-frota.js fica só no repositório")
class Tela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_contrato_e_sem_internet(self):
        for x in ("window.FROTA = {", "window.telaFrota = telaFrota", "window.FROTA_I18N = {", "window.FROTA_I18N_RX = [",
                  "<h1>Frota e combustível</h1>", "api/frota/estado", "api/frota/rota", "aria-pressed", "role=\"group\"",
                  "SIMULADO", "LGPD", "__frEventos", "<caption>", "data-fr-mapa", "ArrowLeft"):
            self.assertIn(x, self.js)
        self.assertNotRegex(self.js, r"https?://")
        self.assertNotRegex(self.js, r"(?i)</script")
        self.assertNotRegex(self.js, r"\beval\s*\(|new Function")
        self.assertEqual(self.js.count("<h1>"), 1)

    def test_mesmas_premissas_e_constantes(self):
        m = re.search(r"const PREMISSAS_RESERVA = \{(.*?)\};", self.js, re.S).group(1)
        js = {k: float(v) for k, v in re.findall(r'"([\w.]+)":([\d.]+)', m)}
        self.assertEqual(js, {k: float(v) for k, v in frota.PREMISSAS_PADRAO.items()})
        base = {p["id"]: p for p in json.loads((RAIZ / "sistema" / "physis-premissas.json").read_text(encoding="utf-8"))["premissas"]}
        for k, v in frota.PREMISSAS_PADRAO.items():
            self.assertEqual(base[k]["valor_padrao"], v, k)
            self.assertEqual(base[k]["status"], "conferir", k)
        self.assertIn(f"R_TERRA_KM = {frota.R_TERRA_KM}", self.js)
        self.assertIn(f"K_MAD = {frota.K_MAD}", self.js)
        self.assertIn(f"INTERVALO_MAX_S = {frota.INTERVALO_MAX_S}", self.js)
        self.assertEqual(re.search(r"const COMBUSTIVEIS = \[(.*?)\]", self.js).group(1).replace('"', "").split(", "), list(frota.COMBUSTIVEIS))
        self.assertEqual(set(re.findall(r"(\w+):\"", re.search(r"const TIPOS = \{(.*?)\};", self.js).group(1))), set(frota.TIPOS))

    @unittest.skipUnless(PAINEL.is_file(), "painel ausente")
    def test_aba_no_painel(self):
        h = PAINEL.read_text(encoding="utf-8")
        self.assertIn('["frota","Frota e combustível"]', h)
        self.assertIn('"frota"]);', re.search(r"const ABAS_DEV = new Set\(\[.*?\]\);", h).group(0))
        self.assertIn('"frota"', re.search(r"const COM_INTERFACE = new Set\(\[.*?\]\);", h).group(0))
        self.assertIn('frota: () => typeof telaFrota === "function" ? seloDev(telaFrota(),', h)
        self.assertIn('<script id="mod-frota">', h)
        self.assertIn("window.FROTA_I18N,", h)
        self.assertIn("FROTA.resumoGestao", h)
        self.assertIn('{ id:"frota", g:"pdi"', h)
        self.assertNotIn('"frota"', re.search(r"const LOJA_VENDA = new Set\(\[(.*?)\]\)", h).group(1))   # loja interna só
        self.assertEqual(Hub.ITEM_MODULOS["frota"], ("frota",))
        self.assertIn("frota", Hub.MODULOS_PLATAFORMA)


if __name__ == "__main__":
    unittest.main()
