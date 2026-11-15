"""Secador solar (TIPO:SEC, a homologar; docs/SECADOR.md).

Protege:
1. Linha V6 TIPO:SEC: tipo conhecido; campo fora da faixa física sai e a leitura fica; VENT e ABT só 0/1;
   as faixas do secador não mexem nas outras linhas (IRR do secador é irradiância).
2. Adaptador: grandezas temperatura_interna, umidade_interna, temperatura_coletor, peso_produto, irradiancia,
   temperatura/umidade externas (-ext) e estado do ventilador e da tampa.
3. Hub: alertas de superaquecimento pelo produto do lote, umidade alta sem ventilação, chuva prevista com o
   secador aberto (Open-Meteo guardada pelo clima) e nó fora; comando VENT confirmado pela linha seguinte.
4. Balanço de massa, modelo exponencial (ajuste à série de pesos) e dimensionamento, contra contas à mão.
5. Ponte MQTT: tópicos do ESPHome viram TIPO:SEC; segurança de temperatura força o ventilador e recusa VENT:0.
6. A tela (sistema/physis-secador.js) não chama a internet, tem um h1, o contrato com a plataforma e as mesmas
   premissas e constantes do secador.py.
"""
import json
import math
import re
import unittest
from pathlib import Path

from physis_hub import adaptador, clima, mqtt, nucleo, protocolo
from physis_hub import secador as S
from physis_hub.hub import Hub

T0 = 1_794_600_000
LINHA = "ID:41,TIPO:SEC,TI:38.5,UI:42.0,TE:27.1,UE:70.0,TC:52.3,VENT:1,PESO:84.20,IRR:820,BAT:3.95,TS:1794600000"
JS = Path(__file__).resolve().parents[2] / "sistema" / "physis-secador.js"


class Relogio:
    def __init__(self, t=float(T0)):
        self.t = t

    def __call__(self):
        return self.t


class Protocolo(unittest.TestCase):
    def test_sec_conhecido_e_faixas(self):
        ok, motivo, c = protocolo.validar_telemetria(LINHA)
        self.assertTrue(ok, motivo)
        self.assertNotIn("_FORA", c)
        ok, _, c = protocolo.validar_telemetria("ID:41,TIPO:SEC,TI:200,UI:105,VENT:2,ABT:1,PESO:-3,IRR:2000,TC:90,TS:1794600000")
        self.assertTrue(ok)
        for k in ("TI", "UI", "VENT", "PESO", "IRR"):
            self.assertNotIn(k, c)
        self.assertEqual(c["TC"], "90")
        self.assertEqual(c["ABT"], "1")
        self.assertEqual(set(c["_FORA"].split(",")), {"TI", "UI", "VENT", "PESO", "IRR"})
        ok, _, c = protocolo.validar_telemetria("ID:41,TIPO:SEC,TI:-,VENT:-")           # sem leitura: fica
        self.assertTrue(ok); self.assertNotIn("_FORA", c)
        # fora do secador as chaves do secador não têm faixa (nada muda nas outras linhas)
        ok, _, c = protocolo.validar_telemetria("ID:03,U1:45,TI:500")
        self.assertTrue(ok); self.assertEqual(c["TI"], "500")

    def test_comando_vent(self):
        self.assertEqual(protocolo.comando_valido("CMD:41:VENT:1"), (True, 41, "CMD:41:VENT:1"))
        self.assertFalse(protocolo.comando_valido("CMD:41:VENT:2")[0])
        self.assertFalse(protocolo.comando_valido("CMD:41:VENT")[0])


class Adaptador(unittest.TestCase):
    def test_grandezas(self):
        c = protocolo.validar_telemetria(LINHA)[2]
        e = adaptador.interpretar(c)
        self.assertEqual((e["tipo"], e["ti"], e["vent"], e["abt"], e["peso"]), ("SEC", 38.5, True, None, 84.2))
        m = {(x["grandeza"], x["ativo"]): x for x in adaptador.adaptar(c, "fazenda-teste", "sede")}
        self.assertEqual(m[("temperatura_interna", "sede-no41")]["valor"], 38.5)
        self.assertEqual(m[("umidade_interna", "sede-no41")]["unidade"], "%")
        self.assertEqual(m[("temperatura_coletor", "sede-no41")]["valor"], 52.3)
        self.assertEqual(m[("temperatura", "sede-no41-ext")]["valor"], 27.1)
        self.assertEqual(m[("umidade", "sede-no41-ext")]["valor"], 70.0)
        self.assertEqual(m[("peso_produto", "sede-no41")]["unidade"], "kg")
        self.assertEqual(m[("irradiancia", "sede-no41")]["valor"], 820.0)
        self.assertEqual(m[("estado", "sede-no41-ventilador")]["valor"], 1.0)
        self.assertNotIn(("estado", "sede-no41-tampa"), m)                # sem sensor de tampa
        self.assertEqual(m[("temperatura_interna", "sede-no41")]["alarme"], "sem_faixa")   # o limite é do produto
        for g in ("temperatura_interna", "umidade_interna", "temperatura_coletor", "peso_produto", "irradiancia"):
            self.assertIn(g, nucleo.GRANDEZAS_NOVAS)

    def test_nucleo_js_espelha(self):
        js = (Path(__file__).resolve().parents[2] / "sistema" / "physis-nucleo.js")
        if not js.is_file():
            self.skipTest("physis-nucleo.js fora do pacote")
        s = js.read_text(encoding="utf-8")
        for g in ("temperatura_interna", "umidade_interna", "temperatura_coletor", "peso_produto", "irradiancia"):
            self.assertRegex(s, g + r": \[")


class HubSecador(unittest.TestCase):
    def setUp(self):
        self.r = Relogio()
        self.h = Hub(relogio=self.r)

    def txt(self):
        return [a["texto"] for a in self.h.alertas() if a["no"] == 41]

    def test_alertas(self):
        self.assertEqual(self.h.receber_lote("ID:41,TIPO:SEC,TI:47,UI:30,VENT:1,ABT:0,TS:1794600000")["aceitas"], 1)
        self.assertEqual(self.txt(), [])                                  # genérico: até 60 °C
        self.h.secador_produtos[41] = "cafe"
        self.assertTrue(any("superaquecimento" in t and "45" in t for t in self.txt()))
        self.h.secador_produtos[41] = "frutas"
        self.assertEqual(self.txt(), [])
        self.r.t += 60
        self.h.receber_lote("ID:41,TIPO:SEC,TI:35,UI:85,VENT:0,ABT:1,TS:1794600060")
        self.assertTrue(any("umidade alta" in t for t in self.txt()))
        # chuva prevista (Open-Meteo guardada pelo clima) com a tampa aberta
        self.h._db.executescript(clima.ESQUEMA)
        dados = {"dias": [{"dia": "2026-11-15", "prob": 20}], "proximas_6h_mm": 3.2}
        self.h._db.execute("INSERT INTO clima_fonte(fonte,dados,consultado) VALUES('openmeteo',?,?)", (json.dumps(dados), self.r.t))
        self.assertTrue(any("chuva prevista" in t for t in self.txt()))
        self.r.t += 60
        self.h.receber_lote("ID:41,TIPO:SEC,TI:35,UI:50,VENT:0,ABT:0,TS:1794600120")   # tampa fechada: sem aviso
        self.assertEqual(self.txt(), [])
        self.r.t += 7 * 3600                                               # previsão velha e nó calado
        self.assertTrue(any("sem falar" in t for t in self.txt()))
        self.assertEqual(self.h.painel()["nos"][0]["tipo"], "SEC")

    def test_vent_confirmado(self):
        self.h.receber_lote("ID:41,TIPO:SEC,TI:30,VENT:0,TS:1794600000")
        self.assertTrue(self.h.comandar("CMD:41:VENT:1")["ok"])
        self.assertEqual(self.h.comandos_pendentes(41), ["CMD:41:VENT:1"])
        self.r.t += 30
        self.h.receber_lote("ID:41,TIPO:SEC,TI:30,VENT:1,TS:1794600030")
        est = self.h._db.execute("SELECT estado FROM comando ORDER BY seq DESC LIMIT 1").fetchone()[0]
        self.assertEqual(est, "confirmado")

    def test_modulo_e_loja(self):
        self.assertEqual(Hub.ITEM_MODULOS["P23"], ("secador",))
        self.assertIn("secador", Hub.MODULOS_PLATAFORMA)


class Contas(unittest.TestCase):
    def test_balanco_de_massa(self):
        # 100 kg de café com 60 % b.u. até 12 %: matéria seca 40 kg; peso final 40/0,88 = 45,4545 kg
        self.assertAlmostEqual(S.materia_seca(100, 60), 40.0)
        self.assertAlmostEqual(S.peso_na_umidade(100, 60, 12), 45.4545, places=4)
        self.assertAlmostEqual(S.agua_a_remover(100, 60, 12), 54.5455, places=4)       # 100·48/88
        self.assertEqual(S.agua_a_remover(100, 10, 12), 0.0)
        self.assertAlmostEqual(S.umidade_do_peso(100, 60, 50), 20.0)                  # 1 − 40/50
        self.assertAlmostEqual(S.rendimento(100, 45), 45.0)

    def test_ajuste_exponencial(self):
        # W = 10 + 40·e^(−0,1·t), de hora em hora: o ajuste tem de devolver We 10, W0 50 e k 0,1
        serie = [(t, 10 + 40 * math.exp(-0.1 * t)) for t in range(0, 21)]
        m = S.ajustar(serie)
        self.assertAlmostEqual(m["we"], 10.0, delta=0.05)
        self.assertAlmostEqual(m["w0"], 50.0, delta=0.05)
        self.assertAlmostEqual(m["k"], 0.1, delta=0.001)
        # até 20 kg: t = −ln(10/40)/0,1 = 13,863 h
        self.assertAlmostEqual(S.horas_ate(m, 20.0), 13.863, delta=0.05)
        self.assertIsNone(S.horas_ate(m, 9.0))                     # abaixo do equilíbrio: este ar não chega
        self.assertIsNone(S.ajustar([(0, 50), (1, 49)]))            # poucos pontos
        self.assertIsNone(S.ajustar([(0, 50), (1, 51), (2, 52)]))   # o peso não cai

    def test_curva_estimada_e_previsao(self):
        # café 100 kg, 60 % → equilíbrio 10 % (We = 40/0,9 = 44,444), alvo 11,5 %... com alvo 12 %:
        # t = −ln((45,4545 − 44,4444)/(100 − 44,4444))/0,024 = 4,00733/0,024 = 166,97 h
        p = S.previsao_lote({"produto": "cafe", "peso0": 100, "u0": 60, "alvo": 12})
        self.assertFalse(p["medido"])
        self.assertAlmostEqual(p["modelo"]["we"], 44.4444, places=3)
        self.assertAlmostEqual(p["horas_fim"], 166.97, delta=0.05)
        self.assertIsNone(S.previsao_lote({"produto": "cafe", "peso0": 100, "u0": 60, "alvo": 8})["horas_fim"])
        serie = [(t, 10 + 40 * math.exp(-0.1 * t)) for t in range(0, 12)]
        pm = S.previsao_lote({"produto": "frutas", "peso0": 50, "u0": 80, "alvo": 50}, serie)   # alvo 20 kg
        self.assertTrue(pm["medido"])
        self.assertAlmostEqual(pm["peso_alvo"], 20.0)
        self.assertAlmostEqual(pm["horas_fim"], 13.863, delta=0.05)

    def test_dimensionamento(self):
        r = S.dimensionar({"massa": 100, "u0": 60, "alvo": 12, "irradiacao": 5, "eta_coletor": 0.4, "aproveitamento": 0.5,
                           "dias": 5, "horas_sol": 8, "delta_t": 15, "lotes_ano": 10, "eta_eletrico": 0.5,
                           "eta_lenha": 0.35, "fator_rede": 0.0289})
        # à mão: água 54,545 kg; 54,545·2,45 = 133,64 MJ; ÷0,5 = 267,27 MJ no ar; 5·3,6·0,4·5 = 36 MJ/m² → 7,424 m²
        self.assertAlmostEqual(r["agua_kg"], 54.545, places=3)
        self.assertAlmostEqual(r["q_evap_mj"], 133.636, places=2)
        self.assertAlmostEqual(r["mj_m2_lote"], 36.0)
        self.assertAlmostEqual(r["area_m2"], 7.424, places=3)
        # Δw = 1,006·15·0,5/2450 = 0,0030796 kg/kg; ar = 17.712 kg; ÷1,15 ÷40 h = 385,0 m³/h
        self.assertAlmostEqual(r["dw_kg_kg"], 0.0030796, places=6)
        self.assertAlmostEqual(r["vazao_m3h"], 385.0, delta=0.2)
        # o calor que o ar leva bate com o da evaporação ÷ aproveitamento
        self.assertAlmostEqual(r["ar_kg"] * 1.006 * 15 / 1000, r["q_ar_mj"], places=3)
        # elétrico: 133,64/0,5/3,6 = 74,24 kWh por lote; 742,4 kWh/ano; × 0,0289 = 21,46 kg CO2
        self.assertAlmostEqual(r["kwh_eletrico_lote"], 74.242, places=2)
        self.assertAlmostEqual(r["co2_eletrico_kg_ano"], 21.456, places=2)
        # lenha: 133,64/(13·0,35) = 29,37 kg por lote; CH4 e N2O: 293,7 kg·13 MJ = 0,0038182 TJ·(300·28 + 4·265) = 36,12 kg
        self.assertAlmostEqual(r["kg_lenha_lote"], 29.371, places=2)
        self.assertAlmostEqual(r["co2_lenha_kg_ano"], 36.12, places=1)
        nr = S.dimensionar({"massa": 100, "u0": 60, "alvo": 12, "lenha_nao_renovavel": True, "lotes_ano": 10, "eta_lenha": 0.35})
        self.assertAlmostEqual(nr["co2_lenha_kg_ano"] - r["co2_lenha_kg_ano"], 0.0038182 * 112000, delta=0.5)

    def test_premissas_marcadas(self):
        for k, p in S.PRODUTOS.items():
            if k != "outro":
                self.assertIn("verificar", p["fonte"])
            self.assertLess(p["t_ideal"][1], p["t_max"] + 0.01)
            self.assertLess(p["ue"], p["alvo"])
        self.assertEqual(S.PRODUTOS["cafe"]["t_max"], 45.0)
        self.assertEqual(S.PRODUTOS["cafe"]["alvo"], 11.5)


class PonteSecador(unittest.TestCase):
    NO = {"no": "secador-cafe", "id": 41, "tipo": "secador", "ti": "temperatura_interna", "ui": "umidade_interna",
          "vent": "ventilador", "peso": "peso_produto", "abt": "tampa", "tmax": 55}

    def setUp(self):
        self.r = Relogio()
        self.p = mqtt.Ponte([self.NO, {"no": "irrigacao-zona1", "id": 21, "u1": "u", "ir1": "v"}], relogio=self.r)

    def test_topicos_viram_linha_sec(self):
        h = Hub()
        linhas, pub = self.p.mensagem("secador-cafe/sensor/temperatura_interna/state", "38.46")
        self.assertEqual(pub, [])
        self.assertIn("ID:41,TIPO:SEC,TI:38.5,UI:-", linhas[0])
        self.assertIn("ABT:-", linhas[0])
        self.assertEqual(h.receber_lote(linhas[0], origem="mqtt")["aceitas"], 1)
        linhas, _ = self.p.mensagem("secador-cafe/sensor/peso_produto/state", "84.237")
        self.assertIn("PESO:84.24", linhas[0])
        linhas, _ = self.p.mensagem("secador-cafe/binary_sensor/tampa/state", "ON")
        self.assertIn("ABT:1", linhas[0])
        self.assertEqual(h.receber_lote(linhas[0], origem="mqtt")["aceitas"], 1)        # mesmo segundo: não duplica
        self.assertEqual(h.painel()["nos"][0]["peso"], 84.24)
        self.assertIn("secador-cafe/#", self.p.topicos())
        with self.assertRaises(ValueError):
            mqtt.Ponte([{"no": "x", "id": 42, "tipo": "secador", "ti": "t"}])           # sem ventilador

    def test_comando_e_seguranca(self):
        cmd = "secador-cafe/switch/ventilador/command"
        self.assertEqual(self.p.comando("CMD:41:VENT:1"), [(cmd, "ON")])
        self.assertEqual(self.p.comando("CMD:21:VENT:1"), [])                 # a caixinha não tem ventilador
        self.assertEqual(self.p.comando("CMD:41:IRR1:1"), [])                 # o secador não tem válvula
        self.p.mensagem("secador-cafe/switch/ventilador/state", "OFF")
        _, pub = self.p.mensagem("secador-cafe/sensor/temperatura_interna/state", "56")   # passou de 55 °C
        self.assertEqual(pub, [(cmd, "ON")])
        self.p.mensagem("secador-cafe/switch/ventilador/state", "ON")
        self.assertEqual(self.p.comando("CMD:41:VENT:0"), [])                 # recusado: está quente
        _, pub = self.p.mensagem("secador-cafe/sensor/temperatura_interna/state", "52")   # ainda dentro da histerese
        self.assertEqual(pub, [])
        _, pub = self.p.mensagem("secador-cafe/sensor/temperatura_interna/state", "49")   # esfriou 5 °C: volta ao pedido
        self.assertEqual(pub, [(cmd, "OFF")])
        self.assertEqual(self.p.comando("CMD:00:VENT:1"), [(cmd, "ON")])       # para todos: só o secador liga


FW = Path(__file__).resolve().parents[2] / "firmware" / "secador"


@unittest.skipUnless((FW / "parametros.json").is_file(), "firmware/secador fora do pacote")
class Firmware(unittest.TestCase):
    def test_parametros_e_yaml(self):
        d = json.loads((FW / "parametros.json").read_text(encoding="utf-8"))
        self.assertEqual(d["aparelho"]["tipo"], "SEC")
        ok, motivo, c = protocolo.validar_telemetria(d["aparelho"]["linha_exemplo"])
        self.assertTrue(ok, motivo); self.assertNotIn("_FORA", c)
        for p in d["parametros"]:
            if p["valor"] is None:
                self.assertIn("[MARCADOR]", p["fonte"])
            else:
                self.assertTrue(p["faixa_aceita"][0] <= p["valor"] <= p["faixa_aceita"][1], p["id"])
        par = {p["id"]: p["valor"] for p in d["parametros"]}
        self.assertEqual(par["t_seguranca"], S.T_SEGURANCA_PADRAO)
        self.assertEqual(par["histerese"], S.HISTERESE_T)
        self.assertEqual(par["umidade_interna_alta"], S.UMIDADE_INTERNA_ALTA)
        y = (FW / "secador-solar.yaml").read_text(encoding="utf-8")
        self.assertIn(f't_seguranca: "{par["t_seguranca"]:g}"', y)
        self.assertIn(f'histerese: "{par["histerese"]:g}"', y)
        # os nomes do ESPHome viram os objetos que a ponte procura
        for nome, obj in (("Temperatura Interna", "temperatura_interna"), ("Umidade Interna", "umidade_interna"),
                          ("Temperatura Coletor", "temperatura_coletor"), ("Peso Produto", "peso_produto"),
                          ("Irradiancia", "irradiancia"), ("Tampa", "tampa"), ("Ventilador", "ventilador")):
            self.assertIn(f'name: "{nome}"', y)
            self.assertEqual(nome.lower().replace(" ", "_"), obj)
        self.assertNotRegex(y, r"password:\s*[\"']?[^!\s]")             # segredos só por !secret


@unittest.skipUnless(JS.is_file(), "sistema/physis-secador.js ausente")
class ModuloDaTela(unittest.TestCase):
    def setUp(self):
        self.s = JS.read_text(encoding="utf-8")

    def test_sem_internet_e_contrato(self):
        s = self.s
        self.assertIsNone(re.search(r"https?://", s), "a tela não chama a internet")
        self.assertNotIn("</script", s.lower())
        self.assertEqual(s.count("<h1>"), 1)
        for x in ("window.SECADOR", "window.telaSecador", "window.SECADOR_I18N", "__secEventos", "aria-pressed",
                  "<h1>Secador solar</h1>", "api/painel", "api/serie", "Metodologia e normas", "Embrapa", "ASHRAE",
                  "verificar", "TIPO:SEC", "data-sec-sub"):
            self.assertIn(x, s)
        for sub in ("agora", "lotes", "historico", "dimensionamento", "metodologia"):
            self.assertIn(f'"{sub}"', s)

    def test_mesmas_constantes_e_premissas(self):
        s = self.s
        for x in ("2.45", "1.006", "1.15", "3.6", "13.0", "112000", "0.999", "100", "40"):
            self.assertIn(x, s)
        for k, p in S.PRODUTOS.items():
            m = re.search(k + r':\s*\{[^}]*?t_max:\s*([0-9.]+)[^}]*?u0:\s*([0-9.]+)[^}]*?alvo:\s*([0-9.]+)[^}]*?ue:\s*([0-9.]+)[^}]*?k:\s*([0-9.]+)', s)
            self.assertIsNotNone(m, f"produto {k} fora do .js")
            self.assertEqual(tuple(float(x) for x in m.groups()), (p["t_max"], p["u0"], p["alvo"], p["ue"], p["k"]), k)
        self.assertIn(f"UMIDADE_INTERNA_ALTA = {S.UMIDADE_INTERNA_ALTA:g}", s)

    def test_i18n_em_ingles(self):
        m = re.search(r"window\.SECADOR_I18N = (\{.*?\});", self.s, re.S)
        self.assertIsNotNone(m)
        d = json.loads(m.group(1))
        self.assertGreater(len(d), 30)
        self.assertEqual(d["Secador solar"], "Solar dryer")
        self.assertTrue(all(isinstance(v, str) and v.strip() for v in d.values()))


if __name__ == "__main__":
    unittest.main()
