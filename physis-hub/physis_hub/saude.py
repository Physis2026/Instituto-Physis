"""Saúde: caixinha de remédios e pulseira de alerta, no computador central do lugar.

Dois produtos que funcionam juntos ou separados (decisão de 14/11/2026):
  caixinha   compartimentos com horário marcado; avisa quando a dose foi tomada, atrasou ou foi esquecida
  pulseira   para pessoas autistas: alerta de crise e local (GPS), batimentos e movimento quando houver

Dados de saúde são sensíveis (LGPD, art. 11). Por isso:
  - só vê os dados quem foi autorizado para aquela pessoa (tabela saude_acesso); nem o administrador vê sem autorização;
  - nada é guardado sem consentimento registrado, com data e hora; menor de 18 anos só com o responsável legal;
  - com o consentimento revogado, o que chega dos aparelhos é descartado e ninguém é avisado;
  - "apagar" remove tudo da pessoa (direito de eliminação);
  - o registro encadeado do hub guarda só o que foi feito e por quem (nunca remédio, horário ou local).

Linhas novas do protocolo V6 ("a homologar", ver docs/SAUDE.md). O receptor/hub ainda descartam esses TIPOs
(protocolo.TIPOS_CONHECIDOS); até a homologação, elas entram pela rota própria POST /api/saude/linha:
  ID:31,TIPO:MED,CMP:1,EVT:TOMADO,BAT:3.91,TS:1794650400
  ID:51,TIPO:PUL,LAT:-22.51003,LON:-43.18012,GPS:1,CRISE:1,BPM:128,MOV:2,BAT:3.80,TS:1794650400
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

from . import protocolo

FUSO = timezone(timedelta(hours=-3))
TIPOS = ("MED", "PUL")
EVENTOS = ("TOMADO", "ATRASO", "ESQUECEU")
MAX_CMP = 8                  # a caixinha atual tem 4; a versão ESP32 pode ter mais
TOLERANCIA_MIN = 60          # como no caixa_remedios.ino: 60 min para confirmar
ANTES_MIN = 30               # tomar até 30 min antes ainda conta para aquele horário
LIGAR_ATE_H = 12             # um evento da caixinha se liga ao horário marcado mais recente das últimas 12 h
VERIFICAR_H = 24             # o hub só cobra doses esquecidas das últimas 24 h (não inunda e-mail ao religar)
BAT_BAIXA_V = 3.45           # bateria de lítio quase vazia — A CONFIRMAR pela equipe técnica
CRISE_AGRUPAR_S = 15 * 60    # sinais de crise seguidos viram um alerta só (atualiza o local)
RETENCAO_POSICAO_DIAS = 30   # o local da pulseira é apagado depois de 30 dias (minimização)
VERSAO_TERMO = "1"
FINALIDADE = ("Acompanhar os horários dos remédios e os alertas da pulseira, e avisar os cuidadores autorizados. "
              "Os dados ficam no computador central do lugar e só são vistos pelas pessoas autorizadas. "
              "O consentimento pode ser retirado a qualquer momento, e os dados podem ser apagados.")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS saude_pessoa (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, nascimento TEXT NOT NULL DEFAULT '',
  menor INTEGER NOT NULL DEFAULT 0, responsavel TEXT NOT NULL DEFAULT '', criado REAL NOT NULL, criado_por TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS saude_consentimento (
  id INTEGER PRIMARY KEY AUTOINCREMENT, pessoa INTEGER NOT NULL, quem TEXT NOT NULL, papel TEXT NOT NULL,
  finalidade TEXT NOT NULL, versao TEXT NOT NULL, dado REAL NOT NULL, revogado REAL, registrado_por TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS saude_acesso (
  pessoa INTEGER NOT NULL, usuario TEXT NOT NULL, dado REAL NOT NULL, por TEXT NOT NULL, PRIMARY KEY (pessoa, usuario));
CREATE TABLE IF NOT EXISTS saude_contato (
  id INTEGER PRIMARY KEY AUTOINCREMENT, pessoa INTEGER NOT NULL, nome TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
  telefone TEXT NOT NULL DEFAULT '', alerta INTEGER NOT NULL DEFAULT 1, criado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS saude_dispositivo (
  no INTEGER PRIMARY KEY, tipo TEXT NOT NULL, pessoa INTEGER NOT NULL, apelido TEXT NOT NULL DEFAULT '',
  criado REAL NOT NULL, visto REAL, bat REAL);
CREATE TABLE IF NOT EXISTS saude_horario (
  id INTEGER PRIMARY KEY AUTOINCREMENT, pessoa INTEGER NOT NULL, cmp INTEGER NOT NULL, hora TEXT NOT NULL,
  dias TEXT NOT NULL, remedio TEXT NOT NULL DEFAULT '', dose TEXT NOT NULL DEFAULT '',
  tolerancia INTEGER NOT NULL DEFAULT 60, criado REAL NOT NULL, removido REAL);
CREATE TABLE IF NOT EXISTS saude_dose (
  id INTEGER PRIMARY KEY AUTOINCREMENT, pessoa INTEGER NOT NULL, horario INTEGER, dia TEXT NOT NULL,
  cmp INTEGER NOT NULL, evento TEXT NOT NULL, quando REAL NOT NULL, ts INTEGER NOT NULL DEFAULT 0, no INTEGER,
  origem TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS saude_dose_unica ON saude_dose(no, cmp, evento, ts) WHERE ts > 0;
CREATE INDEX IF NOT EXISTS saude_dose_pessoa ON saude_dose(pessoa, dia);
CREATE TABLE IF NOT EXISTS saude_posicao (
  id INTEGER PRIMARY KEY AUTOINCREMENT, pessoa INTEGER NOT NULL, no INTEGER NOT NULL, ts INTEGER NOT NULL,
  quando REAL NOT NULL, lat REAL, lon REAL, gps INTEGER NOT NULL, crise INTEGER NOT NULL, bpm REAL, mov INTEGER, bat REAL);
CREATE UNIQUE INDEX IF NOT EXISTS saude_posicao_unica ON saude_posicao(no, ts) WHERE ts > 0;
CREATE TABLE IF NOT EXISTS saude_alerta (
  id INTEGER PRIMARY KEY AUTOINCREMENT, pessoa INTEGER NOT NULL, tipo TEXT NOT NULL, mensagem TEXT NOT NULL,
  ref TEXT NOT NULL UNIQUE, criado REAL NOT NULL, atualizado REAL NOT NULL, lat REAL, lon REAL,
  visto REAL, visto_por TEXT NOT NULL DEFAULT '');
"""

_RE_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_RE_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_RE_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Linhas MED e PUL (a homologar) ───────────────────────────────────────────────────────────────
def _faixa(v, lo, hi):
    return v if v is not None and lo <= v <= hi else None


def ler_linha(bruta: str) -> tuple[bool, str, dict]:
    """(ok, motivo, dados) de uma linha MED ou PUL. Usa as mesmas regras de leitura da linha V6
    (separadores, sentinelas, "primeira chave vence"), sem mudar o protocolo.py.

    Motivos: vazia, longa, comando, beacon, sem_id, id_fora, tipo_desconhecido, cmp_invalido, evento_invalido."""
    linha = protocolo.limpar_linha(bruta or "")
    if not linha:
        return False, "vazia", {}
    if linha.startswith(protocolo.PREFIXO_COMANDO):
        return False, "comando", {}
    if linha.startswith(protocolo.PREFIXO_BEACON):
        return False, "beacon", {}
    if len(linha) > protocolo.LINHA_MAX:
        return False, "longa", {}
    c = protocolo.extrair_campos(linha)
    if "ID" not in c:
        return False, "sem_id", {}
    no = protocolo.para_int(c["ID"], -1)
    if not 1 <= no <= protocolo.TOTAL_NOS:
        return False, "id_fora", {}
    tipo = c.get("TIPO", "").strip().upper()
    if tipo not in TIPOS:
        return False, "tipo_desconhecido", {}
    ts = protocolo.para_int(c.get("TS"), 0)
    if not protocolo.EPOCH_MIN_VALIDO <= ts <= protocolo.EPOCH_MAX_VALIDO:
        ts = 0                                            # aparelho sem relógio: vale a hora de chegada
    d = {"id": no, "tipo": tipo, "ts": ts, "bat": _faixa(protocolo.para_float(c.get("BAT")), 0.0, 60.0), "linha": linha}
    if tipo == "MED":
        cmp_ = protocolo.para_int(c.get("CMP"), -1)
        if not 1 <= cmp_ <= MAX_CMP:
            return False, "cmp_invalido", {}
        evt = c.get("EVT", "").strip().upper()
        if evt not in EVENTOS:
            return False, "evento_invalido", {}
        d.update(cmp=cmp_, evt=evt)
    else:
        gps = protocolo.para_bool(c.get("GPS"), False)
        lat = _faixa(protocolo.para_float(c.get("LAT")), -90.0, 90.0)
        lon = _faixa(protocolo.para_float(c.get("LON")), -180.0, 180.0)
        if not gps or lat is None or lon is None:
            gps, lat, lon = False, None, None
        mov = protocolo.para_int(c.get("MOV"), -1) if c.get("MOV") not in (None, "-") else -1
        d.update(gps=gps, lat=lat, lon=lon, crise=protocolo.para_bool(c.get("CRISE"), False),
                 bpm=_faixa(protocolo.para_float(c.get("BPM")), 20.0, 250.0), mov=mov if 0 <= mov <= 2 else None)
    return True, "", d


def linha_de_dict(d: dict) -> str:
    """{"ID": 31, "TIPO": "MED", ...} -> "ID:31,TIPO:MED,..." (chaves em maiúsculas)."""
    return ",".join(f"{str(k).strip().upper()}:{v}" for k, v in d.items() if v is not None and str(v) != "")


# ── Contas de horário (funções puras: os testes e a tela usam as mesmas regras) ──────────────────
def dia_de(t: float) -> str:
    return datetime.fromtimestamp(t, FUSO).strftime("%Y-%m-%d")


def previsto_de(dia: str, hora: str) -> float:
    y, m, d = (int(x) for x in dia.split("-"))
    hh, mm = (int(x) for x in hora.split(":"))
    return datetime(y, m, d, hh, mm, tzinfo=FUSO).timestamp()


def ocorrencias(horarios: list[dict], ini: float, fim: float) -> list[dict]:
    """Cada dose marcada com hora prevista em [ini, fim). Um horário só conta depois de criado
    (a janela ainda aberta quando foi criado) e até ser removido."""
    out = []
    d0 = datetime.fromtimestamp(ini, FUSO).date() - timedelta(days=1)
    d1 = datetime.fromtimestamp(fim, FUSO).date() + timedelta(days=1)
    for h in horarios:
        tol = int(h.get("tolerancia") or TOLERANCIA_MIN) * 60
        d = d0
        while d <= d1:
            if str(d.isoweekday()) in str(h.get("dias") or ""):
                dia = d.strftime("%Y-%m-%d")
                p = previsto_de(dia, h["hora"])
                if (ini <= p < fim and (not h.get("criado") or p + tol > h["criado"])
                        and (not h.get("removido") or p < h["removido"])):
                    out.append({"horario": h.get("id"), "cmp": h["cmp"], "hora": h["hora"], "remedio": h.get("remedio", ""),
                                "dose": h.get("dose", ""), "dia": dia, "previsto": p, "inicio": p - ANTES_MIN * 60,
                                "fim": p + tol})
            d += timedelta(days=1)
    out.sort(key=lambda o: (o["previsto"], o["cmp"]))
    return out


def estado_dose(oc: dict, eventos: list[tuple[str, float]], agora: float) -> str:
    """tomado | atrasado | esquecido | pendente (na hora, esperando confirmar) | esperando (ainda não é a hora)."""
    tomou = [q for e, q in eventos if e == "TOMADO"]
    if any(q <= oc["fim"] for q in tomou):
        return "tomado"
    if tomou or any(e == "ATRASO" for e, _ in eventos):
        return "atrasado"
    if any(e == "ESQUECEU" for e, _ in eventos) or agora >= oc["fim"]:
        return "esquecido"
    return "pendente" if agora >= oc["previsto"] else "esperando"


def resumo_adesao(estados: list[str]) -> dict:
    """Adesão = doses tomadas (no horário ou com atraso) ÷ doses com resultado conhecido."""
    t, a, e = estados.count("tomado"), estados.count("atrasado"), estados.count("esquecido")
    total = t + a + e
    return {"total": total, "tomadas": t, "atrasadas": a, "esquecidas": e,
            "taxa": round((t + a) / total, 3) if total else None,
            "taxa_no_horario": round(t / total, 3) if total else None}


def _idade(nascimento: str, hoje: date) -> int | None:
    try:
        n = datetime.strptime(nascimento, "%Y-%m-%d").date()
    except ValueError:
        return None
    return hoje.year - n.year - ((hoje.month, hoje.day) < (n.month, n.day))


def _int(v, padrao: int = -1) -> int:
    if isinstance(v, bool):
        return padrao
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return protocolo.para_int(str(v), padrao) if v is not None and re.fullmatch(r"\s*[+-]?\d+\s*", str(v)) else padrao


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


SEM_ACESSO = {"ok": False, "erro": "Você não tem autorização para os dados desta pessoa.", "codigo": 403}


class Saude:
    """Pessoas acompanhadas, consentimento, horários, doses, pulseira e alertas, guardados no hub."""

    def __init__(self, hub):
        self.hub = hub
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    def _agora(self) -> float:
        return self.hub.relogio()

    def _auditar(self, acao: str, pessoa: int | None, por: str) -> None:
        # só o fato e quem fez; nada de remédio, horário ou local (o registro pode ir para a nuvem da Physis)
        self.hub.registrar("saude", por or "plataforma", {"acao": acao, "pessoa": pessoa})

    # ── Acesso e consentimento ───────────────────────────────────────────────────────────────
    def pode(self, usuario: str, pessoa: int) -> bool:
        if not usuario:
            return False
        with self.hub._trava:
            return self._db.execute("SELECT 1 FROM saude_acesso WHERE pessoa=? AND usuario=?",
                                    (pessoa, usuario)).fetchone() is not None

    def consentimento(self, pessoa: int) -> dict | None:
        with self.hub._trava:
            r = self._db.execute("SELECT quem, papel, versao, dado, revogado, registrado_por FROM saude_consentimento "
                                 "WHERE pessoa=? ORDER BY id DESC LIMIT 1", (pessoa,)).fetchone()
        if not r:
            return None
        return {"quem": r[0], "papel": r[1], "versao": r[2], "dado": r[3], "revogado": r[4],
                "registrado_por": r[5], "ativo": r[4] is None}

    def consentido(self, pessoa: int) -> bool:
        c = self.consentimento(pessoa)
        return bool(c and c["ativo"])

    def _validar_consentimento(self, cons: dict, nome: str, menor: bool, responsavel: str) -> tuple[dict | None, str]:
        if not isinstance(cons, dict) or cons.get("aceito") is not True:
            return None, "Sem o consentimento marcado, nada é guardado."
        papel = "responsavel" if menor else (str(cons.get("papel") or "titular").strip().lower())
        if papel not in ("titular", "responsavel"):
            return None, "Quem consente é a própria pessoa (titular) ou o responsável legal."
        if papel == "responsavel" and not responsavel:
            return None, ("Para menor de 18 anos, informe o responsável legal." if menor
                          else "Informe o nome do responsável legal.")
        quem = _txt(cons.get("quem"), 80) or (responsavel if papel == "responsavel" else nome)
        return {"quem": quem, "papel": papel}, ""

    def criar_pessoa(self, d: dict, usuario: str) -> dict:
        if not usuario:
            return {"ok": False, "erro": "Entre com seu usuário para cadastrar.", "codigo": 401}
        nome = _txt(d.get("nome"), 80)
        if not nome:
            return {"ok": False, "erro": "Informe o nome da pessoa."}
        nasc = _txt(d.get("nascimento"), 10)
        agora = self._agora()
        idade = _idade(nasc, datetime.fromtimestamp(agora, FUSO).date()) if nasc else None
        if nasc and (idade is None or idade < 0 or idade > 130):
            return {"ok": False, "erro": "Data de nascimento inválida (use dia/mês/ano)."}
        menor = idade < 18 if idade is not None else bool(d.get("menor"))
        resp = _txt(d.get("responsavel"), 80)
        cons, erro = self._validar_consentimento(d.get("consentimento"), nome, menor, resp)
        if not cons:
            return {"ok": False, "erro": erro}
        with self.hub._trava:
            cur = self._db.execute("INSERT INTO saude_pessoa(nome,nascimento,menor,responsavel,criado,criado_por) "
                                   "VALUES(?,?,?,?,?,?)", (nome, nasc, int(menor), resp, agora, usuario))
            pid = cur.lastrowid
            self._db.execute("INSERT INTO saude_consentimento(pessoa,quem,papel,finalidade,versao,dado,registrado_por) "
                             "VALUES(?,?,?,?,?,?,?)", (pid, cons["quem"], cons["papel"], FINALIDADE, VERSAO_TERMO, agora, usuario))
            self._db.execute("INSERT INTO saude_acesso(pessoa,usuario,dado,por) VALUES(?,?,?,?)", (pid, usuario, agora, usuario))
            self._auditar("pessoa_criada", pid, usuario)
            self._db.commit()
        return {"ok": True, "pessoa": pid, "menor": menor}

    def renovar_consentimento(self, pessoa: int, cons: dict, usuario: str) -> dict:
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        with self.hub._trava:
            nome, menor, resp = self._db.execute("SELECT nome, menor, responsavel FROM saude_pessoa WHERE id=?", (pessoa,)).fetchone()
            ok, erro = self._validar_consentimento(cons, nome, bool(menor), resp)
            if not ok:
                return {"ok": False, "erro": erro}
            agora = self._agora()
            self._db.execute("UPDATE saude_consentimento SET revogado=? WHERE pessoa=? AND revogado IS NULL", (agora, pessoa))
            self._db.execute("INSERT INTO saude_consentimento(pessoa,quem,papel,finalidade,versao,dado,registrado_por) "
                             "VALUES(?,?,?,?,?,?,?)", (pessoa, ok["quem"], ok["papel"], FINALIDADE, VERSAO_TERMO, agora, usuario))
            self._auditar("consentimento_dado", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    def revogar(self, pessoa: int, usuario: str) -> dict:
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        with self.hub._trava:
            self._db.execute("UPDATE saude_consentimento SET revogado=? WHERE pessoa=? AND revogado IS NULL", (self._agora(), pessoa))
            self._auditar("consentimento_revogado", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    def apagar(self, pessoa: int, usuario: str) -> dict:
        """Eliminação: some tudo da pessoa, inclusive os e-mails de aviso ainda não enviados."""
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        with self.hub._trava:
            refs = [f"saude-{i}" for (i,) in self._db.execute("SELECT id FROM saude_alerta WHERE pessoa=?", (pessoa,))]
            for r in refs:
                self._db.execute("DELETE FROM email_saida WHERE ref=? AND estado='pendente'", (r,))
            for t in ("saude_dose", "saude_posicao", "saude_alerta", "saude_horario", "saude_contato",
                      "saude_dispositivo", "saude_acesso", "saude_consentimento"):
                self._db.execute(f"DELETE FROM {t} WHERE pessoa=?", (pessoa,))
            self._db.execute("DELETE FROM saude_pessoa WHERE id=?", (pessoa,))
            self._auditar("pessoa_apagada", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    def dar_acesso(self, pessoa: int, alvo: str, usuario: str) -> dict:
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        alvo = _txt(alvo, 120).lower()
        with self.hub._trava:
            if not self._db.execute("SELECT 1 FROM conta WHERE usuario=? AND ativa=1", (alvo,)).fetchone():
                return {"ok": False, "erro": "Não há conta ativa com esse usuário na plataforma."}
            self._db.execute("INSERT OR IGNORE INTO saude_acesso(pessoa,usuario,dado,por) VALUES(?,?,?,?)",
                             (pessoa, alvo, self._agora(), usuario))
            self._auditar("acesso_dado", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    def tirar_acesso(self, pessoa: int, alvo: str, usuario: str) -> dict:
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        alvo = _txt(alvo, 120).lower()
        with self.hub._trava:
            n = self._db.execute("SELECT COUNT(*) FROM saude_acesso WHERE pessoa=?", (pessoa,)).fetchone()[0]
            if n <= 1:
                return {"ok": False, "erro": "Precisa ficar pelo menos uma pessoa autorizada. Para encerrar, retire o consentimento ou apague os dados."}
            self._db.execute("DELETE FROM saude_acesso WHERE pessoa=? AND usuario=?", (pessoa, alvo))
            self._auditar("acesso_retirado", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    # ── Cadastro: contatos, horários e aparelhos ─────────────────────────────────────────────
    def _exige(self, pessoa: int, usuario: str) -> dict | None:
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        if not self.consentido(pessoa):
            return {"ok": False, "erro": "O consentimento foi retirado. Registre um novo para continuar."}
        return None

    def adicionar_contato(self, pessoa: int, d: dict, usuario: str) -> dict:
        if (e := self._exige(pessoa, usuario)):
            return e
        nome, email, tel = _txt(d.get("nome"), 80), _txt(d.get("email"), 120).lower(), _txt(d.get("telefone"), 30)
        if not nome:
            return {"ok": False, "erro": "Informe o nome do cuidador."}
        if email and not _RE_EMAIL.match(email):
            return {"ok": False, "erro": "E-mail inválido."}
        if not email and not tel:
            return {"ok": False, "erro": "Informe um e-mail ou telefone."}
        alerta = d.get("alerta", True) not in (False, 0, "0", "nao", "não", "")
        with self.hub._trava:
            cur = self._db.execute("INSERT INTO saude_contato(pessoa,nome,email,telefone,alerta,criado) VALUES(?,?,?,?,?,?)",
                                   (pessoa, nome, email, tel, int(alerta), self._agora()))
            self._auditar("contato_incluido", pessoa, usuario)
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid}

    def remover_contato(self, pessoa: int, ident: int, usuario: str) -> dict:
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        with self.hub._trava:
            self._db.execute("DELETE FROM saude_contato WHERE id=? AND pessoa=?", (ident, pessoa))
            self._auditar("contato_removido", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    def adicionar_horario(self, pessoa: int, d: dict, usuario: str) -> dict:
        if (e := self._exige(pessoa, usuario)):
            return e
        cmp_ = _int(d.get("cmp"))
        if not 1 <= cmp_ <= MAX_CMP:
            return {"ok": False, "erro": f"Compartimento de 1 a {MAX_CMP}."}
        hora = _txt(d.get("hora"), 5)
        if len(hora) == 4 and hora[1] == ":":
            hora = "0" + hora
        if not _RE_HORA.match(hora):
            return {"ok": False, "erro": "Hora no formato 08:00."}
        dias = d.get("dias", "1234567")
        dias = "".join(sorted({str(x) for x in (dias if isinstance(dias, list) else list(str(dias)))
                               if len(str(x)) == 1 and str(x) in "1234567"}))
        if not dias:
            return {"ok": False, "erro": "Escolha pelo menos um dia da semana."}
        tol = _int(d.get("tolerancia"), TOLERANCIA_MIN) if d.get("tolerancia") not in (None, "") else TOLERANCIA_MIN
        if not 5 <= tol <= 240:
            return {"ok": False, "erro": "Tolerância de 5 a 240 minutos."}
        with self.hub._trava:
            if self._db.execute("SELECT 1 FROM saude_horario WHERE pessoa=? AND cmp=? AND hora=? AND removido IS NULL",
                                (pessoa, cmp_, hora)).fetchone():
                return {"ok": False, "erro": "Este compartimento já tem esse horário."}
            cur = self._db.execute("INSERT INTO saude_horario(pessoa,cmp,hora,dias,remedio,dose,tolerancia,criado) "
                                   "VALUES(?,?,?,?,?,?,?,?)", (pessoa, cmp_, hora, dias, _txt(d.get("remedio"), 80),
                                                               _txt(d.get("dose"), 40), tol, self._agora()))
            self._auditar("horario_incluido", pessoa, usuario)
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid}

    def remover_horario(self, pessoa: int, ident: int, usuario: str) -> dict:
        """Não apaga: marca como removido, para o histórico de adesão continuar certo."""
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        with self.hub._trava:
            self._db.execute("UPDATE saude_horario SET removido=? WHERE id=? AND pessoa=? AND removido IS NULL",
                             (self._agora(), ident, pessoa))
            self._auditar("horario_removido", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    def vincular(self, pessoa: int, d: dict, usuario: str) -> dict:
        if (e := self._exige(pessoa, usuario)):
            return e
        no, tipo = _int(d.get("no")), str(d.get("tipo") or "").strip().upper()
        if not 1 <= no <= protocolo.TOTAL_NOS:
            return {"ok": False, "erro": "Número do aparelho (ID) de 1 a 99."}
        if tipo not in TIPOS:
            return {"ok": False, "erro": "Tipo do aparelho: MED (caixinha) ou PUL (pulseira)."}
        with self.hub._trava:
            try:
                self._db.execute("INSERT INTO saude_dispositivo(no,tipo,pessoa,apelido,criado) VALUES(?,?,?,?,?)",
                                 (no, tipo, pessoa, _txt(d.get("apelido"), 40), self._agora()))
            except sqlite3.IntegrityError:
                return {"ok": False, "erro": "Este número de aparelho já está em uso."}
            self._auditar("aparelho_ligado", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    def desvincular(self, pessoa: int, no: int, usuario: str) -> dict:
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        with self.hub._trava:
            self._db.execute("DELETE FROM saude_dispositivo WHERE no=? AND pessoa=?", (no, pessoa))
            self._auditar("aparelho_desligado", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    # ── Doses ───────────────────────────────────────────────────────────────────────────────
    def _horarios(self, pessoa: int, cmp_: int | None = None) -> list[dict]:
        q = "SELECT id, cmp, hora, dias, remedio, dose, tolerancia, criado, removido FROM saude_horario WHERE pessoa=?"
        args: tuple = (pessoa,)
        if cmp_ is not None:
            q += " AND cmp=?"
            args += (cmp_,)
        with self.hub._trava:
            return [dict(zip(("id", "cmp", "hora", "dias", "remedio", "dose", "tolerancia", "criado", "removido"), r))
                    for r in self._db.execute(q + " ORDER BY hora, cmp", args)]

    def _eventos(self, pessoa: int, desde_dia: str) -> dict:
        ev: dict = {}
        with self.hub._trava:
            for h, dia, e, q in self._db.execute("SELECT horario, dia, evento, quando FROM saude_dose "
                                                 "WHERE pessoa=? AND dia>=? AND horario IS NOT NULL", (pessoa, desde_dia)):
                ev.setdefault((h, dia), []).append((e, q))
        return ev

    def _doses(self, pessoa: int, ini: float, fim: float, agora: float) -> list[dict]:
        ocs = ocorrencias(self._horarios(pessoa), ini, fim)
        ev = self._eventos(pessoa, dia_de(ini - 86400))
        for o in ocs:
            o["estado"] = estado_dose(o, ev.get((o["horario"], o["dia"]), []), agora)
        return ocs

    def _ligar(self, pessoa: int, cmp_: int, quando: float) -> tuple[int | None, str]:
        """Horário marcado a que um evento da caixinha se refere: o mais recente que já abriu a janela."""
        ocs = [o for o in ocorrencias(self._horarios(pessoa, cmp_), quando - LIGAR_ATE_H * 3600, quando + ANTES_MIN * 60 + 1)
               if o["inicio"] <= quando]
        if not ocs:
            return None, dia_de(quando)
        o = max(ocs, key=lambda x: x["previsto"])
        return o["horario"], o["dia"]

    def marcar_dose(self, pessoa: int, horario: int, dia: str, usuario: str) -> dict:
        """Quem cuida confirma pela tela que a dose foi tomada (caixinha sem rede ou dose dada à mão)."""
        if (e := self._exige(pessoa, usuario)):
            return e
        dia = _txt(dia, 10)
        h = [x for x in self._horarios(pessoa) if x["id"] == horario]
        if not h or not _RE_DIA.match(dia):
            return {"ok": False, "erro": "Horário não encontrado."}
        agora = self._agora()
        p = previsto_de(dia, h[0]["hora"])
        if p - ANTES_MIN * 60 > agora:
            return {"ok": False, "erro": "Ainda não é a hora desta dose."}
        with self.hub._trava:
            self._db.execute("INSERT INTO saude_dose(pessoa,horario,dia,cmp,evento,quando,ts,no,origem) VALUES(?,?,?,?,?,?,0,NULL,?)",
                             (pessoa, horario, dia, h[0]["cmp"], "TOMADO", agora, "tela"))
            self._auditar("dose_confirmada", pessoa, usuario)
            self._db.commit()
        return {"ok": True}

    # ── Entrada dos aparelhos ─────────────────────────────────────────────────────────────────
    def registrar_evento(self, entrada, origem: str = "aparelho") -> dict:
        """Linha V6 (texto) ou dict com as chaves da linha. Devolve o que foi feito e, se houver, o alerta novo."""
        bruta = linha_de_dict(entrada) if isinstance(entrada, dict) else str(entrada or "")
        ok, motivo, d = ler_linha(bruta)
        if not ok:
            return {"ok": False, "motivo": motivo}
        agora = self._agora()
        with self.hub._trava:
            dev = self._db.execute("SELECT pessoa, tipo FROM saude_dispositivo WHERE no=?", (d["id"],)).fetchone()
            if not dev:
                return {"ok": False, "motivo": "aparelho_desconhecido"}
            pessoa, tipo = dev
            if tipo != d["tipo"]:
                return {"ok": False, "motivo": "tipo_trocado"}
            if not self.consentido(pessoa):
                return {"ok": False, "motivo": "sem_consentimento"}     # nada é guardado
            quando = float(d["ts"]) if d["ts"] and d["ts"] <= agora + 600 else agora
            self._db.execute("UPDATE saude_dispositivo SET visto=?, bat=COALESCE(?, bat) WHERE no=?", (agora, d["bat"], d["id"]))
            r = {"ok": True, "tipo": tipo, "pessoa": pessoa, "alertas": []}
            nome = self._db.execute("SELECT nome FROM saude_pessoa WHERE id=?", (pessoa,)).fetchone()[0]
            if tipo == "MED":
                horario, dia = self._ligar(pessoa, d["cmp"], quando)
                try:
                    self._db.execute("INSERT INTO saude_dose(pessoa,horario,dia,cmp,evento,quando,ts,no,origem) VALUES(?,?,?,?,?,?,?,?,?)",
                                     (pessoa, horario, dia, d["cmp"], d["evt"], quando, d["ts"], d["id"], origem))
                except sqlite3.IntegrityError:
                    self._db.commit()
                    return {"ok": True, "duplicada": True, "tipo": tipo, "pessoa": pessoa, "alertas": []}
                r.update(horario=horario, dia=dia)
                if d["evt"] == "ESQUECEU" and horario is not None:
                    hora = next((h["hora"] for h in self._horarios(pessoa, d["cmp"]) if h["id"] == horario), "")
                    a = self._alerta_dose(pessoa, nome, horario, dia, hora, d["cmp"])
                    if a:
                        r["alertas"].append(a)
            else:
                try:
                    self._db.execute("INSERT INTO saude_posicao(pessoa,no,ts,quando,lat,lon,gps,crise,bpm,mov,bat) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                     (pessoa, d["id"], d["ts"], quando, d["lat"], d["lon"], int(d["gps"]), int(d["crise"]),
                                      d["bpm"], d["mov"], d["bat"]))
                except sqlite3.IntegrityError:
                    self._db.commit()
                    return {"ok": True, "duplicada": True, "tipo": tipo, "pessoa": pessoa, "alertas": []}
                self._db.execute("DELETE FROM saude_posicao WHERE pessoa=? AND quando<?", (pessoa, agora - RETENCAO_POSICAO_DIAS * 86400))
                if d["crise"]:
                    a = self._alerta_crise(pessoa, nome, d, quando)
                    if a:
                        r["alertas"].append(a)
            if d["bat"] is not None and d["bat"] < BAT_BAIXA_V:
                qual = "caixinha de remédios" if tipo == "MED" else "pulseira"
                a, novo = self._alerta(pessoa, "bateria", f"Bateria fraca na {qual} de {nome}. Coloque para carregar.",
                                       f"bat:{d['id']}:{dia_de(agora)}")
                if novo:
                    r["alertas"].append(a)
            self._db.commit()
        return r

    # ── Alertas ───────────────────────────────────────────────────────────────────────────────
    def _alerta(self, pessoa: int, tipo: str, msg: str, ref: str, lat=None, lon=None, assunto: str = "") -> tuple[int, bool]:
        """Cria o alerta (uma vez por ref) e põe na fila um e-mail para cada cuidador com e-mail e aviso ligado."""
        agora = self._agora()
        cur = self._db.execute("INSERT OR IGNORE INTO saude_alerta(pessoa,tipo,mensagem,ref,criado,atualizado,lat,lon) "
                               "VALUES(?,?,?,?,?,?,?,?)", (pessoa, tipo, msg, ref, agora, agora, lat, lon))
        if not cur.rowcount:
            return self._db.execute("SELECT id FROM saude_alerta WHERE ref=?", (ref,)).fetchone()[0], False
        aid = cur.lastrowid
        corpo = msg + "\n\nAviso automático da plataforma Physis (Saúde). Você recebe porque foi cadastrado como cuidador."
        for (email,) in self._db.execute("SELECT email FROM saude_contato WHERE pessoa=? AND alerta=1 AND email<>''", (pessoa,)).fetchall():
            self._db.execute("INSERT INTO email_saida(para,assunto,corpo,estado,ref,criado) VALUES(?,?,?,?,?,?)",
                             (email, assunto or "Physis Saúde · aviso", corpo, "pendente", f"saude-{aid}", agora))
        return aid, True

    def _alerta_dose(self, pessoa, nome, horario, dia, hora, cmp_) -> int | None:
        dd = f"{dia[8:10]}/{dia[5:7]}"
        aid, novo = self._alerta(pessoa, "dose_esquecida",
                                 f"A dose das {hora} de {dd} (compartimento {cmp_}) de {nome} não foi confirmada.",
                                 f"dose:{horario}:{dia}", assunto="Physis Saúde · dose não confirmada")
        return aid if novo else None

    def _alerta_crise(self, pessoa, nome, d, quando) -> int | None:
        agora = self._agora()
        aberto = self._db.execute("SELECT id FROM saude_alerta WHERE pessoa=? AND tipo='crise' AND visto IS NULL AND atualizado>=? "
                                  "ORDER BY id DESC LIMIT 1", (pessoa, agora - CRISE_AGRUPAR_S)).fetchone()
        if aberto:
            self._db.execute("UPDATE saude_alerta SET atualizado=?, lat=COALESCE(?,lat), lon=COALESCE(?,lon) WHERE id=?",
                             (agora, d["lat"], d["lon"], aberto[0]))
            return None
        hora = datetime.fromtimestamp(quando, FUSO).strftime("%H:%M")
        onde = f"Último local (GPS): {d['lat']:.5f}, {d['lon']:.5f}." if d["gps"] else "A pulseira está sem posição do GPS agora."
        aid, _ = self._alerta(pessoa, "crise", f"Possível crise de {nome} às {hora}. {onde}",
                              f"crise:{pessoa}:{int(quando)}:{d['id']}", d["lat"], d["lon"],
                              assunto="Physis Saúde · ALERTA: possível crise")
        return aid

    def verificar(self, agora: float | None = None) -> int:
        """Cobra as doses cuja tolerância acabou sem confirmação: marca como esquecida e avisa os cuidadores.
        Devolve quantos alertas novos foram criados."""
        agora = self._agora() if agora is None else agora
        novos = 0
        with self.hub._trava:
            pessoas = [(p, n) for p, n in self._db.execute("SELECT id, nome FROM saude_pessoa").fetchall() if self.consentido(p)]
            for pessoa, nome in pessoas:
                for o in self._doses(pessoa, agora - (VERIFICAR_H + 5) * 3600, agora, agora):
                    if o["estado"] != "esquecido" or o["fim"] <= agora - VERIFICAR_H * 3600:
                        continue
                    ja = self._db.execute("SELECT 1 FROM saude_dose WHERE pessoa=? AND horario=? AND dia=?",
                                          (pessoa, o["horario"], o["dia"])).fetchone()
                    if not ja:
                        self._db.execute("INSERT INTO saude_dose(pessoa,horario,dia,cmp,evento,quando,ts,no,origem) "
                                         "VALUES(?,?,?,?,'ESQUECEU',?,0,NULL,'hub')", (pessoa, o["horario"], o["dia"], o["cmp"], o["fim"]))
                    if self._alerta_dose(pessoa, nome, o["horario"], o["dia"], o["hora"], o["cmp"]):
                        novos += 1
            self._db.commit()
        return novos

    def alertas_pendentes(self, pessoa: int | None = None, agora: float | None = None) -> list[dict]:
        """Alertas ainda não vistos (cobra as doses vencidas antes de responder)."""
        self.verificar(agora)
        q = ("SELECT a.id, a.pessoa, p.nome, a.tipo, a.mensagem, a.criado, a.atualizado, a.lat, a.lon, a.visto "
             "FROM saude_alerta a JOIN saude_pessoa p ON p.id=a.pessoa WHERE a.visto IS NULL")
        args: tuple = ()
        if pessoa is not None:
            q += " AND a.pessoa=?"
            args = (pessoa,)
        with self.hub._trava:
            linhas = self._db.execute(q + " ORDER BY a.tipo='crise' DESC, a.id DESC", args).fetchall()
        return [dict(zip(("id", "pessoa", "nome", "tipo", "mensagem", "criado", "atualizado", "lat", "lon", "visto"), r)) for r in linhas]

    def marcar_visto(self, pessoa: int, ident: int, usuario: str) -> dict:
        if not self.pode(usuario, pessoa):
            return SEM_ACESSO
        with self.hub._trava:
            self._db.execute("UPDATE saude_alerta SET visto=?, visto_por=? WHERE id=? AND pessoa=? AND visto IS NULL",
                             (self._agora(), usuario, ident, pessoa))
            self._db.commit()
        return {"ok": True}

    # ── Leituras para a tela ──────────────────────────────────────────────────────────────────
    def adesao(self, dias: int = 7, pessoa: int | None = None, agora: float | None = None) -> dict:
        """Adesão dos últimos `dias` dias (hoje incluído), só com doses de resultado conhecido.
        Com `pessoa`, o resumo dela; sem, {id: resumo} de todas com consentimento."""
        agora = self._agora() if agora is None else agora
        dias = max(1, min(int(dias), 366))
        if pessoa is None:
            with self.hub._trava:
                ids = [p for (p,) in self._db.execute("SELECT id FROM saude_pessoa").fetchall()]
            return {p: self.adesao(dias, p, agora) for p in ids if self.consentido(p)}
        hoje = datetime.fromtimestamp(agora, FUSO).date()
        d0 = hoje - timedelta(days=dias - 1)
        ini = datetime(d0.year, d0.month, d0.day, tzinfo=FUSO).timestamp()
        doses = [o for o in self._doses(pessoa, ini, agora + 1, agora) if o["estado"] in ("tomado", "atrasado", "esquecido")]
        r = resumo_adesao([o["estado"] for o in doses])
        por_dia = []
        for i in range(dias):
            dia = (d0 + timedelta(days=i)).strftime("%Y-%m-%d")
            s = resumo_adesao([o["estado"] for o in doses if o["dia"] == dia])
            s["dia"] = dia
            por_dia.append(s)
        r.update(dias=dias, por_dia=por_dia)
        return r

    def proximas_doses(self, agora: float | None = None, pessoa: int | None = None, horas: int = 24) -> list[dict]:
        """Doses ainda por tomar: na hora (pendente) ou nas próximas `horas` horas (esperando)."""
        agora = self._agora() if agora is None else agora
        if pessoa is None:
            with self.hub._trava:
                ids = [(p, n) for p, n in self._db.execute("SELECT id, nome FROM saude_pessoa").fetchall()]
            out = []
            for p, n in ids:
                if self.consentido(p):
                    out += [dict(o, pessoa=p, nome=n) for o in self.proximas_doses(agora, p, horas)]
            return sorted(out, key=lambda o: o["previsto"])
        ocs = self._doses(pessoa, agora - 6 * 3600, agora + horas * 3600, agora)
        return [o for o in ocs if o["estado"] in ("pendente", "esperando")]

    def _pessoa(self, pid: int, agora: float) -> dict:
        with self.hub._trava:
            nome, nasc, menor, resp, criado = self._db.execute(
                "SELECT nome, nascimento, menor, responsavel, criado FROM saude_pessoa WHERE id=?", (pid,)).fetchone()
            acesso = [u for (u,) in self._db.execute("SELECT usuario FROM saude_acesso WHERE pessoa=? ORDER BY dado", (pid,))]
        p = {"id": pid, "nome": nome, "nascimento": nasc, "menor": bool(menor), "responsavel": resp, "criado": criado,
             "consentimento": self.consentimento(pid), "acesso": acesso}
        p["ativo"] = bool(p["consentimento"] and p["consentimento"]["ativo"])
        if not p["ativo"]:
            return p            # sem consentimento, a tela não mostra dado de saúde
        with self.hub._trava:
            p["contatos"] = [dict(zip(("id", "nome", "email", "telefone", "alerta"), r[:4] + (bool(r[4]),))) for r in self._db.execute(
                "SELECT id, nome, email, telefone, alerta FROM saude_contato WHERE pessoa=? ORDER BY id", (pid,))]
            p["dispositivos"] = [dict(zip(("no", "tipo", "apelido", "visto", "bat"), r)) for r in self._db.execute(
                "SELECT no, tipo, apelido, visto, bat FROM saude_dispositivo WHERE pessoa=? ORDER BY no", (pid,))]
            pos = self._db.execute("SELECT lat, lon, gps, crise, bpm, mov, bat, quando FROM saude_posicao WHERE pessoa=? "
                                   "ORDER BY quando DESC, id DESC LIMIT 1", (pid,)).fetchone()
            ult_gps = self._db.execute("SELECT lat, lon, quando FROM saude_posicao WHERE pessoa=? AND gps=1 "
                                       "ORDER BY quando DESC, id DESC LIMIT 1", (pid,)).fetchone()
            alertas = self._db.execute("SELECT id, tipo, mensagem, criado, atualizado, lat, lon, visto, visto_por FROM saude_alerta "
                                       "WHERE pessoa=? ORDER BY id DESC LIMIT 30", (pid,)).fetchall()
            eventos = self._db.execute(
                "SELECT d.quando, d.dia, d.cmp, d.evento, d.origem, h.hora, h.remedio FROM saude_dose d "
                "LEFT JOIN saude_horario h ON h.id=d.horario WHERE d.pessoa=? AND d.dia>=? ORDER BY d.quando DESC LIMIT 100",
                (pid, dia_de(agora - 30 * 86400))).fetchall()
        p["horarios"] = [{k: h[k] for k in ("id", "cmp", "hora", "dias", "remedio", "dose", "tolerancia")}
                         for h in self._horarios(pid) if not h["removido"]]
        hoje = dia_de(agora)
        ini = previsto_de(hoje, "00:00")
        p["hoje"] = self._doses(pid, ini, ini + 86400, agora)
        p["proximas"] = self.proximas_doses(agora, pid)
        p["adesao"] = {"semana": self.adesao(7, pid, agora), "mes": self.adesao(30, pid, agora)}
        p["posicao"] = dict(zip(("lat", "lon", "gps", "crise", "bpm", "mov", "bat", "quando"), pos)) if pos else None
        if p["posicao"]:
            p["posicao"]["gps"], p["posicao"]["crise"] = bool(pos[2]), bool(pos[3])
            p["posicao"]["ultimo_gps"] = dict(zip(("lat", "lon", "quando"), ult_gps)) if ult_gps else None
        p["alertas"] = [dict(zip(("id", "tipo", "mensagem", "criado", "atualizado", "lat", "lon", "visto", "visto_por"), a)) for a in alertas]
        p["eventos"] = [dict(zip(("quando", "dia", "cmp", "evento", "origem", "hora", "remedio"), e)) for e in eventos]
        return p

    def estado(self, usuario: str) -> dict:
        """Tudo o que a aba Saúde mostra, só das pessoas que este usuário pode ver."""
        agora = self._agora()
        self.verificar(agora)
        with self.hub._trava:
            ids = [p for (p,) in self._db.execute("SELECT a.pessoa FROM saude_acesso a JOIN saude_pessoa p ON p.id=a.pessoa "
                                                  "WHERE a.usuario=? ORDER BY p.nome", (usuario or "",))]
        pessoas = [self._pessoa(pid, agora) for pid in ids]
        alertas = [a for a in self.alertas_pendentes(agora=agora) if a["pessoa"] in ids]
        return {"ok": True, "agora": agora, "pessoas": pessoas, "alertas": alertas, "finalidade": FINALIDADE,
                "versao_termo": VERSAO_TERMO, "max_cmp": MAX_CMP, "tolerancia_padrao": TOLERANCIA_MIN}

    # ── Uma porta só para a tela: POST /api/saude/<acao> ──────────────────────────────────────
    ACOES = ("pessoa", "consentimento", "revogar", "apagar", "acesso_dar", "acesso_tirar", "contato", "contato_tirar",
             "horario", "horario_tirar", "dispositivo", "dispositivo_tirar", "dose", "alerta_visto")

    def executar(self, acao: str, d: dict, usuario: str) -> dict:
        d = d if isinstance(d, dict) else {}
        if acao not in self.ACOES:
            return {"ok": False, "erro": "ação desconhecida", "codigo": 404}
        if not usuario:
            return {"ok": False, "erro": "Entre com seu usuário.", "codigo": 401}
        if acao == "pessoa":
            return self.criar_pessoa(d, usuario)
        pid = _int(d.get("pessoa"))
        if not self.pode(usuario, pid):
            return SEM_ACESSO
        if acao == "consentimento":
            return self.renovar_consentimento(pid, d.get("consentimento"), usuario)
        if acao == "revogar":
            return self.revogar(pid, usuario)
        if acao == "apagar":
            return self.apagar(pid, usuario)
        if acao == "acesso_dar":
            return self.dar_acesso(pid, d.get("usuario"), usuario)
        if acao == "acesso_tirar":
            return self.tirar_acesso(pid, d.get("usuario"), usuario)
        if acao == "contato":
            return self.adicionar_contato(pid, d, usuario)
        if acao == "contato_tirar":
            return self.remover_contato(pid, _int(d.get("id")), usuario)
        if acao == "horario":
            return self.adicionar_horario(pid, d, usuario)
        if acao == "horario_tirar":
            return self.remover_horario(pid, _int(d.get("id")), usuario)
        if acao == "dispositivo":
            return self.vincular(pid, d, usuario)
        if acao == "dispositivo_tirar":
            return self.desvincular(pid, _int(d.get("no")), usuario)
        if acao == "dose":
            return self.marcar_dose(pid, _int(d.get("horario")), d.get("dia"), usuario)
        return self.marcar_visto(pid, _int(d.get("id")), usuario)


def enviar_avisos(hub, enviar_fila) -> int:
    """Manda só os e-mails pendentes da Saúde (ref "saude-<alerta>"), um alerta por vez.
    enviar_fila é correio.enviar_fila (passado de fora para este módulo não depender do correio)."""
    refs = sorted({e["ref"] for e in hub.emails("pendente") if str(e["ref"]).startswith("saude-")})
    return sum(enviar_fila(hub, r) for r in refs)


def rodar(saude: Saude, parar: threading.Event, passo: float = 60.0, enviar=None) -> None:
    """Laço de fundo: cobra as doses vencidas a cada minuto e, se houver, manda os e-mails (enviar())."""
    while not parar.is_set():
        try:
            if saude.verificar() and enviar:
                enviar()
        except Exception:          # noqa: BLE001 — um defeito aqui não pode derrubar o hub
            pass
        parar.wait(passo)
