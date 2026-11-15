"""Editais, eventos e e-mails escritos na Gestão (15/11/2026).

O que faz, em palavras simples:
1. Editais: o servidor da Physis lê páginas PÚBLICAS de fomento (FINEP, BNDES, CNPq, FAPs, Prosas,
   Fundo Clima, fundos internacionais...), em RSS ou HTML, e guarda o resultado num arquivo (cache).
   A Gestão pede a lista ao servidor; ninguém da equipe precisa abrir site por site.
2. Eventos: o mesmo mecanismo, com outra lista de fontes (agendas de eventos e feiras).
3. E-mails: a tela "E-mails" da Gestão escreve um e-mail novo e ele entra na MESMA fila de saída
   (tabela email_saida) que já existe. Sai pelo servidor de e-mail da Physis, se estiver configurado;
   sem ele, fica pendente para a equipe copiar e marcar como enviado, como os outros.

Desenho:
- Cada fonte é um registro (Fonte). O jeito de ler cada formato é uma função em INTERPRETES:
  dá para acrescentar um formato novo (por exemplo, uma API em JSON) sem mexer no resto.
- A rede é uma função passada de fora (`abrir`). Nos testes, ela é trocada por uma falsa: nada sai
  para a internet.
- Nenhuma inteligência artificial externa: a relevância é uma regra simples por palavras das áreas
  da Physis. O servidor de IA local pode entrar depois (ver `GANCHO_IA`).
- Os endereços padrão são páginas públicas conhecidas, mas sites mudam: cada fonte tem `conferir=True`
  até a equipe confirmar que o endereço ainda lista editais. Fonte que falha não derruba as outras.

Só a biblioteca padrão do Python.
"""
from __future__ import annotations

import datetime
import hashlib
import html as html_mod
import ipaddress
import json
import os
import re
import threading
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

# Quem vê os editais (decisão de 14/11/2026: Rafaella, Erick e Marzia). Pode ser trocado no servidor
# pela variável PHYSIS_EDITAIS_ACESSO="rafaella,ericklopes,marzia" (ids das pessoas da equipe).
ACESSO_PADRAO = ("rafaella", "ericklopes", "marzia")

LIMITE_BYTES = 2_000_000        # página maior que isso é cortada
TEMPO_S = 10                    # cada fonte tem até 10 s
VALIDADE_S = 6 * 3600           # a lista guardada vale 6 horas; depois disso, busca de novo
MAX_ITENS_FONTE = 80
MAX_FONTES_EXTRAS = 40

# Áreas da Physis e as palavras que as indicam (sem acento, minúsculas; pedaço de palavra vale).
AREAS = {
    "energia": ["energia", "solar", "fotovolt", "eficiencia energetica", "renovave", "hidrogenio", "energy", "photovolt", "renewable"],
    "agua": ["agua", "saneamento", "hidric", "irrigac", "efluente", "water", "sanitation"],
    "clima": ["clima", "climat", "carbono", "carbon", "emiss", "descarbon", "net zero", "adaptac", "mitigac", "resilien"],
    "agro": ["agro", "rural", "agricult", "agrofloresta", "bioeconomia", "pecuar", "agri", "farm"],
    "inovacao": ["inovac", "tecnolog", "startup", "p&d", "pd&i", "iot", "sensor", "automac", "digital", "innovation", "technology"],
    "sustentabilidade": ["sustentab", "ambient", "residuo", "economia circular", "esg", "biodivers", "sustainab", "circular", "environment"],
    "construcao": ["edificac", "construc", "climatizac", "avac", "hvac", "building", "cidades"],
    "capacitacao": ["capacitac", "curso", "formacao", "treinamento", "training", "educac"],
}
MARCAS = {
    "edital": ["edital", "editais", "chamada", "chamamento", "selecao publica", "call for", "funding", "grant", "premio", "programa", "convocatoria", "tender"],
    "evento": ["evento", "congresso", "feira", "seminario", "forum", "summit", "conference", "conferencia", "expo", "workshop", "webinar", "encontro", "simposio", "week", "semana"],
}

# Gancho para o servidor de IA local (4 GPUs no destino). Hoje é None: a relevância é só a regra de palavras.
# Quando o servidor de IA existir, basta apontar para uma função f(item: dict) -> dict com {"resumo", "relevancia"}.
GANCHO_IA: Callable[[dict], dict] | None = None


@dataclass(frozen=True)
class Fonte:
    id: str
    nome: str
    url: str
    formato: str = "html"          # "rss" ou "html" (ou outro registrado em INTERPRETES)
    tipo: str = "edital"           # "edital" ou "evento"
    grupo: str = ""                # FINEP, BNDES, CNPq, FAPs, Prosas, Fundo Clima, Internacional...
    pais: str = "BR"
    conferir: bool = True          # endereço ainda não conferido pela equipe
    filtro: str = ""               # expressão extra que o endereço do link precisa ter (só HTML)
    extra: bool = False            # acrescentada pela equipe (pode ser removida)


# Fontes padrão. São páginas públicas; todas com conferir=True até a equipe olhar uma vez.
FONTES_EDITAIS = [
    Fonte("finep", "FINEP · chamadas públicas abertas", "http://www.finep.gov.br/chamadas-publicas?situacao=aberta", "html", grupo="FINEP", filtro=r"chamada"),
    Fonte("bndes", "BNDES · chamadas públicas", "https://www.bndes.gov.br/wps/portal/site/home/onde-atuamos/chamadas-publicas", "html", grupo="BNDES"),
    Fonte("fundo-clima", "Fundo Clima (BNDES)", "https://www.bndes.gov.br/wps/portal/site/home/financiamento/produto/fundo-clima", "html", grupo="Fundo Clima"),
    Fonte("cnpq", "CNPq · chamadas abertas", "https://www.gov.br/cnpq/pt-br/chamadas/abertas-para-submissao", "html", grupo="CNPq"),
    Fonte("faperj", "FAPERJ · editais", "https://www.faperj.br/?id=28.5.7", "html", grupo="FAPs"),
    Fonte("fapesp", "FAPESP · chamadas", "https://fapesp.br/chamadas/", "html", grupo="FAPs"),
    Fonte("fapemig", "FAPEMIG · chamadas abertas", "https://fapemig.br/pt/chamadas_abertas_fapemig/", "html", grupo="FAPs"),
    Fonte("fapdf", "FAPDF · editais", "https://www.fap.df.gov.br/editais/", "html", grupo="FAPs"),
    Fonte("prosas", "Prosas · editais abertos", "https://prosas.com.br/editais", "html", grupo="Prosas", filtro=r"/editais/"),
    Fonte("embrapii", "EMBRAPII · chamadas", "https://embrapii.org.br/chamadas-publicas/", "html", grupo="Inovação"),
    Fonte("ue-horizonte", "União Europeia · Funding & Tenders", "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-proposals", "html", grupo="Internacional", pais="UE"),
    Fonte("bid", "BID (IDB) · chamadas", "https://www.iadb.org/en/how-we-can-work-together/calls-proposals", "html", grupo="Internacional", pais="INT"),
    Fonte("bid-lab", "BID Lab · oportunidades", "https://bidlab.org/en/calls-for-proposals", "html", grupo="Internacional", pais="INT"),
    Fonte("gcf", "Green Climate Fund · RFPs", "https://www.greenclimate.fund/about/procurement", "html", grupo="Internacional", pais="INT"),
]
FONTES_EVENTOS = [
    Fonte("sympla-sust", "Sympla · sustentabilidade", "https://www.sympla.com.br/eventos?s=sustentabilidade", "html", tipo="evento", grupo="Nacional"),
    Fonte("sympla-energia", "Sympla · energia solar", "https://www.sympla.com.br/eventos?s=energia%20solar", "html", tipo="evento", grupo="Nacional"),
    Fonte("eventbrite-clima", "Eventbrite · clima (Brasil)", "https://www.eventbrite.com.br/d/brazil/climate/", "html", tipo="evento", grupo="Nacional"),
    Fonte("abrava", "ABRAVA · agenda", "https://abrava.com.br/agenda/", "html", tipo="evento", grupo="Nacional"),
    Fonte("absolar", "ABSOLAR · eventos", "https://www.absolar.org.br/eventos/", "html", tipo="evento", grupo="Nacional"),
    Fonte("unfccc", "ONU Clima (UNFCCC) · calendário", "https://unfccc.int/calendar", "html", tipo="evento", grupo="Internacional", pais="INT"),
    Fonte("iea-eventos", "IEA · eventos", "https://www.iea.org/events", "html", tipo="evento", grupo="Internacional", pais="INT"),
]

MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
         "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
         "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
         "september": 9, "october": 10, "november": 11, "december": 12}
ROTULOS = [  # (pedaço de palavra perto da data, rótulo em português simples, é prazo de envio?)
    ("submiss", "Envio da proposta", True), ("inscri", "Inscrição", True), ("envio", "Envio da proposta", True),
    ("deadline", "Envio da proposta", True), ("encerr", "Prazo final", True), ("prazo", "Prazo final", True),
    ("ate ", "Prazo final", True), ("recurso", "Recursos", False), ("resultado", "Resultado", False),
    ("homolog", "Resultado", False), ("abertura", "Abertura", False), ("lancamento", "Abertura", False),
    ("publicac", "Publicação", False), ("contrat", "Contratação", False), ("inicio", "Início", False),
]


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn").lower()


def limpar_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", str(s or ""))
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html_mod.unescape(s)).strip()


def _iso(a: int, m: int, d: int) -> str:
    try:
        return datetime.date(a, m, d).isoformat() if 2000 <= a <= 2100 else ""
    except (ValueError, TypeError):
        return ""


_DATA_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b")
_DATA_PT = re.compile(r"\b(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})\b")
_DATA_EN1 = re.compile(r"\b(\d{1,2})\s+([a-z]+)\s+(\d{4})\b")
_DATA_EN2 = re.compile(r"\b([a-z]+)\s+(\d{1,2}),\s*(\d{4})\b")
_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def extrair_datas(texto: str) -> list[dict]:
    """Datas citadas no texto, com um rótulo tirado das palavras antes delas. Ordem do texto, sem repetir."""
    t = sem_acento(limpar_html(texto))
    achados: list[tuple[int, str]] = []
    for m in _DATA_NUM.finditer(t):
        a = int(m.group(3)); a = a + 2000 if a < 100 else a
        achados.append((m.start(), _iso(a, int(m.group(2)), int(m.group(1)))))
    for m in _DATA_PT.finditer(t):
        achados.append((m.start(), _iso(int(m.group(3)), MESES.get(m.group(2), 0), int(m.group(1)))))
    for m in _DATA_EN1.finditer(t):
        if m.group(2) in MESES:
            achados.append((m.start(), _iso(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))))
    for m in _DATA_EN2.finditer(t):
        if m.group(1) in MESES:
            achados.append((m.start(), _iso(int(m.group(3)), MESES[m.group(1)], int(m.group(2)))))
    for m in _DATA_ISO.finditer(t):
        achados.append((m.start(), _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
    out, vistos = [], set()
    for pos, iso in sorted(achados):
        if not iso:
            continue
        antes = t[max(0, pos - 70):pos]
        rotulo, envio, melhor = "Data citada", False, -1
        for chave, rot, e in ROTULOS:
            k = antes.rfind(chave)
            if k > melhor:
                melhor, rotulo, envio = k, rot, e
        if (iso, rotulo) in vistos:
            continue
        vistos.add((iso, rotulo))
        out.append({"rotulo": rotulo, "data": iso, "envio": envio})
    return out


def prazo_de(datas: list[dict]) -> str:
    """O prazo de envio: a última data marcada como envio; sem nenhuma, vazio (ninguém inventa prazo)."""
    envio = sorted(d["data"] for d in datas if d.get("envio"))
    return envio[-1] if envio else ""


def areas_de(texto: str) -> list[str]:
    t = sem_acento(texto)
    return [a for a, palavras in AREAS.items() if any(p in t for p in palavras)]


def relevancia(item: dict, hoje: str) -> int:
    """Regra simples e explicável: 10 pontos por área da Physis citada; +5 se o prazo ainda não passou;
    -20 se já passou. Sem área nenhuma, fica 0 (aparece só com o filtro 'todos')."""
    n = 10 * len(item.get("areas") or [])
    if not n:
        return 0
    p = item.get("prazo") or ""
    if p:
        n += 5 if p >= hoje else -20
    return max(0, n)


def _id(fonte: str, link: str, titulo: str) -> str:
    return hashlib.sha1(f"{fonte}|{link}|{titulo}".encode("utf-8")).hexdigest()[:16]


def _item(fonte: Fonte, titulo: str, link: str, resumo: str = "", publicado: str = "") -> dict:
    titulo, resumo = limpar_html(titulo)[:300], limpar_html(resumo)[:1500]
    datas = extrair_datas(titulo + " . " + resumo)
    return {"id": _id(fonte.id, link, titulo), "fonte": fonte.id, "fonteNome": fonte.nome, "grupo": fonte.grupo,
            "pais": fonte.pais, "tipo": fonte.tipo, "titulo": titulo, "link": link, "resumo": resumo,
            "publicado": publicado, "datas": datas, "prazo": prazo_de(datas), "areas": areas_de(titulo + " " + resumo)}


def ler_rss(texto: str, fonte: Fonte) -> list[dict]:
    """RSS 2.0 e Atom."""
    try:
        raiz = ET.fromstring(texto.encode("utf-8") if isinstance(texto, str) else texto)
    except ET.ParseError:
        return []
    out = []
    sem_ns = lambda tag: tag.rsplit("}", 1)[-1]
    for el in raiz.iter():
        if sem_ns(el.tag) not in ("item", "entry"):
            continue
        campos = {}
        for f in el:
            nome = sem_ns(f.tag)
            if nome == "link" and f.get("href"):
                campos.setdefault("link", f.get("href"))
            elif f.text:
                campos.setdefault(nome, f.text)
        link = (campos.get("link") or "").strip()
        titulo = campos.get("title") or ""
        if not titulo or not link.startswith(("http://", "https://")):
            continue
        out.append(_item(fonte, titulo, link, campos.get("description") or campos.get("summary") or campos.get("content") or "",
                         (campos.get("pubDate") or campos.get("updated") or campos.get("published") or "")[:40]))
    return out


_ANCORA = re.compile(r"""<a\b[^>]*?href\s*=\s*["']([^"'#][^"']*)["'][^>]*>(.*?)</a>""", re.I | re.S)


def ler_html(texto: str, fonte: Fonte) -> list[dict]:
    """Links da página cujo texto parece edital (ou evento). O texto ao redor entra como resumo (datas)."""
    marcas = MARCAS.get(fonte.tipo, MARCAS["edital"])
    filtro = re.compile(fonte.filtro, re.I) if fonte.filtro else None
    out, vistos = [], set()
    for m in _ANCORA.finditer(texto):
        href, rotulo = html_mod.unescape(m.group(1).strip()), limpar_html(m.group(2))
        if len(rotulo) < 12:
            continue
        link = urljoin(fonte.url, href)
        if not link.startswith(("http://", "https://")) or link in vistos:
            continue
        if filtro and not filtro.search(link) and not filtro.search(rotulo):
            continue
        if not any(p in sem_acento(rotulo) for p in marcas):
            continue
        vistos.add(link)
        perto = limpar_html(texto[m.end():m.end() + 600])[:400]
        out.append(_item(fonte, rotulo, link, perto))
        if len(out) >= MAX_ITENS_FONTE:
            break
    return out


INTERPRETES: dict[str, Callable[[str, Fonte], list[dict]]] = {"rss": ler_rss, "html": ler_html}


def registrar_interprete(formato: str, funcao: Callable[[str, Fonte], list[dict]]) -> None:
    """Formato novo (por exemplo, a API em JSON de um portal): uma função texto -> itens."""
    INTERPRETES[formato] = funcao


def endereco_publico(url: str) -> bool:
    """Só http(s) para nomes ou IPs públicos: uma fonte acrescentada não pode apontar para a rede interna."""
    try:
        u = urlparse(url)
    except ValueError:
        return False
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    h = u.hostname.lower()
    if h == "localhost" or h.endswith((".local", ".localhost", ".internal", ".lan")):
        return False
    try:
        ip = ipaddress.ip_address(h)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    except ValueError:
        return "." in h


def abrir_url(url: str, tempo: float = TEMPO_S, limite: int = LIMITE_BYTES) -> str:
    """Baixa uma página pública. Só http(s); corta em `limite` bytes."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("so http ou https")
    pedido = urllib.request.Request(url, headers={"User-Agent": "PhysisHub/0.1 (lista de editais e eventos)",
                                                  "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(pedido, timeout=tempo) as r:          # noqa: S310 (endereço conferido acima)
        dados = r.read(limite)
        cs = r.headers.get_content_charset() or "utf-8"
    try:
        return dados.decode(cs, errors="replace")
    except LookupError:
        return dados.decode("utf-8", errors="replace")


class Coletor:
    """Busca, junta e guarda (cache em arquivo JSON) os itens de um conjunto de fontes."""

    def __init__(self, pasta: str | Path, tipo: str = "edital", fontes: list[Fonte] | None = None,
                 abrir: Callable[[str], str] | None = None, relogio: Callable[[], float] = time.time,
                 validade_s: float = VALIDADE_S):
        self.tipo = tipo
        self.pasta = Path(pasta)
        nome = {"edital": "editais", "evento": "eventos"}.get(tipo, tipo)
        self.arq = self.pasta / f"{nome}-cache.json"
        self.arq_fontes = self.pasta / f"{nome}-fontes.json"
        self._padrao = list(fontes if fontes is not None else (FONTES_EVENTOS if tipo == "evento" else FONTES_EDITAIS))
        self._abrir = abrir or abrir_url
        self.relogio = relogio
        self.validade_s = validade_s
        self._trava = threading.Lock()

    # ── arquivos ──
    def _ler(self, arq: Path, padrao):
        try:
            return json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return padrao

    def _gravar(self, arq: Path, dados) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, arq)

    # ── fontes ──
    def fontes(self) -> list[Fonte]:
        extras = []
        for d in self._ler(self.arq_fontes, []):
            try:
                extras.append(Fonte(**{**d, "extra": True, "tipo": self.tipo}))
            except TypeError:
                continue
        return self._padrao + extras

    def acrescentar_fonte(self, d: dict) -> dict:
        nome = str(d.get("nome") or "").strip()[:120]
        url = str(d.get("url") or "").strip()[:500]
        formato = str(d.get("formato") or "html")
        if not nome or not endereco_publico(url):
            return {"ok": False, "erro": "informe o nome e um endereço público (http ou https)"}
        if formato not in INTERPRETES:
            return {"ok": False, "erro": "formato desconhecido: use html ou rss"}
        with self._trava:
            extras = self._ler(self.arq_fontes, [])
            if len(extras) >= MAX_FONTES_EXTRAS:
                return {"ok": False, "erro": "limite de fontes acrescentadas"}
            ident = "x-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
            if any(f.id == ident for f in self.fontes()):
                return {"ok": False, "erro": "essa fonte já está na lista"}
            extras.append({"id": ident, "nome": nome, "url": url, "formato": formato,
                           "grupo": str(d.get("grupo") or "Outras")[:40], "pais": str(d.get("pais") or "BR")[:8], "conferir": False})
            self._gravar(self.arq_fontes, extras)
        return {"ok": True, "id": ident}

    def remover_fonte(self, ident: str) -> dict:
        with self._trava:
            extras = self._ler(self.arq_fontes, [])
            fica = [f for f in extras if f.get("id") != ident]
            if len(fica) == len(extras):
                return {"ok": False, "erro": "só dá para remover fonte acrescentada pela equipe"}
            self._gravar(self.arq_fontes, fica)
        return {"ok": True}

    # ── busca ──
    def ler_cache(self) -> dict:
        c = self._ler(self.arq, {})
        return {"ok": True, "tipo": self.tipo, "atualizado": c.get("atualizado", 0), "itens": c.get("itens", []),
                "fontes": c.get("fontes", []), "lista_fontes": [asdict(f) for f in self.fontes()]}

    def _uma(self, fonte: Fonte) -> tuple[Fonte, list[dict], str]:
        try:
            ler = INTERPRETES.get(fonte.formato)
            if not ler:
                return fonte, [], "formato desconhecido"
            return fonte, ler(self._abrir(fonte.url), fonte)[:MAX_ITENS_FONTE], ""
        except Exception as e:                      # uma fonte fora do ar não derruba as outras
            return fonte, [], (type(e).__name__ + ": " + str(e))[:200]

    def buscar(self, forcar: bool = False) -> dict:
        agora = self.relogio()
        antes = self._ler(self.arq, {})
        if not forcar and antes.get("atualizado") and agora - antes["atualizado"] < self.validade_s:
            r = self.ler_cache(); r["do_cache"] = True
            return r
        fontes = self.fontes()
        with ThreadPoolExecutor(max_workers=6) as ex:
            resultados = list(ex.map(self._uma, fontes))
        hoje = time.strftime("%Y-%m-%d", time.localtime(agora))
        primeira = {i["id"]: i.get("visto_em", agora) for i in antes.get("itens", [])}
        itens, estado = {}, []
        for fonte, lista, erro in resultados:
            estado.append({"id": fonte.id, "nome": fonte.nome, "ok": not erro, "erro": erro, "n": len(lista)})
            for it in lista:
                it["visto_em"] = primeira.get(it["id"], agora)
                it["novo"] = it["id"] not in primeira
                it["relevancia"] = relevancia(it, hoje)
                if GANCHO_IA:
                    try:
                        it.update({k: v for k, v in (GANCHO_IA(dict(it)) or {}).items() if k in ("resumo", "relevancia")})
                    except Exception:
                        pass
                itens[it["id"]] = it
        # itens que a fonte deixou de listar somem; quem já foi aceito fica guardado na Gestão (navegador e servidor)
        lista = sorted(itens.values(), key=lambda i: (-i.get("relevancia", 0), i.get("prazo") or "9999"))
        with self._trava:
            self._gravar(self.arq, {"atualizado": agora, "itens": lista, "fontes": estado})
        r = self.ler_cache(); r["do_cache"] = False
        return r


# ── Quem pode o quê ──
def acesso_editais() -> tuple[str, ...]:
    v = os.environ.get("PHYSIS_EDITAIS_ACESSO")
    return tuple(x.strip() for x in v.split(",") if x.strip()) if v else ACESSO_PADRAO


def pode_editais(conta: dict | None) -> bool:
    return bool(conta) and (conta.get("pessoa") or "") in acesso_editais()


# ── E-mail escrito na Gestão: entra na fila de saída que já existe ──
_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def enfileirar_email(hub, para: str, assunto: str, corpo: str, quem: str = "") -> dict:
    enderecos = [x.strip() for x in re.split(r"[,;]", str(para or "")) if x.strip()]
    if not enderecos or len(enderecos) > 10 or not all(_EMAIL.match(x) for x in enderecos):
        return {"ok": False, "erro": "confira o endereço (até 10, separados por vírgula)"}
    assunto = re.sub(r"[\r\n]+", " ", str(assunto or "")).strip()[:200]
    corpo = str(corpo or "")
    if not assunto or not corpo.strip():
        return {"ok": False, "erro": "o e-mail precisa de assunto e de texto"}
    if len(corpo) > 20000:
        return {"ok": False, "erro": "texto grande demais (até 20 mil letras)"}
    ref = "G-" + hashlib.sha1(f"{time.time()}|{para}|{assunto}|{os.urandom(4).hex()}".encode()).hexdigest()[:10].upper()
    with hub._trava:
        cur = hub._db.execute("INSERT INTO email_saida(para,assunto,corpo,estado,ref,criado) VALUES(?,?,?,?,?,?)",
                              (", ".join(enderecos), assunto, corpo, "pendente", ref, hub.relogio()))
        ident = cur.lastrowid
        hub.registrar("email", ref, {"o_que": "escrito na gestao", "por": quem, "id": ident})
        hub._db.commit()
    return {"ok": True, "id": ident, "ref": ref}


# ── Rotas: o servidor chama rota(...) e, se vier resposta, devolve (código, json) ──
def rota(metodo: str, caminho: str, conta: dict | None, corpo: str | None, editais: Coletor, eventos: Coletor,
         hub=None, correio_mod=None) -> tuple[int, dict] | None:
    eh_editais = caminho == "/api/editais" or caminho.startswith("/api/editais/")
    eh_eventos = caminho == "/api/eventos" or caminho.startswith("/api/eventos/")
    eh_correio = caminho == "/api/gestao/correio"
    if not (eh_editais or eh_eventos or eh_correio):
        return None
    if not conta:
        return 401, {"ok": False, "erro": "entre com usuario e senha", "login": True}
    if eh_editais and not pode_editais(conta):
        return 403, {"ok": False, "erro": "os editais são só de " + ", ".join(acesso_editais())}
    if metodo == "POST" and corpo is None:          # o servidor devolve None quando o corpo passa do limite
        return 413, {"ok": False, "erro": "pedido grande demais"}
    try:
        d = json.loads(corpo or "{}") if metodo == "POST" else {}
    except ValueError:
        return 400, {"ok": False, "erro": "json invalido"}
    if not isinstance(d, dict):
        return 400, {"ok": False, "erro": "json invalido"}
    if eh_correio:
        if metodo != "POST" or hub is None:
            return 405, {"ok": False, "erro": "use POST"}
        r = enfileirar_email(hub, d.get("para", ""), d.get("assunto", ""), d.get("corpo", ""), conta.get("usuario", ""))
        if r["ok"]:
            r["servidor_email"] = bool(correio_mod and correio_mod.configurado())
            if r["servidor_email"]:
                threading.Thread(target=correio_mod.enviar_fila, args=(hub, r["ref"]), daemon=True).start()
        return (200 if r["ok"] else 400), r
    col = editais if eh_editais else eventos
    base = "/api/editais" if eh_editais else "/api/eventos"
    resto = caminho[len(base):]
    if resto == "" and metodo == "GET":
        return 200, col.ler_cache()
    if resto == "/buscar" and metodo == "POST":
        return 200, col.buscar(forcar=bool(d.get("forcar")))
    if resto == "/fontes" and metodo == "GET":
        return 200, {"ok": True, "fontes": [asdict(f) for f in col.fontes()]}
    if resto == "/fontes" and metodo == "POST":
        r = col.remover_fonte(str(d.get("remover"))) if d.get("remover") else col.acrescentar_fonte(d)
        return (200 if r["ok"] else 400), r
    return 404, {"ok": False, "erro": "rota desconhecida"}
