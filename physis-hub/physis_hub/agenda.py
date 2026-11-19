"""Agenda de eventos e oportunidades do Instituto Physis (site, aba Eventos). Ver docs/COMUNIDADE.md, etapa 3.

Decisões de 19/11/2026:
- Quatro tipos de oportunidade mapeados desde já, mais os eventos do próprio Instituto:
  hackathons de segurança e computação quântica; modelos virtuais e gêmeo digital; feiras e eventos de outras redes;
  desafios abertos e chamadas.
- Três origens: a equipe cadastra (publica direto); participantes sugerem; o coletor de eventos (editais.py) traz itens das
  fontes públicas. Sugestão e coletor entram como "sugerido" e só aparecem depois que a equipe aprova (fila de moderação).
- Link só https://. Data no formato AAAA-MM-DD; sem data, o item fica como "data a confirmar". Nada é inventado: o que o
  coletor não achou (data, local) fica vazio.
"""
from __future__ import annotations

import re
import time

from . import seguranca as seg

CATEGORIAS = {
    "hackathon_seg_quantum": "Hackathons de segurança e computação quântica",
    "modelos_gemeo": "Modelos virtuais e gêmeo digital",
    "feiras_redes": "Feiras e eventos de outras redes",
    "desafios_chamadas": "Desafios abertos e chamadas",
    "instituto": "Eventos do Instituto",
}
CATEGORIAS_EN = {
    "hackathon_seg_quantum": "Security and quantum computing hackathons", "modelos_gemeo": "Virtual models and digital twins",
    "feiras_redes": "Fairs and other networks' events", "desafios_chamadas": "Open challenges and calls", "instituto": "Institute events",
}
MODALIDADES = ("online", "presencial", "hibrido", "")
# Palavras (sem acento, minúsculas) que classificam um item do coletor. A ordem decide o empate: o mais específico primeiro.
PALAVRAS = [
    ("hackathon_seg_quantum", ["hackathon", "hackaton", "capture the flag", " ctf", "ciberseg", "cyber", "seguranca da informacao",
                               "seguranca cibernetica", "quantic", "quantum", "qiskit"]),
    ("modelos_gemeo", ["gemeo digital", "digital twin", "modelo virtual", "modelos virtuais", "virtual model", "simulac", "simulation",
                       "modelagem", "modeling", "modelling", "metaverso"]),
    ("desafios_chamadas", ["desafio", "challenge", "premio", "award", "call for", "chamada", "inovacao aberta", "open innovation",
                           "maratona", "competicao", "competition"]),
    ("feiras_redes", ["feira", "expo", "congresso", "summit", "conferencia", "conference", "forum", "encontro", "simposio",
                      "mulheres", "women", "girls", "meninas", "rede ", "network"]),
]
ESTADOS = ("sugerido", "publicado", "recusado", "arquivado")
_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")
_S = str
ESQUEMAS = {
    "ag_evento": {"categoria": (_S, 30, True), "titulo": (_S, 200, True), "descricao": (_S, 2000, False), "inicio": (_S, 10, False),
                  "fim": (_S, 10, False), "modalidade": (_S, 12, False), "local": (_S, 160, False), "link": (_S, 500, False),
                  "fonte": (_S, 160, False)},
    "ag_importar": {"limite": (int, 200, False)},
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ag_evento (
  id INTEGER PRIMARY KEY AUTOINCREMENT, categoria TEXT NOT NULL, titulo TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '',
  inicio TEXT NOT NULL DEFAULT '', fim TEXT NOT NULL DEFAULT '', modalidade TEXT NOT NULL DEFAULT '', local TEXT NOT NULL DEFAULT '',
  link TEXT NOT NULL DEFAULT '', fonte TEXT NOT NULL DEFAULT '', origem TEXT NOT NULL, ref_coletor TEXT,
  estado TEXT NOT NULL DEFAULT 'sugerido', motivo TEXT NOT NULL DEFAULT '', criado_por TEXT NOT NULL, criado REAL NOT NULL,
  moderado_por TEXT NOT NULL DEFAULT '', moderado_em REAL);
CREATE UNIQUE INDEX IF NOT EXISTS ag_evento_coletor ON ag_evento(ref_coletor) WHERE ref_coletor IS NOT NULL;
"""


def _texto(v, n: int) -> str:
    return str(v or "").strip()[:n]


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def classificar(titulo: str, resumo: str = "") -> str | None:
    """Tipo de oportunidade pelo texto (ou None quando não é de nenhum dos quatro tipos mapeados)."""
    t = " " + _sem_acento(f"{titulo} {resumo}") + " "
    for cat, palavras in PALAVRAS:
        if any(p in t for p in palavras):
            return cat
    return None


def _eh_equipe(quem: dict | None) -> bool:
    return bool(quem) and seg.pode(quem, seg.EQUIPE)


class Agenda:
    def __init__(self, hub, relogio=None, hoje=None):
        self.hub = hub
        self.relogio = relogio or hub.relogio
        self.hoje = hoje or (lambda: time.strftime("%Y-%m-%d", time.localtime(self.relogio())))
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    COLS = ("id", "categoria", "titulo", "descricao", "inicio", "fim", "modalidade", "local", "link", "fonte", "origem",
            "estado", "motivo", "criado")

    def _linha(self, r) -> dict:
        d = dict(zip(self.COLS, r))
        d["categoria_nome"] = CATEGORIAS.get(d["categoria"], d["categoria"])
        d["categoria_nome_en"] = CATEGORIAS_EN.get(d["categoria"], d["categoria"])
        return d

    def _validar(self, d: dict) -> tuple[dict | None, str]:
        cat = _texto(d.get("categoria"), 30)
        if cat not in CATEGORIAS:
            return None, "tipo: " + ", ".join(CATEGORIAS)
        tit = _texto(d.get("titulo"), 200)
        if len(tit) < 4:
            return None, "escreva o título"
        ini, fim = _texto(d.get("inicio"), 10), _texto(d.get("fim"), 10)
        for v in (ini, fim):
            if v and not _DATA.fullmatch(v):
                return None, "data no formato AAAA-MM-DD"
        if ini and fim and fim < ini:
            return None, "o fim vem antes do início"
        link = _texto(d.get("link"), 500)
        if link and not link.startswith("https://"):
            return None, "o link precisa começar com https://"
        mod = _texto(d.get("modalidade"), 12)
        if mod not in MODALIDADES:
            return None, "modalidade: online, presencial ou hibrido"
        return {"categoria": cat, "titulo": tit, "descricao": _texto(d.get("descricao"), 2000), "inicio": ini, "fim": fim or ini,
                "modalidade": mod, "local": _texto(d.get("local"), 160), "link": link, "fonte": _texto(d.get("fonte"), 160)}, ""

    def _inserir(self, v: dict, origem: str, estado: str, quem: str, ref: str | None = None) -> int:
        cur = self._db.execute("INSERT INTO ag_evento(categoria,titulo,descricao,inicio,fim,modalidade,local,link,fonte,origem,ref_coletor,"
                               "estado,criado_por,criado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (v["categoria"], v["titulo"], v["descricao"], v["inicio"], v["fim"], v["modalidade"], v["local"],
                                v["link"], v["fonte"], origem, ref, estado, quem, self.relogio()))
        return cur.lastrowid

    # ── leitura ──────────────────────────────────────────────────────────────────────────────────
    def publicos(self, categoria: str = "", passados: bool = False) -> dict:
        """Publicados; por padrão só os que ainda não terminaram (ou sem data). Ordem: data, depois sem data."""
        hoje = self.hoje()
        q, a = "SELECT " + ",".join(self.COLS) + " FROM ag_evento WHERE estado='publicado'", []
        if categoria:
            if categoria not in CATEGORIAS:
                return {"ok": False, "erro": "tipo: " + ", ".join(CATEGORIAS), "codigo": 404}
            q, a = q + " AND categoria=?", [categoria]
        if not passados:
            q, a = q + " AND (fim='' OR fim>=?)", a + [hoje]
        q += " ORDER BY (inicio=''), inicio, id"
        itens = [self._linha(r) for r in self._db.execute(q, a)]
        for i in itens:
            i.pop("motivo", None)
        return {"ok": True, "itens": itens, "categorias": [{"id": k, "nome": v, "nome_en": CATEGORIAS_EN[k]} for k, v in CATEGORIAS.items()]}

    def todos(self, quem: dict) -> dict:
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe", "codigo": 403}
        return {"ok": True, "itens": [self._linha(r) for r in self._db.execute("SELECT " + ",".join(self.COLS) + " FROM ag_evento ORDER BY criado DESC")]}

    # ── escrita ──────────────────────────────────────────────────────────────────────────────────
    def criar(self, d: dict, quem: dict) -> dict:
        """Equipe: publica direto (é a própria moderação)."""
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe cadastra; participantes sugerem", "codigo": 403}
        v, erro = self._validar(d)
        if not v:
            return {"ok": False, "erro": erro}
        with self.hub._trava:
            i = self._inserir(v, "equipe", "publicado", quem["usuario"])
            self.hub.registrar("agenda", quem["usuario"], {"o_que": "evento publicado", "id": i, "categoria": v["categoria"]})
            self._db.commit()
        return {"ok": True, "id": i, "estado": "publicado"}

    def sugerir(self, d: dict, quem: dict, pode_publicar) -> dict:
        """Participante: entra como sugerido (fila de moderação)."""
        ok, motivo = pode_publicar(quem)
        if not ok:
            return {"ok": False, "erro": motivo}
        v, erro = self._validar(d)
        if not v:
            return {"ok": False, "erro": erro}
        with self.hub._trava:
            i = self._inserir(v, "participante", "sugerido", quem["usuario"])
            self.hub.registrar("agenda", quem["usuario"], {"o_que": "evento sugerido", "id": i})
            self._db.commit()
        return {"ok": True, "id": i, "estado": "sugerido", "aviso": "Recebido. Aparece na agenda depois da moderação da equipe."}

    def importar(self, itens_coletor: list[dict], quem: dict, limite: int = 100) -> dict:
        """Equipe: traz do coletor de eventos (editais.py) só o que é de um dos quatro tipos; entra como sugerido.
        O mesmo item do coletor nunca entra duas vezes (ref_coletor único)."""
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe", "codigo": 403}
        novos, ignorados, repetidos = 0, 0, 0
        with self.hub._trava:
            for it in (itens_coletor or [])[:max(1, min(int(limite or 100), 200))]:
                cat = classificar(str(it.get("titulo") or ""), str(it.get("resumo") or ""))
                if not cat:
                    ignorados += 1
                    continue
                ref = _texto(it.get("id"), 120) or None
                if ref and self._db.execute("SELECT 1 FROM ag_evento WHERE ref_coletor=?", (ref,)).fetchone():
                    repetidos += 1
                    continue
                datas = [x.get("data") for x in (it.get("datas") or []) if isinstance(x, dict) and _DATA.fullmatch(str(x.get("data") or ""))]
                link = _texto(it.get("link"), 500)
                v = {"categoria": cat, "titulo": _texto(it.get("titulo"), 200) or "(sem título)", "descricao": _texto(it.get("resumo"), 2000),
                     "inicio": min(datas) if datas else "", "fim": max(datas) if datas else "", "modalidade": "", "local": "",
                     "link": link if link.startswith("https://") else "", "fonte": _texto(it.get("fonteNome") or it.get("fonte"), 160)}
                self._inserir(v, "coletor", "sugerido", quem["usuario"], ref)
                novos += 1
            if novos:
                self.hub.registrar("agenda", quem["usuario"], {"o_que": "importado do coletor", "novos": novos})
            self._db.commit()
        return {"ok": True, "novos": novos, "fora_dos_tipos": ignorados, "repetidos": repetidos}

    # ── moderação (a fila única fica em comunidade.py) ──────────────────────────────────────────
    def pendentes(self) -> list[dict]:
        return [{"tipo": "evento", "id": r[0], "titulo": r[2], "texto": r[3], "categoria": r[1], "origem": r[4], "inicio": r[5],
                 "link": r[6], "criado": r[7]}
                for r in self._db.execute("SELECT id, categoria, titulo, descricao, origem, inicio, link, criado FROM ag_evento "
                                          "WHERE estado='sugerido' ORDER BY criado")]

    def decidir(self, ident: int, decisao: str, motivo: str, quem: dict) -> dict:
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe modera", "codigo": 403}
        novo = {"aprovar": "publicado", "recusar": "recusado"}.get(decisao)
        if not novo:
            return {"ok": False, "erro": "decisão: aprovar ou recusar"}
        with self.hub._trava:
            n = self._db.execute("UPDATE ag_evento SET estado=?, motivo=?, moderado_por=?, moderado_em=? WHERE id=? AND estado='sugerido'",
                                 (novo, _texto(motivo, 400), quem["usuario"], self.relogio(), int(ident))).rowcount
            if n:
                self.hub.registrar("agenda", quem["usuario"], {"o_que": "moderação", "id": int(ident), "decisao": decisao})
            self._db.commit()
        return {"ok": n > 0, **({} if n else {"erro": "item não encontrado ou já decidido", "codigo": 404})}

    def arquivar(self, ident: int, quem: dict) -> dict:
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe", "codigo": 403}
        with self.hub._trava:
            n = self._db.execute("UPDATE ag_evento SET estado='arquivado' WHERE id=? AND estado='publicado'", (int(ident),)).rowcount
            self._db.commit()
        return {"ok": n > 0}
