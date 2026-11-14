"""Simulador de dispositivos V6 para teste sem hardware.

Gera linhas plausiveis para os quatro tipos (SOLO, ZONA, COL, COM), responde a
comandos como o firmware responde, e produz linhas defeituosas para o teste de
estresse. Deterministico para uma mesma semente.
"""
from __future__ import annotations

import random

from . import protocolo

TS_BASE = 1_794_600_000        # 2026-11-13, dentro da faixa valida de epoch


class NoSimulado:
    def __init__(self, no: int, tipo: str, rng: random.Random):
        self.no, self.tipo, self.rng = no, tipo, rng
        self.bat = rng.uniform(3.75, 4.10)
        self.lim1 = self.lim2 = 30.0
        self.u1 = rng.uniform(34, 60)
        self.u2 = self.u1 + rng.uniform(-4, 4)
        self.ir1 = self.ir2 = False
        self.manual = False
        self.taxa = rng.uniform(0.02, 0.12)       # % por ciclo simulado
        self.leituras = 0
        self.mudo = False
        self.lat, self.lon = -22.5100 + rng.uniform(-0.01, 0.01), -43.1800 + rng.uniform(-0.01, 0.01)
        self.niv = rng.uniform(40, 95)
        self.porc = 0
        self.imp = False

    def aplicar(self, linha: str) -> None:
        partes = protocolo.separar_comando(linha)
        if partes is None:
            return
        destino, acao, arg = partes
        if destino not in (0, self.no) or not protocolo.argumento_valido(acao, arg):
            return
        if acao == "LIM1":
            self.lim1 = float(arg)
        elif acao == "LIM2":
            self.lim2 = float(arg)
        elif acao == "IRR1":                           # comando manual: o automatico nao desfaz
            self.ir1, self.manual = arg == "1", True
        elif acao == "IRR2" and self.tipo == "ZONA":   # no de solo recusa IRR2
            self.ir2, self.manual = arg == "1", True
        elif acao == "MODO":
            self.manual = arg.upper() == "MANUAL"

    def linha(self, ciclo: int) -> str | None:
        if self.mudo:
            return None
        self.leituras += 1
        self.bat = max(3.30, self.bat - 0.0004)
        ts = TS_BASE + ciclo * 9 + self.no % 9
        base = f"ID:{self.no:02d}"
        if self.tipo in ("SOLO", "ZONA"):
            media = (self.u1 + self.u2) / 2
            if not self.manual:
                if media <= self.lim1:
                    self.ir1 = True
                elif media >= self.lim1 + 12:
                    self.ir1 = False
            delta = 1.6 if self.ir1 else -self.taxa
            self.u1 = min(100.0, max(0.0, self.u1 + delta + self.rng.uniform(-0.05, 0.05)))
            self.u2 = min(100.0, max(0.0, self.u2 + delta + self.rng.uniform(-0.05, 0.05)))
            media = (self.u1 + self.u2) / 2
            if self.leituras < 4:
                p1 = "-1"
            elif media <= self.lim1:
                p1 = "0.0"
            else:
                p1 = f"{min(43200.0, (media - self.lim1) / self.taxa * 0.15):.1f}"
            if self.tipo == "SOLO":
                return (f"{base},U1:{self.u1:.1f},IR1:{int(self.ir1)},U2:{self.u2:.1f},IR2:0,"
                        f"T:{27 + self.rng.uniform(-2, 2):.1f},UAR:{63 + self.rng.uniform(-6, 6):.1f},"
                        f"TSOLO:{23 + self.rng.uniform(-1, 1):.1f},P1:{p1},P2:{p1},"
                        f"LIM1:{self.lim1:.1f},LIM2:{self.lim2:.1f},BAT:{self.bat:.2f},TS:{ts}")
            if not self.manual:
                if self.u2 <= self.lim2:
                    self.ir2 = True
                elif self.u2 >= self.lim2 + 12:
                    self.ir2 = False
            bomba = int(self.ir1 or self.ir2)          # regra: bomba so com valvula aberta
            return (f"{base},TIPO:ZONA,U1:{self.u1:.1f},IR1:{int(self.ir1)},U2:{self.u2:.1f},IR2:{int(self.ir2)},"
                    f"BOMBA:{bomba},TMAX:15,LIM1:{self.lim1:.1f},LIM2:{self.lim2:.1f},BAT:-,TS:{ts}")
        if self.tipo == "COL":
            atv = self.rng.choice((0, 0, 1, 1, 1, 2))
            self.lat += self.rng.uniform(-0.00008, 0.00008) * atv
            self.lon += self.rng.uniform(-0.00008, 0.00008) * atv
            self.imp = self.rng.random() < 0.01
            return (f"{base},TIPO:COL,LAT:{self.lat:.5f},LON:{self.lon:.5f},GPS:1,ATV:{atv},"
                    f"IMP:{int(self.imp)},BAT:{self.bat:.2f},TS:{ts}")
        if self.rng.random() < 0.05 and self.porc < 4:
            self.porc += 1
            self.niv = max(0.0, self.niv - 2.5)
        return (f"{base},TIPO:COM,NIV:{self.niv:.1f},PORC:{self.porc},TAG:{self.no:02X}A1,"
                f"BLOQ:{int(self.porc >= 4)},BAT:-,TS:{ts}")


class Simulador:
    def __init__(self, solo: int = 6, zona: int = 1, col: int = 3, com: int = 1, semente: int = 7):
        self.rng = random.Random(semente)
        total = solo + zona + col + com
        if total > protocolo.TOTAL_NOS:
            raise ValueError(f"no maximo {protocolo.TOTAL_NOS} dispositivos por receptor")
        self.nos: list[NoSimulado] = []
        no = 1
        for tipo, qtd in (("SOLO", solo), ("ZONA", zona), ("COL", col), ("COM", com)):
            for _ in range(qtd):
                self.nos.append(NoSimulado(no, tipo, self.rng))
                no += 1
        self.ciclo = 0

    def passo(self, comandos: list[str] | None = None) -> list[str]:
        for c in comandos or []:
            for n in self.nos:
                n.aplicar(c)
        self.ciclo += 1
        linhas = []
        for n in self.nos:
            l = n.linha(self.ciclo)
            if l is not None:
                # o receptor acrescenta RSSI/SNR medidos na recepcao
                linhas.append(l + f",RSSI:{self.rng.uniform(-110, -75):.1f},SNR:{self.rng.uniform(-3, 11):.1f}")
        return linhas

    def defeituosas(self) -> list[tuple[str, str]]:
        """(linha, motivo esperado de descarte) — o que o campo e a bancada produzem."""
        return [
            ("", "vazia"),
            ("U1:45.2,IR1:1,U2:50.0", "sem_id"),
            ("ID:00,U1:45.2,IR1:1", "id_fora"),
            ("ID:100,U1:45.2,IR1:1", "id_fora"),
            ("ID:abc,U1:45.2", "id_fora"),
            ("ID:-3,U1:45.2", "id_fora"),
            ("CMD:03:IRR1:1", "comando"),
            ("BCN:12,TS:1794600000,CH:0", "beacon"),
            ("ID:05," + "X" * 400, "longa"),
            ("lixo binario \x00\x01\x02 sem campos", "sem_id"),
        ]

    def toleradas(self) -> list[str]:
        """Linhas estranhas que DEVEM ser aceitas sem derrubar nada."""
        return [
            "ID:07,U1:-,IR1:0,U2:-,IR2:0,T:-,UAR:-,TSOLO:-,P1:-,P2:-,LIM1:30.0,LIM2:30.0,BAT:-,TS:0",
            "ID:08,U1:nan,IR1:SIM,U2:null,IR2:OFF,P1:-1,LIM1:30.0,LIM2:30.0,BAT:3.9",
            "ID:09,U1:45,2,IR1:1,U2:50.0,IR2:0,LIM1:30.0,LIM2:30.0",      # virgula decimal parte o campo
            "ID:10;U1:41.0;IR1:0;U2:40.0;IR2:0;LIM1:30.0;LIM2:30.0",       # separador ;
            "ID:11,U1:44.0,IR1:0,U2:43.0,IR2:0,NOVA:xyz,OUTRA:1.5,LIM1:30.0,LIM2:30.0",  # extensao
            "ID:12,U1:45.2,IR1:1\nU2:50.0,IR2:0",                           # \\n no meio vira outra linha sem ID
        ]
