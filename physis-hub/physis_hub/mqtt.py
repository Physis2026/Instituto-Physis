"""Ponte MQTT → hub para a Caixinha Physis IoT (nós ESP32 com ESPHome).

A Caixinha publica no broker (Mosquitto no Raspberry Pi) nos tópicos padrão do ESPHome:
    <nó>/sensor/<objeto>/state     ex.: irrigacao-zona1/sensor/umidade_solo_zona_1/state  → "41.3"
    <nó>/switch/<objeto>/state     ex.: irrigacao-zona1/switch/valvula_zona_1/state       → "ON" / "OFF"
    <nó>/status                    "online" / "offline"
e recebe ordens em <nó>/switch/<objeto>/command ("ON" / "OFF").

A ponte:
1. assina <nó>/# de cada nó configurado;
2. junta o estado do nó e entrega ao hub uma linha V6 TIPO:ZONA (a mesma do Wi-Fi e do LoRa),
   então telas, alarmes, registro e exportação funcionam sem nada novo;
3. entrega os comandos pendentes do hub: IRR1/IRR2 viram ON/OFF na válvula; LIM1/LIM2/MODO ficam
   na ponte, que faz a rega automática (abre abaixo do limite, fecha no limite + 5 pontos ou no tempo
   máximo). A segurança final continua no nó: o ESPHome fecha a válvula sozinho depois de TMAX.

Só a biblioteca padrão (socket/ssl): MQTT 3.1.1, QoS 0, usuário e senha, TLS opcional (porta 8883).
A senha vem de PHYSIS_MQTT_SENHA (nunca do código nem do instancia.json).
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import struct
import threading
import time

from .protocolo import comando_valido, separar_comando

HISTERESE = 5.0          # pontos de umidade acima do limite para fechar no modo automático
TMAX_PADRAO_MIN = 15     # minutos máximos por rega, se o nó não disser outro


# ── Codificação MQTT 3.1.1 (só o que a ponte usa) ──────────────────────────────────────────────
def _tam(n: int) -> bytes:
    out = bytearray()
    while True:
        b, n = n % 128, n // 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _texto(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("!H", len(b)) + b


def pacote_connect(cliente: str, usuario: str = "", senha: str = "", keepalive: int = 60) -> bytes:
    flags = 0x02 | (0x80 if usuario else 0) | (0x40 if usuario and senha else 0)      # clean session
    corpo = _texto("MQTT") + bytes([4, flags]) + struct.pack("!H", keepalive) + _texto(cliente)
    if usuario:
        corpo += _texto(usuario)
        if senha:
            corpo += _texto(senha)
    return bytes([0x10]) + _tam(len(corpo)) + corpo


def pacote_subscribe(pid: int, topicos: list[str]) -> bytes:
    corpo = struct.pack("!H", pid) + b"".join(_texto(t) + b"\x00" for t in topicos)
    return bytes([0x82]) + _tam(len(corpo)) + corpo


def pacote_publish(topico: str, carga: str, reter: bool = False) -> bytes:
    corpo = _texto(topico) + carga.encode("utf-8")
    return bytes([0x30 | (1 if reter else 0)]) + _tam(len(corpo)) + corpo


PINGREQ, DISCONNECT = b"\xc0\x00", b"\xe0\x00"


def ler_pacote(ler) -> tuple[int, bytes]:
    """ler(n) devolve exatamente n bytes (ou levanta). Devolve (tipo, corpo)."""
    cab = ler(1)[0]
    n, mult = 0, 1
    for _ in range(4):
        b = ler(1)[0]
        n += (b & 0x7F) * mult
        if not b & 0x80:
            break
        mult *= 128
    else:
        raise ValueError("tamanho MQTT inválido")
    return cab, ler(n) if n else b""


def ler_publish(cab: int, corpo: bytes) -> tuple[str, str]:
    t = struct.unpack("!H", corpo[:2])[0]
    topico = corpo[2:2 + t].decode("utf-8", "replace")
    i = 2 + t + (2 if (cab >> 1) & 3 else 0)          # QoS > 0 traz o id do pacote
    return topico, corpo[i:].decode("utf-8", "replace").strip()


# ── Estado de cada nó e tradução para a linha V6 ──────────────────────────────────────────────
class No:
    """Configuração de um nó: {"no": "irrigacao-zona1", "id": 21, "u1": "umidade_solo_zona_1",
    "ir1": "valvula_zona_1", "u2": ..., "ir2": ..., "bomba": ..., "bat": ..., "tmax": 15}."""

    def __init__(self, cfg: dict):
        self.nome = str(cfg["no"])
        self.id = int(cfg["id"])
        if not 1 <= self.id <= 99:
            raise ValueError("id do nó entre 1 e 99")
        self.obj = {k: str(cfg[k]) for k in ("u1", "u2", "ir1", "ir2", "bomba", "bat") if cfg.get(k)}
        self.tmax = int(cfg.get("tmax") or TMAX_PADRAO_MIN)
        self.val: dict[str, float | int | None] = {}
        self.lim = {1: None, 2: None}
        self.modo = "MANUAL"
        self.aberta_em: dict[int, float] = {}
        self.online = None

    def chave_de(self, objeto: str) -> str | None:
        for k, o in self.obj.items():
            if o == objeto:
                return k
        return None

    def linha(self, agora: float) -> str:
        def v(k, casas=1):
            x = self.val.get(k)
            if x is None:
                return "-"
            return str(int(x)) if k in ("ir1", "ir2", "bomba") else f"{x:.{casas}f}"
        lim = lambda i: "-" if self.lim[i] is None else f"{self.lim[i]:.1f}"
        # o hub guarda uma leitura por (nó, segundo): duas mudanças no mesmo segundo andam 1 s para não se perder
        self.ultimo_ts = max(int(agora), getattr(self, "ultimo_ts", 0) + 1)
        agora = self.ultimo_ts
        return (f"ID:{self.id},TIPO:ZONA,U1:{v('u1')},IR1:{v('ir1')},U2:{v('u2')},IR2:{v('ir2')},BOMBA:{v('bomba')},"
                f"TMAX:{self.tmax},LIM1:{lim(1)},LIM2:{lim(2)},BAT:{v('bat', 2)},TS:{int(agora)}")


def _num(carga: str) -> float | None:
    try:
        f = float(carga)
        return f if f == f and abs(f) != float("inf") else None
    except ValueError:
        return None


def _liga(carga: str) -> int | None:
    c = carga.strip().upper()
    return 1 if c in ("ON", "1", "TRUE") else 0 if c in ("OFF", "0", "FALSE") else None


class Ponte:
    """Sem rede: recebe (tópico, carga), devolve linhas V6 para o hub e (tópico, carga) para publicar."""

    def __init__(self, nos: list[dict], relogio=time.time):
        self.nos = {n.nome: n for n in (No(c) for c in nos)}
        self.por_id = {n.id: n for n in self.nos.values()}
        self.relogio = relogio

    def topicos(self) -> list[str]:
        return [f"{n}/#" for n in self.nos]

    def mensagem(self, topico: str, carga: str) -> tuple[list[str], list[tuple[str, str]]]:
        partes = topico.split("/")
        no = self.nos.get(partes[0])
        if not no:
            return [], []
        if len(partes) == 2 and partes[1] == "status":
            no.online = carga.strip().lower() == "online"
            return [], []
        if len(partes) != 4 or partes[3] != "state" or partes[1] not in ("sensor", "switch", "binary_sensor"):
            return [], []
        k = no.chave_de(partes[2])
        if not k:
            return [], []
        x = _liga(carga) if k in ("ir1", "ir2", "bomba") else _num(carga)
        if x is None:
            return [], []
        antes = no.val.get(k)
        no.val[k] = x
        agora = self.relogio()
        if k in ("ir1", "ir2"):
            i = int(k[-1])
            if x and not antes:
                no.aberta_em[i] = agora
            elif not x:
                no.aberta_em.pop(i, None)
        pub = self._automatico(no, agora)
        # válvula e bomba mudando: linha na hora; umidade e bateria: a cada leitura do nó (60 s no ESPHome)
        return [no.linha(agora)], pub

    def _valvula(self, no: No, i: int, ligar: bool) -> list[tuple[str, str]]:
        obj = no.obj.get(f"ir{i}")
        return [(f"{no.nome}/switch/{obj}/command", "ON" if ligar else "OFF")] if obj else []

    def _automatico(self, no: No, agora: float) -> list[tuple[str, str]]:
        pub: list[tuple[str, str]] = []
        for i in (1, 2):
            aberta = bool(no.val.get(f"ir{i}"))
            if aberta and agora - no.aberta_em.get(i, agora) >= no.tmax * 60:
                pub += self._valvula(no, i, False)          # tempo máximo: fecha em qualquer modo
                continue
            if no.modo != "AUTO" or no.lim[i] is None:
                continue
            u = no.val.get(f"u{i}")
            if u is None:
                continue
            if not aberta and u < no.lim[i]:
                pub += self._valvula(no, i, True)
            elif aberta and u >= no.lim[i] + HISTERESE:
                pub += self._valvula(no, i, False)
        return pub

    def comando(self, linha: str) -> list[tuple[str, str]]:
        """Comando V6 do hub (CMD:21:IRR1:1) → o que publicar. LIM e MODO ficam na ponte."""
        ok, destino, normal = comando_valido(linha)
        if not ok:
            return []
        _, acao, arg = separar_comando(normal)
        alvos = list(self.por_id.values()) if destino == 0 else [self.por_id[destino]] if destino in self.por_id else []
        pub: list[tuple[str, str]] = []
        for no in alvos:
            if acao in ("IRR1", "IRR2"):
                pub += self._valvula(no, int(acao[-1]), arg == "1")
            elif acao in ("LIM1", "LIM2"):
                no.lim[int(acao[-1])] = float(arg)
                pub += self._automatico(no, self.relogio())
            elif acao == "MODO":
                no.modo = arg
                pub += self._automatico(no, self.relogio())
        return pub

    def verificar(self) -> list[tuple[str, str]]:
        """Chamado de tempos em tempos: aplica o tempo máximo mesmo sem mensagem nova."""
        agora = self.relogio()
        return [p for no in self.nos.values() for p in self._automatico(no, agora)]


# ── Cliente com reconexão ──────────────────────────────────────────────────────────────────────
def config_de(instancia: dict) -> dict | None:
    """Configuração: instancia.json "mqtt" (broker, porta, usuario, tls, nos) e variáveis de ambiente
    PHYSIS_MQTT_BROKER / _PORTA / _USUARIO / _SENHA / _NOS (JSON). Sem broker, a ponte não liga."""
    c = dict((instancia or {}).get("mqtt") or {})
    env = os.environ
    c["broker"] = env.get("PHYSIS_MQTT_BROKER") or c.get("broker") or ""
    if not c["broker"]:
        return None
    c["tls"] = (env.get("PHYSIS_MQTT_TLS") or str(c.get("tls", ""))).lower() in ("1", "true", "sim")
    c["porta"] = int(env.get("PHYSIS_MQTT_PORTA") or c.get("porta") or (8883 if c["tls"] else 1883))
    c["usuario"] = env.get("PHYSIS_MQTT_USUARIO") or c.get("usuario") or ""
    c["senha"] = env.get("PHYSIS_MQTT_SENHA") or ""
    if env.get("PHYSIS_MQTT_NOS"):
        c["nos"] = json.loads(env["PHYSIS_MQTT_NOS"])
    c["nos"] = c.get("nos") or []
    return c if c["nos"] else None


def rodar(hub, cfg: dict, parar: threading.Event, conectar=None) -> None:
    """Liga no broker, repassa as mensagens ao hub e os comandos aos nós; reconecta com espera crescente."""
    ponte = Ponte(cfg["nos"], relogio=hub.relogio)
    espera = 2
    while not parar.is_set():
        try:
            if conectar:
                s = conectar()
            else:
                s = socket.create_connection((cfg["broker"], cfg["porta"]), timeout=10)
                if cfg.get("tls"):
                    s = ssl.create_default_context().wrap_socket(s, server_hostname=cfg["broker"])
            _sessao(hub, ponte, s, cfg, parar)
            espera = 2
        except (OSError, ValueError, struct.error) as exc:
            hub_registrar(hub, f"MQTT fora: {exc}")
        parar.wait(espera)
        espera = min(espera * 2, 120)


def hub_registrar(hub, texto: str) -> None:
    try:
        hub.registrar("mqtt", "ponte", {"o_que": texto[:200]})
    except Exception:       # o registro nunca derruba a ponte
        pass


def _sessao(hub, ponte: Ponte, s, cfg: dict, parar: threading.Event) -> None:
    s.settimeout(1.0)
    trava = threading.Lock()
    buf = bytearray()

    def ler(n):
        while len(buf) < n:
            if parar.is_set():
                raise OSError("parando")
            try:
                d = s.recv(4096)
            except socket.timeout:
                tique()
                continue
            if not d:
                raise OSError("broker fechou a conexão")
            buf.extend(d)
        out = bytes(buf[:n]); del buf[:n]
        return out

    def enviar(b: bytes):
        with trava:
            s.sendall(b)

    ultimo = [time.time(), 0.0]

    def tique():
        agora = time.time()
        if agora - ultimo[0] >= 30:
            enviar(PINGREQ); ultimo[0] = agora
        if agora - ultimo[1] >= 2:            # comandos pendentes do hub e tempo máximo das válvulas
            ultimo[1] = agora
            pub = list(ponte.verificar())
            for no in ponte.por_id.values():
                for linha in hub.comandos_pendentes(no.id):
                    pub += ponte.comando(linha)
            for t, c in pub:
                enviar(pacote_publish(t, c))

    cliente = f"physis-hub-{os.getpid()}"
    enviar(pacote_connect(cliente, cfg.get("usuario", ""), cfg.get("senha", "")))
    cab, corpo = ler_pacote(ler)
    if cab >> 4 != 2 or len(corpo) < 2 or corpo[1] != 0:
        raise ValueError(f"broker recusou a conexão (código {corpo[1] if len(corpo) > 1 else '?'})")
    enviar(pacote_subscribe(1, ponte.topicos()))
    hub_registrar(hub, f"MQTT ligado em {cfg['broker']}:{cfg['porta']} ({len(ponte.nos)} nós)")
    try:
        while not parar.is_set():
            cab, corpo = ler_pacote(ler)
            if cab >> 4 == 3:
                linhas, pub = ponte.mensagem(*ler_publish(cab, corpo))
                if linhas:
                    hub.receber_lote("\n".join(linhas), origem="mqtt")
                for t, c in pub:
                    enviar(pacote_publish(t, c))
    finally:
        try:
            enviar(DISCONNECT); s.close()
        except OSError:
            pass
