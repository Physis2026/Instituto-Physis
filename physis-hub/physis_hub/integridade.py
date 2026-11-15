"""Integridade dos dados (docs/INTEGRIDADE_DADOS.md).

Princípio (15/11/2026): a Physis entrega o mapeamento e a integridade dos dados; o parceiro entrega a camada de
blockchain, os tokens e a custódia. A fonte da verdade é o BANCO DE DADOS DA PHYSIS, sempre legível por si só:
o blockchain é uma metodologia ADICIONAL, opcional, que só recebe o resumo de um lote que já está guardado aqui.
Este módulo não fala com nenhuma rede.

  fechar_lote(registros, ...)          -> lote imutável (dict) com resumo SHA-256
  conferir_lote(lote)                  -> (ok, problemas)  refaz os resumos
  corrigir(registro, novo, ...)        -> correção que aponta para o anterior (nada é apagado)
  preparar(con)                        -> cria as tabelas (só acrescentar: UPDATE e DELETE são recusados)
  guardar_lote(con, lote)              -> grava o lote e os registros no banco
  ler_lote(con, lote_id) / listar_lotes(con)
  registrar_ancoragem(con, lote_id, metodo, referencia)  -> anota onde o resumo foi registrado (ex.: blockchain)
  exportar_banco_leitura(con, destino) -> arquivo SQLite separado, só para leitura, para auditor ou parceiro
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sqlite3
from pathlib import Path

ESQUEMA = "physis-lote/1"
QUALIDADES = ("valido", "suspeito", "corrigido")
OBRIGATORIOS = ("id", "grandeza", "valor", "unidade", "quando", "origem", "metodo", "qualidade")


def _canonico(obj) -> bytes:
    """JSON canônico: chaves em ordem, sem espaços, UTF-8. Mesmo conteúdo = mesmo resumo, em qualquer máquina."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def resumo(obj) -> str:
    return hashlib.sha256(_canonico(obj)).hexdigest()


def problemas_do_registro(r) -> list[str]:
    """O que impede o registro de entrar num lote (rastreabilidade e qualidade)."""
    if not isinstance(r, dict):
        return ["registro não é um objeto"]
    faltam = [c for c in OBRIGATORIOS if r.get(c) in (None, "", {})]
    erros = [f"{r.get('id', '?')}: falta {c}" for c in faltam]
    origem = r.get("origem") if isinstance(r.get("origem"), dict) else {}
    if r.get("origem") and not origem.get("aparelho") and not origem.get("calculo"):
        erros.append(f"{r.get('id', '?')}: origem sem aparelho nem cálculo")
    if r.get("qualidade") and r.get("qualidade") not in QUALIDADES:
        erros.append(f"{r.get('id', '?')}: qualidade inválida")
    if r.get("qualidade") == "corrigido" and not r.get("corrige"):
        erros.append(f"{r.get('id', '?')}: correção sem o registro anterior")
    v = r.get("valor")
    if isinstance(v, float) and v != v:
        erros.append(f"{r.get('id', '?')}: valor não numérico")
    return erros


def fechar_lote(registros: list[dict], *, lote_id: str, periodo: tuple[str, str], responsavel: str,
                dicionario: str, aceitar_suspeitos: bool = False) -> dict:
    """Fecha o lote. Recusa registro incompleto, id repetido e (por padrão) dado suspeito."""
    erros = [e for r in registros for e in problemas_do_registro(r)]
    ids = [r.get("id") for r in registros if isinstance(r, dict)]
    erros += [f"{i}: id repetido" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if not aceitar_suspeitos:
        erros += [f"{r['id']}: dado suspeito (revisar antes de fechar)" for r in registros
                  if isinstance(r, dict) and r.get("qualidade") == "suspeito"]
    if not registros:
        erros.append("lote vazio")
    if erros:
        raise ValueError("lote não fechado:\n" + "\n".join(erros))
    ordenados = sorted(registros, key=lambda r: str(r["id"]))
    corpo = {"esquema": ESQUEMA, "lote": lote_id, "periodo": list(periodo), "responsavel": responsavel,
             "dicionario": dicionario, "quantidade": len(ordenados),
             "registros": [dict(r, resumo=resumo({k: v for k, v in r.items() if k != "resumo"})) for r in ordenados]}
    return dict(corpo, fechado_em=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                resumo_lote=resumo(corpo))


def conferir_lote(lote: dict) -> tuple[bool, list[str]]:
    """Refaz os resumos. Qualquer mudança depois do fechamento aparece aqui."""
    problemas = []
    corpo = {k: v for k, v in lote.items() if k not in ("fechado_em", "resumo_lote")}
    if resumo(corpo) != lote.get("resumo_lote"):
        problemas.append("resumo do lote não confere")
    for r in lote.get("registros", []):
        if resumo({k: v for k, v in r.items() if k != "resumo"}) != r.get("resumo"):
            problemas.append(f"{r.get('id', '?')}: resumo do registro não confere")
    if lote.get("quantidade") != len(lote.get("registros", [])):
        problemas.append("quantidade não confere")
    return (not problemas, problemas)


def corrigir(anterior: dict, novo_valor, *, novo_id: str, quem: str, motivo: str, quando: str) -> dict:
    """Correção sem apagar: um registro novo que aponta para o anterior e guarda o valor antigo."""
    if not motivo.strip():
        raise ValueError("correção precisa de motivo")
    return dict({k: v for k, v in anterior.items() if k != "resumo"}, id=novo_id, valor=novo_valor, qualidade="corrigido",
                corrige={"id": anterior["id"], "valor_anterior": anterior.get("valor"),
                         "resumo_anterior": anterior.get("resumo") or resumo(anterior), "quem": quem, "motivo": motivo,
                         "quando": quando})


# ── Banco de dados (fonte da verdade, legível sem blockchain) ────────────────────────────────────
ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS integridade_lote (
  lote TEXT PRIMARY KEY, esquema TEXT NOT NULL, periodo_ini TEXT NOT NULL, periodo_fim TEXT NOT NULL,
  responsavel TEXT NOT NULL, dicionario TEXT NOT NULL, quantidade INTEGER NOT NULL,
  fechado_em TEXT NOT NULL, resumo_lote TEXT NOT NULL, conteudo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS integridade_registro (
  lote TEXT NOT NULL, id TEXT NOT NULL, grandeza TEXT NOT NULL, valor TEXT NOT NULL, unidade TEXT NOT NULL,
  quando TEXT NOT NULL, aparelho TEXT NOT NULL, local TEXT NOT NULL, qualidade TEXT NOT NULL,
  corrige TEXT NOT NULL, resumo TEXT NOT NULL, conteudo TEXT NOT NULL, PRIMARY KEY (lote, id));
CREATE TABLE IF NOT EXISTS integridade_ancoragem (
  lote TEXT NOT NULL, metodo TEXT NOT NULL, referencia TEXT NOT NULL, quando TEXT NOT NULL,
  PRIMARY KEY (lote, metodo, referencia));
CREATE TRIGGER IF NOT EXISTS integridade_lote_sem_update BEFORE UPDATE ON integridade_lote
  BEGIN SELECT RAISE(ABORT, 'lote fechado nao muda'); END;
CREATE TRIGGER IF NOT EXISTS integridade_lote_sem_delete BEFORE DELETE ON integridade_lote
  BEGIN SELECT RAISE(ABORT, 'lote fechado nao se apaga'); END;
CREATE TRIGGER IF NOT EXISTS integridade_registro_sem_update BEFORE UPDATE ON integridade_registro
  BEGIN SELECT RAISE(ABORT, 'registro nao muda: use uma correcao'); END;
CREATE TRIGGER IF NOT EXISTS integridade_registro_sem_delete BEFORE DELETE ON integridade_registro
  BEGIN SELECT RAISE(ABORT, 'registro nao se apaga: use uma correcao'); END;
CREATE TRIGGER IF NOT EXISTS integridade_ancoragem_sem_update BEFORE UPDATE ON integridade_ancoragem
  BEGIN SELECT RAISE(ABORT, 'ancoragem nao muda'); END;
CREATE TRIGGER IF NOT EXISTS integridade_ancoragem_sem_delete BEFORE DELETE ON integridade_ancoragem
  BEGIN SELECT RAISE(ABORT, 'ancoragem nao se apaga'); END;
CREATE VIEW IF NOT EXISTS integridade_leitura AS
  SELECT r.lote, r.id, r.grandeza, r.valor, r.unidade, r.quando, r.aparelho, r.local, r.qualidade, r.corrige,
         r.resumo AS resumo_registro, l.resumo_lote, l.fechado_em, l.responsavel, l.dicionario
  FROM integridade_registro r JOIN integridade_lote l USING (lote);
"""

LEIA_ME_BANCO = ("Banco de leitura da Physis. Fonte da verdade dos dados: legível sem blockchain. "
                 "Comece pela visão integridade_leitura. Para conferir: o resumo_lote é o SHA-256 do JSON canônico "
                 "(chaves em ordem, sem espaços, UTF-8) do lote sem os campos fechado_em e resumo_lote, guardado "
                 "na coluna conteudo de integridade_lote. A tabela integridade_ancoragem diz onde o resumo também "
                 "foi registrado (blockchain ou outro método adicional), quando houver.")


def preparar(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA_SQL)


def guardar_lote(con: sqlite3.Connection, lote: dict) -> None:
    ok, problemas = conferir_lote(lote)
    if not ok:
        raise ValueError("lote não confere: " + "; ".join(problemas))
    with con:
        con.execute("INSERT INTO integridade_lote VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (lote["lote"], lote["esquema"], lote["periodo"][0], lote["periodo"][1], lote["responsavel"],
                     lote["dicionario"], lote["quantidade"], lote["fechado_em"], lote["resumo_lote"],
                     _canonico({k: v for k, v in lote.items() if k not in ("fechado_em", "resumo_lote")}).decode("utf-8")))
        for r in lote["registros"]:
            o = r.get("origem") or {}
            con.execute("INSERT INTO integridade_registro VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (lote["lote"], str(r["id"]), str(r["grandeza"]), json.dumps(r["valor"], ensure_ascii=False),
                         str(r["unidade"]), str(r["quando"]), str(o.get("aparelho") or o.get("calculo") or ""),
                         str(o.get("local") or ""), r["qualidade"], (r.get("corrige") or {}).get("id", ""),
                         r["resumo"], _canonico(r).decode("utf-8")))


def ler_lote(con: sqlite3.Connection, lote_id: str) -> dict | None:
    """Reconstrói o lote só a partir do banco (e o confere)."""
    linha = con.execute("SELECT conteudo, fechado_em, resumo_lote FROM integridade_lote WHERE lote=?", (lote_id,)).fetchone()
    if not linha:
        return None
    return dict(json.loads(linha[0]), fechado_em=linha[1], resumo_lote=linha[2])


def listar_lotes(con: sqlite3.Connection) -> list[dict]:
    cols = ("lote", "periodo_ini", "periodo_fim", "responsavel", "quantidade", "fechado_em", "resumo_lote")
    lotes = [dict(zip(cols, l)) for l in con.execute(f"SELECT {', '.join(cols)} FROM integridade_lote ORDER BY fechado_em, lote")]
    for l in lotes:
        l["ancoragens"] = [{"metodo": m, "referencia": r, "quando": q} for m, r, q in
                           con.execute("SELECT metodo, referencia, quando FROM integridade_ancoragem WHERE lote=?", (l["lote"],))]
    return lotes


def registrar_ancoragem(con: sqlite3.Connection, lote_id: str, metodo: str, referencia: str, quando: str | None = None) -> None:
    """Metodologia adicional (ex.: blockchain do parceiro): só anota onde o resumo do lote foi registrado."""
    if not con.execute("SELECT 1 FROM integridade_lote WHERE lote=?", (lote_id,)).fetchone():
        raise ValueError("lote não existe no banco da Physis: guarde antes de ancorar")
    if not str(metodo).strip() or not str(referencia).strip():
        raise ValueError("ancoragem precisa de método e referência")
    with con:
        con.execute("INSERT INTO integridade_ancoragem VALUES (?,?,?,?)", (lote_id, metodo.strip(), referencia.strip(),
                    quando or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")))


def exportar_banco_leitura(con: sqlite3.Connection, destino: str | Path) -> Path:
    """Arquivo SQLite separado com lotes, registros, ancoragens e a visão de leitura. Abre em qualquer leitor de SQLite."""
    destino = Path(destino)
    if destino.exists():
        destino.unlink()
    saida = sqlite3.connect(destino)
    try:
        con.backup(saida)
        tabelas = {n for (n,) in saida.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in sorted(tabelas - {"integridade_lote", "integridade_registro", "integridade_ancoragem"}):
            if not t.startswith("sqlite_"):
                saida.execute(f'DROP TABLE "{t}"')
        for (v,) in saida.execute("SELECT name FROM sqlite_master WHERE type='view' AND name<>'integridade_leitura'").fetchall():
            saida.execute(f'DROP VIEW "{v}"')
        saida.execute("CREATE TABLE leia_me (texto TEXT NOT NULL)")
        saida.execute("INSERT INTO leia_me VALUES (?)", (LEIA_ME_BANCO,))
        saida.commit()
        saida.execute("VACUUM")
    finally:
        saida.close()
    return destino


def abrir_leitura(caminho: str | Path) -> sqlite3.Connection:
    """Abre o banco de leitura sem permissão de escrita."""
    return sqlite3.connect(f"file:{Path(caminho).as_posix()}?mode=ro", uri=True)
