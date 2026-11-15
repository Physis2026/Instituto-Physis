"""Marketplace de serviços: instaladores e projetistas parceiros, com ART e curadoria da Physis.

Tabelas: parceiro, parceiro_documento, parceiro_avaliacao (no banco do hub).

Quem faz o quê:
- o profissional se candidata (formulário público da loja) ou a equipe cadastra em nome dele, sempre com o
  consentimento dele (LGPD art. 7º I; data e versão do termo guardadas). Tudo nasce "em_analise";
- a equipe registra os documentos (ART/RRT modelo, seguro, NR-10, NR-35, certificados) com a validade;
- só a DIREÇÃO muda o status de curadoria (em_analise, aprovado, suspenso). Aprovar exige registro no
  CREA/CAU e os documentos obrigatórios da especialidade dentro da validade (REQUISITOS, abaixo);
- a loja lista só aprovados, com documento em dia, que atendem a região e a especialidade; o cliente pede
  orçamento e isso vira um pedido na Central (hub.central_por("pedido", ...)), sem expor o contato do parceiro;
- depois do serviço concluído, quem pediu (ou a equipe por ele) avalia de 1 a 5.

LGPD (dado mínimo em público): a vitrine mostra nome público, especialidades, regiões, conselho e UF do registro,
documentos "em dia" (sem número nem arquivo), nota média e quantas avaliações. CPF/CNPJ, telefone, e-mail,
número do registro e comentários das avaliações ficam só para a equipe (CPF/CNPJ mascarado; completo só para a
direção). apagar() remove o parceiro, os documentos e as avaliações (direito de eliminação, art. 18 VI).

REQUISITOS é política da Physis (padrão inicial, a direção confirma): ART/RRT modelo e seguro para todos;
NR-10 para quem mexe em instalação elétrica (solar, elétrica, automação, AVAC); NR-35 para trabalho em altura (solar).
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime

from . import clima as clima_mod

VERSAO_TERMO = "1"
FINALIDADE = ("Cadastro de profissional parceiro da Physis: conferir registro profissional e documentos, mostrar o "
              "perfil público (nome, especialidades, regiões e nota) na loja e encaminhar pedidos de orçamento. "
              "Você pode pedir a exclusão a qualquer momento.")
FINALIDADE_PEDIDO = ("Encaminhar o seu pedido de orçamento ao profissional parceiro escolhido, pela Central da Physis. "
                     "O seu contato só é passado ao parceiro com o pedido.")
ESPECIALIDADES = {"solar": "Energia solar", "avac": "AVAC (ar-condicionado e ventilação)", "hidraulica": "Hidráulica",
                  "eletrica": "Elétrica", "sbn": "SbN e paisagismo", "automacao": "Automação"}
CONSELHOS = ("CREA", "CAU", "CFT")
STATUS = {"em_analise": "Em análise", "aprovado": "Aprovado", "suspenso": "Suspenso"}
TIPOS_DOC = {"art_modelo": "ART/RRT modelo", "seguro": "Seguro de responsabilidade civil", "nr10": "Certificado NR-10",
             "nr35": "Certificado NR-35", "certificado": "Outro certificado", "outro": "Outro documento"}
REQUISITOS = {"*": ("art_modelo", "seguro"), "solar": ("nr10", "nr35"), "eletrica": ("nr10",), "automacao": ("nr10",), "avac": ("nr10",)}
ESTADOS_CONCLUIDO = ("concluido", "concluído", "fechado", "entregue", "atendido")
UFS = ("AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
       "RO", "RR", "RS", "SC", "SE", "SP", "TO")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS parceiro (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT NOT NULL, nome TEXT NOT NULL, nome_publico TEXT NOT NULL,
  documento TEXT NOT NULL, conselho TEXT NOT NULL DEFAULT '', registro TEXT NOT NULL DEFAULT '', registro_uf TEXT NOT NULL DEFAULT '',
  especialidades TEXT NOT NULL, regioes TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', telefone TEXT NOT NULL DEFAULT '',
  descricao TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'em_analise', status_motivo TEXT NOT NULL DEFAULT '',
  status_por TEXT NOT NULL DEFAULT '', status_em REAL, registro_conferido REAL,
  consentimento REAL NOT NULL, versao_termo TEXT NOT NULL, criado REAL NOT NULL, atualizado REAL NOT NULL, por TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS parceiro_doc ON parceiro(documento);
CREATE TABLE IF NOT EXISTS parceiro_documento (
  id INTEGER PRIMARY KEY AUTOINCREMENT, parceiro INTEGER NOT NULL, tipo TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '',
  validade TEXT NOT NULL DEFAULT '', arquivo TEXT NOT NULL DEFAULT '', criado REAL NOT NULL, por TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS parceiro_avaliacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT, parceiro INTEGER NOT NULL, pedido TEXT NOT NULL, nota INTEGER NOT NULL,
  comentario TEXT NOT NULL DEFAULT '', criado REAL NOT NULL, por TEXT NOT NULL, UNIQUE (parceiro, pedido));
"""

_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ══ Documentos brasileiros (dígitos verificadores; o JS da tela usa a mesma conta) ═════════════════
def so_digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def cpf_valido(v) -> bool:
    d = so_digitos(v)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        s = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (s * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def cnpj_valido(v) -> bool:
    d = so_digitos(v)
    if len(d) != 14 or d == d[0] * 14:
        return False
    for n, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        r = sum(int(d[i]) * pesos[i] for i in range(n)) % 11
        if (0 if r < 2 else 11 - r) != int(d[n]):
            return False
    return True


def mascarar(doc: str) -> str:
    d = so_digitos(doc)
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:
        return f"{d[:2]}.***.***/{d[8:12]}-**"
    return "***"


def _sem(s) -> str:
    return clima_mod._sem_acento(str(s or ""))


def _hoje(agora: float) -> str:
    return datetime.fromtimestamp(agora, clima_mod.FUSO).strftime("%Y-%m-%d")


def validar_regioes(regs) -> tuple[list | None, str]:
    if not isinstance(regs, list) or not 1 <= len(regs) <= 60:
        return None, "informe de 1 a 60 regiões atendidas (UF ou município/UF)"
    out = []
    for r in regs:
        r = r if isinstance(r, dict) else {"uf": r}
        uf = str(r.get("uf") or "").strip().upper()
        if uf not in UFS:
            return None, f"UF inválida: {uf or '(vazia)'}"
        ibge = str(r.get("ibge") or "").strip()
        if ibge and not re.fullmatch(r"\d{7}", ibge):
            return None, "código IBGE do município tem 7 dígitos"
        mun = str(r.get("municipio") or "").strip()[:80]
        item = {"uf": uf, "municipio": mun, "ibge": ibge}
        if item not in out:
            out.append(item)
    return out, ""


def validar_cadastro(d: dict, parcial: bool = False) -> tuple[dict | None, str]:
    if not isinstance(d, dict):
        return None, "json invalido"
    out = {}
    if not parcial or "documento" in d or "tipo" in d:
        tipo = str(d.get("tipo") or "").lower()
        if tipo not in ("pf", "pj"):
            return None, "tipo: pf (pessoa física) ou pj (empresa)"
        doc = so_digitos(d.get("documento"))
        if (tipo == "pf" and not cpf_valido(doc)) or (tipo == "pj" and not cnpj_valido(doc)):
            return None, "CPF inválido" if tipo == "pf" else "CNPJ inválido"
        out.update(tipo=tipo, documento=doc)
    if not parcial or "nome" in d:
        nome = str(d.get("nome") or "").strip()
        if not 2 <= len(nome) <= 160:
            return None, "razão social ou nome obrigatório (até 160 letras)"
        out["nome"] = nome
    if not parcial or "nome_publico" in d or "nome" in d:
        out["nome_publico"] = (str(d.get("nome_publico") or "").strip() or out.get("nome") or "")[:120]
    if not parcial or "conselho" in d or "registro" in d or "registro_uf" in d:
        conselho = str(d.get("conselho") or "").strip().upper()
        registro = re.sub(r"[^0-9A-Za-z./-]", "", str(d.get("registro") or ""))[:30]
        ruf = str(d.get("registro_uf") or "").strip().upper()
        if conselho or registro:
            if conselho not in CONSELHOS or not registro or ruf not in UFS:
                return None, "registro profissional: conselho (CREA, CAU ou CFT), número e UF"
        out.update(conselho=conselho, registro=registro, registro_uf=ruf if conselho else "")
    if not parcial or "especialidades" in d:
        esp = d.get("especialidades")
        if not isinstance(esp, list) or not esp or any(e not in ESPECIALIDADES for e in esp):
            return None, "especialidades: " + ", ".join(ESPECIALIDADES)
        out["especialidades"] = sorted(set(esp))
    if not parcial or "regioes" in d:
        regs, erro = validar_regioes(d.get("regioes"))
        if regs is None:
            return None, erro
        out["regioes"] = regs
    if not parcial or "email" in d:
        email = str(d.get("email") or "").strip()[:160]
        if email and not _EMAIL.match(email):
            return None, "e-mail inválido"
        out["email"] = email
    if not parcial or "telefone" in d:
        tel = so_digitos(d.get("telefone"))[:13]
        if tel and len(tel) < 10:
            return None, "telefone com DDD"
        out["telefone"] = tel
    if not parcial and not (out.get("email") or out.get("telefone")):
        return None, "informe e-mail ou telefone para a Physis falar com você"
    if not parcial or "descricao" in d:
        out["descricao"] = str(d.get("descricao") or "").strip()[:1000]
    return out, ""


def requisitos(especialidades) -> list[str]:
    req = list(REQUISITOS["*"])
    for e in especialidades or []:
        for t in REQUISITOS.get(e, ()):
            if t not in req:
                req.append(t)
    return req


def pendencias(p: dict, docs: list[dict], hoje: str) -> list[str]:
    """O que impede aprovar (ou manter na vitrine)."""
    out = []
    if not p.get("conselho") or not p.get("registro"):
        out.append("registro no CREA, CAU ou CFT")
    for t in requisitos(p.get("especialidades")):
        validos = [x for x in docs if x["tipo"] == t and (not x["validade"] or x["validade"] >= hoje)]
        if not validos:
            vencido = any(x["tipo"] == t for x in docs)
            out.append(f"{TIPOS_DOC[t]} {'vencido' if vencido else 'ausente'}")
    return out


def atende(p: dict, uf: str, municipio: str = "", ibge: str = "") -> int:
    """0 = não atende; 1 = atende o estado todo; 2 = atende o município citado."""
    uf, mun, ibge = (uf or "").upper(), _sem(municipio), str(ibge or "")
    melhor = 0
    for r in p.get("regioes") or []:
        if r["uf"] != uf:
            continue
        if not r.get("municipio") and not r.get("ibge"):
            melhor = max(melhor, 1)
        elif (ibge and r.get("ibge") == ibge) or (mun and _sem(r.get("municipio")) == mun):
            melhor = 2
    return melhor


def nota_bayes(soma: float, n: int, previa: float = 3.0, peso: int = 2) -> float:
    """Média puxada para 3 com poucas avaliações (um 5 sozinho não passa na frente de vinte 4,8)."""
    return (soma + previa * peso) / (n + peso)


# ══ Banco ════════════════════════════════════════════════════════════════════════════════════════
class Parceiros:
    COLS = ("id", "tipo", "nome", "nome_publico", "documento", "conselho", "registro", "registro_uf", "especialidades", "regioes",
            "email", "telefone", "descricao", "status", "status_motivo", "status_por", "status_em", "registro_conferido",
            "consentimento", "versao_termo", "criado", "atualizado", "por")

    def __init__(self, hub, relogio=None):
        self.hub = hub
        self.relogio = relogio or hub.relogio
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    def _ler(self, ident: int) -> dict | None:
        r = self._db.execute("SELECT " + ",".join(self.COLS) + " FROM parceiro WHERE id=?", (int(ident),)).fetchone()
        if not r:
            return None
        p = dict(zip(self.COLS, r))
        p["especialidades"], p["regioes"] = json.loads(p["especialidades"]), json.loads(p["regioes"])
        return p

    def _docs(self, ident: int) -> list[dict]:
        cols = ("id", "tipo", "descricao", "validade", "arquivo", "criado")
        return [dict(zip(cols, r)) for r in self._db.execute("SELECT " + ",".join(cols) + " FROM parceiro_documento WHERE parceiro=? "
                                                             "ORDER BY tipo, validade DESC", (int(ident),))]

    def _notas(self) -> dict[int, tuple[float, int]]:
        return {p: (s, n) for p, s, n in self._db.execute("SELECT parceiro, SUM(nota), COUNT(*) FROM parceiro_avaliacao GROUP BY parceiro")}

    # ── cadastro ─────────────────────────────────────────────────────────────────────────────
    def cadastrar(self, d: dict, quem: str = "site") -> dict:
        if not isinstance(d, dict) or d.get("consentimento") is not True:
            return {"ok": False, "erro": "é preciso aceitar o uso dos dados para o cadastro (LGPD)", "finalidade": FINALIDADE}
        p, erro = validar_cadastro(d)
        if not p:
            return {"ok": False, "erro": erro}
        agora = self.relogio()
        with self.hub._trava:
            if self._db.execute("SELECT 1 FROM parceiro WHERE documento=?", (p["documento"],)).fetchone():
                return {"ok": False, "erro": "já existe um cadastro com este CPF/CNPJ; fale com a Physis"}
            cur = self._db.execute(
                "INSERT INTO parceiro(tipo,nome,nome_publico,documento,conselho,registro,registro_uf,especialidades,regioes,email,telefone,"
                "descricao,consentimento,versao_termo,criado,atualizado,por) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p["tipo"], p["nome"], p["nome_publico"], p["documento"], p["conselho"], p["registro"], p["registro_uf"],
                 json.dumps(p["especialidades"]), json.dumps(p["regioes"], ensure_ascii=False), p["email"], p["telefone"],
                 p["descricao"], agora, VERSAO_TERMO, agora, agora, quem))
            self.hub.registrar("parceiro", quem or "site", {"o_que": "cadastro", "id": cur.lastrowid, "termo": VERSAO_TERMO})
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid, "status": "em_analise"}

    def editar(self, ident: int, d: dict, quem: str) -> dict:
        p0 = self._ler(ident)
        if not p0:
            return {"ok": False, "erro": "parceiro desconhecido"}
        campos, erro = validar_cadastro(d, parcial=True)
        if campos is None:
            return {"ok": False, "erro": erro}
        if not campos:
            return {"ok": True}
        with self.hub._trava:
            if "documento" in campos and self._db.execute("SELECT 1 FROM parceiro WHERE documento=? AND id<>?", (campos["documento"], ident)).fetchone():
                return {"ok": False, "erro": "CPF/CNPJ já cadastrado em outro parceiro"}
            for k in ("especialidades", "regioes"):
                if k in campos:
                    campos[k] = json.dumps(campos[k], ensure_ascii=False)
            if any(k in campos for k in ("conselho", "registro", "registro_uf")):
                campos["registro_conferido"] = None          # registro mudou: a equipe confere de novo
            sets = ", ".join(f"{k}=?" for k in campos)
            self._db.execute(f"UPDATE parceiro SET {sets}, atualizado=? WHERE id=?", (*campos.values(), self.relogio(), int(ident)))
            self.hub.registrar("parceiro", quem, {"o_que": "editado", "id": int(ident), "campos": sorted(campos)})
            self._db.commit()
        return {"ok": True}

    def conferir_registro(self, ident: int, quem: str) -> dict:
        """A equipe conferiu o registro no site do conselho (CREA/CAU/CFT): fica a data."""
        with self.hub._trava:
            cur = self._db.execute("UPDATE parceiro SET registro_conferido=?, atualizado=? WHERE id=? AND registro<>''",
                                   (self.relogio(), self.relogio(), int(ident)))
            if cur.rowcount:
                self.hub.registrar("parceiro", quem, {"o_que": "registro conferido", "id": int(ident)})
            self._db.commit()
        return {"ok": cur.rowcount > 0}

    def documento(self, ident: int, d: dict, quem: str) -> dict:
        if not self._ler(ident):
            return {"ok": False, "erro": "parceiro desconhecido"}
        if not isinstance(d, dict) or d.get("tipo") not in TIPOS_DOC:
            return {"ok": False, "erro": "tipo de documento: " + ", ".join(TIPOS_DOC)}
        val = str(d.get("validade") or "")
        if val and not _DATA.match(val):
            return {"ok": False, "erro": "validade no formato AAAA-MM-DD"}
        if d["tipo"] in ("seguro", "nr10", "nr35") and not val:
            return {"ok": False, "erro": "este documento precisa de validade"}
        arquivo = str(d.get("arquivo") or "")[:40]
        with self.hub._trava:
            if arquivo:
                try:
                    ok = self._db.execute("SELECT 1 FROM gestao_arquivo WHERE id=?", (arquivo,)).fetchone()
                except Exception:      # noqa: BLE001
                    ok = None
                if not ok:
                    return {"ok": False, "erro": "arquivo da Gestão não encontrado"}
            cur = self._db.execute("INSERT INTO parceiro_documento(parceiro,tipo,descricao,validade,arquivo,criado,por) VALUES(?,?,?,?,?,?,?)",
                                   (int(ident), d["tipo"], str(d.get("descricao") or "").strip()[:200], val, arquivo, self.relogio(), quem))
            self.hub.registrar("parceiro", quem, {"o_que": "documento", "id": int(ident), "tipo": d["tipo"], "validade": val})
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid}

    def remover_documento(self, ident: int, doc: int, quem: str) -> dict:
        with self.hub._trava:
            cur = self._db.execute("DELETE FROM parceiro_documento WHERE id=? AND parceiro=?", (int(doc), int(ident)))
            if cur.rowcount:
                self.hub.registrar("parceiro", quem, {"o_que": "documento removido", "id": int(ident)})
            self._db.commit()
        return {"ok": cur.rowcount > 0}

    # ── curadoria (só a direção) ─────────────────────────────────────────────────────────────
    def curar(self, ident: int, status: str, motivo: str, quem: str, eh_direcao: bool) -> dict:
        if not eh_direcao:
            return {"ok": False, "erro": "só a direção muda a curadoria", "codigo": 403}
        if status not in STATUS:
            return {"ok": False, "erro": "status: " + ", ".join(STATUS)}
        p = self._ler(ident)
        if not p:
            return {"ok": False, "erro": "parceiro desconhecido", "codigo": 404}
        motivo = str(motivo or "").strip()[:300]
        if status == "aprovado":
            pend = pendencias(p, self._docs(ident), _hoje(self.relogio()))
            if not p.get("registro_conferido"):
                pend.insert(0, "registro profissional conferido pela equipe")
            if pend:
                return {"ok": False, "erro": "falta para aprovar: " + "; ".join(pend), "pendencias": pend}
        if status == "suspenso" and not motivo:
            return {"ok": False, "erro": "diga o motivo da suspensão"}
        with self.hub._trava:
            self._db.execute("UPDATE parceiro SET status=?, status_motivo=?, status_por=?, status_em=?, atualizado=? WHERE id=?",
                             (status, motivo, quem, self.relogio(), self.relogio(), int(ident)))
            self.hub.registrar("parceiro", quem, {"o_que": "curadoria", "id": int(ident), "status": status})
            self._db.commit()
        return {"ok": True, "status": status}

    # ── avaliações ───────────────────────────────────────────────────────────────────────────
    def avaliar(self, ident: int, d: dict, quem: str, eh_equipe: bool = False) -> dict:
        if not self._ler(ident):
            return {"ok": False, "erro": "parceiro desconhecido", "codigo": 404}
        try:
            nota = int((d or {}).get("nota"))
        except (TypeError, ValueError):
            nota = 0
        if not 1 <= nota <= 5:
            return {"ok": False, "erro": "nota de 1 a 5"}
        numero = str(d.get("pedido") or "")
        ped = next((x for x in self.hub.central_listar() if x["tipo"] == "pedido" and x["numero"] == numero), None)
        if not ped or str(ped["dados"].get("parceiro")) != str(ident):
            return {"ok": False, "erro": "pedido não encontrado para este parceiro"}
        if _sem(ped["estado"]) not in {_sem(e) for e in ESTADOS_CONCLUIDO}:
            return {"ok": False, "erro": "só depois do serviço concluído"}
        if not eh_equipe and ped["dados"].get("usuario") != quem:
            return {"ok": False, "erro": "só quem pediu o serviço avalia", "codigo": 403}
        with self.hub._trava:
            try:
                self._db.execute("INSERT INTO parceiro_avaliacao(parceiro,pedido,nota,comentario,criado,por) VALUES(?,?,?,?,?,?)",
                                 (int(ident), numero, nota, str(d.get("comentario") or "").strip()[:1000], self.relogio(), quem))
            except Exception:          # noqa: BLE001 — UNIQUE(parceiro, pedido)
                return {"ok": False, "erro": "este pedido já foi avaliado"}
            self.hub.registrar("parceiro", quem, {"o_que": "avaliação", "id": int(ident), "nota": nota})
            self._db.commit()
        return {"ok": True}

    # ── vitrine e busca ──────────────────────────────────────────────────────────────────────
    def _publico(self, p: dict, docs: list[dict], notas: dict, hoje: str) -> dict:
        s, n = notas.get(p["id"], (0, 0))
        return {"id": p["id"], "nome": p["nome_publico"], "descricao": p["descricao"],
                "especialidades": [{"id": e, "nome": ESPECIALIDADES[e]} for e in p["especialidades"]],
                "regioes": [{"uf": r["uf"], "municipio": r["municipio"]} for r in p["regioes"]],
                "registro": f"{p['conselho']}-{p['registro_uf']}" if p["conselho"] else "",
                "registro_conferido": bool(p["registro_conferido"]),
                "documentos_em_dia": sorted({TIPOS_DOC[x["tipo"]] for x in docs if not x["validade"] or x["validade"] >= hoje}),
                "nota": round(s / n, 1) if n else None, "avaliacoes": n}

    def vitrine(self, servico: str = "", uf: str = "", municipio: str = "", ibge: str = "") -> dict:
        """Parceiros aprovados e com documentos em dia, filtrados por especialidade e região, do melhor para o pior."""
        hoje, notas = _hoje(self.relogio()), self._notas()
        ids = [r[0] for r in self._db.execute("SELECT id FROM parceiro WHERE status='aprovado'")]
        out = []
        for i in ids:
            p, docs = self._ler(i), self._docs(i)
            if pendencias(p, docs, hoje):
                continue                                  # documento venceu: sai da vitrine até a equipe atualizar
            if servico and servico not in p["especialidades"]:
                continue
            onde = atende(p, uf, municipio, ibge) if uf else 1
            if not onde:
                continue
            s, n = notas.get(i, (0, 0))
            out.append((onde, nota_bayes(s, n), n, p["nome_publico"].lower(), self._publico(p, docs, notas, hoje)))
        out.sort(key=lambda x: (-x[0], -x[1], -x[2], x[3]))
        return {"ok": True, "parceiros": [x[4] for x in out], "especialidades": ESPECIALIDADES,
                "aviso": "Profissionais independentes com registro conferido e documentos em dia pela Physis. "
                         "O serviço e a ART são do profissional."}

    def interno(self, completo: bool = False) -> dict:
        hoje, notas = _hoje(self.relogio()), self._notas()
        out = []
        for (i,) in self._db.execute("SELECT id FROM parceiro ORDER BY status, nome").fetchall():
            p, docs = self._ler(i), self._docs(i)
            s, n = notas.get(i, (0, 0))
            p = dict(p, documento=p["documento"] if completo else mascarar(p["documento"]), documentos=[
                dict(x, tipo_nome=TIPOS_DOC[x["tipo"]], vencido=bool(x["validade"]) and x["validade"] < hoje) for x in docs],
                pendencias=pendencias(p, docs, hoje), nota=round(s / n, 1) if n else None, avaliacoes=n,
                comentarios=[{"pedido": pe, "nota": no, "comentario": c, "criado": cr} for pe, no, c, cr in self._db.execute(
                    "SELECT pedido, nota, comentario, criado FROM parceiro_avaliacao WHERE parceiro=? ORDER BY criado DESC LIMIT 20", (i,))])
            out.append(p)
        return {"ok": True, "parceiros": out, "status": STATUS, "tipos_doc": TIPOS_DOC, "especialidades": ESPECIALIDADES,
                "requisitos": {k: list(v) for k, v in REQUISITOS.items()}, "hoje": hoje}

    # ── pedido de orçamento (vira pedido na Central) ─────────────────────────────────────────
    def pedir_orcamento(self, d: dict, usuario: str = "") -> dict:
        if not isinstance(d, dict) or d.get("consentimento") is not True:
            return {"ok": False, "erro": "é preciso aceitar o envio do seu contato ao profissional", "finalidade": FINALIDADE_PEDIDO}
        try:
            ident = int(d.get("parceiro"))
        except (TypeError, ValueError):
            return {"ok": False, "erro": "escolha o profissional"}
        servico = str(d.get("servico") or "")
        if servico not in ESPECIALIDADES:
            return {"ok": False, "erro": "escolha o serviço"}
        uf = str(d.get("uf") or "").upper()
        mun = str(d.get("municipio") or "").strip()[:80]
        if uf not in UFS or not mun:
            return {"ok": False, "erro": "informe o município e a UF do serviço"}
        nome, email, tel = str(d.get("nome") or "").strip()[:120], str(d.get("email") or "").strip()[:160], so_digitos(d.get("telefone"))[:13]
        if len(nome) < 2 or not (email or tel) or (email and not _EMAIL.match(email)) or (tel and len(tel) < 10):
            return {"ok": False, "erro": "nome e um contato (e-mail ou telefone com DDD) para o orçamento"}
        desc = str(d.get("descricao") or "").strip()[:2000]
        if len(desc) < 10:
            return {"ok": False, "erro": "descreva o serviço em poucas palavras"}
        vit = {p["id"]: p for p in self.vitrine(servico, uf, mun, str(d.get("ibge") or ""))["parceiros"]}
        if ident not in vit:
            return {"ok": False, "erro": "este profissional não atende este serviço nesta região agora"}
        numero = "PQ-" + datetime.fromtimestamp(self.relogio(), clima_mod.FUSO).strftime("%y%m%d") + "-" + secrets.token_hex(3).upper()
        ped = {"_formato": "physis-pedido/1", "numero": numero, "origem": "parceiros", "data": datetime.fromtimestamp(self.relogio(), clima_mod.FUSO).isoformat(),
               "parceiro": ident, "parceiro_nome": vit[ident]["nome"], "servico": servico, "areas": [ESPECIALIDADES[servico]],
               "municipio": mun, "uf": uf, "texto": desc, "nome": nome, "email": email, "telefone": tel, "usuario": usuario or "",
               "consentimento": {"quando": self.relogio(), "finalidade": FINALIDADE_PEDIDO}}
        r = self.hub.central_por("pedido", numero, ped)
        return {"ok": r.get("ok", False), "numero": numero, "estado": r.get("estado")}

    # ── LGPD: eliminação ─────────────────────────────────────────────────────────────────────
    def apagar(self, ident: int, quem: str) -> dict:
        with self.hub._trava:
            cur = self._db.execute("DELETE FROM parceiro WHERE id=?", (int(ident),))
            self._db.execute("DELETE FROM parceiro_documento WHERE parceiro=?", (int(ident),))
            self._db.execute("DELETE FROM parceiro_avaliacao WHERE parceiro=?", (int(ident),))
            if cur.rowcount:
                self.hub.registrar("parceiro", quem, {"o_que": "apagado (LGPD)", "id": int(ident)})
            self._db.commit()
        return {"ok": cur.rowcount > 0}
