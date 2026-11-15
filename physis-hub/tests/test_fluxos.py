"""Fluxos de ponta a ponta que faltavam (auditoria de 14/11/2026).

Protege:
1. POST /api/v6/linha: da rede local sem chave entra e devolve os comandos pendentes do nó; com PHYSIS_EXPOSTO=1 sem chave = 401;
   chave do dispositivo certa entra, errada = 401, chave de outro nó recusa a linha (recusadas_outro_no).
2. GET /api/painel depois das linhas: formato que as telas e a supervisão leem (nós, alertas, comandos, registro, saúde).
3. GET /api/gis/rio e /api/gis/relevo com buscadores de mentira (sem internet): conta do rio (nível) e declividade.
4. POST /api/saude/linha: aparelho cadastrado entra; sem chave fora da rede local = 401.
5. MQTT (broker de mentira) → hub → GET /api/painel mostra o nó da Caixinha.
6. correio.enviar com um servidor SMTP de mentira (socket local): sem STARTTLS não envia; com TLS entrega a mensagem.
"""
import base64
import json
import os
import socket
import ssl
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from physis_hub import correio, gis as gis_mod, mqtt, saude as saude_mod
from physis_hub import seguranca as seg
from physis_hub.hub import Hub
from physis_hub.servidor import iniciar

TS = 1_794_700_000


def buscar_falso(url: str):
    """Responde como o Open-Meteo (relevo) e o GloFAS (rio), sem internet."""
    if "elevation" in url:
        return {"elevation": [100.0 + 2.0 * (i % 10) + 5.0 * (i // 10) for i in range(100)]}
    if "flood" in url and "start_date" in url:
        return {"daily": {"river_discharge": [float(10 + (i % 50)) for i in range(1000)]}}
    if "flood" in url:
        return {"daily": {"time": ["2026-11-15", "2026-11-16"], "river_discharge": [20.0, 70.0], "river_discharge_max": [30.0, 90.0]}}
    raise OSError("sem internet no teste")


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("PHYSIS_EXPOSTO", None)
        os.environ.pop("PHYSIS_ACEITAR_SEM_CHAVE", None)
        cls.hub = Hub(org="fazenda-teste", lugar="sede")
        cls.irr = gis_mod.Irradiacao(cls.hub, buscar=buscar_falso)
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": False}, irradiacao=cls.irr)
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def c(self, metodo, rota, corpo=None, extra=None, tipo="text/plain"):
        h = {"Content-Type": tipo}
        h.update(extra or {})
        dados = corpo.encode() if isinstance(corpo, str) else (json.dumps(corpo).encode() if corpo is not None else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", data=dados, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")


class LinhaV6EPainel(Base):
    def test_linha_v6_rede_local_e_chave(self):
        self.assertTrue(self.hub.comandar("CMD:03:LIM1:35")["ok"])
        st, j = self.c("POST", "/api/v6/linha", f"ID:03,TIPO:ZONA,U1:41.0,IR1:0,U2:43.0,IR2:0,BOMBA:0,LIM1:30,TS:{TS}")
        self.assertEqual((st, j["aceitas"], j["comandos"]), (200, 1, ["CMD:03:LIM1:35"]))
        os.environ["PHYSIS_EXPOSTO"] = "1"                         # ninguém é "rede local"
        try:
            st, j = self.c("POST", "/api/v6/linha", f"ID:03,U1:40,TS:{TS + 60}")
            self.assertEqual((st, j["erro"]), (401, "chave do dispositivo ausente"))
            self.assertEqual(self.c("POST", "/api/v6/linha", f"ID:03,U1:40,TS:{TS + 60}", {"X-Physis-Chave": "phk_errada"})[0], 401)
            ch = seg.chave_criar(self.hub, 3, "caixinha 3", "teste")["chave"]
            st, j = self.c("POST", "/api/v6/linha", f"ID:03,U1:40,TS:{TS + 60}", {"Authorization": "Bearer " + ch})
            self.assertEqual((st, j["aceitas"]), (200, 1))
            st, j = self.c("POST", "/api/v6/linha", f"ID:04,U1:40,TS:{TS + 60}", {"X-Physis-Chave": ch})
            self.assertEqual((st, j["aceitas"], j["recusadas_outro_no"]), (200, 0, 1))
        finally:
            os.environ.pop("PHYSIS_EXPOSTO", None)

    def test_painel_depois_das_linhas(self):
        self.c("POST", "/api/gateway/webhook", f"ID:05,U1:41.0,IR1:1,U2:43.0,IR2:0,LIM1:30,BAT:3.2,RSSI:-90,SNR:7,TS:{TS}\n"
                                               f"ID:06,TIPO:COM,NIV:10,PORC:3,TAG:-,BLOQ:0,TS:{TS}\nlixo")
        st, p = self.c("GET", "/api/painel")
        self.assertEqual(st, 200)
        for k in ("org", "lugar", "agora", "nos", "alertas", "comandos", "registro", "saude"):
            self.assertIn(k, p)
        self.assertEqual((p["org"], p["lugar"]), ("fazenda-teste", "sede"))
        nos = {n["id"]: n for n in p["nos"]}
        n5 = nos[5]
        for k in ("tipo", "online", "ha_s", "linha", "visto", "pacotes", "u1", "u2", "media", "ir1", "bat", "rssi", "snr"):
            self.assertIn(k, n5)
        self.assertEqual((n5["tipo"], n5["online"], n5["media"], n5["ir1"]), ("SOLO", True, 42.0, True))
        self.assertEqual((nos[6]["tipo"], nos[6]["niv"]), ("COM", 10.0))
        textos = " ".join(a["texto"] for a in p["alertas"])
        self.assertIn("bateria baixa", textos); self.assertIn("racao em 10", textos)
        self.assertGreaterEqual(p["saude"]["descartes"].get("sem_id", 0), 1)
        self.assertIn("fila_envio", p["saude"])
        self.assertTrue(any(r["tipo"] == "no_descoberto" for r in p["registro"]))


class GisComBuscadorFalso(Base):
    def test_relevo_e_rio(self):
        st, j = self.c("GET", "/api/gis/relevo?lat=-22.5&lon=-43.2")
        self.assertEqual((st, j["ok"], j["n"], j["min"], j["max"]), (200, True, 10, 100.0, 163.0))
        self.assertGreater(j["decl_max_pct"], 0)
        st, j = self.c("GET", "/api/gis/rio?lat=-22.5&lon=-43.2")
        self.assertEqual((st, j["ok"]), (200, True))
        self.assertEqual(j["historico"]["max"], 59.0)
        self.assertEqual(j["nivel"], "alerta")                                   # pico 70 acima do p99 do histórico
        self.assertEqual(self.c("GET", "/api/gis/rio?lat=40&lon=-3")[0], 400)    # fora do Brasil
        self.assertEqual(self.c("GET", "/api/gis/relevo?lat=x&lon=1")[0], 400)


class SaudeLinha(Base):
    def test_rota_da_saude(self):
        s = saude_mod.Saude(self.hub)
        self.hub.criar_conta("Ana", "ana", "senha-bem-comprida-123")
        p = s.criar_pessoa({"nome": "Rui", "nascimento": "1950-01-01", "consentimento": {"aceito": True}}, "ana")["pessoa"]
        self.assertTrue(s.executar("dispositivo", {"pessoa": p, "no": 41, "tipo": "MED"}, "ana")["ok"])
        st, j = self.c("POST", "/api/saude/linha", f"ID:41,TIPO:MED,CMP:1,EVT:TOMADO,TS:{TS}\nID:42,TIPO:MED,CMP:1,EVT:TOMADO")
        self.assertEqual((st, j["aceitas"], j["linhas"][1]["motivo"]), (200, 1, "aparelho_desconhecido"))
        # a mesma linha MED pelo receptor (protocolo V6, PHYSIS_SAUDE_V6=1) também chega à Saúde: aqui, repetida
        st, j = self.c("POST", "/api/gateway/webhook", f"ID:41,TIPO:MED,CMP:1,EVT:TOMADO,TS:{TS}")
        self.assertEqual((st, j["duplicadas"]), (200, 1))
        st, j = self.c("POST", "/api/v6/linha", f"ID:41,TIPO:MED,CMP:2,EVT:TOMADO,TS:{TS + 5}")
        self.assertEqual((st, j["aceitas"]), (200, 1))
        self.assertEqual(self.hub._db.execute("SELECT COUNT(*) FROM medicao m JOIN leitura l ON l.seq=m.leitura WHERE l.no=41").fetchone()[0], 0)
        os.environ["PHYSIS_EXPOSTO"] = "1"
        try:
            self.assertEqual(self.c("POST", "/api/saude/linha", f"ID:41,TIPO:MED,CMP:1,EVT:TOMADO,TS:{TS + 9}")[0], 401)
        finally:
            os.environ.pop("PHYSIS_EXPOSTO", None)


class MqttAtePainel(Base):
    def test_broker_hub_painel(self):
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
        porta, pronto = srv.getsockname()[1], threading.Event()

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
            try:
                mqtt.ler_pacote(ler); c.sendall(b"\x20\x02\x00\x00")                # CONNECT -> CONNACK
                _, corpo = mqtt.ler_pacote(ler); c.sendall(b"\x90\x03" + corpo[:2] + b"\x00")   # SUBSCRIBE -> SUBACK
                c.sendall(mqtt.pacote_publish("irrigacao-zona1/sensor/umidade_solo_zona_1/state", "33.4"))
                pronto.wait(10)
            finally:
                c.close()

        threading.Thread(target=broker, daemon=True).start()
        parar = threading.Event()
        no = {"no": "irrigacao-zona1", "id": 21, "u1": "umidade_solo_zona_1", "ir1": "valvula_zona_1", "bat": "bateria", "tmax": 15}
        cfg = {"broker": "127.0.0.1", "porta": porta, "usuario": "hub", "senha": "s", "nos": [no]}
        t = threading.Thread(target=mqtt.rodar, args=(self.hub, cfg, parar), daemon=True); t.start()
        try:
            achou = None
            for _ in range(50):
                nos = {n["id"]: n for n in self.c("GET", "/api/painel")[1]["nos"]}
                if 21 in nos:
                    achou = nos[21]; break
                time.sleep(0.1)
            self.assertIsNotNone(achou, "o nó da Caixinha não apareceu no painel")
            self.assertEqual((achou["tipo"], achou["u1"]), ("ZONA", 33.4))
            self.assertEqual(self.hub._db.execute("SELECT origem FROM leitura WHERE no=21").fetchone()[0], "mqtt")
        finally:
            pronto.set(); parar.set(); t.join(5); srv.close()


class SmtpDeMentira:
    """Servidor SMTP mínimo num socket local. Com tls=True anuncia STARTTLS (certificado de teste do Python)."""

    def __init__(self, tls_ctx=None):
        self.tls_ctx, self.recebido, self.comandos = tls_ctx, None, []
        self.s = socket.socket(); self.s.bind(("127.0.0.1", 0)); self.s.listen(1)
        self.porta = self.s.getsockname()[1]
        self.t = threading.Thread(target=self._rodar, daemon=True); self.t.start()

    def _rodar(self):
        try:
            c, _ = self.s.accept()
        except OSError:
            return
        c.settimeout(10)
        f = c.makefile("rb")
        def diz(t):
            c.sendall(t.encode() + b"\r\n")
        try:
            diz("220 stub ESMTP")
            dados = False
            while True:
                linha = f.readline()
                if not linha:
                    break
                cmd = linha.decode().strip()
                self.comandos.append(cmd.split(" ")[0].upper())
                u = cmd.upper()
                if u.startswith(("EHLO", "HELO")):
                    tls_ok = self.tls_ctx is not None and not isinstance(c, ssl.SSLSocket)
                    diz("250-stub"); diz("250-STARTTLS" if tls_ok else "250-8BITMIME"); diz("250 AUTH PLAIN")
                elif u == "STARTTLS" and self.tls_ctx is not None:
                    diz("220 pode")
                    c = self.tls_ctx.wrap_socket(c, server_side=True)
                    f = c.makefile("rb")
                elif u.startswith("AUTH PLAIN"):
                    self.auth = base64.b64decode(cmd.split(" ")[2]).split(b"\x00")
                    diz("235 ok")
                elif u.startswith(("MAIL", "RCPT")):
                    diz("250 ok")
                elif u == "DATA":
                    diz("354 manda")
                    corpo = b""
                    while not corpo.endswith(b"\r\n.\r\n"):
                        corpo += f.readline()
                    self.recebido = corpo.decode("utf-8", "replace")
                    diz("250 guardado")
                elif u == "QUIT":
                    diz("221 tchau"); break
                else:
                    diz("502 nao")
        except (OSError, ssl.SSLError):
            pass
        finally:
            c.close(); self.s.close()


class CorreioComSmtpFalso(unittest.TestCase):
    VARS = ("PHYSIS_SMTP_HOST", "PHYSIS_SMTP_PORTA", "PHYSIS_SMTP_USUARIO", "PHYSIS_SMTP_SENHA", "PHYSIS_SMTP_REMETENTE")

    def setUp(self):
        self.antes = {k: os.environ.get(k) for k in self.VARS}

    def tearDown(self):
        for k, v in self.antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def configurar(self, porta):
        os.environ.update({"PHYSIS_SMTP_HOST": "localhost", "PHYSIS_SMTP_PORTA": str(porta), "PHYSIS_SMTP_USUARIO": "hub@physis.example",
                           "PHYSIS_SMTP_SENHA": "segredo-de-teste", "PHYSIS_SMTP_REMETENTE": "Physis <hub@physis.example>"})

    def test_sem_starttls_nao_envia(self):
        stub = SmtpDeMentira(tls_ctx=None)
        self.configurar(stub.porta)
        ok, erro = correio.enviar("cliente@exemplo.com", "Assunto", "Corpo")
        stub.t.join(5)
        self.assertFalse(ok)
        self.assertNotIn("segredo-de-teste", erro)
        self.assertNotIn("MAIL", stub.comandos)                     # nada foi entregue sem TLS
        self.assertIsNone(stub.recebido)

    def test_com_tls_entrega_e_marca_a_fila(self):
        try:
            import test as pacote_teste
            cert = Path(pacote_teste.__file__).parent / "certdata" / "keycert.pem"
        except ImportError:
            cert = None
        if not cert or not cert.is_file():
            self.skipTest("certificado de teste do Python ausente (pacote test não instalado)")
        srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); srv_ctx.load_cert_chain(str(cert))
        stub = SmtpDeMentira(tls_ctx=srv_ctx)
        self.configurar(stub.porta)
        cli_ctx = ssl.create_default_context(cafile=str(cert))
        original = correio.ssl.create_default_context
        correio.ssl.create_default_context = lambda *a, **k: cli_ctx          # confia só no certificado de teste
        try:
            h = Hub()
            h._db.execute("INSERT INTO email_saida(para,assunto,corpo,estado,ref,criado) VALUES(?,?,?,?,?,?)",
                          ("cliente@exemplo.com", "Suporte SP-0001 · Olá", "Texto com acentuação: ção", "pendente", "SP-0001-R1", 0))
            h._db.commit()
            self.assertEqual(correio.enviar_fila(h, "SP-0001-R1"), 1)
        finally:
            correio.ssl.create_default_context = original
        stub.t.join(5)
        self.assertIn("STARTTLS", stub.comandos)
        self.assertIn("MAIL", stub.comandos)
        self.assertIn("Subject:", stub.recebido)
        self.assertIn("cliente@exemplo.com", stub.recebido)
        self.assertEqual(stub.auth[1:], [b"hub@physis.example", b"segredo-de-teste"])
        self.assertEqual(h.emails()[0]["estado"], "enviado")


if __name__ == "__main__":
    unittest.main()
