"""Logica do hub: recebe linhas V6, guarda, adapta, acompanha comandos.

Sem dependencia fora da biblioteca padrao. O banco e SQLite; um arquivo por
lugar. O registro do lugar e uma cadeia: cada entrada guarda o resumo da
anterior, entao alterar uma linha antiga quebra a verificacao.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from collections import Counter, deque

from . import adaptador, protocolo

OFFLINE_S_PADRAO = 160          # 3 ciclos do TDMA com 99 nos (~53 s cada)
LINHAS_PARA_CONFIRMAR = 3       # leituras do no ate declarar "nao confirmado"
BAT_BAIXA_V = 3.5
NIVEL_RACAO_BAIXO = 15.0

ESQUEMA = """
CREATE TABLE IF NOT EXISTS leitura (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, no INTEGER NOT NULL, ts INTEGER NOT NULL,
  recebido REAL NOT NULL, origem TEXT NOT NULL, linha TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS leitura_unica ON leitura(no, ts) WHERE ts > 0;
CREATE TABLE IF NOT EXISTS medicao (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, leitura INTEGER NOT NULL, topico TEXT NOT NULL,
  grandeza TEXT NOT NULL, ativo TEXT NOT NULL, valor REAL NOT NULL, ts INTEGER NOT NULL,
  alarme TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS medicao_ativo ON medicao(ativo, grandeza, seq);
CREATE TABLE IF NOT EXISTS registro (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, tipo TEXT NOT NULL,
  quando REAL NOT NULL, origem TEXT NOT NULL, conteudo TEXT NOT NULL,
  anterior TEXT NOT NULL, resumo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comando (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, linha TEXT NOT NULL, destino INTEGER NOT NULL,
  estado TEXT NOT NULL, criado REAL NOT NULL, atualizado REAL NOT NULL,
  restam INTEGER NOT NULL, detalhe TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS conta (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, usuario TEXT NOT NULL UNIQUE,
  papel TEXT NOT NULL, sal BLOB NOT NULL, resumo BLOB NOT NULL, criado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessao (
  token TEXT PRIMARY KEY, conta INTEGER NOT NULL, expira REAL NOT NULL);
CREATE TABLE IF NOT EXISTS central (
  tipo TEXT NOT NULL, numero TEXT NOT NULL, dados TEXT NOT NULL, estado TEXT NOT NULL,
  criado REAL NOT NULL, atualizado REAL NOT NULL, PRIMARY KEY (tipo, numero));
CREATE TABLE IF NOT EXISTS central_arquivo (
  id TEXT PRIMARY KEY, pedido TEXT NOT NULL, nome TEXT NOT NULL, tamanho INTEGER NOT NULL,
  dados BLOB NOT NULL, criado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS gestao_estado (
  chave TEXT PRIMARY KEY, valor TEXT NOT NULL, versao INTEGER NOT NULL, atualizado REAL NOT NULL, por TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gestao_arquivo (
  id TEXT PRIMARY KEY, nome TEXT NOT NULL, tipo TEXT NOT NULL, dados BLOB NOT NULL, tamanho INTEGER NOT NULL,
  criado REAL NOT NULL, por TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS instalacao (
  numero TEXT PRIMARY KEY, compra TEXT NOT NULL UNIQUE, org TEXT NOT NULL, nome TEXT NOT NULL,
  email TEXT NOT NULL, modulos TEXT NOT NULL, sal BLOB NOT NULL, resumo BLOB NOT NULL, pacote TEXT,
  criado REAL NOT NULL, ativado REAL, erros INTEGER NOT NULL DEFAULT 0, bloqueado_ate REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS email_saida (
  id INTEGER PRIMARY KEY AUTOINCREMENT, para TEXT NOT NULL, assunto TEXT NOT NULL, corpo TEXT NOT NULL,
  estado TEXT NOT NULL, ref TEXT NOT NULL, criado REAL NOT NULL, enviado REAL, erro TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS loja_item (
  id TEXT PRIMARY KEY, dados TEXT NOT NULL, revisado TEXT, publicado TEXT, atualizado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS envio (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, registro INTEGER NOT NULL, enviado INTEGER NOT NULL DEFAULT 0);
"""


def _resumo(anterior: str, tipo: str, quando: float, origem: str, conteudo: str) -> str:
    base = "|".join((anterior, tipo, f"{quando:.6f}", origem, conteudo))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


class Hub:
    def __init__(self, caminho: str = ":memory:", org: str = "org-teste", lugar: str = "lugar01",
                 offline_s: int = OFFLINE_S_PADRAO, guardar_medicoes: bool = True,
                 enviar_comando=None, relogio=time.time):
        self.org, self.lugar = org, lugar
        self.offline_s = offline_s
        self.guardar_medicoes = guardar_medicoes
        self.enviar_comando = enviar_comando      # funcao(linha) -> (ok, detalhe) ou None
        self.relogio = relogio
        self._trava = threading.RLock()
        self._db = sqlite3.connect(caminho, check_same_thread=False)
        self._db.executescript(ESQUEMA)
        # migração: contas ganham a pessoa da equipe a que pertencem e podem ser desativadas
        cols = {r[1] for r in self._db.execute("PRAGMA table_info(conta)")}
        if "pessoa" not in cols:
            self._db.execute("ALTER TABLE conta ADD COLUMN pessoa TEXT NOT NULL DEFAULT ''")
        if "ativa" not in cols:
            self._db.execute("ALTER TABLE conta ADD COLUMN ativa INTEGER NOT NULL DEFAULT 1")
        self._db.commit()
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self.nos: dict[int, dict] = {}
        self.descartes: Counter = Counter()
        self.contagem: Counter = Counter()
        self.ultimas_descartadas: deque = deque(maxlen=20)
        linha = self._db.execute("SELECT resumo FROM registro ORDER BY seq DESC LIMIT 1").fetchone()
        self._ultimo_resumo = linha[0] if linha else "0" * 64

    # ── Registro do lugar ────────────────────────────────────────────────────
    def registrar(self, tipo: str, origem: str, conteudo: dict) -> str:
        with self._trava:
            quando = self.relogio()
            texto = json.dumps(conteudo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            resumo = _resumo(self._ultimo_resumo, tipo, quando, origem, texto)
            ident = resumo[:16]
            cur = self._db.execute(
                "INSERT INTO registro(id,tipo,quando,origem,conteudo,anterior,resumo) VALUES(?,?,?,?,?,?,?)",
                (ident, tipo, quando, origem, texto, self._ultimo_resumo, resumo))
            self._db.execute("INSERT INTO envio(registro) VALUES(?)", (cur.lastrowid,))
            self._ultimo_resumo = resumo
            return ident

    def verificar_cadeia(self) -> tuple[bool, int]:
        """(integra, quantidade). Recalcula todos os resumos na ordem."""
        with self._trava:
            anterior, n = "0" * 64, 0
            for tipo, quando, origem, conteudo, ant, resumo in self._db.execute(
                    "SELECT tipo,quando,origem,conteudo,anterior,resumo FROM registro ORDER BY seq"):
                if ant != anterior or _resumo(anterior, tipo, quando, origem, conteudo) != resumo:
                    return False, n
                anterior, n = resumo, n + 1
            return True, n

    # ── Entrada de telemetria ────────────────────────────────────────────────
    def receber_lote(self, corpo: str, origem: str = "receptor") -> dict:
        """Corpo text/plain com uma linha V6 por linha, como o receptor envia."""
        aceitas = duplicadas = descartadas = 0
        with self._trava:
            for bruta in corpo.split("\n"):
                if not bruta.strip():
                    continue
                r = self._receber_linha(bruta, origem)
                if r == "aceita":
                    aceitas += 1
                elif r == "duplicada":
                    duplicadas += 1
                else:
                    descartadas += 1
            self._db.commit()
        return {"ok": True, "aceitas": aceitas, "duplicadas": duplicadas, "descartadas": descartadas}

    def _receber_linha(self, bruta: str, origem: str) -> str:
        self.contagem["recebidas"] += 1
        ok, motivo, campos = protocolo.validar_telemetria(bruta)
        if not ok:
            self.descartes[motivo] += 1
            self.ultimas_descartadas.append({"motivo": motivo, "linha": bruta[:160]})
            return "descartada"
        if campos.pop("_FORA", None):
            self.descartes["campo_fora_da_faixa"] += 1   # so o campo foi descartado; a leitura segue
        linha = protocolo.limpar_linha(bruta)
        est = adaptador.interpretar(campos)
        no, ts, agora = est["id"], est["ts"], self.relogio()
        if not (protocolo.EPOCH_MIN_VALIDO <= ts <= protocolo.EPOCH_MAX_VALIDO):
            ts = 0                      # no sem relogio: nao ha como deduplicar
        try:
            cur = self._db.execute(
                "INSERT INTO leitura(no,ts,recebido,origem,linha) VALUES(?,?,?,?,?)",
                (no, ts, agora, origem, linha))
        except sqlite3.IntegrityError:
            self.contagem["duplicadas"] += 1
            return "duplicada"
        self.contagem["aceitas"] += 1
        if self.guardar_medicoes:
            campos_ts = dict(campos)
            campos_ts["TS"] = str(ts)
            self._db.executemany(
                "INSERT INTO medicao(leitura,topico,grandeza,ativo,valor,ts,alarme) VALUES(?,?,?,?,?,?,?)",
                [(cur.lastrowid, m["topico"], m["grandeza"], m["ativo"], m["valor"], m["ts"], m["alarme"])
                 for m in adaptador.adaptar(campos_ts, self.org, self.lugar)])
        self._atualizar_no(est, agora, linha)
        return "aceita"

    def _atualizar_no(self, est: dict, agora: float, linha: str) -> None:
        no = est["id"]
        antes = self.nos.get(no)
        novo = dict(est)
        novo.update({"visto": agora, "linha": linha,
                     "pacotes": (antes["pacotes"] + 1) if antes else 1})
        for chave in ("rssi", "snr"):          # nao medido nesta linha: preserva
            if novo.get(chave) is None and antes:
                novo[chave] = antes.get(chave)
        self.nos[no] = novo
        if antes is None:
            self.registrar("no_descoberto", f"no{no:02d}", {"no": no, "tipo": est["tipo"]})
        else:
            for chave, nome in (("ir1", "valvula1"), ("ir2", "valvula2"), ("bomba", "bomba"), ("imp", "impacto")):
                if chave in est and bool(antes.get(chave)) != bool(est.get(chave)):
                    self.registrar("evento", f"no{no:02d}", {"no": no, "o_que": nome, "valor": bool(est.get(chave))})
        self._conferir_comandos(no, est)

    # ── Comandos ─────────────────────────────────────────────────────────────
    def comandar(self, linha: str, autor: str = "painel") -> dict:
        ok, destino, normal = protocolo.comando_valido(linha)
        if not ok:
            self.contagem["comandos_recusados"] += 1
            return {"ok": False, "erro": "comando fora do contrato"}
        with self._trava:
            agora = self.relogio()
            estado, detalhe = "pendente", ""
            if self.enviar_comando is not None:
                try:
                    enviado, detalhe = self.enviar_comando(normal)
                except Exception as exc:        # receptor fora do ar nao derruba o hub
                    enviado, detalhe = False, f"falha ao enviar: {exc}"
                estado = "enviado" if enviado else "falhou"
            cur = self._db.execute(
                "INSERT INTO comando(linha,destino,estado,criado,atualizado,restam,detalhe) VALUES(?,?,?,?,?,?,?)",
                (normal, destino, estado, agora, agora, LINHAS_PARA_CONFIRMAR, detalhe))
            self.registrar("comando", autor, {"linha": normal, "estado": estado})
            self._db.commit()
            return {"ok": estado != "falhou", "id": cur.lastrowid, "comando": normal, "estado": estado,
                    "detalhe": detalhe}

    def comandos_pendentes(self, no: int | None = None, marcar_enviado: bool = True) -> list[str]:
        """Para quem entrega o comando sem o receptor (no Wi-Fi ou simulador)."""
        with self._trava:
            sql = "SELECT seq, linha FROM comando WHERE estado='pendente'"
            args: tuple = ()
            if no is not None:
                sql += " AND destino IN (?, 0)"
                args = (no,)
            linhas = self._db.execute(sql + " ORDER BY seq", args).fetchall()
            if marcar_enviado and linhas:
                self._db.executemany("UPDATE comando SET estado='enviado', atualizado=? WHERE seq=?",
                                     [(self.relogio(), s) for s, _ in linhas])
                self._db.commit()
            return [l for _, l in linhas]

    def _conferir_comandos(self, no: int, est: dict) -> None:
        abertos = self._db.execute(
            "SELECT seq, linha, restam FROM comando WHERE estado='enviado' AND destino=?", (no,)).fetchall()
        for seq, linha, restam in abertos:
            _, acao, arg = protocolo.separar_comando(linha)
            alvo = {"LIM1": "lim1", "LIM2": "lim2", "IRR1": "ir1", "IRR2": "ir2"}.get(acao)
            if alvo is None:                    # SYNC, MODO, PING: a linha do no nao confirma
                self._db.execute("UPDATE comando SET estado='sem_confirmacao', atualizado=? WHERE seq=?",
                                 (self.relogio(), seq))
                continue
            atual = est.get(alvo)
            if acao.startswith("LIM"):
                bateu = atual is not None and abs(atual - float(arg)) < 0.051
            else:
                bateu = atual is not None and bool(atual) == (arg == "1")
            if bateu:
                novo = "confirmado"
            elif restam <= 1:
                novo = "nao_confirmado"
            else:
                self._db.execute("UPDATE comando SET restam=? WHERE seq=?", (restam - 1, seq))
                continue
            self._db.execute("UPDATE comando SET estado=?, atualizado=? WHERE seq=?", (novo, self.relogio(), seq))
            self.registrar("comando", f"no{no:02d}", {"linha": linha, "estado": novo})

    # ── Leitura para as telas ────────────────────────────────────────────────
    def alertas(self) -> list[dict]:
        agora, out = self.relogio(), []
        for no, n in sorted(self.nos.items()):
            nome = f"No {no:02d}"
            if agora - n["visto"] > self.offline_s:
                out.append({"nivel": "alarme", "no": no, "texto": f"{nome} sem falar ha {int(agora - n['visto'])} s"})
                continue
            if n.get("bat") is not None and n["bat"] < BAT_BAIXA_V:
                out.append({"nivel": "atencao", "no": no, "texto": f"{nome} com bateria baixa ({n['bat']:.2f} V)"})
            if n["tipo"] == "SOLO" and n.get("media") is None:
                out.append({"nivel": "alarme", "no": no, "texto": f"{nome} sem leitura de solo"})
            if n["tipo"] == "ZONA" and n.get("bomba") and not (n.get("ir1") or n.get("ir2")):
                out.append({"nivel": "alarme", "no": no, "texto": f"{nome}: bomba ligada sem valvula aberta"})
            if n["tipo"] == "COL" and n.get("imp"):
                out.append({"nivel": "alarme", "no": no, "texto": f"{nome}: impacto detectado na coleira"})
            if n["tipo"] == "COM" and n.get("niv") is not None and n["niv"] < NIVEL_RACAO_BAIXO:
                out.append({"nivel": "atencao", "no": no, "texto": f"{nome}: racao em {n['niv']:.0f} %"})
        return out

    def painel(self) -> dict:
        with self._trava:
            agora = self.relogio()
            nos = []
            for no, n in sorted(self.nos.items()):
                d = {k: v for k, v in n.items() if k != "linha"}
                d["online"] = agora - n["visto"] <= self.offline_s
                d["ha_s"] = int(agora - n["visto"])
                d["linha"] = n["linha"]
                nos.append(d)
            comandos = [dict(zip(("id", "linha", "destino", "estado", "detalhe"), r)) for r in self._db.execute(
                "SELECT seq,linha,destino,estado,detalhe FROM comando ORDER BY seq DESC LIMIT 20")]
            registro = [dict(zip(("id", "tipo", "quando", "origem", "conteudo"), r)) for r in self._db.execute(
                "SELECT id,tipo,quando,origem,conteudo FROM registro ORDER BY seq DESC LIMIT 40")]
            pend = self._db.execute("SELECT COUNT(*) FROM envio WHERE enviado=0").fetchone()[0]
            return {
                "org": self.org, "lugar": self.lugar, "agora": agora, "nos": nos,
                "alertas": self.alertas(), "comandos": comandos, "registro": registro,
                "saude": {"contagem": dict(self.contagem), "descartes": dict(self.descartes),
                          "ultimas_descartadas": list(self.ultimas_descartadas),
                          "fila_envio": pend},
            }

    def serie(self, ativo: str, grandeza: str, limite: int = 200) -> list[dict]:
        with self._trava:
            linhas = self._db.execute(
                "SELECT ts, valor, alarme FROM medicao WHERE ativo=? AND grandeza=? ORDER BY seq DESC LIMIT ?",
                (ativo, grandeza, limite)).fetchall()
        return [{"ts": t, "valor": v, "alarme": a} for t, v, a in reversed(linhas)]

    def leituras(self, limite: int = 1000, no: int | None = None) -> list[dict]:
        """Historico das leituras aceitas, da mais nova para a mais antiga (tela Registros e download)."""
        limite = max(1, min(int(limite), 20000))
        with self._trava:
            if no is None:
                linhas = self._db.execute("SELECT no, ts, recebido, linha FROM leitura ORDER BY seq DESC LIMIT ?", (limite,)).fetchall()
            else:
                linhas = self._db.execute("SELECT no, ts, recebido, linha FROM leitura WHERE no=? ORDER BY seq DESC LIMIT ?", (int(no), limite)).fetchall()
        return [{"no": n, "ts": t, "recebido": r, "linha": l} for n, t, r, l in linhas]

    def fila_envio(self, limite: int = 500) -> list[dict]:
        """Registros ainda nao confirmados pelo servidor (store-and-forward)."""
        with self._trava:
            return [dict(zip(("seq", "id", "tipo", "quando", "origem", "conteudo", "resumo"), r))
                    for r in self._db.execute(
                        "SELECT e.seq, r.id, r.tipo, r.quando, r.origem, r.conteudo, r.resumo "
                        "FROM envio e JOIN registro r ON r.seq = e.registro WHERE e.enviado=0 "
                        "ORDER BY e.seq LIMIT ?", (limite,))]

    def marcar_enviados(self, ate_seq: int) -> None:
        with self._trava:
            self._db.execute("UPDATE envio SET enviado=1 WHERE seq<=?", (ate_seq,))
            self._db.commit()

    # ── Contas e sessoes (acesso local da instalacao) ───────────────────────
    # Senha nunca e guardada: so o resumo PBKDF2-SHA256 com sal por conta.
    ITERACOES = 240_000
    SENHA_MIN = 10
    SESSAO_S = 30 * 24 * 3600

    @staticmethod
    def _resumir(senha: str, sal: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, Hub.ITERACOES)

    def tem_conta(self) -> bool:
        with self._trava:
            return self._db.execute("SELECT COUNT(*) FROM conta").fetchone()[0] > 0

    def _eh_admin(self, autor: int | None) -> bool:
        r = self._db.execute("SELECT papel, ativa FROM conta WHERE id=?", (autor or -1,)).fetchone()
        return bool(r) and r[0] == "administrador" and bool(r[1])

    def criar_conta(self, nome: str, usuario: str, senha: str, autor: int | None = None,
                    pessoa: str = "", papel: str = "operador") -> dict:
        """A primeira conta e criada por quem abre a instalacao e vira administradora; as demais, por um administrador.

        Com PHYSIS_DOMINIO_EMAIL definido (ex.: physisengineering.com), as contas novas precisam ser e-mails desse dominio."""
        nome, usuario = (nome or "").strip(), (usuario or "").strip().lower()
        if not nome or not usuario:
            return {"ok": False, "erro": "Informe o nome e o usuario."}
        if len(senha or "") < self.SENHA_MIN:
            return {"ok": False, "erro": f"A senha precisa de pelo menos {self.SENHA_MIN} caracteres."}
        dominio = (os.environ.get("PHYSIS_DOMINIO_EMAIL") or "").strip().lower().lstrip("@")
        if dominio and not usuario.endswith("@" + dominio):
            return {"ok": False, "erro": f"Use um e-mail @{dominio}."}
        if papel not in ("operador", "administrador"):
            return {"ok": False, "erro": "Papel invalido."}
        with self._trava:
            primeira = not self.tem_conta()
            if not primeira and not self._eh_admin(autor):
                return {"ok": False, "erro": "So um administrador cria novas contas."}
            papel = "administrador" if primeira else papel
            sal = os.urandom(16)
            try:
                self._db.execute("INSERT INTO conta(nome,usuario,papel,sal,resumo,criado,pessoa) VALUES(?,?,?,?,?,?,?)",
                                 (nome, usuario, papel, sal, self._resumir(senha, sal), self.relogio(), (pessoa or "")[:40]))
            except sqlite3.IntegrityError:
                return {"ok": False, "erro": "Ja existe uma conta com esse usuario."}
            self._db.commit()
            self.registrar("conta", usuario, {"o_que": "conta criada", "papel": papel, "pessoa": pessoa or ""})
            self._db.commit()
            return {"ok": True, "primeira": primeira}

    def contas(self) -> list[dict]:
        with self._trava:
            linhas = self._db.execute("SELECT nome, usuario, papel, pessoa, ativa, criado FROM conta ORDER BY nome").fetchall()
        return [{"nome": n, "usuario": u, "papel": p, "pessoa": pe, "ativa": bool(a), "criado": c} for n, u, p, pe, a, c in linhas]

    def alterar_conta(self, autor: int | None, usuario: str, *, senha: str | None = None, ativa: bool | None = None,
                      papel: str | None = None, pessoa: str | None = None) -> dict:
        """Só administrador. Desativar ou trocar a senha encerra as sessões abertas da conta."""
        usuario = (usuario or "").strip().lower()
        with self._trava:
            if not self._eh_admin(autor):
                return {"ok": False, "erro": "So um administrador altera contas."}
            alvo = self._db.execute("SELECT id, papel FROM conta WHERE usuario=?", (usuario,)).fetchone()
            if not alvo:
                return {"ok": False, "erro": "Conta nao encontrada."}
            if alvo[0] == autor and (ativa is False or papel == "operador"):
                return {"ok": False, "erro": "Voce nao pode desativar nem rebaixar a propria conta."}
            if senha is not None:
                if len(senha) < self.SENHA_MIN:
                    return {"ok": False, "erro": f"A senha precisa de pelo menos {self.SENHA_MIN} caracteres."}
                sal = os.urandom(16)
                self._db.execute("UPDATE conta SET sal=?, resumo=? WHERE id=?", (sal, self._resumir(senha, sal), alvo[0]))
            if ativa is not None:
                self._db.execute("UPDATE conta SET ativa=? WHERE id=?", (1 if ativa else 0, alvo[0]))
            if papel is not None:
                if papel not in ("operador", "administrador"):
                    return {"ok": False, "erro": "Papel invalido."}
                self._db.execute("UPDATE conta SET papel=? WHERE id=?", (papel, alvo[0]))
            if pessoa is not None:
                self._db.execute("UPDATE conta SET pessoa=? WHERE id=?", (pessoa[:40], alvo[0]))
            if senha is not None or ativa is False:
                self._db.execute("DELETE FROM sessao WHERE conta=?", (alvo[0],))
            self.registrar("conta", usuario, {"o_que": "conta alterada", "senha": senha is not None, "ativa": ativa, "papel": papel, "pessoa": pessoa})
            self._db.commit()
            return {"ok": True}

    def trocar_senha(self, conta_id: int, atual: str, nova: str) -> dict:
        with self._trava:
            r = self._db.execute("SELECT usuario, sal, resumo FROM conta WHERE id=?", (conta_id,)).fetchone()
            if not r or not hmac.compare_digest(self._resumir(atual or "", r[1]), r[2]):
                return {"ok": False, "erro": "A senha atual nao confere."}
            if len(nova or "") < self.SENHA_MIN:
                return {"ok": False, "erro": f"A senha nova precisa de pelo menos {self.SENHA_MIN} caracteres."}
            sal = os.urandom(16)
            self._db.execute("UPDATE conta SET sal=?, resumo=? WHERE id=?", (sal, self._resumir(nova, sal), conta_id))
            self.registrar("conta", r[0], {"o_que": "senha trocada pela propria pessoa"})
            self._db.commit()
            return {"ok": True}

    # ── Dados da Gestão Physis no servidor ────────────────────────────────────
    # Cada parte da Gestão (atividades, painel administrativo, reuniões, documentos...) é guardada como
    # um texto JSON por chave, com número de versão. Quem grava informa a versão em que se baseou; se outra
    # pessoa gravou antes, o servidor recusa (conflito) e devolve a versão atual, e a tela junta as duas.
    GESTAO_CHAVE = re.compile(r"^gestao-physis:[A-Za-z0-9_.:-]{1,80}$")
    GESTAO_VALOR_MAX = 8 * 1024 * 1024
    GESTAO_ARQ_MAX = 20 * 1024 * 1024

    def gestao_ler(self, desde: float = 0.0) -> dict:
        with self._trava:
            linhas = self._db.execute("SELECT chave, valor, versao, atualizado, por FROM gestao_estado WHERE atualizado > ?", (desde,)).fetchall()
        return {c: {"valor": v, "versao": n, "atualizado": a, "por": p} for c, v, n, a, p in linhas}

    def gestao_gravar(self, chave: str, valor: str, versao_base: int, por: str) -> dict:
        if not self.GESTAO_CHAVE.match(chave or ""):
            return {"ok": False, "erro": "chave invalida"}
        if not isinstance(valor, str) or len(valor.encode("utf-8")) > self.GESTAO_VALOR_MAX:
            return {"ok": False, "erro": "valor invalido ou grande demais"}
        with self._trava:
            r = self._db.execute("SELECT valor, versao, por, atualizado FROM gestao_estado WHERE chave=?", (chave,)).fetchone()
            atual = r[1] if r else 0
            if int(versao_base or 0) != atual:
                return {"ok": False, "conflito": True, "valor": r[0] if r else None, "versao": atual, "por": r[2] if r else ""}
            if r and r[0] == valor:
                return {"ok": True, "versao": atual, "igual": True}
            agora = max(self.relogio(), (r[3] if r else 0) + 1e-6)
            self._db.execute("INSERT INTO gestao_estado(chave,valor,versao,atualizado,por) VALUES(?,?,?,?,?) "
                             "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, versao=excluded.versao, atualizado=excluded.atualizado, por=excluded.por",
                             (chave, valor, atual + 1, agora, por))
            self.registrar("gestao", por, {"o_que": "gravou", "chave": chave, "versao": atual + 1, "bytes": len(valor)})
            self._db.commit()
            return {"ok": True, "versao": atual + 1, "atualizado": agora}

    def gestao_arquivo_por(self, ident: str, nome: str, tipo: str, dados: bytes, por: str) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", ident or ""):
            return {"ok": False, "erro": "identificador invalido"}
        if not dados or len(dados) > self.GESTAO_ARQ_MAX:
            return {"ok": False, "erro": "arquivo vazio ou maior que 20 MB"}
        nome = (nome or "arquivo").replace("\\", "/").rsplit("/", 1)[-1][:120]
        tipo = tipo if re.fullmatch(r"[\w.+-]+/[\w.+-]+", tipo or "") else "application/octet-stream"
        with self._trava:
            self._db.execute("INSERT OR REPLACE INTO gestao_arquivo(id,nome,tipo,dados,tamanho,criado,por) VALUES(?,?,?,?,?,?,?)",
                             (ident, nome, tipo, dados, len(dados), self.relogio(), por))
            self.registrar("gestao", por, {"o_que": "arquivo guardado", "id": ident, "nome": nome, "bytes": len(dados)})
            self._db.commit()
            return {"ok": True}

    def gestao_arquivo(self, ident: str) -> tuple[str, str, bytes] | None:
        with self._trava:
            r = self._db.execute("SELECT nome, tipo, dados FROM gestao_arquivo WHERE id=?", (ident,)).fetchone()
        return (r[0], r[1], bytes(r[2])) if r else None

    def gestao_arquivo_apagar(self, ident: str, por: str) -> bool:
        with self._trava:
            cur = self._db.execute("DELETE FROM gestao_arquivo WHERE id=?", (ident,))
            if cur.rowcount:
                self.registrar("gestao", por, {"o_que": "arquivo apagado", "id": ident})
            self._db.commit()
            return cur.rowcount > 0

    def entrar(self, usuario: str, senha: str) -> dict:
        usuario = (usuario or "").strip().lower()
        with self._trava:
            agora = self.relogio()
            falhas = getattr(self, "_falhas", {})
            self._falhas = falhas
            n, ate = falhas.get(usuario, (0, 0.0))
            if agora < ate:
                return {"ok": False, "erro": f"Muitas tentativas. Tente de novo em {int(ate - agora) + 1} s.", "espera": True}
            linha = self._db.execute("SELECT id, nome, papel, sal, resumo FROM conta WHERE usuario=? AND ativa=1", (usuario,)).fetchone()
            certo = bool(linha) and hmac.compare_digest(self._resumir(senha or "", linha[3]), linha[4])
            if not certo:
                n += 1
                falhas[usuario] = (n, agora + 30 if n >= 5 else 0.0)
                return {"ok": False, "erro": "Usuario ou senha nao conferem."}
            falhas.pop(usuario, None)
            token = secrets.token_urlsafe(32)
            self._db.execute("DELETE FROM sessao WHERE expira < ?", (agora,))
            self._db.execute("INSERT INTO sessao(token,conta,expira) VALUES(?,?,?)", (token, linha[0], agora + self.SESSAO_S))
            self._db.commit()
            return {"ok": True, "token": token, "nome": linha[1], "papel": linha[2]}

    def sessao(self, token: str | None) -> dict | None:
        if not token:
            return None
        with self._trava:
            r = self._db.execute("SELECT c.id, c.nome, c.usuario, c.papel, c.pessoa FROM sessao s JOIN conta c ON c.id = s.conta "
                                 "WHERE s.token=? AND s.expira > ? AND c.ativa=1", (token, self.relogio())).fetchone()
        return dict(zip(("id", "nome", "usuario", "papel", "pessoa"), r)) if r else None

    def sair(self, token: str | None) -> None:
        with self._trava:
            self._db.execute("DELETE FROM sessao WHERE token=?", (token or "",))
            self._db.commit()

    # ── Caixa central: o que a loja entrega e a gestao recebe, sem copiar e colar ──
    TIPOS_CENTRAL = ("compra", "pedido", "alocacao")

    def central_por(self, tipo: str, numero: str, dados: dict) -> dict:
        """Guarda uma compra paga ou um pedido de proposta. Repetir o mesmo numero nao duplica."""
        if tipo not in self.TIPOS_CENTRAL or not numero or len(numero) > 40:
            return {"ok": False, "erro": "registro invalido"}
        with self._trava:
            ja = self._db.execute("SELECT estado, dados FROM central WHERE tipo=? AND numero=?", (tipo, numero)).fetchone()
            if ja:
                return {"ok": True, "repetido": True, "estado": ja[0], "fatura": (json.loads(ja[1]) or {}).get("fatura")}
            agora = self.relogio()
            if tipo == "compra":      # as faturas sao numeradas em sequencia, a partir de 0000
                dados = dict(dados, fatura="%04d" % self._db.execute("SELECT COUNT(*) FROM central WHERE tipo='compra'").fetchone()[0])
            self._db.execute("INSERT INTO central(tipo,numero,dados,estado,criado,atualizado) VALUES(?,?,?,?,?,?)",
                             (tipo, numero, json.dumps(dados, ensure_ascii=False), "aguardando" if tipo == "compra" else "novo", agora, agora))
            self.registrar("central", numero, {"o_que": f"{tipo} recebida"})
            self._db.commit()
            return {"ok": True, "repetido": False, "estado": "aguardando" if tipo == "compra" else "novo", "fatura": dados.get("fatura")}

    def central_gravar(self, tipo: str, numero: str, dados: dict, estado: str = "ativo") -> dict:
        """Cria ou atualiza um registro que muda com o tempo (a equipe de consultores de um projeto)."""
        if tipo not in self.TIPOS_CENTRAL or not numero or len(numero) > 60:
            return {"ok": False, "erro": "registro invalido"}
        with self._trava:
            agora = self.relogio()
            self._db.execute("INSERT INTO central(tipo,numero,dados,estado,criado,atualizado) VALUES(?,?,?,?,?,?) "
                             "ON CONFLICT(tipo,numero) DO UPDATE SET dados=excluded.dados, estado=excluded.estado, atualizado=excluded.atualizado",
                             (tipo, numero, json.dumps(dados, ensure_ascii=False), estado, agora, agora))
            self.registrar("central", numero, {"o_que": f"{tipo} gravada"})
            self._db.commit()
            return {"ok": True}

    EXT_ARQUIVO = (".xlsx", ".xls", ".xlsm", ".csv", ".pdf", ".docx", ".doc")
    ARQUIVO_MAX = 20 * 1024 * 1024
    ARQUIVOS_POR_PEDIDO = 10

    def arquivo_por(self, pedido: str, nome: str, dados: bytes) -> dict:
        """Guarda um arquivo de apoio enviado pela loja junto com um pedido de proposta ja recebido."""
        nome = (nome or "").replace("\\", "/").rsplit("/", 1)[-1].strip()[:120]
        if not nome or not nome.lower().endswith(self.EXT_ARQUIVO):
            return {"ok": False, "erro": "so sao aceitos arquivos Excel, PDF e Word"}
        if not dados or len(dados) > self.ARQUIVO_MAX:
            return {"ok": False, "erro": "arquivo vazio ou maior que 20 MB"}
        with self._trava:
            if not self._db.execute("SELECT 1 FROM central WHERE tipo='pedido' AND numero=?", (pedido,)).fetchone():
                return {"ok": False, "erro": "pedido desconhecido"}
            if self._db.execute("SELECT COUNT(*) FROM central_arquivo WHERE pedido=?", (pedido,)).fetchone()[0] >= self.ARQUIVOS_POR_PEDIDO:
                return {"ok": False, "erro": "limite de arquivos por pedido atingido"}
            aid = secrets.token_urlsafe(12)
            self._db.execute("INSERT INTO central_arquivo(id,pedido,nome,tamanho,dados,criado) VALUES(?,?,?,?,?,?)",
                             (aid, pedido, nome, len(dados), dados, self.relogio()))
            self.registrar("central", pedido, {"o_que": "arquivo recebido", "nome": nome, "bytes": len(dados)})
            self._db.commit()
            return {"ok": True, "id": aid, "nome": nome, "tamanho": len(dados)}

    def arquivos_de(self, pedido: str) -> list[dict]:
        with self._trava:
            linhas = self._db.execute("SELECT id, nome, tamanho, criado FROM central_arquivo WHERE pedido=? ORDER BY criado", (pedido,)).fetchall()
        return [{"id": i, "nome": n, "tamanho": t, "criado": c} for i, n, t, c in linhas]

    def arquivo(self, aid: str) -> tuple[str, bytes] | None:
        with self._trava:
            r = self._db.execute("SELECT nome, dados FROM central_arquivo WHERE id=?", (aid,)).fetchone()
        return (r[0], bytes(r[1])) if r else None

    def central_estado(self, tipo: str, numero: str) -> str | None:
        with self._trava:
            r = self._db.execute("SELECT estado FROM central WHERE tipo=? AND numero=?", (tipo, numero)).fetchone()
        return r[0] if r else None

    def central_listar(self) -> list[dict]:
        with self._trava:
            linhas = self._db.execute("SELECT tipo, numero, dados, estado, criado, atualizado FROM central ORDER BY criado").fetchall()
        return [{"tipo": t, "numero": n, "dados": json.loads(d), "estado": e, "criado": c, "atualizado": a} for t, n, d, e, c, a in linhas]

    def central_marcar(self, tipo: str, numero: str, estado: str, quem: str = "") -> bool:
        with self._trava:
            cur = self._db.execute("UPDATE central SET estado=?, atualizado=? WHERE tipo=? AND numero=?", (estado, self.relogio(), tipo, numero))
            if cur.rowcount:
                self.registrar("central", numero, {"o_que": f"{tipo} {estado}", "quem": quem})
            self._db.commit()
            return cur.rowcount > 0

    # ── Montagem automática depois da compra aprovada ─────────────────────────
    # Aprovar o uso de uma compra cria, sozinho: o número da instalação, a plataforma só com os
    # módulos comprados, um código de ativação secreto (guardado só como resumo com sal) e o
    # e-mail de acesso na fila de saída. O código nunca aparece na loja: só no e-mail.
    MODULOS_PLATAFORMA = ("monitoramento", "agua", "zonas", "animais", "sustainkit", "supervisao", "gestao", "painel")
    ATIVAR_ERROS = 5
    ATIVAR_ESPERA_S = 15 * 60

    @staticmethod
    def _codigo_ativacao() -> str:
        abc = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"          # sem 0/O e 1/I, que se confundem
        s = "".join(secrets.choice(abc) for _ in range(12))
        return "-".join((s[0:4], s[4:8], s[8:12]))

    @staticmethod
    def _resumo_codigo(sal: bytes, codigo: str) -> bytes:
        limpo = re.sub(r"[^A-Z0-9]", "", (codigo or "").upper())
        return hashlib.pbkdf2_hmac("sha256", limpo.encode(), sal, 100_000)

    def instalar_compra(self, numero_compra: str, link_base: str, fabricar=None, quem: str = "") -> dict:
        """Monta a instalação de uma compra aprovada. Repetir não cria outra nem troca o código."""
        with self._trava:
            ja = self._db.execute("SELECT numero FROM instalacao WHERE compra=?", (numero_compra,)).fetchone()
            if ja:
                return {"ok": True, "repetido": True, "numero": ja[0]}
            r = self._db.execute("SELECT dados FROM central WHERE tipo='compra' AND numero=?", (numero_compra,)).fetchone()
            if not r:
                return {"ok": False, "erro": "compra desconhecida"}
            dados = json.loads(r[0])
            pag = dados.get("pagador") or {}
            email, nome = str(pag.get("email") or "").strip(), str(pag.get("nome") or "Cliente").strip()[:120]
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                return {"ok": False, "erro": "compra sem e-mail valido"}
            modulos = [m for m in (dados.get("modulos") or []) if m in self.MODULOS_PLATAFORMA]
            cursos = [c for c in (dados.get("cursos") or []) if isinstance(c, dict) and str(c.get("link", "")).startswith("https://")]
            seq = self._db.execute("SELECT COUNT(*) FROM instalacao").fetchone()[0] + 1
            numero = "PH-%04d" % seq
            base = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFD", nome.lower()).encode("ascii", "ignore").decode()).strip("-")[:40] or "cliente"
            org = f"{base}-{seq:04d}"
            codigo, sal = self._codigo_ativacao(), secrets.token_bytes(16)
            pacote = None
            if modulos and fabricar is not None:
                try:
                    pacote = str(fabricar(org, modulos, nome, cursos))
                except Exception as e:          # a instalação existe mesmo sem pacote; a equipe vê o motivo
                    self.registrar("instalacao", numero, {"o_que": "pacote nao montado", "erro": str(e)[:200]})
            self._db.execute("INSERT INTO instalacao(numero,compra,org,nome,email,modulos,sal,resumo,pacote,criado) VALUES(?,?,?,?,?,?,?,?,?,?)",
                             (numero, numero_compra, org, nome, email, json.dumps(modulos), sal, self._resumo_codigo(sal, codigo), pacote, self.relogio()))
            link = link_base.rstrip("/") + "/ativar/" + numero
            linhas = [f"Olá, {nome}.", "",
                      "O seu pedido " + numero_compra + " foi aprovado pela Physis Engineering.", ""]
            if modulos:
                linhas += ["Sua plataforma Physis está pronta:", "",
                           f"  Número da instalação: {numero}",
                           f"  Link de acesso: {link}",
                           f"  Código de ativação: {codigo}", "",
                           "Abra o link, digite o código e baixe a sua plataforma, já com os módulos comprados:",
                           "  " + ", ".join(modulos) + ".",
                           "No primeiro acesso, a plataforma pede o seu nome, um usuário e uma senha. A senha fica só com você.", ""]
            if cursos:
                linhas += ["Seus cursos:"] + [f"  {c.get('nome', 'Curso')}: {c['link']}" for c in cursos] + [""]
            linhas += ["Guarde o código: ele é pessoal e vale só para esta instalação.",
                       "Dúvidas: responda a este e-mail.", "", "Physis Engineering"]
            assunto = f"Physis · seu acesso ({numero})" if modulos else f"Physis · seu pedido {numero_compra} foi aprovado"
            self._db.execute("INSERT INTO email_saida(para,assunto,corpo,estado,ref,criado) VALUES(?,?,?,?,?,?)",
                             (email, assunto, "\n".join(linhas), "pendente", numero, self.relogio()))
            self.registrar("instalacao", quem or "gestao", {"o_que": "instalacao criada", "numero": numero, "compra": numero_compra,
                                                           "modulos": modulos, "pacote": bool(pacote)})
            self._db.commit()
            return {"ok": True, "repetido": False, "numero": numero, "org": org, "link": link, "modulos": modulos,
                    "pacote": bool(pacote), "email": "pendente"}

    def ativar(self, numero: str, codigo: str) -> dict:
        """Confere o código. Cinco erros seguidos bloqueiam por 15 minutos."""
        with self._trava:
            r = self._db.execute("SELECT sal, resumo, pacote, erros, bloqueado_ate, nome, modulos FROM instalacao WHERE numero=?", (numero,)).fetchone()
            if not r:
                return {"ok": False, "erro": "instalacao ou codigo nao conferem"}
            sal, resumo, pacote, erros, ate, nome, modulos = r
            agora = self.relogio()
            if ate > agora:
                return {"ok": False, "erro": "muitas tentativas; espere alguns minutos", "espera": int(ate - agora)}
            if not hmac.compare_digest(bytes(resumo), self._resumo_codigo(bytes(sal), codigo)):
                erros += 1
                self._db.execute("UPDATE instalacao SET erros=?, bloqueado_ate=? WHERE numero=?",
                                 (0 if erros >= self.ATIVAR_ERROS else erros, agora + self.ATIVAR_ESPERA_S if erros >= self.ATIVAR_ERROS else 0, numero))
                self._db.commit()
                return {"ok": False, "erro": "instalacao ou codigo nao conferem"}
            self._db.execute("UPDATE instalacao SET erros=0, ativado=COALESCE(ativado, ?) WHERE numero=?", (agora, numero))
            self.registrar("instalacao", numero, {"o_que": "ativacao conferida"})
            self._db.commit()
            return {"ok": True, "numero": numero, "nome": nome, "modulos": json.loads(modulos), "pacote": pacote}

    def instalacoes(self) -> list[dict]:
        with self._trava:
            linhas = self._db.execute("SELECT numero, compra, org, nome, email, modulos, pacote, criado, ativado FROM instalacao ORDER BY criado").fetchall()
        return [{"numero": n, "compra": c, "org": o, "nome": nm, "email": e, "modulos": json.loads(m), "pacote": bool(p),
                 "criado": cr, "ativado": a} for n, c, o, nm, e, m, p, cr, a in linhas]

    def emails(self, estado: str | None = None) -> list[dict]:
        with self._trava:
            q = "SELECT id, para, assunto, corpo, estado, ref, criado, enviado, erro FROM email_saida"
            linhas = self._db.execute(q + (" WHERE estado=?" if estado else "") + " ORDER BY id", ((estado,) if estado else ())).fetchall()
        return [{"id": i, "para": p, "assunto": a, "corpo": c, "estado": e, "ref": r, "criado": cr, "enviado": en, "erro": er}
                for i, p, a, c, e, r, cr, en, er in linhas]

    def email_marcar(self, ident: int, estado: str, erro: str = "") -> bool:
        if estado not in ("pendente", "enviado", "falhou", "enviado_a_mao"):
            return False
        with self._trava:
            cur = self._db.execute("UPDATE email_saida SET estado=?, erro=?, enviado=? WHERE id=?",
                                   (estado, erro[:300], self.relogio() if estado.startswith("enviado") else None, ident))
            if cur.rowcount and estado.startswith("enviado"):
                # depois de enviado, o código de ativação não fica guardado em texto no servidor
                self._db.execute("UPDATE email_saida SET corpo=? WHERE id=?",
                                 (re.sub(r"(Código de ativação: )[A-Z0-9-]+", r"\1(enviado ao cliente)",
                                         self._db.execute("SELECT corpo FROM email_saida WHERE id=?", (ident,)).fetchone()[0]), ident))
            if cur.rowcount:
                self.registrar("email", str(ident), {"o_que": estado})
            self._db.commit()
            return cur.rowcount > 0

    # ── Catálogo da loja: o servidor é quem diz o que o cliente vê ────────────
    # Regra: tudo nasce interno. Primeiro alguém da Physis revisa (fixa situação e preço);
    # só depois um item em funcionamento pode ir ao público. Mudar conteúdo, preço ou
    # situação depois disso desfaz a revisão e tira do público: precisa revisar de novo.
    LOJA_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
    LOJA_PUBLICAVEL = ("func",)                      # "Em funcionamento"; desenvolvimento, simulação e parcerias não
    LOJA_SITUACOES = ("func", "sim", "dev", "par")
    LOJA_CATEGORIAS = ("", "campo", "agua", "energia", "cert", "cuidado", "mat", "cursos")
    LOJA_TEXTOS = {"nome": 120, "cod": 20, "sub": 400, "carga": 40, "modalidade": 60, "link": 300, "resumo": 2000}

    def _loja_ler(self, ident: str) -> dict | None:
        r = self._db.execute("SELECT dados, revisado, publicado FROM loja_item WHERE id=?", (ident,)).fetchone()
        if not r:
            return None
        d = json.loads(r[0])
        d["revisado"] = json.loads(r[1]) if r[1] else None
        d["publicado"] = json.loads(r[2]) if r[2] else None
        return d

    def loja_gravar(self, ident: str, campos: dict, quem: str) -> dict:
        """Cria ou altera um item. Campos aceitos: st, preco (número ou null = sob consulta), categ, e,
        para produto novo ou curso, nome, cod, sub, carga, modalidade, link, resumo."""
        if not self.LOJA_ID.match(ident or ""):
            return {"ok": False, "erro": "identificador invalido"}
        novo_d: dict = {}
        if "st" in campos:
            if campos["st"] not in self.LOJA_SITUACOES:
                return {"ok": False, "erro": "situacao invalida"}
            novo_d["st"] = campos["st"]
        if "preco" in campos:
            p = campos["preco"]
            if p is not None and (isinstance(p, bool) or not isinstance(p, (int, float)) or p < 0 or p > 10_000_000):
                return {"ok": False, "erro": "preco invalido"}
            novo_d["preco"] = p
        if "categ" in campos:
            if campos["categ"] not in self.LOJA_CATEGORIAS:
                return {"ok": False, "erro": "assunto invalido"}
            novo_d["categ"] = campos["categ"]
        if "novo" in campos:
            novo_d["novo"] = bool(campos["novo"])
        for k, lim in self.LOJA_TEXTOS.items():
            if k in campos:
                v = campos[k]
                if v is not None and (not isinstance(v, str) or len(v) > lim):
                    return {"ok": False, "erro": f"{k} invalido"}
                if k == "link" and v and not v.startswith("https://"):
                    return {"ok": False, "erro": "o link precisa comecar com https://"}
                novo_d[k] = (v or "").strip()
        with self._trava:
            atual = self._loja_ler(ident)
            d = {k: v for k, v in (atual or {}).items() if k not in ("revisado", "publicado")}
            if novo_d.get("novo") and not (d.get("nome") or novo_d.get("nome")):
                return {"ok": False, "erro": "produto novo precisa de nome"}
            mudou = any(d.get(k) != v for k, v in novo_d.items())
            d.update(novo_d)
            revisado = None if mudou else (atual or {}).get("revisado")
            publicado = None if mudou else (atual or {}).get("publicado")
            self._db.execute("INSERT INTO loja_item(id,dados,revisado,publicado,atualizado) VALUES(?,?,?,?,?) "
                             "ON CONFLICT(id) DO UPDATE SET dados=excluded.dados, revisado=excluded.revisado, "
                             "publicado=excluded.publicado, atualizado=excluded.atualizado",
                             (ident, json.dumps(d, ensure_ascii=False), json.dumps(revisado) if revisado else None,
                              json.dumps(publicado) if publicado else None, self.relogio()))
            if mudou:
                self.registrar("loja", quem, {"o_que": "item alterado", "id": ident, "campos": sorted(novo_d)})
            self._db.commit()
            return {"ok": True, "item": self._loja_ler(ident), "revisao_desfeita": mudou and bool((atual or {}).get("revisado"))}

    def loja_revisar(self, ident: str, quem: str, revisado: bool = True) -> dict:
        """Primeira revisão: a pessoa confirma a situação e o preço como estão gravados."""
        with self._trava:
            atual = self._loja_ler(ident)
            if not atual or "st" not in atual:
                return {"ok": False, "erro": "grave a situacao do item antes de revisar"}
            rev = {"por": quem, "em": self.relogio()} if revisado else None
            pub = atual.get("publicado") if revisado else None      # desfazer a revisão tira do público
            self._db.execute("UPDATE loja_item SET revisado=?, publicado=?, atualizado=? WHERE id=?",
                             (json.dumps(rev) if rev else None, json.dumps(pub) if pub else None, self.relogio(), ident))
            self.registrar("loja", quem, {"o_que": "revisado" if revisado else "revisao desfeita", "id": ident})
            self._db.commit()
            return {"ok": True, "item": self._loja_ler(ident)}

    def loja_publicar(self, ident: str, quem: str, publico: bool = True) -> dict:
        with self._trava:
            atual = self._loja_ler(ident)
            if not atual:
                return {"ok": False, "erro": "item desconhecido"}
            if publico:
                if not atual.get("revisado"):
                    return {"ok": False, "erro": "o item precisa da primeira revisao antes de ir ao publico"}
                if atual.get("st") not in self.LOJA_PUBLICAVEL:
                    return {"ok": False, "erro": "so item em funcionamento vai ao publico; em desenvolvimento fica interno"}
            pub = {"por": quem, "em": self.relogio()} if publico else None
            self._db.execute("UPDATE loja_item SET publicado=?, atualizado=? WHERE id=?",
                             (json.dumps(pub) if pub else None, self.relogio(), ident))
            self.registrar("loja", quem, {"o_que": "publicado" if publico else "retirado do publico", "id": ident})
            self._db.commit()
            return {"ok": True, "item": self._loja_ler(ident)}

    def loja_catalogo(self, interno: bool = False) -> dict:
        """Público: só itens revisados, em funcionamento e publicados, sem dados de revisão.
        Interno: tudo, com quem revisou e publicou."""
        with self._trava:
            ids = [r[0] for r in self._db.execute("SELECT id FROM loja_item ORDER BY id")]
            itens = {i: self._loja_ler(i) for i in ids}
        if interno:
            return {"ok": True, "itens": itens}
        visiveis = {}
        for i, d in itens.items():
            if d.get("publicado") and d.get("revisado") and d.get("st") in self.LOJA_PUBLICAVEL:
                visiveis[i] = {k: v for k, v in d.items() if k not in ("revisado", "publicado")}
        return {"ok": True, "itens": visiveis}

    def fechar(self) -> None:
        with self._trava:
            self._db.commit()
            self._db.close()
