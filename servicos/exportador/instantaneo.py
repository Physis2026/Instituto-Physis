"""Instantâneo periódico do banco do hub para o BI (só biblioteca padrão; contêiner sem rede).

Copia /hub/physis-hub.db com a API de backup do SQLite (o hub segue ligado), confere integrity_check,
tira o WAL (journal_mode=DELETE) e troca /instantaneos/physis-hub.db de uma vez (os.replace).
Quem lê o instantâneo (exportar_hub.py) nunca toca o banco vivo.

Variáveis: INSTANTANEO_MIN (minutos entre cópias; padrão 1440), INSTANTANEO_HORA (hora da cópia diária; padrão 2).
`python instantaneo.py --saude` sai 0 se a última cópia é recente (healthcheck).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ORIGEM = Path(os.environ.get("INSTANTANEO_ORIGEM", "/hub/physis-hub.db"))
DESTINO = Path(os.environ.get("INSTANTANEO_DESTINO", "/instantaneos/physis-hub.db"))
MARCA = DESTINO.parent / ".ultimo"


def copiar(origem: Path = ORIGEM, destino: Path = DESTINO) -> int:
    """Faz a cópia; devolve o número de páginas. Levanta erro se a cópia não estiver íntegra."""
    tmp = destino.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    src = sqlite3.connect(origem, timeout=30)
    dst = sqlite3.connect(tmp)
    try:
        with dst:
            src.backup(dst, pages=2048, sleep=0.05)
        r = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if r != "ok":
            raise RuntimeError("integrity_check: " + r)
        dst.execute("PRAGMA journal_mode=DELETE")
        paginas = dst.execute("PRAGMA page_count").fetchone()[0]
    finally:
        dst.close()
        src.close()
    os.chmod(tmp, 0o640)
    os.replace(tmp, destino)
    MARCA.write_text(str(int(time.time())), encoding="ascii")
    return paginas


def proxima(agora: datetime, minutos: int, hora: int) -> datetime:
    if minutos >= 1440:
        alvo = agora.replace(hour=hora, minute=0, second=0, microsecond=0)
        return alvo if alvo > agora else alvo + timedelta(days=1)
    return agora + timedelta(minutes=minutos)


def saude() -> int:
    minutos = int(os.environ.get("INSTANTANEO_MIN", "1440"))
    try:
        idade = time.time() - int(MARCA.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return 1
    return 0 if idade < (minutos + 120) * 60 else 1


def main() -> None:
    if "--saude" in sys.argv:
        sys.exit(saude())
    minutos = int(os.environ.get("INSTANTANEO_MIN", "1440"))
    hora = int(os.environ.get("INSTANTANEO_HORA", "2"))
    while True:
        try:
            if ORIGEM.is_file():
                n = copiar()
                print(f"{datetime.now():%Y-%m-%d %H:%M:%S} instantâneo ok ({n} páginas)", flush=True)
            else:
                print(f"banco do hub ainda não existe em {ORIGEM}", flush=True)
        except (sqlite3.Error, OSError, RuntimeError) as exc:
            print(f"instantâneo FALHOU: {exc}", file=sys.stderr, flush=True)
        espera = (proxima(datetime.now(), minutos, hora) - datetime.now()).total_seconds()
        time.sleep(max(60, espera))


if __name__ == "__main__":
    main()
