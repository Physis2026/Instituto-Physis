"""InovaSTEM: site e plataforma como living lab online (decisão D94 de 19/11/2026). Ver docs/INOVASTEM.md.

Terceira instalação ("inovastem"), montada do mesmo código do Instituto, com banco, porta, marca e subdomínio próprios.
Até o CNPJ do Instituto, sai sob a Physis Engineering (marca endossada: "uma iniciativa da Physis Engineering").
O fórum, o cadastro com conta, a InovaSTEM Delas e a biblioteca do Physis 3D vêm de comunidade.py e impressao3d.py;
este módulo traz só o que é próprio da InovaSTEM:

- Cadastro de interesse, sem conta e com coleta mínima: nome (ou apelido), e-mail, áreas de interesse e aceite do aviso
  de privacidade beta. Cidade, instituição e gênero são opcionais. Gênero "feminino" abre o convite para a InovaSTEM Delas
  (rede dedicada a mulheres jovens, cis e trans); o gênero serve só para esse convite e não vai para o registro encadeado.
  Menor de 18 anos informa o nome e o e-mail do responsável legal.
- Desafios abertos (a equipe publica) e sugestões de projetos abertos (qualquer pessoa sugere; só aparecem depois da
  moderação). O e-mail de quem sugere nunca aparece no público.
- Materiais para download: só os arquivos que a direção pôs na pasta de materiais e listou no instancia.json (PDF e ODF).
- Link do grupo de WhatsApp: opcional (regra 11). Só aparece quando é um convite https://chat.whatsapp.com/.
- LGPD: a equipe apaga um interesse pelo e-mail (pedido do titular); as sugestões ficam sem nome e sem e-mail.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import seguranca as seg

VERSAO_AVISO = "beta-2026-11"            # aviso de privacidade beta, em revisão jurídica
# Uma área por escopo (pedido da direção, 20/11/2026: "devem ser separados, são escopos diferentes")
AREAS = {
    "gis": "GIS (mapas)", "bim": "BIM (IFC)", "modelagem3d": "Modelagem 3D", "physis3d": "Physis 3D (impressão com plástico reciclado)",
    "gemeo": "Gêmeo digital", "simulacoes": "Simulações", "ciberseguranca": "Cibersegurança", "hackathon": "Hackathon",
    "delas": "InovaSTEM Delas", "mentoria": "Mentoria (quero ser mentora ou mentor)", "desafios": "Desafios abertos",
    "projetos": "Projetos abertos", "patrocinio": "Patrocínio", "parcerias": "Parcerias",
}
AREAS_EN = {
    "gis": "GIS (maps)", "bim": "BIM (IFC)", "modelagem3d": "3D modelling", "physis3d": "Physis 3D (recycled-plastic printing)",
    "gemeo": "Digital twin", "simulacoes": "Simulations", "ciberseguranca": "Cybersecurity", "hackathon": "Hackathon",
    "delas": "InovaSTEM Delas", "mentoria": "Mentoring (I want to mentor)", "desafios": "Open challenges",
    "projetos": "Open projects", "patrocinio": "Sponsorship", "parcerias": "Partnerships",
}
GENEROS = ("", "feminino", "masculino", "nao_informar")
TIPOS = ("desafio", "projeto")           # desafio: a equipe publica; projeto: sugestão aberta, com moderação
ESTADOS = ("pendente", "publicado", "recusado", "encerrado")
EXTENSOES_MATERIAIS = {".pdf": "application/pdf", ".odt": "application/vnd.oasis.opendocument.text",
                       ".odp": "application/vnd.oasis.opendocument.presentation",
                       ".ods": "application/vnd.oasis.opendocument.spreadsheet"}
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,120}\.[^@\s]{2,40}")
_WHATS = re.compile(r"https://chat\.whatsapp\.com/[A-Za-z0-9]{10,40}")
_ARQ = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}")
_S = str
ESQUEMAS = {
    "ino_interesse": {"nome": (_S, 120, True), "email": (_S, 160, True), "areas": (list, len(AREAS), False),
                      "cidade": (_S, 80, False), "instituicao": (_S, 120, False), "genero": (_S, 20, False),
                      "quero_delas": (bool, None, False), "maior_de_idade": (bool, None, True),
                      "responsavel_nome": (_S, 120, False), "responsavel_email": (_S, 160, False),
                      "aceite": (bool, None, True), "versao": (_S, 30, False)},
    "ino_proposta": {"titulo": (_S, 160, True), "descricao": (_S, 4000, True), "area": (_S, 20, False),
                     "organizacao": (_S, 120, False), "nome": (_S, 120, False), "email": (_S, 160, False),
                     "prazo": (_S, 10, False), "aceite": (bool, None, False)},
    "ino_moderar": {"id": (int, 10**12, True), "decisao": (_S, 10, True), "motivo": (_S, 400, False)},
    "ino_remover": {"email": (_S, 160, True)},
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ino_interesse (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, email TEXT NOT NULL, areas TEXT NOT NULL DEFAULT '[]',
  cidade TEXT NOT NULL DEFAULT '', instituicao TEXT NOT NULL DEFAULT '', genero TEXT NOT NULL DEFAULT '',
  quero_delas INTEGER NOT NULL DEFAULT 0, maior INTEGER NOT NULL DEFAULT 1, responsavel_nome TEXT NOT NULL DEFAULT '',
  responsavel_email TEXT NOT NULL DEFAULT '', versao_aviso TEXT NOT NULL, criado REAL NOT NULL, atualizado REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS ino_interesse_email ON ino_interesse(email);
CREATE TABLE IF NOT EXISTS ino_proposta (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT NOT NULL, titulo TEXT NOT NULL, descricao TEXT NOT NULL,
  area TEXT NOT NULL DEFAULT '', organizacao TEXT NOT NULL DEFAULT '', nome TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '', prazo TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL, motivo TEXT NOT NULL DEFAULT '',
  criado_por TEXT NOT NULL DEFAULT '', criado REAL NOT NULL, moderado_por TEXT NOT NULL DEFAULT '', moderado_em REAL);
"""


def _texto(v, n: int) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(v or "")).strip()[:n]


def _eh_equipe(quem: dict | None) -> bool:
    return bool(quem) and seg.pode(quem, seg.EQUIPE)


def link_whatsapp(v) -> str:
    """Convite do grupo, só se for https://chat.whatsapp.com/<código>; senão vazio (o botão não aparece)."""
    v = str(v or "").strip()
    return v if _WHATS.fullmatch(v) else ""


def config_de(instancia: dict) -> dict:
    """Bloco "inovastem" do instancia.json, com PHYSIS_INOVASTEM_WHATSAPP valendo mais que o arquivo."""
    c = instancia.get("inovastem") if isinstance(instancia.get("inovastem"), dict) else {}
    return {"whatsapp": link_whatsapp(os.environ.get("PHYSIS_INOVASTEM_WHATSAPP") or c.get("whatsapp_grupo")),
            "hackathon": str(c.get("hackathon") or "2027-03")[:7],
            "endereco": str(c.get("endereco") or "")[:120],
            "materiais": [m for m in (c.get("materiais") or []) if isinstance(m, dict)][:60]}


class InovaSTEM:
    def __init__(self, hub, instancia: dict | None = None, pasta_materiais: Path | None = None, relogio=None):
        self.hub = hub
        self.cfg = config_de(instancia or {})
        self.pasta_materiais = Path(pasta_materiais) if pasta_materiais else None
        self.relogio = relogio or hub.relogio
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    # ── público ────────────────────────────────────────────────────────────────────────────────
    def publico(self) -> dict:
        """O que o site precisa saber da instalação: WhatsApp (se houver), mês do hackathon, áreas e materiais."""
        return {"ok": True, "whatsapp": self.cfg["whatsapp"], "hackathon": self.cfg["hackathon"],
                "areas": [{"id": k, "nome": v, "nome_en": AREAS_EN[k]} for k, v in AREAS.items()],
                "materiais": self.materiais(), "versao_aviso": VERSAO_AVISO}

    def materiais(self) -> list:
        """Só os arquivos listados no instancia.json E presentes na pasta de materiais (a direção aprova cada um)."""
        out = []
        for m in self.cfg["materiais"]:
            arq = str(m.get("arquivo") or "")
            if not _ARQ.fullmatch(arq) or Path(arq).suffix.lower() not in EXTENSOES_MATERIAIS:
                continue
            if not self.pasta_materiais or not (self.pasta_materiais / arq).is_file():
                continue
            out.append({"titulo": _texto(m.get("titulo"), 160) or arq, "titulo_en": _texto(m.get("titulo_en"), 160),
                        "grupo": _texto(m.get("grupo"), 40), "arquivo": arq, "tipo": Path(arq).suffix.lower()[1:]})
        return out

    def arquivo_material(self, nome: str) -> tuple[str, bytes] | None:
        """(tipo, bytes) de um material listado; None para qualquer outro nome (sem subir de pasta)."""
        if not any(m["arquivo"] == nome for m in self.materiais()):
            return None
        return EXTENSOES_MATERIAIS[Path(nome).suffix.lower()], (self.pasta_materiais / nome).read_bytes()

    def interesse(self, d: dict) -> dict:
        nome, email = _texto(d.get("nome"), 120), _texto(d.get("email"), 160).lower()
        if len(nome) < 2:
            return {"ok": False, "erro": "Escreva o seu nome ou apelido."}
        if not _EMAIL.fullmatch(email):
            return {"ok": False, "erro": "Confira o e-mail."}
        if d.get("aceite") is not True:
            return {"ok": False, "erro": "Para se cadastrar, é preciso ler e aceitar o aviso de privacidade (beta)."}
        areas = [a for a in (d.get("areas") or []) if a in AREAS]
        genero = _texto(d.get("genero"), 20)
        if genero not in GENEROS:
            return {"ok": False, "erro": "Gênero: escolha uma das opções ou deixe em branco."}
        maior = d.get("maior_de_idade") is True
        rn, re_ = _texto(d.get("responsavel_nome"), 120), _texto(d.get("responsavel_email"), 160).lower()
        if not maior and (len(rn) < 2 or not _EMAIL.fullmatch(re_)):
            return {"ok": False, "erro": "Menores de 18 anos: informe o nome e o e-mail do responsável legal."}
        if maior:
            rn = re_ = ""
        quero_delas = bool(d.get("quero_delas")) and genero == "feminino"
        if quero_delas and "delas" not in areas:
            areas.append("delas")
        agora = self.relogio()
        vals = (nome, email, json.dumps(areas), _texto(d.get("cidade"), 80), _texto(d.get("instituicao"), 120), genero,
                int(quero_delas), int(maior), rn, re_, VERSAO_AVISO)
        with self.hub._trava:
            ja = self._db.execute("SELECT id FROM ino_interesse WHERE email=?", (email,)).fetchone()
            if ja:      # mesmo e-mail: atualiza (sem dizer ao público se o e-mail já existia)
                self._db.execute("UPDATE ino_interesse SET nome=?, email=?, areas=?, cidade=?, instituicao=?, genero=?, quero_delas=?,"
                                 " maior=?, responsavel_nome=?, responsavel_email=?, versao_aviso=?, atualizado=? WHERE id=?",
                                 vals + (agora, ja[0]))
                ident = ja[0]
            else:
                ident = self._db.execute(
                    "INSERT INTO ino_interesse(nome,email,areas,cidade,instituicao,genero,quero_delas,maior,responsavel_nome,"
                    "responsavel_email,versao_aviso,criado,atualizado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", vals + (agora, agora)).lastrowid
            self._db.commit()
        # registro encadeado: só o número e as áreas (nada de nome, e-mail ou gênero)
        self.hub.registrar("inovastem", "publico", {"o_que": "interesse", "id": ident, "areas": areas})
        return {"ok": True, "delas": genero == "feminino"}

    def propostas(self, tipo: str = "") -> dict:
        """Desafios abertos e projetos aprovados (sem nome nem e-mail de quem sugeriu)."""
        if tipo and tipo not in TIPOS:
            return {"ok": False, "erro": "tipo: " + ", ".join(TIPOS), "codigo": 404}
        q = "SELECT id, tipo, titulo, descricao, area, organizacao, prazo, criado FROM ino_proposta WHERE estado='publicado'"
        args: tuple = ()
        if tipo:
            q += " AND tipo=?"
            args = (tipo,)
        itens = [dict(zip(("id", "tipo", "titulo", "descricao", "area", "organizacao", "prazo", "criado"), r))
                 for r in self._db.execute(q + " ORDER BY criado DESC LIMIT 200", args)]
        for x in itens:
            x["area_nome"], x["area_nome_en"] = AREAS.get(x["area"], ""), AREAS_EN.get(x["area"], "")
        return {"ok": True, "itens": itens}

    def _proposta(self, d: dict, tipo: str, estado: str, quem: str) -> dict:
        tit, desc = _texto(d.get("titulo"), 160), _texto(d.get("descricao"), 4000)
        if len(tit) < 4 or len(desc) < 20:
            return {"ok": False, "erro": "Escreva um título e uma descrição de pelo menos 20 letras."}
        area = _texto(d.get("area"), 20)
        if area and area not in AREAS:
            return {"ok": False, "erro": "área: " + ", ".join(AREAS)}
        prazo = _texto(d.get("prazo"), 10)
        if prazo and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", prazo):
            return {"ok": False, "erro": "Prazo no formato AAAA-MM-DD."}
        email = _texto(d.get("email"), 160).lower()
        if tipo == "projeto":
            if not _EMAIL.fullmatch(email):
                return {"ok": False, "erro": "Informe um e-mail para a equipe responder (ele não aparece no site)."}
            if d.get("aceite") is not True:
                return {"ok": False, "erro": "É preciso aceitar o aviso de privacidade (beta)."}
        with self.hub._trava:
            ident = self._db.execute(
                "INSERT INTO ino_proposta(tipo,titulo,descricao,area,organizacao,nome,email,prazo,estado,criado_por,criado)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (tipo, tit, desc, area, _texto(d.get("organizacao"), 120), _texto(d.get("nome"), 120), email, prazo, estado,
                 quem, self.relogio())).lastrowid
            self._db.commit()
        self.hub.registrar("inovastem", quem or "publico", {"o_que": tipo, "id": ident, "estado": estado})
        return {"ok": True, "id": ident, "estado": estado}

    def sugerir_projeto(self, d: dict) -> dict:
        return self._proposta(d, "projeto", "pendente", "")

    # ── equipe ─────────────────────────────────────────────────────────────────────────────────
    def publicar_desafio(self, d: dict, quem: dict) -> dict:
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe publica desafios", "codigo": 403}
        return self._proposta(d, "desafio", "publicado", quem["usuario"])

    def fila(self, quem: dict) -> dict:
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe modera", "codigo": 403}
        cols = ("id", "tipo", "titulo", "descricao", "area", "organizacao", "nome", "email", "prazo", "criado")
        return {"ok": True, "itens": [dict(zip(cols, r)) for r in self._db.execute(
            "SELECT " + ",".join(cols) + " FROM ino_proposta WHERE estado='pendente' ORDER BY criado")]}

    def moderar(self, d: dict, quem: dict) -> dict:
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe modera", "codigo": 403}
        dec = _texto(d.get("decisao"), 10)
        novo = {"aprovar": "publicado", "recusar": "recusado", "encerrar": "encerrado"}.get(dec)
        if not novo:
            return {"ok": False, "erro": "decisao: aprovar, recusar ou encerrar"}
        motivo = _texto(d.get("motivo"), 400)
        if novo == "recusado" and len(motivo) < 3:
            return {"ok": False, "erro": "Escreva o motivo da recusa."}
        with self.hub._trava:
            r = self._db.execute("SELECT estado FROM ino_proposta WHERE id=?", (int(d.get("id") or 0),)).fetchone()
            if not r:
                return {"ok": False, "erro": "não encontrado", "codigo": 404}
            if novo != "encerrado" and r[0] != "pendente":
                return {"ok": False, "erro": "já moderado", "codigo": 409}
            self._db.execute("UPDATE ino_proposta SET estado=?, motivo=?, moderado_por=?, moderado_em=? WHERE id=?",
                             (novo, motivo, quem["usuario"], self.relogio(), int(d["id"])))
            self._db.commit()
        self.hub.registrar("inovastem", quem["usuario"], {"o_que": "moderação", "id": int(d["id"]), "estado": novo})
        return {"ok": True, "estado": novo}

    def interesses(self, quem: dict) -> dict:
        """Lista para a equipe (dado pessoal: só com sessão da equipe). O gênero só aparece como convite Delas."""
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe vê os cadastros", "codigo": 403}
        cols = ("id", "nome", "email", "areas", "cidade", "instituicao", "quero_delas", "maior", "responsavel_nome",
                "responsavel_email", "versao_aviso", "criado")
        itens = []
        for r in self._db.execute("SELECT " + ",".join(cols) + " FROM ino_interesse ORDER BY criado DESC"):
            x = dict(zip(cols, r))
            x["areas"] = json.loads(x["areas"] or "[]")
            itens.append(x)
        por_area = {k: sum(1 for x in itens if k in x["areas"]) for k in AREAS}
        return {"ok": True, "total": len(itens), "por_area": por_area, "itens": itens}

    def remover_interesse(self, d: dict, quem: dict) -> dict:
        """Pedido do titular (LGPD art. 18): apaga o cadastro de interesse e tira nome e e-mail das sugestões dele."""
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe atende pedidos de exclusão", "codigo": 403}
        email = _texto(d.get("email"), 160).lower()
        with self.hub._trava:
            n = self._db.execute("DELETE FROM ino_interesse WHERE email=?", (email,)).rowcount
            m = self._db.execute("UPDATE ino_proposta SET nome='', email='' WHERE email=?", (email,)).rowcount
            self._db.commit()
        self.hub.registrar("inovastem", quem["usuario"], {"o_que": "exclusão a pedido", "interesses": n, "propostas": m})
        return {"ok": True, "interesses": n, "propostas": m}


__all__ = ["InovaSTEM", "ESQUEMAS", "AREAS", "VERSAO_AVISO", "config_de", "link_whatsapp"]
