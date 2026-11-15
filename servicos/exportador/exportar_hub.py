"""Exporta o instantâneo do banco do hub para o PostGIS (BI e mapas), o TimescaleDB (séries) e GeoJSON.

Desenho seguro:
- lê SÓ o instantâneo (/instantaneos/physis-hub.db, aberto "immutable" e somente leitura), nunca o banco vivo;
- lista FECHADA de tabelas sem dado pessoal: medicao, leitura (sem o texto da linha), comando, clima_observado,
  clima_aposta e o ponto do lugar. Contas, sessões, e-mails, Gestão, loja, Saúde: nunca saem.
  Leituras de nós cadastrados como aparelho de Saúde (saude_dispositivo) também ficam de fora;
- incremental por "seq" (o que já foi exportado não é regravado); tabelas pequenas são trocadas inteiras;
- grava com o papel "exportador"; o Superset lê com "bi_leitor" (só SELECT, transação somente leitura).

Variáveis (env/exportador.env): PG_URL (postgresql://exportador:...@postgis:5432/physis),
SERIES_URL (opcional, postgresql://series_gravador:...@timescaledb:5432/series), EXPORTAR_MIN (padrão 15).
`python exportar_hub.py --uma-vez` exporta e sai; `--saude` é o healthcheck.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

INSTANTANEO = Path(os.environ.get("INSTANTANEO_DESTINO", "/instantaneos/physis-hub.db"))
SAIDA_GEOJSON = Path(os.environ.get("SAIDA_GEOJSON", "/saida_geojson"))
VIVO = Path("/tmp/.exportador-vivo")
LOTE = 5000

# ── leitura do instantâneo (só biblioteca padrão; testável sem PostgreSQL) ──────────────────────────
def abrir(caminho: Path = INSTANTANEO) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{caminho}?mode=ro&immutable=1", uri=True)


def _tem_tabela(c: sqlite3.Connection, nome: str) -> bool:
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone() is not None


def _sem_saude(c: sqlite3.Connection, coluna: str) -> str:
    """Filtro SQL que tira os nós cadastrados como aparelho de Saúde (se a tabela existir)."""
    if not _tem_tabela(c, "saude_dispositivo"):
        return ""
    return f" AND {coluna} NOT IN (SELECT no FROM saude_dispositivo WHERE no IS NOT NULL)"


def medicoes(c: sqlite3.Connection, desde_seq: int = 0, limite: int = LOTE) -> list[tuple]:
    """(seq, instante_epoch, no, topico, grandeza, ativo, valor, ts_aparelho, alarme), em ordem de seq."""
    return c.execute(
        "SELECT m.seq, l.recebido, l.no, m.topico, m.grandeza, m.ativo, m.valor, m.ts, m.alarme "
        "FROM medicao m JOIN leitura l ON l.seq = m.leitura WHERE m.seq > ?" + _sem_saude(c, "l.no") +
        " ORDER BY m.seq LIMIT ?", (desde_seq, limite)).fetchall()


def leituras(c: sqlite3.Connection, desde_seq: int = 0, limite: int = LOTE) -> list[tuple]:
    """(seq, no, ts_aparelho, recebido_epoch, origem) — sem o texto da linha."""
    return c.execute("SELECT seq, no, ts, recebido, origem FROM leitura WHERE seq > ?" + _sem_saude(c, "no") +
                     " ORDER BY seq LIMIT ?", (desde_seq, limite)).fetchall()


def pequenas(c: sqlite3.Connection) -> dict[str, list[tuple]]:
    t = {}
    if _tem_tabela(c, "comando"):
        t["comando"] = c.execute("SELECT seq, linha, destino, estado, criado, atualizado, restam FROM comando").fetchall()
    if _tem_tabela(c, "clima_observado"):
        t["clima_observado"] = c.execute("SELECT dia, origem, mm, atualizado FROM clima_observado").fetchall()
    if _tem_tabela(c, "clima_aposta"):
        t["clima_aposta"] = c.execute("SELECT fonte, dia, chove, mm, feita FROM clima_aposta").fetchall()
    return t


def lugar(c: sqlite3.Connection) -> dict | None:
    """Ponto do lugar (clima_local) como Feature GeoJSON, ou None."""
    if not _tem_tabela(c, "clima_local"):
        return None
    r = c.execute("SELECT dados FROM clima_local WHERE id = 1").fetchone()
    if not r:
        return None
    try:
        d = json.loads(r[0])
        lat, lon = float(d["lat"]), float(d["lon"])
    except (ValueError, KeyError, TypeError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    props = {k: d.get(k) for k in ("municipio", "uf", "ibge") if d.get(k) is not None}
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def gravar_geojson(feicoes: dict[str, list[dict]], pasta: Path = SAIDA_GEOJSON) -> list[Path]:
    """Uma FeatureCollection por camada (EPSG:4326), gravada de uma vez (arquivo temporário + os.replace)."""
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = []
    for nome, fs in feicoes.items():
        arq = pasta / f"{nome}.geojson"
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps({"type": "FeatureCollection", "name": nome, "features": fs}, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, arq)
        feitos.append(arq)
    return feitos


# ── gravação no PostgreSQL (psycopg só aqui) ─────────────────────────────────────────────────────────
ESQUEMA_BI = """
CREATE TABLE IF NOT EXISTS bi.medicao (seq bigint PRIMARY KEY, instante timestamptz NOT NULL, no int NOT NULL,
  topico text NOT NULL, grandeza text NOT NULL, ativo text NOT NULL, valor double precision NOT NULL,
  ts_aparelho bigint NOT NULL, alarme text NOT NULL);
CREATE INDEX IF NOT EXISTS medicao_ativo ON bi.medicao (ativo, grandeza, instante);
CREATE TABLE IF NOT EXISTS bi.leitura (seq bigint PRIMARY KEY, no int NOT NULL, ts_aparelho bigint NOT NULL,
  recebido timestamptz NOT NULL, origem text NOT NULL);
CREATE TABLE IF NOT EXISTS bi.comando (seq bigint PRIMARY KEY, linha text, destino int, estado text,
  criado timestamptz, atualizado timestamptz, restam int);
CREATE TABLE IF NOT EXISTS bi.clima_observado (dia text, origem text, mm double precision, atualizado timestamptz,
  PRIMARY KEY (dia, origem));
CREATE TABLE IF NOT EXISTS bi.clima_aposta (fonte text, dia text, chove int, mm double precision, feita timestamptz,
  PRIMARY KEY (fonte, dia));
CREATE TABLE IF NOT EXISTS bi.exportacao (quando timestamptz PRIMARY KEY, medicoes int, leituras int, instantaneo text);
CREATE TABLE IF NOT EXISTS geo.hub_lugar (id int PRIMARY KEY, municipio text, uf text, ibge text,
  geom geometry(Point, 4326) NOT NULL);
"""


def _ultimo(cur, tabela: str) -> int:
    cur.execute(f"SELECT coalesce(max(seq), 0) FROM {tabela}")
    return int(cur.fetchone()[0])


def exportar_pg(c: sqlite3.Connection, url: str) -> dict:
    import psycopg

    n_med = n_lei = 0
    with psycopg.connect(url) as pg, pg.cursor() as cur:
        cur.execute(ESQUEMA_BI)
        desde = _ultimo(cur, "bi.medicao")
        while True:
            lote = medicoes(c, desde)
            if not lote:
                break
            with cur.copy("COPY bi.medicao (seq, instante, no, topico, grandeza, ativo, valor, ts_aparelho, alarme) FROM STDIN") as cp:
                for s, rec, no, top, gr, at, v, ts, al in lote:
                    cp.write_row((s, _ts(rec), no, top, gr, at, v, ts, al))
            n_med += len(lote)
            desde = lote[-1][0]
        desde = _ultimo(cur, "bi.leitura")
        while True:
            lote = leituras(c, desde)
            if not lote:
                break
            with cur.copy("COPY bi.leitura (seq, no, ts_aparelho, recebido, origem) FROM STDIN") as cp:
                for s, no, ts, rec, orig in lote:
                    cp.write_row((s, no, ts, _ts(rec), orig))
            n_lei += len(lote)
            desde = lote[-1][0]
        p = pequenas(c)
        if "comando" in p:
            cur.execute("TRUNCATE bi.comando")
            cur.executemany("INSERT INTO bi.comando VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            [(s, ln, d, e, _ts(cr), _ts(at), r) for s, ln, d, e, cr, at, r in p["comando"]])
        if "clima_observado" in p:
            cur.execute("TRUNCATE bi.clima_observado")
            cur.executemany("INSERT INTO bi.clima_observado VALUES (%s,%s,%s,%s)",
                            [(d, o, mm, _ts(a)) for d, o, mm, a in p["clima_observado"]])
        if "clima_aposta" in p:
            cur.execute("TRUNCATE bi.clima_aposta")
            cur.executemany("INSERT INTO bi.clima_aposta VALUES (%s,%s,%s,%s,%s)",
                            [(f, d, ch, mm, _ts(fe)) for f, d, ch, mm, fe in p["clima_aposta"]])
        lg = lugar(c)
        cur.execute("TRUNCATE geo.hub_lugar")
        if lg:
            lon, lat = lg["geometry"]["coordinates"]
            pr = lg["properties"]
            cur.execute("INSERT INTO geo.hub_lugar VALUES (1, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
                        (pr.get("municipio"), pr.get("uf"), pr.get("ibge"), lon, lat))
        cur.execute("INSERT INTO bi.exportacao VALUES (now(), %s, %s, %s)", (n_med, n_lei, str(INSTANTANEO)))
    return {"medicoes": n_med, "leituras": n_lei, "lugar": bool(lg)}


def exportar_series(c: sqlite3.Connection, url: str) -> int:
    """Ponte para o TimescaleDB (medicao -> medida), incremental por seq guardado em ponte_estado."""
    import psycopg

    n = 0
    with psycopg.connect(url) as pg, pg.cursor() as cur:
        cur.execute("SELECT ultimo_seq FROM ponte_estado WHERE id = 1")
        r = cur.fetchone()
        desde = int(r[0]) if r else 0
        while True:
            lote = medicoes(c, desde)
            if not lote:
                break
            with cur.copy("COPY medida (instante, seq, ativo, grandeza, valor, alarme) FROM STDIN") as cp:
                for s, rec, _no, _top, gr, at, v, _ts_ap, al in lote:
                    cp.write_row((_ts(rec), s, at, gr, v, al))
            desde = lote[-1][0]
            n += len(lote)
            cur.execute("INSERT INTO ponte_estado VALUES (1, %s, now()) ON CONFLICT (id) DO UPDATE "
                        "SET ultimo_seq = excluded.ultimo_seq, quando = excluded.quando", (desde,))
            pg.commit()
    return n


def _ts(epoch):
    from datetime import datetime, timezone
    if epoch is None or epoch == 0:
        return None
    return datetime.fromtimestamp(float(epoch), timezone.utc)


def exportar_uma_vez() -> dict:
    if not INSTANTANEO.is_file():
        return {"ok": False, "erro": f"sem instantâneo em {INSTANTANEO}"}
    c = abrir()
    try:
        r = {"ok": True}
        lg = lugar(c)
        r["geojson"] = [str(p) for p in gravar_geojson({"hub_lugar": [lg] if lg else []})]
        if os.environ.get("PG_URL"):
            r["bi"] = exportar_pg(c, os.environ["PG_URL"])
        if os.environ.get("SERIES_URL"):
            try:
                r["series"] = exportar_series(c, os.environ["SERIES_URL"])
            except Exception as exc:  # noqa: BLE001 — séries são opcionais: não derrubam o BI
                r["series_erro"] = type(exc).__name__
        return r
    finally:
        c.close()


def main() -> None:
    if "--saude" in sys.argv:
        try:
            sys.exit(0 if time.time() - VIVO.stat().st_mtime < 3 * 3600 else 1)
        except OSError:
            sys.exit(1)
    minutos = int(os.environ.get("EXPORTAR_MIN", "15"))
    visto = 0.0
    while True:
        VIVO.touch()
        try:
            mtime = INSTANTANEO.stat().st_mtime if INSTANTANEO.is_file() else 0.0
            if mtime and mtime != visto:
                r = exportar_uma_vez()
                print(json.dumps(r, ensure_ascii=False), flush=True)
                if r.get("ok"):
                    visto = mtime
        except Exception as exc:  # noqa: BLE001 — registra e tenta de novo no próximo ciclo
            print(f"exportação FALHOU: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if "--uma-vez" in sys.argv:
            return
        time.sleep(minutos * 60)


if __name__ == "__main__":
    main()
