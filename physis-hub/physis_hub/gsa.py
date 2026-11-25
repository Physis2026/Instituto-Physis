"""GSA · Global South Alliance: plataforma de GESTÃO INTERNA (25/11/2026; o site público vem depois).

Base do Instituto Physis. Entra só quem foi CONVIDADO ou quem PEDIU ACESSO e teve o pedido aceito pela direção (admin).
Aqui: pedido de acesso (público, com aceite LGPD), fila de pedidos da direção (aprovar = convite com link; recusar com motivo)
e a lista de documentos base (pasta PHYSIS_GSA_DOCS, só leitura; só para quem tem conta). Membros, projetos, tarefas e
alertas, financeiro, editais, parceiros, indicadores e marketing usam os módulos que já existem (Gestão interna em /gestao,
editais, parceiros, indicadores, convites e contas) — ver web/gsa.html.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import seguranca as seg

_S = str
ESQUEMAS = {
    "gsa_pedido": {"nome": (_S, 120, True), "email": (_S, 160, True), "organizacao": (_S, 160, False), "pais": (_S, 60, False),
                   "motivo": (_S, 1000, False), "aceite": (bool, None, True)},
    "gsa_decidir": {"id": (int, 10**12, True), "decisao": (_S, 10, True), "papel": (_S, 20, False), "motivo": (_S, 400, False)},
}
ESQUEMA = """
CREATE TABLE IF NOT EXISTS gsa_pedido (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, email TEXT NOT NULL, organizacao TEXT NOT NULL DEFAULT '',
  pais TEXT NOT NULL DEFAULT '', motivo TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'pendente',
  motivo_decisao TEXT NOT NULL DEFAULT '', criado REAL NOT NULL, decidido_por TEXT NOT NULL DEFAULT '', decidido_em REAL);
"""
FINALIDADE = ("Seus dados (nome, e-mail, organização, país e o motivo) servem só para a direção da GSA decidir o acesso à "
              "plataforma de gestão. Quem não for aceito tem o pedido apagado em até 90 dias.")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
DOCS_EXT = {".pdf", ".odt", ".ods", ".odp", ".docx", ".xlsx", ".pptx", ".md", ".txt", ".csv"}


def _t(v, n):
    return " ".join(str(v or "").split())[:n]


def pasta_docs() -> Path | None:
    p = os.environ.get("PHYSIS_GSA_DOCS", "").strip()
    return Path(p) if p else _pasta_auto()


class GSA:
    def __init__(self, hub, base_url: str = ""):
        self.hub, self.base = hub, base_url
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    def pedir(self, d: dict) -> dict:
        nome, email = _t(d.get("nome"), 120), _t(d.get("email"), 160).lower()
        if len(nome) < 2 or not _EMAIL.fullmatch(email):
            return {"ok": False, "erro": "Informe o nome e um e-mail válido."}
        if d.get("aceite") is not True:
            return {"ok": False, "erro": "É preciso aceitar o uso dos dados para o pedido.", "finalidade": FINALIDADE}
        with self.hub._trava:
            if self._db.execute("SELECT 1 FROM conta WHERE usuario=?", (email,)).fetchone():
                return {"ok": True, "ja_tem_conta": True}          # não revela nada além de "entre com a sua senha"
            if self._db.execute("SELECT 1 FROM gsa_pedido WHERE email=? AND estado='pendente'", (email,)).fetchone():
                return {"ok": True, "pendente": True}
            ident = self._db.execute("INSERT INTO gsa_pedido(nome,email,organizacao,pais,motivo,criado) VALUES(?,?,?,?,?,?)",
                                     (nome, email, _t(d.get("organizacao"), 160), _t(d.get("pais"), 60), _t(d.get("motivo"), 1000),
                                      self.hub.relogio())).lastrowid
            self._db.commit()
        self.hub.registrar("gsa", "publico", {"o_que": "pedido de acesso", "id": ident})
        return {"ok": True, "pendente": True}

    def pedidos(self, quem: dict) -> dict:
        if not seg.pode(quem, seg.DIRECAO):
            return {"ok": False, "erro": "só a direção", "codigo": 403}
        cols = ("id", "nome", "email", "organizacao", "pais", "motivo", "estado", "motivo_decisao", "criado", "decidido_por", "decidido_em")
        return {"ok": True, "itens": [dict(zip(cols, r)) for r in self._db.execute(
            "SELECT " + ",".join(cols) + " FROM gsa_pedido ORDER BY estado<>'pendente', criado DESC LIMIT 300")]}

    def decidir(self, d: dict, quem: dict) -> dict:
        if not seg.pode(quem, seg.DIRECAO):
            return {"ok": False, "erro": "só a direção", "codigo": 403}
        dec = _t(d.get("decisao"), 10)
        if dec not in ("aprovar", "recusar"):
            return {"ok": False, "erro": "decisao: aprovar ou recusar"}
        r = self._db.execute("SELECT nome, email, estado FROM gsa_pedido WHERE id=?", (int(d["id"]),)).fetchone()
        if not r:
            return {"ok": False, "erro": "pedido não encontrado", "codigo": 404}
        if r[2] != "pendente":
            return {"ok": False, "erro": "pedido já decidido", "codigo": 409}
        out = {"ok": True}
        if dec == "aprovar":
            c = seg.convite_criar(self.hub, r[1], d.get("papel") or seg.EQUIPE, "", r[0], quem["usuario"], self.base)
            if not c.get("ok"):
                return c
            # sem servidor de e-mail, a direção manda o link por outro canal: o mesmo texto que iria por e-mail
            m = self._db.execute("SELECT corpo FROM email_saida WHERE ref=? ORDER BY id DESC LIMIT 1", (c["ref"],)).fetchone()
            out.update(convite=c["id"], texto_convite=m[0] if m else "")
            novo = "aprovado"
        else:
            if len(_t(d.get("motivo"), 400)) < 3:
                return {"ok": False, "erro": "Escreva o motivo da recusa."}
            novo = "recusado"
        with self.hub._trava:
            self._db.execute("UPDATE gsa_pedido SET estado=?, motivo_decisao=?, decidido_por=?, decidido_em=? WHERE id=?",
                             (novo, _t(d.get("motivo"), 400), quem["usuario"], self.hub.relogio(), int(d["id"])))
            self._db.commit()
        self.hub.registrar("gsa", quem["usuario"], {"o_que": "pedido " + novo, "id": int(d["id"])})
        out["estado"] = novo
        return out

    def documentos(self, quem: dict) -> dict:
        p = pasta_docs()
        if not p:
            return {"ok": True, "itens": [], "aviso": "pasta dos documentos base não configurada (PHYSIS_GSA_DOCS)"}
        if not p.is_dir():
            return {"ok": True, "itens": [], "aviso": f"pasta não encontrada: {p}"}
        itens = []
        for f in sorted(x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in DOCS_EXT and not x.name.startswith("~$")):
            itens.append({"nome": f.name, "pasta": str(f.parent.relative_to(p)), "tamanho_kb": round(f.stat().st_size / 1024),
                          "modificado": f.stat().st_mtime, "caminho": str(f.relative_to(p)).replace("\\", "/")})
            if len(itens) >= 500:
                break
        return {"ok": True, "itens": itens, "pasta": str(p)}

    def arquivo(self, rel: str) -> tuple[str, bytes] | None:
        p = pasta_docs()
        if not p:
            return None
        alvo = (p / rel).resolve()
        if p.resolve() not in alvo.parents or not alvo.is_file() or alvo.suffix.lower() not in DOCS_EXT:
            return None
        return alvo.name, alvo.read_bytes()


# ── Versão básica da GSA (25/11/2026: "somente versão básica com os itens indicados") ───────────────────────────────────
# Um registro por item, num só lugar: projetos, tarefas (com alerta de prazo), financeiro, propostas e editais, parceiros
# (com o ponto no mapa) e marketing. Membros = contas e convites do próprio servidor; indicadores = contas sobre estes itens.
TIPOS = {
    "projeto": {"titulo": 160, "descricao": 4000, "responsavel": 120, "inicio": 10, "fim": 10, "situacao": 20},
    "tarefa": {"titulo": 160, "projeto": 160, "responsavel": 120, "prazo": 10, "situacao": 20},
    "financeiro": {"descricao": 200, "tipo_lancamento": 10, "valor": 20, "data": 10, "projeto": 160, "categoria": 60},
    "edital": {"titulo": 200, "orgao": 160, "link": 400, "prazo": 10, "valor": 40, "situacao": 20, "responsavel": 120},
    "parceiro": {"nome": 160, "tipo": 60, "pais": 60, "cidade": 80, "lat": 12, "lon": 12, "contato": 160, "site": 300},
    "marketing": {"titulo": 160, "canal": 60, "data": 10, "situacao": 20, "texto": 4000},
}
OBRIGATORIO = {"projeto": "titulo", "tarefa": "titulo", "financeiro": "descricao", "edital": "titulo", "parceiro": "nome", "marketing": "titulo"}
SITUACOES = {"projeto": ("ideia", "em andamento", "pausado", "concluido"), "tarefa": ("a fazer", "fazendo", "feita"),
             "edital": ("mapeado", "preparando", "enviado", "aprovado", "recusado"), "marketing": ("rascunho", "agendado", "publicado")}
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ESQUEMAS["gsa_item"] = {"id": (int, 10**12, False), "tipo": (_S, 20, True), "dados": (dict, 20, True)}
ESQUEMAS["gsa_apagar"] = {"id": (int, 10**12, True)}
ESQUEMAS["gsa_convidar"] = {"email": (_S, 160, True), "nome": (_S, 120, False), "papel": (_S, 20, False)}
ESQUEMA_ITENS = """
CREATE TABLE IF NOT EXISTS gsa_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT NOT NULL, dados TEXT NOT NULL, criado REAL NOT NULL, atualizado REAL NOT NULL,
  por TEXT NOT NULL, apagado INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS gsa_item_tipo ON gsa_item(tipo, apagado);
"""


def _validar_item(tipo: str, dados: dict) -> tuple[dict | None, str | None]:
    if tipo not in TIPOS:
        return None, "tipo: " + ", ".join(TIPOS)
    out = {}
    for k, n in TIPOS[tipo].items():
        v = _t(dados.get(k), n) if k not in ("descricao", "texto") else str(dados.get(k) or "")[:n]
        if v:
            out[k] = v
    if not out.get(OBRIGATORIO[tipo]):
        return None, f"preencha: {OBRIGATORIO[tipo]}"
    for k in ("inicio", "fim", "prazo", "data"):
        if out.get(k) and not _DATA.fullmatch(out[k]):
            return None, f"{k} no formato AAAA-MM-DD"
    if tipo in SITUACOES and out.get("situacao") and out["situacao"] not in SITUACOES[tipo]:
        return None, "situação: " + ", ".join(SITUACOES[tipo])
    if tipo == "financeiro":
        if out.get("tipo_lancamento") not in ("entrada", "saida"):
            return None, "lançamento: entrada ou saida"
        try:
            out["valor"] = round(float(str(out.get("valor", "")).replace(".", "").replace(",", ".") if "," in str(out.get("valor", "")) else out.get("valor", "")), 2)
        except ValueError:
            return None, "valor em reais (ex.: 1.234,56)"
    if tipo == "parceiro":
        for k, lim in (("lat", 90), ("lon", 180)):
            if out.get(k):
                try:
                    x = float(str(out[k]).replace(",", "."))
                except ValueError:
                    return None, f"{k} inválida"
                if abs(x) > lim:
                    return None, f"{k} fora da faixa"
                out[k] = x
    if out.get("link") and not re.match(r"https?://", out["link"]):
        return None, "link começa com https://"
    if out.get("site") and not re.match(r"https?://", out["site"]):
        return None, "site começa com https://"
    return out, None


def _instalar_itens(self):
    with self.hub._trava:
        self.hub._db.executescript(ESQUEMA_ITENS)
        self.hub._db.commit()


def _itens(self, tipo: str) -> dict:
    if tipo not in TIPOS:
        return {"ok": False, "erro": "tipo desconhecido", "codigo": 404}
    rows = self._db.execute("SELECT id, dados, criado, atualizado, por FROM gsa_item WHERE tipo=? AND apagado=0 ORDER BY atualizado DESC LIMIT 1000", (tipo,))
    return {"ok": True, "tipo": tipo, "campos": list(TIPOS[tipo]), "situacoes": list(SITUACOES.get(tipo, ())),
            "itens": [dict(json.loads(d), id=i, criado=c, atualizado=a, por=p) for i, d, c, a, p in rows]}


def _salvar(self, d: dict, quem: dict) -> dict:
    tipo = _t(d.get("tipo"), 20)
    dados, erro = _validar_item(tipo, d.get("dados") or {})
    if erro:
        return {"ok": False, "erro": erro}
    if tipo == "financeiro" and not seg.pode(quem, seg.DIRECAO):
        return {"ok": False, "erro": "lançamentos financeiros: só a direção", "codigo": 403}
    agora, txt = self.hub.relogio(), json.dumps(dados, ensure_ascii=False)
    with self.hub._trava:
        if d.get("id"):
            r = self._db.execute("UPDATE gsa_item SET dados=?, atualizado=?, por=? WHERE id=? AND tipo=? AND apagado=0",
                                 (txt, agora, quem["usuario"], int(d["id"]), tipo))
            if not r.rowcount:
                return {"ok": False, "erro": "item não encontrado", "codigo": 404}
            ident = int(d["id"])
        else:
            ident = self._db.execute("INSERT INTO gsa_item(tipo,dados,criado,atualizado,por) VALUES(?,?,?,?,?)",
                                     (tipo, txt, agora, agora, quem["usuario"])).lastrowid
        self._db.commit()
    self.hub.registrar("gsa", quem["usuario"], {"o_que": tipo, "id": ident})
    return {"ok": True, "id": ident}


def _apagar(self, d: dict, quem: dict) -> dict:
    with self.hub._trava:
        r = self._db.execute("SELECT tipo FROM gsa_item WHERE id=? AND apagado=0", (int(d["id"]),)).fetchone()
        if not r:
            return {"ok": False, "erro": "item não encontrado", "codigo": 404}
        if r[0] == "financeiro" and not seg.pode(quem, seg.DIRECAO):
            return {"ok": False, "erro": "só a direção", "codigo": 403}
        self._db.execute("UPDATE gsa_item SET apagado=1, atualizado=?, por=? WHERE id=?", (self.hub.relogio(), quem["usuario"], int(d["id"])))
        self._db.commit()
    self.hub.registrar("gsa", quem["usuario"], {"o_que": "apagado", "id": int(d["id"])})
    return {"ok": True}


def _indicadores(self, hoje: str | None = None) -> dict:
    import time as _time
    hoje = hoje or _time.strftime("%Y-%m-%d", _time.localtime(self.hub.relogio()))
    todos = {t: _itens(self, t)["itens"] for t in TIPOS}
    tar = todos["tarefa"]
    atrasadas = [x for x in tar if x.get("prazo") and x["prazo"] < hoje and x.get("situacao") != "feita"]
    semana = [x for x in tar if x.get("prazo") and hoje <= x["prazo"] <= _data_mais(hoje, 7) and x.get("situacao") != "feita"]
    editais = [x for x in todos["edital"] if x.get("prazo") and hoje <= x["prazo"] <= _data_mais(hoje, 30) and x.get("situacao") in ("mapeado", "preparando", None)]
    ent = sum(x.get("valor", 0) for x in todos["financeiro"] if x.get("tipo_lancamento") == "entrada")
    sai = sum(x.get("valor", 0) for x in todos["financeiro"] if x.get("tipo_lancamento") == "saida")
    pend = self._db.execute("SELECT COUNT(*) FROM gsa_pedido WHERE estado='pendente'").fetchone()[0]
    alertas = ([f"Tarefa atrasada: {x['titulo']} (prazo {x['prazo']})" for x in atrasadas]
               + [f"Tarefa vence em até 7 dias: {x['titulo']} ({x['prazo']})" for x in semana]
               + [f"Edital fecha em até 30 dias: {x['titulo']} ({x['prazo']})" for x in editais]
               + ([f"{pend} pedido(s) de acesso aguardando a direção"] if pend else []))
    return {"ok": True, "hoje": hoje, "membros": len(self.hub.contas()), "pedidos_pendentes": pend,
            "projetos": {s: sum(1 for x in todos["projeto"] if (x.get("situacao") or "ideia") == s) for s in SITUACOES["projeto"]},
            "tarefas": {"total": len(tar), "feitas": sum(1 for x in tar if x.get("situacao") == "feita"), "atrasadas": len(atrasadas)},
            "editais": {s: sum(1 for x in todos["edital"] if (x.get("situacao") or "mapeado") == s) for s in SITUACOES["edital"]},
            "financeiro": {"entradas": round(ent, 2), "saidas": round(sai, 2), "saldo": round(ent - sai, 2)},
            "parceiros": len(todos["parceiro"]), "marketing": {s: sum(1 for x in todos["marketing"] if (x.get("situacao") or "rascunho") == s) for s in SITUACOES["marketing"]},
            "alertas": alertas}


def _data_mais(d: str, dias: int) -> str:
    import datetime as _dt
    return (_dt.date.fromisoformat(d) + _dt.timedelta(days=dias)).isoformat()


def _membros(self) -> dict:
    return {"ok": True, "contas": [{k: c[k] for k in ("nome", "usuario", "papel", "ativa")} for c in self.hub.contas()],
            "convites": seg.convite_listar(self.hub)}


def _convidar(self, d: dict, quem: dict) -> dict:
    c = seg.convite_criar(self.hub, d["email"], d.get("papel") or seg.EQUIPE, "", d.get("nome") or "", quem["usuario"], self.base)
    if not c.get("ok"):
        return c
    m = self._db.execute("SELECT corpo FROM email_saida WHERE ref=? ORDER BY id DESC LIMIT 1", (c["ref"],)).fetchone()
    return {"ok": True, "convite": c["id"], "texto_convite": m[0] if m else ""}


GSA.instalar_itens, GSA.itens, GSA.salvar, GSA.apagar = _instalar_itens, _itens, _salvar, _apagar
GSA.indicadores, GSA.membros, GSA.convidar = _indicadores, _membros, _convidar
_init_antigo = GSA.__init__


def _init_novo(self, hub, base_url: str = ""):
    _init_antigo(self, hub, base_url)
    self.instalar_itens()


GSA.__init__ = _init_novo


def _pasta_auto() -> Path | None:
    """Sem PHYSIS_GSA_DOCS: procura a pasta "Global South Alliance" (ou "Global Sourh Alliance") nos Documentos do OneDrive."""
    bases = [Path(os.environ[v]) / "Documents" for v in ("OneDriveCommercial", "OneDrive") if os.environ.get(v)]
    bases += [Path.home() / "OneDrive - Physis Engineering" / "Documents", Path.home() / "Documents"]
    for b in bases:
        for n in ("Global South Alliance", "Global Sourh Alliance"):
            if (b / n).is_dir():
                return b / n
    return None
