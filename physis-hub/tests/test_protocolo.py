"""Casos comuns do contrato V6. A mesma lista deve valer nos dois protocolo.cpp."""
import unittest

from physis_hub import adaptador, nucleo, protocolo as p
from physis_hub.hub import Hub
from physis_hub.simulador import Simulador

EXEMPLO_README = ("ID:03,U1:45.2,IR1:1,U2:50.0,IR2:0,T:27.5,UAR:63.5,TSOLO:23.1,"
                  "P1:12.5,P2:-1,LIM1:30.0,LIM2:30.0,BAT:3.87,TS:1786000000")


class Telemetria(unittest.TestCase):
    def test_exemplo_do_readme(self):
        ok, motivo, c = p.validar_telemetria(EXEMPLO_README + ",RSSI:-92.0,SNR:9.5")
        self.assertTrue(ok, motivo)
        e = adaptador.interpretar(c)
        self.assertEqual(e["id"], 3)
        self.assertAlmostEqual(e["media"], 47.6)
        self.assertTrue(e["ir1"])
        self.assertEqual(e["p1"], 12.5)
        self.assertEqual(e["rssi"], -92.0)

    def test_descartes(self):
        for linha, motivo in Simulador().defeituosas():
            ok, m, _ = p.validar_telemetria(linha)
            self.assertFalse(ok, linha)
            self.assertEqual(m, motivo, linha)

    def test_sentinelas_e_aprendendo(self):
        _, _, c = p.validar_telemetria("ID:07,U1:-,IR1:0,U2:nan,IR2:0,P1:-1,TSOLO:-,BAT:n/d")
        e = adaptador.interpretar(c)
        self.assertIsNone(e["u1"]); self.assertIsNone(e["u2"]); self.assertIsNone(e["media"])
        self.assertTrue(e["aprendendo"]); self.assertIsNone(e["tsolo"]); self.assertIsNone(e["bat"])

    def test_media_com_um_sensor(self):
        self.assertEqual(adaptador.media_controle(40.0, None), 40.0)
        self.assertEqual(adaptador.media_controle(None, 50.0), 50.0)
        self.assertEqual(adaptador.media_controle(40.0, 50.0), 45.0)

    def test_extensao_nao_quebra(self):
        ok, _, c = p.validar_telemetria("ID:11,U1:44.0,IR1:0,NOVA:xyz,OUTRA:1.5")
        self.assertTrue(ok); self.assertEqual(c["NOVA"], "xyz")

    def test_booleanos(self):
        for v in ("1", "SIM", "on", "True", "ligado"):
            self.assertTrue(p.para_bool(v), v)
        for v in ("0", "nao", "OFF", "false", "desligado"):
            self.assertFalse(p.para_bool(v), v)


class Comandos(unittest.TestCase):
    VALIDOS = ["CMD:03:LIM1:35", "CMD:03:LIM1:35.5", "CMD:00:IRR1:1", "CMD:3:IRR1:0", "CMD:99:PING",
               "CMD:03:MODO:auto", "CMD:03:MODO:MANUAL", "CMD:00:SYNC:1786000000", "CMD:03:LIM2:0", "CMD:03:LIM2:100"]
    INVALIDOS = ["CMD:03:LIM1:35,5", "CMD:03:LIM1:nan", "CMD:03:LIM1:", "CMD:03:LIM1:101", "CMD:03:LIM1:-1",
                 "CMD:xx:IRR1:1", "CMD:100:IRR1:1", "CMD:123:IRR1:1", "CMD::IRR1:1", "CMD:03:IRR1:2",
                 "CMD:03:IRR1:", "CMD:03:PING:1", "CMD:03:MODO:TURBO", "CMD:03:SYNC:123", "CMD:03:SYNC:9999999999",
                 "CMD:03:ABRIR:1", "CMD:03", "IRR1:1", "", "CMD:03:LIM1:inf", "CMD:03:LIM1:1e9"]

    def test_validos(self):
        for l in self.VALIDOS:
            self.assertTrue(p.comando_valido(l)[0], l)

    def test_invalidos(self):
        for l in self.INVALIDOS:
            self.assertFalse(p.comando_valido(l)[0], l)

    def test_normalizacao(self):
        self.assertEqual(p.comando_valido("CMD:3:modo:auto")[2], "CMD:03:MODO:AUTO")
        self.assertEqual(p.comando_valido("CMD:00:PING")[2], "CMD:00:PING")


class AdaptadorENucleo(unittest.TestCase):
    def test_topicos_do_exemplo(self):
        _, _, c = p.validar_telemetria(EXEMPLO_README + ",RSSI:-92.0,SNR:9.5")
        ms = adaptador.adaptar(c, "cliente-alfa-01", "faz01")
        topicos = {m["topico"]: m for m in ms}
        self.assertIn("physis/cliente-alfa-01/umidade_solo/faz01-no03", topicos)
        self.assertAlmostEqual(topicos["physis/cliente-alfa-01/umidade_solo/faz01-no03"]["valor"], 47.6)
        self.assertEqual(topicos["physis/cliente-alfa-01/estado/faz01-no03-valvula1"]["valor"], 1.0)
        self.assertEqual(topicos["physis/cliente-alfa-01/bateria/faz01-no03"]["alarme"], "ok")
        self.assertIn("physis/cliente-alfa-01/temperatura/faz01-no03-solo", topicos)

    def test_aprendendo_nao_vira_medicao(self):
        _, _, c = p.validar_telemetria("ID:05,U1:40.0,IR1:0,U2:41.0,IR2:0,P1:-1")
        self.assertFalse([m for m in adaptador.adaptar(c, "org-teste", "l1") if m["grandeza"] == "previsao_min"])

    def test_tipos(self):
        for linha, tipo, grandeza in (
                ("ID:21,TIPO:ZONA,U1:40.0,IR1:1,U2:38.0,IR2:0,BOMBA:1", "ZONA", "estado"),
                ("ID:41,TIPO:COL,LAT:-22.51,LON:-43.18,GPS:1,ATV:1,IMP:0,BAT:3.9", "COL", "latitude"),
                ("ID:71,TIPO:COM,NIV:62.0,PORC:3,TAG:A1B2,BLOQ:0", "COM", "nivel")):
            _, _, c = p.validar_telemetria(linha)
            self.assertEqual(adaptador.tipo_da_linha(c), tipo)
            self.assertTrue([m for m in adaptador.adaptar(c, "org-teste", "l1") if m["grandeza"] == grandeza])

    def test_org_e_topico(self):
        self.assertIsNone(nucleo.montar_topico("X", "umidade", "a"))
        self.assertIsNone(nucleo.montar_topico("org-teste", "umi dade", "a"))
        self.assertEqual(nucleo.montar_topico("cliente-alfa-01", "umidade", "no03"), "physis/cliente-alfa-01/umidade/no03")


class HubTeste(unittest.TestCase):
    def setUp(self):
        self.t = [1_794_600_000.0]
        self.hub = Hub(relogio=lambda: self.t[0])

    def test_duplicata_com_ts(self):
        r = self.hub.receber_lote(EXEMPLO_README + "\n" + EXEMPLO_README)
        self.assertEqual((r["aceitas"], r["duplicadas"]), (1, 1))

    def test_offline(self):
        self.hub.receber_lote(EXEMPLO_README)
        self.assertTrue(self.hub.painel()["nos"][0]["online"])
        self.t[0] += 200
        self.assertFalse(self.hub.painel()["nos"][0]["online"])
        self.assertEqual(self.hub.alertas()[0]["nivel"], "alarme")

    def test_comando_confirmado(self):
        self.hub.receber_lote("ID:03,U1:45.0,IR1:0,U2:45.0,IR2:0,LIM1:30.0,LIM2:30.0,TS:1794600001")
        r = self.hub.comandar("CMD:03:LIM1:35")
        self.assertEqual(r["estado"], "pendente")
        self.assertEqual(self.hub.comandos_pendentes(3), ["CMD:03:LIM1:35"])
        self.hub.receber_lote("ID:03,U1:45.0,IR1:0,U2:45.0,IR2:0,LIM1:35.0,LIM2:30.0,TS:1794600010")
        self.assertEqual(self.hub.painel()["comandos"][0]["estado"], "confirmado")

    def test_comando_nao_confirmado(self):
        self.hub.comandar("CMD:03:IRR1:1")
        self.hub.comandos_pendentes(3)
        for i in range(3):
            self.hub.receber_lote(f"ID:03,U1:45.0,IR1:0,U2:45.0,IR2:0,LIM1:30.0,LIM2:30.0,TS:{1794600020 + i}")
        self.assertEqual(self.hub.painel()["comandos"][0]["estado"], "nao_confirmado")

    def test_irrigar_agora_no_simulador(self):
        sim = Simulador(solo=1, zona=1, col=0, com=0)
        self.hub.receber_lote("\n".join(sim.passo()))
        self.hub.comandar("CMD:02:IRR1:1")
        for _ in range(2):
            self.hub.receber_lote("\n".join(sim.passo(self.hub.comandos_pendentes())))
        estados = {c["linha"]: c["estado"] for c in self.hub.painel()["comandos"]}
        self.assertEqual(estados["CMD:02:IRR1:1"], "confirmado")
        self.assertTrue(self.hub.nos[2]["bomba"])

    def test_comando_recusado(self):
        self.assertFalse(self.hub.comandar("CMD:03:LIM1:35,5")["ok"])

    def test_receptor_fora_do_ar(self):
        def falha(_):
            raise OSError("sem rota")
        hub = Hub(enviar_comando=falha)
        self.assertEqual(hub.comandar("CMD:03:IRR1:1")["estado"], "falhou")

    def test_cadeia_detecta_alteracao(self):
        self.hub.receber_lote(EXEMPLO_README)
        self.hub.comandar("CMD:03:IRR1:1")
        self.assertEqual(self.hub.verificar_cadeia()[0], True)
        self.hub._db.execute("UPDATE registro SET conteudo='{\"x\":1}' WHERE seq=1")
        self.assertEqual(self.hub.verificar_cadeia()[0], False)

    def test_alertas_por_tipo(self):
        self.hub.receber_lote("ID:21,TIPO:ZONA,U1:40.0,IR1:0,U2:38.0,IR2:0,BOMBA:1,TS:1794600001\n"
                              "ID:41,TIPO:COL,LAT:-22.51,LON:-43.18,GPS:1,ATV:2,IMP:1,BAT:3.4,TS:1794600001\n"
                              "ID:71,TIPO:COM,NIV:9.0,PORC:4,TAG:A1,BLOQ:1,TS:1794600001")
        textos = " | ".join(a["texto"] for a in self.hub.alertas())
        self.assertIn("bomba ligada sem valvula", textos)
        self.assertIn("impacto", textos)
        self.assertIn("racao em 9", textos)



class Historico(unittest.TestCase):
    def test_historico_de_leituras(self):
        from physis_hub.hub import Hub
        h = Hub()
        for i in range(5):
            h.receber_lote(f"ID:03,U1:{40 + i}.0,IR1:0,U2:50.0,IR2:0,T:27.5,UAR:63.5,TSOLO:23.1,P1:12.5,P2:-1,LIM1:30.0,LIM2:30.0,BAT:3.87,TS:{1794700000 + i * 60}")
        h.receber_lote("ID:04,U1:22.0,IR1:1,U2:24.0,IR2:0,T:29.0,UAR:55.0,TSOLO:24.0,P1:0,P2:-1,LIM1:30.0,LIM2:30.0,BAT:3.7,TS:1794700000")
        todas = h.leituras()
        self.assertEqual(len(todas), 6)
        self.assertEqual(todas[0]["no"], 4)                       # a mais nova primeiro
        self.assertEqual([x["ts"] for x in h.leituras(no=3)], [1794700000 + i * 60 for i in (4, 3, 2, 1, 0)])
        self.assertEqual(len(h.leituras(limite=2)), 2)
        self.assertIn("U1:44.0", h.leituras(no=3)[0]["linha"])


class CorrecoesDeProtocolo(unittest.TestCase):
    def test_tipo_desconhecido_e_recusado(self):
        from physis_hub.hub import Hub
        from physis_hub import protocolo
        ok, motivo, _ = protocolo.validar_telemetria("ID:07,TIPO:XYZ,U1:40.0,TS:1794700000")
        self.assertEqual((ok, motivo), (False, "tipo_desconhecido"))
        self.assertTrue(protocolo.validar_telemetria("ID:07,U1:40.0,TS:1794700000")[0])          # sem TIPO continua valendo (no de solo antigo)
        self.assertTrue(protocolo.validar_telemetria("ID:07,TIPO:zona,U1:40.0,TS:1794700000")[0])
        h = Hub(); h.receber_lote("ID:07,TIPO:XYZ,U1:40.0,TS:1794700000")
        self.assertEqual(h.descartes["tipo_desconhecido"], 1)
        self.assertEqual(len(h.painel()["nos"]), 0)

    def test_campo_fora_da_faixa_sai_e_a_leitura_fica(self):
        from physis_hub.hub import Hub
        h = Hub(); h.receber_lote("ID:05,U1:41.0,IR1:0,U2:43.0,IR2:0,BAT:999,RSSI:-90,TS:1794700000")
        n = h.painel()["nos"][0]
        self.assertIsNone(n.get("bat"))
        self.assertEqual(n.get("rssi"), -90)
        self.assertEqual(n.get("u1"), 41.0)
        self.assertEqual(h.descartes["campo_fora_da_faixa"], 1)

if __name__ == "__main__":
    unittest.main()
