"""Rupturas do fluxo de dados consertadas no servidor (mapa de variáveis, 15/11/2026).

Protege:
R1  Medidores V6 TIPO:ENE e TIPO:HID (e a ponte MQTT) gravam energia, tensão, corrente, fp, vazão e pressão em
    medicao; o modelo de consumo passa a ter dado.
R2  As chaves da Qualidade da água são aceitas pelo servidor (dados do cliente).
R3  O modelo de consumo lê a produção da Gestão DO CLIENTE e reparte o mês igualmente pelos dias.
R6  Lote diário de integridade: fecha o dia anterior uma vez, só com registros validados, pelo laço diário do hub;
    PHYSIS_LOTE_DIARIO=0 e instancia.json desligam. Relógio falso.
R9  Secador sem número fixo de fator da rede nem de irradiação ("local não informado").
R11 Itens 'base' e 'consultoria-pers' da loja em ITEM_MODULOS.
Lacuna 2  O local é da instalação (instancia.json ou perfil), não só do Monitoramento; sem local, None.
"""
import json
import os
import unittest
from datetime import datetime
from unittest import mock

from physis_hub import adaptador, aprendizado, clima, integridade, mqtt, perfil_cliente, protocolo, secador
from physis_hub.hub import Hub

FUSO = clima.FUSO


def ts(a, m, d, h=12, mi=0):
    return int(datetime(a, m, d, h, mi, tzinfo=FUSO).timestamp())


class Relogio:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


def novo_hub(t, inst=None):
    h = Hub(":memory:", org="org-teste", lugar="lugar01", relogio=Relogio(t))
    h.instancia = inst if inst is not None else {}
    return h


class MedidoresV6(unittest.TestCase):
    def test_ene_e_hid_viram_medicao(self):
        h = novo_hub(ts(2026, 11, 10))
        t = ts(2026, 11, 10)
        r = h.receber_lote(f"ID:61,TIPO:ENE,PW:12.5,V:221.0,I:19.8,FP:0.93,TS:{t}\nID:62,TIPO:HID,Q:3.25,PR:2.4,TS:{t}")
        self.assertEqual(r["aceitas"], 2)
        g = dict(h._db.execute("SELECT grandeza, valor FROM medicao").fetchall())
        self.assertEqual(g, {"energia": 12.5, "tensao": 221.0, "corrente": 19.8, "fp": 0.93, "vazao": 3.25, "pressao": 2.4})
        self.assertEqual(adaptador.TIPOS.keys() & {"ENE", "HID"}, {"ENE", "HID"})

    def test_campo_fisicamente_impossivel_sai_e_leitura_fica(self):
        ok, _, campos = protocolo.validar_telemetria("ID:61,TIPO:ENE,PW:-3.0,V:-5,FP:1.4,TS:0")
        self.assertTrue(ok)
        self.assertNotIn("V", campos)
        self.assertNotIn("FP", campos)
        self.assertEqual(campos["PW"], "-3.0")      # potência negativa = injeção: vale

    def test_ponte_mqtt_monta_a_linha_do_medidor(self):
        p = mqtt.Ponte([{"no": "medidor-geral", "id": 61, "tipo": "energia", "pw": "potencia_ativa", "v": "tensao"},
                        {"no": "hidro", "id": 62, "tipo": "agua", "q": "vazao"}], relogio=lambda: 1794600000)
        linhas, pub = p.mensagem("medidor-geral/sensor/potencia_ativa/state", "4.2")
        self.assertEqual(pub, [])
        self.assertEqual(linhas, ["ID:61,TIPO:ENE,PW:4.200,V:-,TS:1794600000"])
        linhas, _ = p.mensagem("hidro/sensor/vazao/state", "1.5")
        self.assertTrue(linhas[0].startswith("ID:62,TIPO:HID,Q:1.500"))
        self.assertEqual(p.comando("CMD:61:IRR1:1"), [])           # medidor não recebe comando
        self.assertTrue(protocolo.validar_telemetria(linhas[0])[0])
        with self.assertRaises(ValueError):
            mqtt.NoMedidor({"no": "x", "id": 5, "tipo": "energia"})

    def test_modelo_de_consumo_recebe_energia_e_producao_do_cliente(self):
        h = novo_hub(ts(2026, 11, 20))
        linhas = [f"ID:61,TIPO:ENE,PW:{2.0 + d % 3},TS:{ts(2026, 11, d, hh)}" for d in range(1, 16) for hh in (6, 18)]
        h.receber_lote("\n".join(linhas))
        g = {"producao": [{"mes": "2026-11", "prod": "300", "un": "kg"}, {"mes": "2026-02", "prod": 280}]}
        self.assertTrue(h.cliente_gravar("physis-gestao-cliente", json.dumps(g), 0, "teste")["ok"])
        prod = aprendizado._producao_gestao(h._db)
        self.assertAlmostEqual(prod["2026-11-05"], 10.0)            # 300 ÷ 30 dias
        self.assertAlmostEqual(prod["2026-02-28"], 10.0)            # 280 ÷ 28 dias
        self.assertNotIn("2026-02-29", prod)
        dados = aprendizado.dados_consumo(h._db)
        serie = dados["lugar01-no61|energia"]
        self.assertEqual(len(serie), 15)
        self.assertAlmostEqual(serie[0]["valor"], (3.0 + 3.0) / 2 * 24)   # média do dia × 24 h = kWh/dia
        self.assertAlmostEqual(serie[0]["producao"], 10.0)
        m = aprendizado.treinar_consumo(serie, h.relogio())
        self.assertEqual(m["metricas"]["modo"], "regressao")
        self.assertIn("producao", m["parametros"]["variaveis"])


class FatorDePotencia(unittest.TestCase):
    """Regra do usuário: o fator de potência entra sempre nos módulos de energia (P, Q, S e FP guardados)."""

    def test_reativa_e_aparente_viram_medicao_e_mqtt(self):
        h = novo_hub(ts(2026, 11, 10))
        h.receber_lote(f"ID:61,TIPO:ENE,PW:8.0,QR:6.0,S:10.0,FP:0.80,TS:{ts(2026, 11, 10)}")
        g = dict(h._db.execute("SELECT grandeza, valor FROM medicao").fetchall())
        self.assertEqual((g["potencia_reativa"], g["potencia_aparente"], g["fp"]), (6.0, 10.0, 0.8))
        ok, _, c = protocolo.validar_telemetria("ID:61,TIPO:ENE,PW:1,S:-2,QR:-3")
        self.assertNotIn("S", c)                                      # aparente negativa: impossível
        self.assertEqual(c["QR"], "-3")                               # reativa capacitiva: vale
        p = mqtt.Ponte([{"no": "m", "id": 61, "tipo": "energia", "pw": "p", "qr": "q", "s": "s", "fp": "fp"}], relogio=lambda: 1794600000)
        p.mensagem("m/sensor/q/state", "2.5")
        self.assertIn("QR:2.500", p.mensagem("m/sensor/p/state", "4")[0][0])

    def test_potencias_do_dia_pela_ordem_de_medicao_e_premissa(self):
        h = novo_hub(ts(2026, 11, 20))
        h.receber_lote("\n".join([
            f"ID:61,TIPO:ENE,PW:8,S:10,TS:{ts(2026, 11, 1)}",          # P e S
            f"ID:61,TIPO:ENE,PW:3,QR:4,TS:{ts(2026, 11, 2)}",          # P e Q
            f"ID:61,TIPO:ENE,PW:6,FP:0.6,TS:{ts(2026, 11, 3)}",        # só FP
            f"ID:61,TIPO:ENE,PW:5,TS:{ts(2026, 11, 4)}"]))             # só P
        d = aprendizado.potencias_dia(h._db, fp_ref=0.92)["lugar01-no61"]
        self.assertEqual((d["2026-11-01"]["fp"], d["2026-11-01"]["q_kvarh"]), (0.8, 144.0))
        self.assertEqual((d["2026-11-02"]["s_kvah"], d["2026-11-02"]["fp"]), (120.0, 0.6))
        self.assertEqual((d["2026-11-03"]["s_kvah"], d["2026-11-03"]["q_kvarh"]), (240.0, 192.0))
        self.assertEqual(d["2026-11-04"]["fp"], 0.92)
        self.assertIn("eletrica.fator_potencia_padrao", d["2026-11-04"]["fp_fonte"])
        with mock.patch.object(aprendizado, "fp_padrao", return_value=None):
            sem = aprendizado.potencias_dia(h._db)["lugar01-no61"]["2026-11-04"]
        self.assertEqual((sem["fp"], sem["s_kvah"]), (None, None))   # sem premissa: nada inventado
        apr = aprendizado.Aprendizado(h)
        with mock.patch.object(aprendizado, "fp_padrao", return_value=0.92):
            r = apr.treinar()
        pot = [m for m in r["modelos"] if m["nome"] == "potencias:lugar01-no61"][0]["metricas"]
        self.assertEqual(pot["dias"], 4)
        self.assertIsNotNone(pot["fp_periodo"])
        self.assertIn("fator de potência", aprendizado.explicar(aprendizado.carregar(h._db, "potencias:lugar01-no61")))


class DadosDoCliente(unittest.TestCase):
    def test_chaves_da_agua_aceitas_no_servidor(self):
        h = novo_hub(ts(2026, 11, 10))
        for k in ("physis-ph-leituras", "physis-ph-calibracoes", "physis-agua-limites"):
            self.assertTrue(perfil_cliente.chave_valida(k))
            self.assertTrue(h.cliente_gravar(k, "[]", 0, "teste")["ok"], k)
        self.assertFalse(perfil_cliente.chave_valida("physis-agua-qualquer-coisa"))

    def test_itens_base_e_consultoria_no_hub(self):
        self.assertEqual(Hub.ITEM_MODULOS["base"], ("monitoramento",))
        self.assertEqual(Hub.ITEM_MODULOS["consultoria-pers"], ())


class LoteDiario(unittest.TestCase):
    def _hub_com_dia(self, inst=None):
        h = novo_hub(ts(2026, 11, 10, 12), inst)
        h.receber_lote("\n".join([f"ID:03,U1:40.0,IR1:0,U2:42.0,IR2:0,T:25.0,LIM1:30.0,LIM2:30.0,BAT:3.9,TS:{ts(2026, 11, 10, 9)}",
                                  f"ID:04,U1:41.0,IR1:0,U2:43.0,IR2:0,T:95.0,LIM1:30.0,LIM2:30.0,BAT:3.9,TS:{ts(2026, 11, 10, 10)}",
                                  f"ID:05,U1:39.0,IR1:0,U2:40.0,IR2:0,LIM1:30.0,LIM2:30.0,TS:{ts(2026, 11, 11, 1)}"]))
        agua = [{"q": "2026-11-10T13:00:00.000Z", "ponto": "pos", "ph": 7.1, "turb": 1.2, "cloro": None, "origem": "manual"},
                {"q": "2026-11-10T13:00:00.000Z", "ponto": "pos", "ph": 7.1, "turb": 1.2, "origem": "manual"},
                {"q": "2026-11-10T14:00:00.000Z", "ponto": "pre", "ph": 6.5, "exemplo": True}]
        h.cliente_gravar("physis-ph-leituras", json.dumps(agua), 0, "teste")
        return h

    def test_fecha_o_dia_anterior_uma_vez_com_relogio_falso(self):
        h = self._hub_com_dia()
        apr = aprendizado.Aprendizado(h)
        h.relogio.t = ts(2026, 11, 11, 2)
        self.assertTrue(aprendizado.passo_diario(apr)["lote"].get("cedo"))        # antes das 3 h: espera
        h.relogio.t = ts(2026, 11, 11, 4)
        r = aprendizado.passo_diario(apr)["lote"]
        self.assertEqual(r["lote"], "dia-org-teste-lugar01-2026-11-10")
        self.assertEqual(r["sem_unidade_fora"], 0)
        lote = integridade.ler_lote(h._db, r["lote"])
        self.assertEqual(integridade.conferir_lote(lote), (True, []))
        ids = {x["id"] for x in lote["registros"]}
        grandezas = {x["grandeza"] for x in lote["registros"]}
        self.assertIn("ph", grandezas)
        self.assertEqual(sum(1 for i in ids if i.startswith("agua:")), 2)   # pH e turbidez, sem repetir, sem exemplo
        self.assertTrue(all(x["qualidade"] == "valido" for x in lote["registros"]))
        quentes = [x for x in lote["registros"] if x["grandeza"] == "temperatura" and x["valor"] == 95.0]
        self.assertEqual([x["alarme"] for x in quentes], ["alto"])  # alarme de operação vai junto, o dado fica
        self.assertEqual(lote["dicionario"], "physis-variaveis/1")
        self.assertFalse(any("no05" in str(x["origem"]) for x in lote["registros"]))   # leitura do dia 11 não entra
        self.assertTrue(aprendizado.passo_diario(apr)["lote"].get("repetido"))
        h.__dict__.pop("_lote_dia", None)                            # como depois de religar o hub
        self.assertTrue(h.fechar_lote_diario()["repetido"])          # o banco também impede o lote duplicado
        self.assertEqual(len(integridade.listar_lotes(h._db)), 1)

    def test_desligar_por_ambiente_ou_instancia(self):
        h = self._hub_com_dia({"integridade": {"lote_diario": False}})
        h.relogio.t = ts(2026, 11, 11, 4)
        self.assertTrue(h.fechar_lote_diario()["desligado"])
        h2 = self._hub_com_dia()
        h2.relogio.t = ts(2026, 11, 11, 4)
        with mock.patch.dict(os.environ, {"PHYSIS_LOTE_DIARIO": "0"}):
            self.assertTrue(h2.fechar_lote_diario()["desligado"])
        self.assertEqual(integridade.listar_lotes(h2._db), [])

    def test_dia_sem_registro_nao_cria_lote(self):
        h = novo_hub(ts(2026, 11, 11, 4))
        self.assertTrue(h.fechar_lote_diario()["vazio"])
        self.assertEqual(integridade.listar_lotes(h._db), [])


class LocalDaInstalacao(unittest.TestCase):
    def test_ordem_planejador_inicio_monitoramento_instalacao_e_sem_padrao(self):
        h = novo_hub(ts(2026, 11, 10))
        L = h.local_da_instalacao()
        self.assertEqual((L["fonte"], L["lat"], L["lon"], L["poligono"]), ("nao_informado", None, None, None))
        c = clima.Clima(h)
        self.assertIsNone(c.local())                                 # sem local: nenhum ponto inventado
        self.assertEqual(c.estado()["lugar"]["fonte"], "nao_informado")
        h.instancia = {"local": {"lat": -22.9, "lon": -43.2, "municipio": "Rio de Janeiro", "uf": "RJ"}}
        self.assertEqual((h.local_da_instalacao()["fonte"], c.local()["lat"]), ("instalacao", -22.9))
        c.definir_local({"lat": -20.0, "lon": -44.0, "cemaden_estacao": "330390601A"})
        self.assertEqual((c.local()["fonte"], c.local()["lat"]), ("monitoramento", -20.0))
        h.cliente_gravar("physis-perfil", json.dumps({"c": {"lat": "-21.5", "lon": "-45.0", "municipio": "Lavras", "uf": "mg",
                                                            "area_total_ha": "2,5"}}), 0, "teste")
        L = h.local_da_instalacao()                                  # o cadastro do Início vale mais que o Monitoramento
        self.assertEqual((L["fonte"], L["lat"], L["municipio"], L["uf"], L["area_m2"]), ("inicio", -21.5, "Lavras", "MG", 25000.0))
        self.assertEqual(L["cemaden_estacao"], "330390601A")         # a estação continua a escolhida no Monitoramento
        terreno = {"meta": {"municipio": "Outro"}, "terreno": {"lat0": -21.6, "lon0": -45.1,
                                                                "poly": [[0, 0], [100, 0], [100, 100], [0, 100]]}}
        h.cliente_gravar("physis.terreno.v1", json.dumps(terreno), 0, "teste")
        L = h.local_da_instalacao()                                  # o lote do Planejador manda na geometria
        self.assertEqual((L["fonte"], L["lat"], L["area_m2"], L["fontes"]["area"]), ("planejador", -21.6, 10000.0, "planejador"))
        self.assertEqual(L["municipio"], "Lavras")                   # o município continua o do cadastro
        self.assertAlmostEqual(L["poligono"][2][1], -21.6 + 100 / 110540, places=6)
        self.assertEqual(c.local()["lat"], -21.6)
        h2 = novo_hub(ts(2026, 11, 10), {"local": {"lat": 10, "lon": 10}})   # fora do Brasil: recusado, não vira padrão
        self.assertEqual(h2.local_da_instalacao()["fonte"], "nao_informado")

    def test_secador_sem_local_e_sem_numero_fixo(self):
        r = secador.dimensionar({"massa": 100, "u0": 60, "alvo": 12})
        self.assertIsNone(r["area_m2"])
        self.assertTrue(any("local não informado" in a for a in r["avisos"]))
        self.assertFalse(hasattr(secador, "FATOR_REDE_PADRAO"))
        from physis_hub import carbono
        self.assertEqual(r["fator_rede"], carbono.premissa("rede.fator_emissao"))   # base de fatores = premissa hoje


if __name__ == "__main__":
    unittest.main()
