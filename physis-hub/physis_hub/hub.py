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
import secrets
import sqlite3
import threading
import time
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

    def criar_conta(self, nome: str, usuario: str, senha: str, autor: int | None = None) -> dict:
        """A primeira conta e criada por quem abre a instalacao; as demais, por um administrador."""
        nome, usuario = (nome or "").strip(), (usuario or "").strip().lower()
        if not nome or not usuario:
            return {"ok": False, "erro": "Informe o nome e o usuario."}
        if len(senha or "") < self.SENHA_MIN:
            return {"ok": False, "erro": f"A senha precisa de pelo menos {self.SENHA_MIN} caracteres."}
        with self._trava:
            primeira = not self.tem_conta()
            if not primeira:
                papel_autor = self._db.execute("SELECT papel FROM conta WHERE id=?", (autor or -1,)).fetchone()
                if not papel_autor or papel_autor[0] != "administrador":
                    return {"ok": False, "erro": "So um administrador cria novas contas."}
            sal = os.urandom(16)
            try:
                self._db.execute("INSERT INTO conta(nome,usuario,papel,sal,resumo,criado) VALUES(?,?,?,?,?,?)",
                                 (nome, usuario, "administrador" if primeira else "operador", sal,
                                  self._resumir(senha, sal), self.relogio()))
            except sqlite3.IntegrityError:
                return {"ok": False, "erro": "Ja existe uma conta com esse usuario."}
            self._db.commit()
            self.registrar("conta", usuario, {"o_que": "conta criada", "papel": "administrador" if primeira else "operador"})
            self._db.commit()
            return {"ok": True, "primeira": primeira}

    def entrar(self, usuario: str, senha: str) -> dict:
        usuario = (usuario or "").strip().lower()
        with self._trava:
            agora = self.relogio()
            falhas = getattr(self, "_falhas", {})
            self._falhas = falhas
            n, ate = falhas.get(usuario, (0, 0.0))
            if agora < ate:
                return {"ok": False, "erro": f"Muitas tentativas. Tente de novo em {int(ate - agora) + 1} s.", "espera": True}
            linha = self._db.execute("SELECT id, nome, papel, sal, resumo FROM conta WHERE usuario=?", (usuario,)).fetchone()
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
            r = self._db.execute("SELECT c.id, c.nome, c.usuario, c.papel FROM sessao s JOIN conta c ON c.id = s.conta "
                                 "WHERE s.token=? AND s.expira > ?", (token, self.relogio())).fetchone()
        return dict(zip(("id", "nome", "usuario", "papel"), r)) if r else None

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

    def fechar(self) -> None:
        with self._trava:
            self._db.commit()
            self._db.close()
