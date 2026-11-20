"""Comunidade aberta do Instituto Physis (site e Rede InovaSTEM). Ver docs/COMUNIDADE.md.

Decisões de 19/11/2026:
- Plataforma aberta: qualquer pessoa LÊ sem conta. Para PUBLICAR, cadastro próprio (papel "cliente" = participante),
  com aceite LGPD. Cadastro aberto só quando o instancia.json tem "cadastro_aberto": true.
- Menor de 18 anos: a conta é criada, mas só publica depois que a equipe registra a autorização do responsável legal.
- Moderação ANTES de aparecer: tópico e resposta ficam "pendente" até a equipe aprovar (fila de moderação).
- InovaSTEM Delas: área só para mulheres (cis e trans), por autodeclaração voluntária (política 29). A autodeclaração é
  dado sensível: só a própria pessoa e a direção veem; ninguém mais vê quem se declarou.
- A fila de moderação também traz o que espera aprovação no Physis 3D (peças, tópicos e mensagens).

Sem dependências fora da biblioteca padrão. Toda escrita fica no registro encadeado do hub (hub.registrar).
"""
from __future__ import annotations

import re

from . import seguranca as seg

VERSAO_TERMO = "1"
FINALIDADE = ("Comunidade do Instituto Physis: mostrar o seu nome público junto do que você publicar no fórum e nas áreas "
              "abertas do site. O e-mail e a senha nunca aparecem. Você pode trocar o nome público ou sair da comunidade "
              "a qualquer momento; o que já foi publicado passa a aparecer como 'Participante removido'.")
FINALIDADE_DELAS = ("InovaSTEM Delas: área dedicada a mulheres (cis e trans). A autodeclaração é voluntária, não pede documento e "
                    "só serve para liberar esta área. Ninguém além de você e da direção do Instituto vê essa informação.")
FINALIDADE_MENOR = ("Menores de 18 anos: a conta pode navegar, mas só publica depois que a equipe do Instituto registrar a "
                    "autorização do responsável legal. O nome e o e-mail do responsável servem só para esse contato.")

CATEGORIAS = {"geral": "Geral", "inovastem": "Rede InovaSTEM", "delas": "InovaSTEM Delas", "physis-3d": "Physis 3D",
              "eventos": "Eventos e oportunidades", "parcerias": "Parcerias e novos projetos",
              # InovaSTEM (D94, 19/11/2026): fóruns do living lab
              "modelagem": "Modelagem 3D (GIS, BIM, 3D e simulação)", "desafios": "Desafios e projetos abertos",
              "hackathon": "Hackathon de cibersegurança"}
CATEGORIAS_EN = {"geral": "General", "inovastem": "InovaSTEM Network", "delas": "InovaSTEM Hers", "physis-3d": "Physis 3D",
                 "eventos": "Events and opportunities", "parcerias": "Partnerships and new projects",
                 "modelagem": "3D modelling (GIS, BIM, 3D and simulation)", "desafios": "Open challenges and projects",
                 "hackathon": "Cybersecurity hackathon"}
RESTRITAS = {"delas"}                 # leitura e escrita só para quem se autodeclarou (e a equipe, para moderar)
ESTADOS = ("pendente", "publicado", "recusado")
TEXTO_MAX, TITULO_MAX = 8000, 160
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,120}\.[^@\s]{2,40}")

_S = str
ESQUEMAS = {
    "com_cadastro": {"nome": (_S, 120, True), "usuario": (_S, 160, True), "senha": (_S, seg.SENHA_MAX, True),
                     "nome_publico": (_S, 80, True), "maior_de_idade": (bool, None, True), "responsavel_nome": (_S, 120, False),
                     "responsavel_email": (_S, 160, False), "delas": (bool, None, False), "consentimento": (dict, 4, True)},
    "com_topico": {"categoria": (_S, 20, True), "titulo": (_S, TITULO_MAX, True), "texto": (_S, TEXTO_MAX, True)},
    "com_resposta": {"texto": (_S, TEXTO_MAX, True)},
    "com_delas": {"autodeclaro": (bool, None, True)},
    "com_nome": {"nome_publico": (_S, 80, True)},
    "com_moderar": {"tipo": (_S, 20, True), "id": (int, 10**12, True), "decisao": (_S, 10, True), "motivo": (_S, 400, False)},
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS com_participante (
  usuario TEXT PRIMARY KEY, nome_publico TEXT NOT NULL, maior INTEGER NOT NULL DEFAULT 1,
  responsavel_nome TEXT NOT NULL DEFAULT '', responsavel_email TEXT NOT NULL DEFAULT '',
  autorizado INTEGER NOT NULL DEFAULT 0, autorizado_por TEXT NOT NULL DEFAULT '', autorizado_em REAL,
  delas INTEGER NOT NULL DEFAULT 0, delas_em REAL, versao_termo TEXT NOT NULL, removido INTEGER NOT NULL DEFAULT 0,
  criado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS com_topico (
  id INTEGER PRIMARY KEY AUTOINCREMENT, categoria TEXT NOT NULL, titulo TEXT NOT NULL, autor TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'pendente', motivo TEXT NOT NULL DEFAULT '', criado REAL NOT NULL,
  moderado_por TEXT NOT NULL DEFAULT '', moderado_em REAL);
CREATE TABLE IF NOT EXISTS com_mensagem (
  id INTEGER PRIMARY KEY AUTOINCREMENT, topico INTEGER NOT NULL, autor TEXT NOT NULL, texto TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'pendente', motivo TEXT NOT NULL DEFAULT '', criado REAL NOT NULL,
  moderado_por TEXT NOT NULL DEFAULT '', moderado_em REAL);
"""


def _texto(v, n: int) -> str:
    return str(v or "").strip()[:n]


def _eh_equipe(quem: dict | None) -> bool:
    return bool(quem) and seg.pode(quem, seg.EQUIPE)


def _eh_direcao(quem: dict | None) -> bool:
    return bool(quem) and seg.pode(quem, seg.DIRECAO)


class Comunidade:
    def __init__(self, hub, aberto: bool = False, impressao3d=None, relogio=None, agenda=None):
        self.hub = hub
        self.agenda = agenda                      # função que devolve a agenda de eventos (ou None)
        self.aberto = bool(aberto)
        self.p3d = impressao3d                      # função que devolve o módulo Physis 3D (ou None)
        self.relogio = relogio or hub.relogio
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    # ── participantes ────────────────────────────────────────────────────────────────────────────
    COLS = ("usuario", "nome_publico", "maior", "responsavel_nome", "responsavel_email", "autorizado", "autorizado_por",
            "autorizado_em", "delas", "delas_em", "versao_termo", "removido", "criado")

    def participante(self, usuario: str) -> dict | None:
        r = self._db.execute("SELECT " + ",".join(self.COLS) + " FROM com_participante WHERE usuario=?", (usuario,)).fetchone()
        return dict(zip(self.COLS, r)) if r else None

    def _nome(self, usuario: str) -> str:
        p = self.participante(usuario)
        return p["nome_publico"] if p else "Participante"

    def pode_publicar(self, quem: dict | None) -> tuple[bool, str]:
        if not quem:
            return False, "entre com a sua conta para publicar"
        if _eh_equipe(quem):
            return True, ""
        p = self.participante(quem["usuario"])
        if not p or p["removido"] or p["versao_termo"] != VERSAO_TERMO:
            return False, "aceite os termos da comunidade (LGPD) antes de publicar"
        if not p["maior"] and not p["autorizado"]:
            return False, "falta a autorização do responsável legal (a equipe do Instituto registra quando receber)"
        return True, ""

    def _ve_delas(self, quem: dict | None) -> bool:
        if _eh_equipe(quem):
            return True
        p = self.participante(quem["usuario"]) if quem else None
        return bool(p and p["delas"] and not p["removido"])

    def cadastrar(self, d: dict) -> dict:
        """Cadastro aberto (rota pública com limite por IP). Cria a conta como participante (papel cliente)."""
        if not self.aberto:
            return {"ok": False, "erro": "o cadastro aberto não está ligado nesta instalação", "codigo": 403}
        aceito, versao = seg._consentimento_do_corpo(d)
        if not aceito:
            return {"ok": False, "erro": "é preciso aceitar os termos e a política de privacidade", "finalidade": FINALIDADE}
        nome_pub = _texto(d.get("nome_publico"), 80)
        if len(nome_pub) < 2:
            return {"ok": False, "erro": "escolha um nome público (pode ser apelido)"}
        maior = d.get("maior_de_idade") is True
        resp_nome, resp_email = _texto(d.get("responsavel_nome"), 120), _texto(d.get("responsavel_email"), 160).lower()
        if not maior and (len(resp_nome) < 3 or not _EMAIL.fullmatch(resp_email)):
            return {"ok": False, "erro": "menores de 18 anos: informe o nome e o e-mail do responsável legal",
                    "finalidade": FINALIDADE_MENOR}
        if maior:
            resp_nome = resp_email = ""
        r = self.hub.criar_conta(_texto(d.get("nome"), 120), _texto(d.get("usuario"), 160), str(d.get("senha") or ""),
                                 papel=seg.CLIENTE, autocadastro=True)
        if not r["ok"]:
            return r
        usuario = _texto(d.get("usuario"), 160).lower()
        delas = d.get("delas") is True
        agora = self.relogio()
        with self.hub._trava:
            self._db.execute("INSERT OR REPLACE INTO com_participante(usuario,nome_publico,maior,responsavel_nome,responsavel_email,"
                             "autorizado,delas,delas_em,versao_termo,removido,criado) VALUES(?,?,?,?,?,0,?,?,?,0,?)",
                             (usuario, nome_pub, int(maior), resp_nome, resp_email, int(delas), agora if delas else None,
                              VERSAO_TERMO, agora))
            # o registro encadeado não leva a autodeclaração (dado sensível): só que houve cadastro
            self.hub.registrar("comunidade", usuario, {"o_que": "cadastro aberto", "maior": maior, "termo": VERSAO_TERMO})
            self._db.commit()
        return {"ok": True, "id": r["id"], "usuario": usuario, "versao": versao, "pode_publicar": maior,
                "aviso": "" if maior else FINALIDADE_MENOR}

    def eu(self, quem: dict) -> dict:
        p = self.participante(quem["usuario"])
        ok, motivo = self.pode_publicar(quem)
        out = {"ok": True, "participante": None, "pode_publicar": ok, "motivo": motivo, "equipe": _eh_equipe(quem),
               "finalidade": FINALIDADE, "finalidade_delas": FINALIDADE_DELAS, "versao_termo": VERSAO_TERMO}
        if p:
            out["participante"] = {"nome_publico": p["nome_publico"], "maior": bool(p["maior"]), "autorizado": bool(p["autorizado"]),
                                   "delas": bool(p["delas"]), "removido": bool(p["removido"])}
        return out

    def aderir(self, quem: dict, d: dict) -> dict:
        """Conta já existente (ex.: criada pela direção) entra na comunidade: nome público + aceite."""
        nome_pub = _texto(d.get("nome_publico"), 80)
        if len(nome_pub) < 2:
            return {"ok": False, "erro": "escolha um nome público (pode ser apelido)"}
        with self.hub._trava:
            self._db.execute("INSERT INTO com_participante(usuario,nome_publico,maior,versao_termo,criado) VALUES(?,?,1,?,?) "
                             "ON CONFLICT(usuario) DO UPDATE SET nome_publico=excluded.nome_publico, versao_termo=excluded.versao_termo, "
                             "removido=0", (quem["usuario"], nome_pub, VERSAO_TERMO, self.relogio()))
            self.hub.registrar("comunidade", quem["usuario"], {"o_que": "nome público", "termo": VERSAO_TERMO})
            self._db.commit()
        return {"ok": True}

    def autodeclarar_delas(self, quem: dict, d: dict) -> dict:
        p = self.participante(quem["usuario"])
        if not p or p["removido"]:
            return {"ok": False, "erro": "entre na comunidade antes (nome público e aceite)"}
        sim = d.get("autodeclaro") is True
        with self.hub._trava:
            self._db.execute("UPDATE com_participante SET delas=?, delas_em=? WHERE usuario=?",
                             (int(sim), self.relogio() if sim else None, quem["usuario"]))
            self._db.commit()
        return {"ok": True, "delas": sim, "finalidade": FINALIDADE_DELAS}

    def remover(self, usuario: str) -> int:
        """LGPD (art. 18, VI): sai da comunidade; o nome público vira 'Participante removido' e os dados do responsável
        e a autodeclaração são apagados. O que foi publicado segue, sem o nome."""
        with self.hub._trava:
            n = self._db.execute("UPDATE com_participante SET nome_publico='Participante removido', responsavel_nome='', "
                                 "responsavel_email='', delas=0, delas_em=NULL, removido=1 WHERE usuario=?", (usuario,)).rowcount
            if n:
                self.hub.registrar("comunidade", usuario, {"o_que": "saiu da comunidade (LGPD)"})
            self._db.commit()
        return n

    # ── fórum ────────────────────────────────────────────────────────────────────────────────────
    def categorias(self, quem: dict | None) -> dict:
        ve_delas = self._ve_delas(quem) if quem else False
        return {"ok": True, "categorias": [{"id": k, "nome": v, "nome_en": CATEGORIAS_EN[k], "restrita": k in RESTRITAS,
                                            "acesso": (k not in RESTRITAS) or ve_delas} for k, v in CATEGORIAS.items()],
                "finalidade_delas": FINALIDADE_DELAS}

    def _pode_ler_categoria(self, cat: str, quem: dict | None) -> bool:
        return cat in CATEGORIAS and (cat not in RESTRITAS or (quem is not None and self._ve_delas(quem)))

    def topicos(self, categoria: str, quem: dict | None) -> dict:
        categoria = categoria or "geral"
        if categoria not in CATEGORIAS:
            return {"ok": False, "erro": "categoria: " + ", ".join(CATEGORIAS), "codigo": 404}
        if not self._pode_ler_categoria(categoria, quem):
            return {"ok": False, "erro": "área só para participantes da InovaSTEM Delas", "codigo": 403, "delas": True,
                    "finalidade": FINALIDADE_DELAS}
        eq = _eh_equipe(quem)
        eu_ = quem["usuario"] if quem else None
        out = []
        q = ("SELECT t.id, t.titulo, t.autor, t.estado, t.criado, COUNT(m.id), MAX(m.criado) FROM com_topico t "
             "LEFT JOIN com_mensagem m ON m.topico=t.id AND m.estado='publicado' WHERE t.categoria=? GROUP BY t.id ORDER BY t.criado DESC")
        for i, tit, aut, est, cr, n, ult in self._db.execute(q, (categoria,)):
            if est != "publicado" and not (eq or aut == eu_):
                continue
            out.append({"id": i, "titulo": tit, "autor_nome": self._nome(aut), "estado": est, "criado": cr, "mensagens": n,
                        "ultima": ult or cr, "meu": aut == eu_})
        return {"ok": True, "categoria": categoria, "nome": CATEGORIAS[categoria], "topicos": out}

    def _topico(self, ident: int):
        r = self._db.execute("SELECT id, categoria, titulo, autor, estado, motivo FROM com_topico WHERE id=?", (int(ident),)).fetchone()
        return dict(zip(("id", "categoria", "titulo", "autor", "estado", "motivo"), r)) if r else None

    def mensagens(self, ident: int, quem: dict | None) -> dict:
        t = self._topico(ident)
        eq = _eh_equipe(quem)
        eu_ = quem["usuario"] if quem else None
        if not t or not self._pode_ler_categoria(t["categoria"], quem) or (t["estado"] != "publicado" and not (eq or t["autor"] == eu_)):
            return {"ok": False, "erro": "tópico não encontrado", "codigo": 404}
        out = []
        for i, aut, txt, est, cr in self._db.execute("SELECT id, autor, texto, estado, criado FROM com_mensagem WHERE topico=? ORDER BY id",
                                                     (t["id"],)):
            if est != "publicado" and not (eq or aut == eu_):
                continue
            out.append({"id": i, "autor_nome": self._nome(aut), "texto": txt, "estado": est, "criado": cr, "minha": aut == eu_})
        return {"ok": True, "topico": {"id": t["id"], "categoria": t["categoria"], "titulo": t["titulo"], "estado": t["estado"],
                                       "autor_nome": self._nome(t["autor"])}, "mensagens": out}

    def abrir_topico(self, d: dict, quem: dict) -> dict:
        ok, motivo = self.pode_publicar(quem)
        if not ok:
            return {"ok": False, "erro": motivo, "finalidade": FINALIDADE}
        cat = _texto(d.get("categoria"), 20)
        if cat not in CATEGORIAS:
            return {"ok": False, "erro": "categoria: " + ", ".join(CATEGORIAS)}
        if not self._pode_ler_categoria(cat, quem):
            return {"ok": False, "erro": "área só para participantes da InovaSTEM Delas", "codigo": 403}
        tit, txt = _texto(d.get("titulo"), TITULO_MAX), _texto(d.get("texto"), TEXTO_MAX)
        if len(tit) < 3 or len(txt) < 2:
            return {"ok": False, "erro": "escreva o título e a mensagem"}
        estado = "publicado" if _eh_equipe(quem) else "pendente"      # a equipe já é a moderação
        agora = self.relogio()
        with self.hub._trava:
            cur = self._db.execute("INSERT INTO com_topico(categoria,titulo,autor,estado,criado) VALUES(?,?,?,?,?)",
                                   (cat, tit, quem["usuario"], estado, agora))
            self._db.execute("INSERT INTO com_mensagem(topico,autor,texto,estado,criado) VALUES(?,?,?,?,?)",
                             (cur.lastrowid, quem["usuario"], txt, estado, agora))
            self.hub.registrar("comunidade", quem["usuario"], {"o_que": "tópico", "id": cur.lastrowid, "categoria": cat, "estado": estado})
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid, "estado": estado,
                "aviso": "" if estado == "publicado" else "Recebido. Aparece para todos depois da moderação da equipe."}

    def responder(self, ident: int, d: dict, quem: dict) -> dict:
        ok, motivo = self.pode_publicar(quem)
        if not ok:
            return {"ok": False, "erro": motivo, "finalidade": FINALIDADE}
        t = self._topico(ident)
        if not t or t["estado"] != "publicado" or not self._pode_ler_categoria(t["categoria"], quem):
            return {"ok": False, "erro": "tópico não encontrado", "codigo": 404}
        txt = _texto(d.get("texto"), TEXTO_MAX)
        if len(txt) < 2:
            return {"ok": False, "erro": "escreva a mensagem"}
        estado = "publicado" if _eh_equipe(quem) else "pendente"
        with self.hub._trava:
            cur = self._db.execute("INSERT INTO com_mensagem(topico,autor,texto,estado,criado) VALUES(?,?,?,?,?)",
                                   (t["id"], quem["usuario"], txt, estado, self.relogio()))
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid, "estado": estado}

    # ── moderação ────────────────────────────────────────────────────────────────────────────────
    def fila(self, quem: dict) -> dict:
        """Tudo o que espera a equipe: fórum, autorizações de menores e o Physis 3D. Sem autodeclaração (dado sensível)."""
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe modera", "codigo": 403}
        itens = []
        for i, cat, tit, aut, cr in self._db.execute("SELECT id, categoria, titulo, autor, criado FROM com_topico WHERE estado='pendente' ORDER BY criado"):
            prim = self._db.execute("SELECT texto FROM com_mensagem WHERE topico=? ORDER BY id LIMIT 1", (i,)).fetchone()
            itens.append({"tipo": "topico", "id": i, "categoria": cat, "titulo": tit, "texto": prim[0] if prim else "",
                          "autor_nome": self._nome(aut), "criado": cr})
        for i, top, aut, txt, cr in self._db.execute("SELECT m.id, m.topico, m.autor, m.texto, m.criado FROM com_mensagem m JOIN com_topico t "
                                                     "ON t.id=m.topico WHERE m.estado='pendente' AND t.estado='publicado' ORDER BY m.criado"):
            itens.append({"tipo": "mensagem", "id": i, "topico": top, "texto": txt, "autor_nome": self._nome(aut), "criado": cr})
        for (u, nome, rn, re_, cr) in self._db.execute("SELECT usuario, nome_publico, responsavel_nome, responsavel_email, criado FROM "
                                                       "com_participante WHERE maior=0 AND autorizado=0 AND removido=0 ORDER BY criado"):
            itens.append({"tipo": "menor", "id": self._conta_id(u), "nome_publico": nome, "responsavel_nome": rn,
                          "responsavel_email": re_, "criado": cr})
        p3d = self.p3d() if callable(self.p3d) else self.p3d
        if p3d is not None and hasattr(p3d, "pendentes"):
            itens += p3d.pendentes()
        ag = self.agenda() if callable(self.agenda) else self.agenda
        if ag is not None:
            itens += ag.pendentes()
        return {"ok": True, "itens": itens, "total": len(itens)}

    def _conta_id(self, usuario: str) -> int:
        r = self._db.execute("SELECT id FROM conta WHERE lower(usuario)=?", (usuario.lower(),)).fetchone()
        return int(r[0]) if r else 0

    def moderar(self, d: dict, quem: dict) -> dict:
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe modera", "codigo": 403}
        tipo, ident, dec = _texto(d.get("tipo"), 20), int(d.get("id") or 0), _texto(d.get("decisao"), 10)
        motivo = _texto(d.get("motivo"), 400)
        if dec not in ("aprovar", "recusar"):
            return {"ok": False, "erro": "decisão: aprovar ou recusar"}
        if dec == "recusar" and not motivo:
            return {"ok": False, "erro": "diga o motivo da recusa"}
        if tipo == "evento":
            ag = self.agenda() if callable(self.agenda) else self.agenda
            if ag is None:
                return {"ok": False, "erro": "agenda não está ligada", "codigo": 404}
            return ag.decidir(ident, dec, motivo, quem)
        if tipo.startswith("p3d_"):
            p3d = self.p3d() if callable(self.p3d) else self.p3d
            if p3d is None:
                return {"ok": False, "erro": "Physis 3D não está ligado", "codigo": 404}
            return p3d.decidir_pendente(tipo, ident, dec, motivo, quem)
        novo = "publicado" if dec == "aprovar" else "recusado"
        agora = self.relogio()
        with self.hub._trava:
            if tipo == "topico":
                n = self._db.execute("UPDATE com_topico SET estado=?, motivo=?, moderado_por=?, moderado_em=? WHERE id=? AND estado='pendente'",
                                     (novo, motivo, quem["usuario"], agora, ident)).rowcount
                if n:          # a primeira mensagem segue o tópico
                    self._db.execute("UPDATE com_mensagem SET estado=?, motivo=?, moderado_por=?, moderado_em=? WHERE id=(SELECT MIN(id) "
                                     "FROM com_mensagem WHERE topico=?) AND estado='pendente'", (novo, motivo, quem["usuario"], agora, ident))
            elif tipo == "mensagem":
                n = self._db.execute("UPDATE com_mensagem SET estado=?, motivo=?, moderado_por=?, moderado_em=? WHERE id=? AND estado='pendente'",
                                     (novo, motivo, quem["usuario"], agora, ident)).rowcount
            elif tipo == "menor":
                r = self._db.execute("SELECT usuario FROM conta WHERE id=?", (ident,)).fetchone()
                n = 0
                if r and dec == "aprovar":
                    n = self._db.execute("UPDATE com_participante SET autorizado=1, autorizado_por=?, autorizado_em=? WHERE lower(usuario)=? "
                                         "AND maior=0", (quem["usuario"], agora, r[0].lower())).rowcount
                elif r:
                    n = 1      # recusa: a conta segue só para navegar; o motivo fica no registro
            else:
                return {"ok": False, "erro": "tipo: topico, mensagem, menor, evento, p3d_peca, p3d_topico ou p3d_mensagem"}
            if n:
                self.hub.registrar("comunidade", quem["usuario"], {"o_que": "moderação", "tipo": tipo, "id": ident, "decisao": dec,
                                                                  "motivo": motivo})
            self._db.commit()
        return {"ok": n > 0, **({} if n else {"erro": "item não encontrado ou já decidido", "codigo": 404})}

    # ── rotas (o servidor confere limite por IP, CSRF e papel; aqui, o acesso de cada item) ─────────
    def rota(self, metodo: str, caminho: str, quem: dict | None, d: dict | None = None, consulta: dict | None = None):
        g = lambda k: ((consulta or {}).get(k) or [""])[0][:40]
        publico = caminho.startswith("/api/publico/comunidade")
        c = caminho[len("/api/publico/comunidade" if publico else "/api/comunidade"):]
        if publico:
            quem = None                                   # a rota pública nunca usa a sessão
        if metodo == "GET":
            if c == "/categorias":
                return self._r(self.categorias(quem))
            if c == "/forum":
                return self._r(self.topicos(g("categoria"), quem))
            m = re.fullmatch(r"/forum/(\d{1,12})", c)
            if m:
                return self._r(self.mensagens(int(m.group(1)), quem))
            if not publico and c == "/eu":
                return self._r(self.eu(quem))
            if not publico and c == "/moderacao":
                return self._r(self.fila(quem))
            return 404, {"ok": False, "erro": "rota desconhecida"}
        if publico or metodo != "POST":
            return 405, {"ok": False, "erro": "método"}
        if c == "/forum":
            return self._r(self.abrir_topico(d, quem))
        m = re.fullmatch(r"/forum/(\d{1,12})", c)
        if m:
            return self._r(self.responder(int(m.group(1)), d, quem))
        if c == "/delas":
            return self._r(self.autodeclarar_delas(quem, d))
        if c == "/participante":
            return self._r(self.aderir(quem, d))
        if c == "/sair":
            return self._r({"ok": self.remover(quem["usuario"]) > 0})
        if c == "/moderar":
            return self._r(self.moderar(d, quem))
        return 404, {"ok": False, "erro": "rota desconhecida"}

    ESQUEMA_DE = {"/forum": "com_topico", "/delas": "com_delas", "/participante": "com_nome", "/sair": "vazio", "/moderar": "com_moderar"}

    def esquema_post(self, caminho: str) -> str | None:
        c = caminho[len("/api/comunidade"):]
        if re.fullmatch(r"/forum/\d{1,12}", c):
            return "com_resposta"
        return self.ESQUEMA_DE.get(c)

    @staticmethod
    def _r(r: dict):
        return r.pop("codigo", 200 if r.get("ok") else 400), r


def dados_do_titular(hub, usuario: str) -> dict:
    """Para a exportação LGPD (art. 18, II): o que a comunidade guarda da pessoa."""
    try:
        r = hub._db.execute("SELECT nome_publico, maior, responsavel_nome, responsavel_email, autorizado, delas, criado FROM "
                            "com_participante WHERE usuario=?", (usuario,)).fetchone()
    except Exception:
        return {}
    return dict(zip(("nome_publico", "maior", "responsavel_nome", "responsavel_email", "autorizado", "delas", "criado"), r)) if r else {}


__all__ = ["Comunidade", "ESQUEMAS", "CATEGORIAS", "dados_do_titular"]
