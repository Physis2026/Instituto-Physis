"""GSA · Global South Alliance: plataforma de GESTÃO INTERNA (25/11/2026; o site público vem depois).

Base do Instituto Physis. Entra só quem foi CONVIDADO ou quem PEDIU ACESSO e teve o pedido aceito pela direção (admin).
Aqui: pedido de acesso (público, com aceite LGPD), fila de pedidos da direção (aprovar = convite com link; recusar com motivo)
e a lista de documentos base (pasta PHYSIS_GSA_DOCS, só leitura; só para quem tem conta). Membros, projetos, tarefas e
alertas, financeiro, editais, parceiros, indicadores e marketing usam os módulos que já existem (Gestão interna em /gestao,
editais, parceiros, indicadores, convites e contas) — ver web/gsa.html.
"""
from __future__ import annotations

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
    return Path(p) if p else None


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
