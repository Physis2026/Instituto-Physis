"""Ponte MQTT da Caixinha Physis IoT (ESPHome → hub).

Protege:
1. Tópicos do ESPHome viram linha V6 TIPO:ZONA aceita pelo hub (umidade, válvula, bateria).
2. Duas mudanças no mesmo segundo não se perdem (o hub guarda uma leitura por nó e segundo).
3. Comando IRR1 do hub vira ON/OFF no tópico da válvula; LIM/MODO fazem a rega automática com histerese.
4. Tempo máximo: a ponte fecha a válvula depois de TMAX minutos, em qualquer modo.
5. Codificação MQTT 3.1.1 conversa com um broker de mentira por socket (CONNECT, SUBSCRIBE, PUBLISH nos dois sentidos).
6. Sem broker configurado, a ponte não liga; a senha só vem do ambiente.
"""
import os
import socket
import struct
import threading
import unittest

from physis_hub import mqtt
from physis_hub.hub import Hub

NO = {"no": "irrigacao-zona1", "id": 21, "u1": "umidade_solo_zona_1", "ir1": "valvula_zona_1", "bat": "bateria", "tmax": 15}


class Relogio:
    def __init__(self, t=1_794_600_000.0):
        self.t = t

    def __call__(self):
        return self.t


class PonteSemRede(unittest.TestCase):
    def setUp(self):
        self.r = Relogio()
        self.p = mqtt.Ponte([NO], relogio=self.r)

    def test_topicos_viram_linha_zona_aceita(self):
        h = Hub()
        linhas, _ = self.p.mensagem("irrigacao-zona1/sensor/umidade_solo_zona_1/state", "41.27")
        self.assertIn("ID:21,TIPO:ZONA,U1:41.3,IR1:-", linhas[0])
        self.assertEqual(h.receber_lote("\n".join(linhas), origem="mqtt")["aceitas"], 1)
        linhas, _ = self.p.mensagem("irrigacao-zona1/switch/valvula_zona_1/state", "ON")   # mesmo segundo
        self.assertIn("IR1:1", linhas[0])
        self.assertEqual(h.receber_lote("\n".join(linhas), origem="mqtt")["aceitas"], 1)     # não vira duplicada
        self.assertEqual(self.p.mensagem("outro-no/sensor/x/state", "1"), ([], []))
        self.assertEqual(self.p.mensagem("irrigacao-zona1/sensor/umidade_solo_zona_1/state", "nan"), ([], []))
        self.assertEqual(self.p.mensagem("irrigacao-zona1/status", "offline"), ([], []))
        self.assertFalse(self.p.nos["irrigacao-zona1"].online)

    def test_comando_irr_e_rega_automatica(self):
        self.assertEqual(self.p.comando("CMD:21:IRR1:1"), [("irrigacao-zona1/switch/valvula_zona_1/command", "ON")])
        self.assertEqual(self.p.comando("CMD:21:IRR2:1"), [])               # nó sem segunda válvula
        self.assertEqual(self.p.comando("CMD:21:IRR1:7"), [])               # argumento inválido
        self.assertEqual(self.p.comando("CMD:05:IRR1:1"), [])               # outro nó
        self.p.mensagem("irrigacao-zona1/sensor/umidade_solo_zona_1/state", "30")
        self.p.comando("CMD:21:LIM1:35")
        self.assertEqual(self.p.comando("CMD:21:MODO:AUTO"), [("irrigacao-zona1/switch/valvula_zona_1/command", "ON")])
        self.p.mensagem("irrigacao-zona1/switch/valvula_zona_1/state", "ON")
        _, pub = self.p.mensagem("irrigacao-zona1/sensor/umidade_solo_zona_1/state", "38")   # < 35 + 5: segue aberta
        self.assertEqual(pub, [])
        _, pub = self.p.mensagem("irrigacao-zona1/sensor/umidade_solo_zona_1/state", "40.5")
        self.assertEqual(pub, [("irrigacao-zona1/switch/valvula_zona_1/command", "OFF")])
        self.assertIn("LIM1:35.0", self.p.nos["irrigacao-zona1"].linha(self.r()))

    def test_tempo_maximo_fecha(self):
        self.p.mensagem("irrigacao-zona1/switch/valvula_zona_1/state", "ON")
        self.r.t += 14 * 60
        self.assertEqual(self.p.verificar(), [])
        self.r.t += 61
        self.assertEqual(self.p.verificar(), [("irrigacao-zona1/switch/valvula_zona_1/command", "OFF")])

    def test_config(self):
        for k in [k for k in os.environ if k.startswith("PHYSIS_MQTT_")]:
            del os.environ[k]
        self.assertIsNone(mqtt.config_de({}))
        self.assertIsNone(mqtt.config_de({"mqtt": {"broker": "10.0.0.2"}}))               # sem nós
        c = mqtt.config_de({"mqtt": {"broker": "10.0.0.2", "usuario": "hub", "senha": "nao-usar", "nos": [NO]}})
        self.assertEqual((c["porta"], c["senha"]), (1883, ""))                              # senha do arquivo é ignorada
        os.environ["PHYSIS_MQTT_SENHA"] = "x"; os.environ["PHYSIS_MQTT_TLS"] = "1"
        try:
            c = mqtt.config_de({"mqtt": {"broker": "10.0.0.2", "nos": [NO]}})
            self.assertEqual((c["porta"], c["senha"], c["tls"]), (8883, "x", True))
        finally:
            del os.environ["PHYSIS_MQTT_SENHA"]; del os.environ["PHYSIS_MQTT_TLS"]
        with self.assertRaises(ValueError):
            mqtt.No({"no": "x", "id": 120})


class BrokerDeMentira(unittest.TestCase):
    def test_conversa_completa(self):
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
        porta = srv.getsockname()[1]
        visto = {}

        def broker():
            c, _ = srv.accept(); c.settimeout(10)
            buf = bytearray()

            def ler(n):
                while len(buf) < n:
                    d = c.recv(4096)
                    if not d:
                        raise OSError("fim")
                    buf.extend(d)
                out = bytes(buf[:n]); del buf[:n]; return out
            cab, corpo = mqtt.ler_pacote(ler)
            visto["connect"] = (cab, corpo)
            c.sendall(b"\x20\x02\x00\x00")                                  # CONNACK aceito
            cab, corpo = mqtt.ler_pacote(ler)
            visto["subscribe"] = corpo
            c.sendall(b"\x90\x03" + corpo[:2] + b"\x00")                     # SUBACK
            c.sendall(mqtt.pacote_publish("irrigacao-zona1/sensor/umidade_solo_zona_1/state", "30.0"))
            while True:                                                       # espera o comando da válvula
                cab, corpo = mqtt.ler_pacote(ler)
                if cab >> 4 == 3:
                    visto["publish"] = mqtt.ler_publish(cab, corpo)
                    break
            c.close()

        t = threading.Thread(target=broker, daemon=True); t.start()
        h = Hub()
        self.assertTrue(h.comandar("CMD:21:IRR1:1").get("ok", True))
        parar = threading.Event()
        cfg = {"broker": "127.0.0.1", "porta": porta, "usuario": "hub", "senha": "s", "nos": [NO]}
        rodando = threading.Thread(target=mqtt.rodar, args=(h, cfg, parar), daemon=True); rodando.start()
        t.join(15); parar.set(); rodando.join(5); srv.close()
        cab, corpo = visto["connect"]
        self.assertEqual(cab, 0x10); self.assertIn(b"MQTT", corpo); self.assertIn(b"hub", corpo)
        self.assertIn(b"irrigacao-zona1/#", visto["subscribe"])
        self.assertEqual(visto.get("publish"), ("irrigacao-zona1/switch/valvula_zona_1/command", "ON"))
        leituras = h._db.execute("SELECT origem, linha FROM leitura WHERE no=21").fetchall()
        self.assertTrue(leituras and leituras[0][0] == "mqtt" and "U1:30.0" in leituras[0][1])


if __name__ == "__main__":
    unittest.main()
