"""Previsão do tempo do lugar: várias fontes lado a lado e o sistema aprendendo qual acerta mais.

Por que no computador central e não na tela: a plataforma não chama nada de fora pelo navegador
(proteção contra vazamento de dados). Quem busca é o hub, que guarda tudo e continua mostrando a
última previsão quando a internet cai — marcada como desatualizada, como no receptor original.

Fontes:
  receptor   a previsão original do Monitoramento Verde (o receptor consulta sozinho e decide a
             irrigação); o hub só lê /api/estado e repassa a localização com /api/localizacao
  openmeteo  previsão por hora e por dia (chuva em mm, probabilidade, temperatura, evapotranspiração)
  inmet      previsão oficial por município (código IBGE), por período do dia
  cemaden    chuva que de fato caiu nos pluviômetros automáticos do município (observação, não previsão)
  physis     (fase 2) pluviômetro da Physis no lugar, pelo protocolo V6 — entra como observação

Aprendizado: cada previsão de "vai chover amanhã?" fica guardada; quando o dia passa, é comparada
com a chuva observada (pluviômetro da Physis, se houver, senão o CEMADEN mais próximo). A taxa de
acerto de cada fonte no lugar decide o peso dela na previsão combinada.

Consulta automática (15/11/2026): o laço `rodar` (classe Agendador) busca ao ligar, logo depois que o local muda no
Início/Planejador/Monitoramento e depois no ritmo de cada fonte, com espera crescente nos erros e sem passar dos limites
publicados (PISO_S). "Consultar agora" na tela continua valendo.

Os endereços das fontes podem ser trocados por variáveis de ambiente (PHYSIS_CLIMA_<FONTE>_URL),
porque serviços públicos mudam de endereço. Nenhuma chave fica no código.
"""
from __future__ import annotations

import gzip
import json
import os
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

FUSO = timezone(timedelta(hours=-3))
CHUVA_MM = 1.0              # a partir de quanto um dia conta como "choveu"
VALIDADE_S = {"receptor": 1.5 * 3600, "openmeteo": 6 * 3600, "inmet": 12 * 3600, "cemaden": 2 * 3600}
INTERVALO_S = {"receptor": 5 * 60, "openmeteo": 60 * 60, "inmet": 3 * 3600, "cemaden": 15 * 60}
# Ritmo das consultas automáticas (laço `rodar`, abaixo). Limites publicados pelas fontes:
#  - Open-Meteo (https://open-meteo.com/en/terms, lido em 15/11/2026): API gratuita com menos de 10.000 chamadas por dia,
#    5.000 por hora e 600 por minuto, e SÓ para uso não comercial. O hub faz 1 por hora (24 por dia) mais as de troca de
#    local, nunca mais de 1 a cada 10 min. Instalação de cliente pagante pode ser uso comercial: plano pago do Open-Meteo
#    ou servidor próprio (o código do Open-Meteo é aberto) [CONFERIR com o jurídico].
#  - INMET (apiprevmet3) e CEMADEN (getJson2.php): nenhum limite publicado encontrado [CONFERIR]; ritmo conservador.
# PISO_S: o menor espaço entre duas chamadas da mesma fonte, mesmo com troca de local ou erro (vale entre reinícios,
# pela hora da última consulta guardada). TETO_S: a maior espera depois de erros seguidos (espera dobra a cada erro).
PISO_S = {"receptor": 60, "openmeteo": 10 * 60, "inmet": 30 * 60, "cemaden": 10 * 60}
PISO_MUDANCA_S = 60         # local acabou de mudar: consulta já, mas não mais que 1 vez por minuto por fonte
TETO_S = {"receptor": 30 * 60, "openmeteo": 6 * 3600, "inmet": 12 * 3600, "cemaden": 2 * 3600}
FONTES_DO_LOCAL = ("openmeteo", "inmet", "cemaden")
SEM_LOCAL = "local não informado (preencha o CEP no Início)"
FALTA_MUNICIPIO = "falta município/UF (preencha o CEP no Início)"
IBGE_ESPERA_S = 6 * 3600     # município que o IBGE não achou: tenta de novo só depois disso
NOMES = {"receptor": "Receptor (previsão original)", "openmeteo": "Open-Meteo", "inmet": "INMET",
         "cemaden": "CEMADEN (chuva medida)", "physis": "Pluviômetro Physis"}
PALAVRAS_CHUVA = ("chuva", "chuvoso", "pancada", "trovoada", "garoa", "chuvisco", "tempestade")

URL = {
    "openmeteo": "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                 "&hourly=precipitation,precipitation_probability"
                 "&daily=precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min,"
                 "et0_fao_evapotranspiration&timezone=America%2FSao_Paulo&forecast_days=3",
    "inmet": "https://apiprevmet3.inmet.gov.br/previsao/{ibge}",
    # pluviômetros automáticos do CEMADEN por estado (o mesmo serviço do mapa interativo; conferido em 14/11/2026)
    "cemaden": "https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf={uf}",
    "ibge": "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios",
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS clima_local (id INTEGER PRIMARY KEY CHECK (id = 1), dados TEXT NOT NULL, atualizado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS clima_fonte (
  fonte TEXT PRIMARY KEY, dados TEXT NOT NULL, consultado REAL NOT NULL, erro TEXT NOT NULL DEFAULT '', erro_em REAL);
CREATE TABLE IF NOT EXISTS clima_aposta (
  fonte TEXT NOT NULL, dia TEXT NOT NULL, chove INTEGER NOT NULL, mm REAL, feita REAL NOT NULL,
  PRIMARY KEY (fonte, dia));
CREATE TABLE IF NOT EXISTS clima_observado (
  dia TEXT NOT NULL, origem TEXT NOT NULL, mm REAL NOT NULL, atualizado REAL NOT NULL, PRIMARY KEY (dia, origem));
"""


def observar_no_banco(db, dia: str, origem: str, mm: float, agora: float) -> None:
    """Grava a chuva medida no dia (sem commit). Usada por Clima.observar e pelo hub, quando chega a linha
    TIPO:PLUV (o pluviômetro do lugar, origem "physis", vale mais que o CEMADEN no placar e no modelo de chuva)."""
    db.execute("CREATE TABLE IF NOT EXISTS clima_observado (dia TEXT NOT NULL, origem TEXT NOT NULL, mm REAL NOT NULL, "
               "atualizado REAL NOT NULL, PRIMARY KEY (dia, origem))")
    db.execute("INSERT INTO clima_observado(dia,origem,mm,atualizado) VALUES(?,?,?,?) "
               "ON CONFLICT(dia,origem) DO UPDATE SET mm=excluded.mm, atualizado=excluded.atualizado",
               (dia, origem, float(mm), agora))


# quando conta a leitura: o TS do aparelho; sem relógio (ts=0), a hora de chegada
_T_CHUVA = "CASE WHEN m.ts > 0 THEN m.ts ELSE l.recebido END"


def chuva_do_periodo(db, ini: float, fim: float) -> tuple[float | None, int]:
    """(mm, pluviômetros) entre ini e fim: soma de cada pluviômetro e média entre eles. None = nenhuma leitura."""
    linhas = db.execute(f"SELECT m.ativo, SUM(m.valor) FROM medicao m JOIN leitura l ON l.seq = m.leitura "
                        f"WHERE m.grandeza='chuva' AND {_T_CHUVA} >= ? AND {_T_CHUVA} < ? GROUP BY m.ativo", (ini, fim)).fetchall()
    if not linhas:
        return None, 0
    return round(sum(s for _, s in linhas) / len(linhas), 2), len(linhas)


def chuva_medida_local(db, agora: float, validade_s: float = 3 * 3600) -> dict | None:
    """Chuva medida no lugar (pluviômetro Physis) no mesmo formato do CEMADEN ({mm_24h, mm_72h, estacao}).
    None quando não há pluviômetro ou ele não fala há mais de validade_s (aí vale o CEMADEN)."""
    try:
        ultima = db.execute(f"SELECT MAX({_T_CHUVA}) FROM medicao m JOIN leitura l ON l.seq = m.leitura "
                            "WHERE m.grandeza='chuva'").fetchone()[0]
    except Exception:          # noqa: BLE001 — banco sem as tabelas de leitura (ex.: só o clima)
        return None
    if not ultima or agora - ultima > validade_s:
        return None
    mm24, n = chuva_do_periodo(db, agora - 86400, agora + 1)
    mm72, _ = chuva_do_periodo(db, agora - 3 * 86400, agora + 1)
    return {"mm_24h": mm24 or 0.0, "mm_72h": mm72 or 0.0, "pluviometros": n, "ultima": ultima,
            "estacao": {"nome": NOMES["physis"], "codigo": "physis"}}


def _url(fonte: str) -> str:
    return os.environ.get(f"PHYSIS_CLIMA_{fonte.upper()}_URL") or URL[fonte]


def buscar_json(url: str, timeout: float = 15.0):
    """GET simples e devolve o JSON. Separado para os testes trocarem por dados gravados."""
    req = urllib.request.Request(url, headers={"User-Agent": "PhysisHub/1.0", "Accept": "application/json",
                                              "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        corpo = r.read()
        if r.headers.get("Content-Encoding", "").lower() == "gzip" or corpo[:2] == b"\x1f\x8b":
            corpo = gzip.decompress(corpo)          # o IBGE responde compactado mesmo sem pedir
        return json.loads(corpo.decode("utf-8", errors="replace"))


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower().strip()


def validar_local(d: dict) -> tuple[dict | None, str]:
    """Confere e limpa a localização. Só aceita pontos dentro do Brasil (como o receptor original)."""
    try:
        lat, lon = float(d.get("lat")), float(d.get("lon"))
    except (TypeError, ValueError):
        return None, "latitude e longitude são obrigatórias (números, ex.: -22.5050 e -43.1830)"
    if not (-35.0 <= lat <= 6.0 and -75.0 <= lon <= -28.0):
        return None, "coordenadas fora do Brasil (latitude de -35 a 6, longitude de -75 a -28)"
    uf = str(d.get("uf") or "").strip().upper()[:2]
    if uf and not uf.isalpha():
        return None, "UF inválida"
    ibge = str(d.get("ibge") or "").strip()
    if ibge and not (ibge.isdigit() and len(ibge) == 7):
        return None, "código IBGE do município tem 7 dígitos"
    return {"lat": round(lat, 5), "lon": round(lon, 5), "municipio": str(d.get("municipio") or "").strip()[:80],
            "uf": uf, "ibge": ibge, "cemaden_estacao": str(d.get("cemaden_estacao") or "").strip()[:80]}, ""


# ── Leitura de cada fonte (funções puras: recebem o JSON, devolvem o resumo) ─────────────────────
def ler_openmeteo(j: dict) -> dict:
    d = j.get("daily") or {}
    dias = []
    for i, dia in enumerate(d.get("time") or []):
        def v(k):
            lst = d.get(k) or []
            return lst[i] if i < len(lst) else None
        mm = v("precipitation_sum")
        dias.append({"dia": dia, "mm": mm, "prob": v("precipitation_probability_max"), "tmax": v("temperature_2m_max"),
                     "tmin": v("temperature_2m_min"), "et0": v("et0_fao_evapotranspiration"),
                     "chove": (mm or 0) >= CHUVA_MM})
    h = j.get("hourly") or {}
    agora = datetime.now(FUSO).strftime("%Y-%m-%dT%H")
    prox = [(t, p) for t, p in zip(h.get("time") or [], h.get("precipitation") or []) if t[:13] >= agora][:6]
    return {"dias": dias, "proximas_6h_mm": round(sum(p or 0 for _, p in prox), 1) if prox else None}


def ler_inmet(j: dict, ibge: str) -> dict:
    bloco = j.get(ibge) if isinstance(j, dict) else None
    if bloco is None and isinstance(j, dict) and len(j) == 1:
        bloco = next(iter(j.values()))
    dias = []
    for data, conteudo in (bloco or {}).items():
        try:
            dia = datetime.strptime(data, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
        periodos = [conteudo[k] for k in ("manha", "tarde", "noite") if isinstance(conteudo, dict) and isinstance(conteudo.get(k), dict)]
        if not periodos and isinstance(conteudo, dict):
            periodos = [conteudo]
        resumos = [str(p.get("resumo") or "") for p in periodos]
        tmax = [p.get("temp_max") for p in periodos if isinstance(p.get("temp_max"), (int, float))]
        tmin = [p.get("temp_min") for p in periodos if isinstance(p.get("temp_min"), (int, float))]
        texto = " · ".join(r for r in resumos if r)
        dias.append({"dia": dia, "resumo": texto, "tmax": max(tmax) if tmax else None, "tmin": min(tmin) if tmin else None,
                     "chove": any(p in _sem_acento(texto) for p in PALAVRAS_CHUVA)})
    dias.sort(key=lambda x: x["dia"])
    return {"dias": dias}


def _quando_cemaden(txt) -> datetime | None:
    try:
        return datetime.strptime(str(txt), "%d/%m/%y %H:%M").replace(tzinfo=timezone.utc)   # o serviço informa em UTC
    except ValueError:
        return None


def ler_cemaden(j, loc: dict, agora: float | None = None) -> dict:
    """Pluviômetros do município do lugar (pelo código IBGE).

    O serviço não traz coordenadas das estações; por isso a escolha é pelo município, e só valem as
    estações que mandaram dado nas últimas 3 horas. Nelas, "-" quer dizer que não choveu na janela.
    Se a pessoa escolheu uma estação (campo cemaden_estacao), vale ela; senão, a maior chuva das ativas
    (para alerta, é melhor não subestimar)."""
    lista = j if isinstance(j, list) else []
    agora_dt = datetime.fromtimestamp(agora if agora is not None else time.time(), timezone.utc)
    ibge, preferida = str(loc.get("ibge") or ""), _sem_acento(loc.get("cemaden_estacao") or "")
    do_municipio = [e for e in lista if str(e.get("codibge")) == ibge] if ibge else []
    if not do_municipio:
        return {"estacao": None, "aviso": "nenhum pluviômetro do CEMADEN neste município" if ibge else "falta o código IBGE do município"}
    ativas = []
    for e in do_municipio:
        t = _quando_cemaden(e.get("datahoraUltimovalor"))
        if t and agora_dt - t <= timedelta(hours=3):
            ativas.append(e)
    if not ativas:
        return {"estacao": None, "aviso": f"os {len(do_municipio)} pluviômetros do CEMADEN no município estão sem dado recente"}
    def n(e, k):
        v = e.get(k)
        if v in ("-", "", None):
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    escolhida = next((e for e in ativas if preferida and _sem_acento(e.get("nomeestacao", "")) == preferida), None)
    if escolhida is None:
        escolhida = max(ativas, key=lambda e: n(e, "acc24hr") or 0.0)
    return {"estacao": {"nome": escolhida.get("nomeestacao"), "cidade": escolhida.get("cidade"), "km": None},
            "ativas": len(ativas), "no_municipio": len(do_municipio),
            "estacoes": sorted(e.get("nomeestacao", "") for e in ativas),
            "mm_1h": n(escolhida, "acc1hr"), "mm_24h": n(escolhida, "acc24hr"), "mm_72h": n(escolhida, "acc72hr")}


def ler_receptor(j: dict) -> dict:
    c = (j or {}).get("clima") or {}
    return {"chuva": bool(c.get("chuva")), "intensidade": c.get("intens"), "mm_h": c.get("precip"),
            "valido": bool(c.get("valido")), "hora": c.get("hora")}


class Clima:
    """Guarda a localização, as consultas de cada fonte e o placar de acertos."""

    def __init__(self, hub, buscar=buscar_json, receptor_url: str | None = None, enviar_local=None):
        self.hub, self.buscar = hub, buscar
        self.receptor_url = (receptor_url or "").rstrip("/") or None
        self.enviar_local = enviar_local        # função(lat, lon) -> (ok, detalhe); None = sem receptor
        self._ibge: dict[tuple[str, str], tuple[str, float]] = {}   # (município, UF) -> (código ou "", quando)
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    def _agora(self) -> float:
        return self.hub.relogio()

    # ── Localização ──────────────────────────────────────────────────────────────────────────
    def local(self) -> dict | None:
        """O local do cliente pela função única do hub (hub.local_da_instalacao: Planejador > Início > Monitoramento >
        instancia.json). Sem coordenadas, None ("local não informado"): nenhuma fonte é consultada com ponto padrão."""
        achar = getattr(self.hub, "local_da_instalacao", None)
        if achar:
            loc = achar()
            return loc if loc.get("lat") is not None else None
        r = self._db.execute("SELECT dados FROM clima_local WHERE id=1").fetchone()
        return json.loads(r[0]) if r else None

    def definir_local(self, d: dict, por: str = "") -> dict:
        loc, erro = validar_local(d)
        if not loc:
            return {"ok": False, "erro": erro}
        if not loc["ibge"] and loc["municipio"] and loc["uf"]:
            loc["ibge"] = self.achar_ibge(loc["municipio"], loc["uf"]) or ""
        with self.hub._trava:
            self._db.execute("INSERT INTO clima_local(id,dados,atualizado) VALUES(1,?,?) "
                             "ON CONFLICT(id) DO UPDATE SET dados=excluded.dados, atualizado=excluded.atualizado",
                             (json.dumps(loc, ensure_ascii=False), self._agora()))
            self._db.execute("DELETE FROM clima_fonte WHERE fonte IN ('openmeteo','inmet','cemaden')")
            self._db.commit()
        self.hub.registrar("local", por or "plataforma", loc)
        r = {"ok": True, "local": loc, "receptor": None}
        if self.enviar_local:
            ok, det = self.enviar_local(loc["lat"], loc["lon"])
            r["receptor"] = {"ok": ok, "detalhe": det}
        return r

    def achar_ibge(self, municipio: str, uf: str) -> str | None:
        try:
            lista = self.buscar(_url("ibge").format(uf=urllib.parse.quote(uf)))
        except (urllib.error.URLError, OSError, ValueError):
            return None
        alvo = _sem_acento(municipio)
        for m in lista if isinstance(lista, list) else []:
            if _sem_acento(m.get("nome", "")) == alvo:
                return str(m.get("id"))
        return None

    # ── Consultas ───────────────────────────────────────────────────────────────────────────
    def _guardar(self, fonte: str, dados: dict | None, erro: str = "") -> None:
        agora = self._agora()
        with self.hub._trava:
            if dados is not None:
                self._db.execute("INSERT INTO clima_fonte(fonte,dados,consultado,erro,erro_em) VALUES(?,?,?, '', NULL) "
                                 "ON CONFLICT(fonte) DO UPDATE SET dados=excluded.dados, consultado=excluded.consultado, erro='', erro_em=NULL",
                                 (fonte, json.dumps(dados, ensure_ascii=False), agora))
            else:   # mantém a última consulta boa; só anota o erro
                self._db.execute("INSERT INTO clima_fonte(fonte,dados,consultado,erro,erro_em) VALUES(?, '{}', 0, ?, ?) "
                                 "ON CONFLICT(fonte) DO UPDATE SET erro=excluded.erro, erro_em=excluded.erro_em",
                                 (fonte, erro[:200], agora))
            self._db.commit()

    def _ibge_do_local(self, loc: dict) -> str:
        """Código IBGE do local; sem ele, procura pelo município e UF (o CEP do Início traz os dois). Guarda a resposta
        (a que não achou, por IBGE_ESPERA_S) para não perguntar ao IBGE a cada consulta."""
        if loc.get("ibge"):
            return str(loc["ibge"])
        mun, uf = str(loc.get("municipio") or "").strip(), str(loc.get("uf") or "").strip().upper()
        if not mun or not uf:
            return ""
        chave, agora = (_sem_acento(mun), uf), self._agora()
        guardado = self._ibge.get(chave)
        if guardado and (guardado[0] or agora - guardado[1] < IBGE_ESPERA_S):
            return guardado[0]
        codigo = self.achar_ibge(mun, uf) or ""
        self._ibge[chave] = (codigo, agora)
        return codigo

    def consultar(self, fonte: str) -> bool:
        return self.consultar_motivo(fonte) == "ok"

    def consultar_motivo(self, fonte: str) -> str:
        """Consulta uma fonte e diz como foi: "ok"; "erro_rede" (a fonte não respondeu: o laço espera mais a cada erro);
        "sem_local" ou "falta_dado" (falta preencher o Início: o erro fica guardado e aparece na tela, em vez de
        silêncio); "desligado" (receptor não configurado ou fonte desconhecida)."""
        loc = self.local()
        try:
            if fonte == "receptor":
                if not self.receptor_url:
                    return "desligado"
                dados = ler_receptor(self.buscar(self.receptor_url + "/api/estado"))
            elif fonte not in FONTES_DO_LOCAL:
                return "desligado"
            elif not loc:
                self._guardar(fonte, None, SEM_LOCAL)
                return "sem_local"
            elif fonte == "openmeteo":
                dados = ler_openmeteo(self.buscar(_url("openmeteo").format(lat=loc["lat"], lon=loc["lon"])))
            elif fonte == "inmet":
                ibge = self._ibge_do_local(loc)
                if not ibge:
                    self._guardar(fonte, None, FALTA_MUNICIPIO)
                    return "falta_dado"
                dados = ler_inmet(self.buscar(_url("inmet").format(ibge=ibge)), ibge)
            else:   # cemaden
                ibge = self._ibge_do_local(loc)
                if not loc.get("uf") or not ibge:
                    self._guardar(fonte, None, FALTA_MUNICIPIO)
                    return "falta_dado"
                dados = ler_cemaden(self.buscar(_url("cemaden").format(uf=urllib.parse.quote(loc["uf"]))),
                                    dict(loc, ibge=ibge), self._agora())
        except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
            self._guardar(fonte, None, f"sem resposta: {exc}")
            return "erro_rede"
        self._guardar(fonte, dados)
        self._apostar(fonte, dados)
        agora = datetime.fromtimestamp(self._agora(), FUSO)
        if fonte == "cemaden" and dados.get("mm_24h") is not None and agora.hour < 3:
            # entre 0 h e 3 h, o acumulado de 24 h é praticamente a chuva do dia que acabou
            self.observar((agora - timedelta(days=1)).strftime("%Y-%m-%d"), "cemaden", dados["mm_24h"])
        return "ok"

    def consultar_tudo(self) -> dict:
        return {f: self.consultar(f) for f in ("receptor", "openmeteo", "inmet", "cemaden")}

    def esquecer_previsoes(self) -> None:
        """O local mudou: a previsão do lugar antigo sai da tela (o placar e as apostas ficam)."""
        with self.hub._trava:
            self._db.execute("DELETE FROM clima_fonte WHERE fonte IN ('openmeteo','inmet','cemaden')")
            self._db.commit()

    def ultimas_chamadas(self) -> dict[str, float]:
        """Hora da última ida a cada fonte (boa ou com erro), para o piso entre chamadas valer também depois de reiniciar."""
        with self.hub._trava:
            linhas = self._db.execute("SELECT fonte, consultado, erro, erro_em FROM clima_fonte").fetchall()
        out = {}
        for f, c, erro, e in linhas:
            e = e if (erro or "").startswith("sem resposta") else None   # "falta município" não foi chamada à fonte
            if c or e:
                out[f] = max(c or 0.0, e or 0.0)
        return out

    # ── Aprendizado: o que cada fonte disse sobre amanhã × o que choveu ───────────────────────
    def _apostar(self, fonte: str, dados: dict) -> None:
        amanha = (datetime.fromtimestamp(self._agora(), FUSO) + timedelta(days=1)).strftime("%Y-%m-%d")
        for d in dados.get("dias") or []:
            if d.get("dia") == amanha:
                with self.hub._trava:
                    # a primeira aposta do dia é a que vale (não dá para "corrigir" a previsão depois)
                    self._db.execute("INSERT OR IGNORE INTO clima_aposta(fonte,dia,chove,mm,feita) VALUES(?,?,?,?,?)",
                                     (fonte, amanha, 1 if d.get("chove") else 0, d.get("mm"), self._agora()))
                    self._db.commit()

    def observar(self, dia: str, origem: str, mm: float) -> None:
        """Chuva medida no dia (CEMADEN ou pluviômetro Physis). O pluviômetro do lugar vale mais."""
        with self.hub._trava:
            observar_no_banco(self._db, dia, origem, mm, self._agora())
            self._db.commit()

    def placar(self) -> dict:
        obs = {}
        for dia, origem, mm in self._db.execute("SELECT dia, origem, mm FROM clima_observado"):
            if dia not in obs or origem == "physis":
                obs[dia] = mm
        r = {}
        for fonte, dia, chove in self._db.execute("SELECT fonte, dia, chove FROM clima_aposta"):
            if dia not in obs:
                continue
            p = r.setdefault(fonte, {"dias": 0, "acertos": 0})
            p["dias"] += 1
            p["acertos"] += int(bool(chove) == (obs[dia] >= CHUVA_MM))
        for p in r.values():
            p["taxa"] = round(p["acertos"] / p["dias"], 3) if p["dias"] else None
        return r

    def combinada(self, dados: dict, placar: dict) -> dict | None:
        """Chance de chover amanhã, pesando cada fonte pelo acerto no lugar (Laplace: começa em 50%)."""
        amanha = (datetime.fromtimestamp(self._agora(), FUSO) + timedelta(days=1)).strftime("%Y-%m-%d")
        soma = peso = 0.0
        votos = []
        for fonte, d in dados.items():
            for dia in (d.get("dados") or {}).get("dias") or []:
                if dia.get("dia") == amanha:
                    p = placar.get(fonte, {"dias": 0, "acertos": 0})
                    w = (p["acertos"] + 1) / (p["dias"] + 2)
                    soma += w * (1.0 if dia.get("chove") else 0.0)
                    peso += w
                    votos.append(fonte)
        if not peso:
            return None
        return {"dia": amanha, "chance_chuva": round(soma / peso, 2), "fontes": votos}

    # ── O que a tela mostra ─────────────────────────────────────────────────────────────────
    def estado(self) -> dict:
        agora = self._agora()
        fontes = {}
        for fonte, dados, consultado, erro, erro_em in self._db.execute(
                "SELECT fonte, dados, consultado, erro, erro_em FROM clima_fonte"):
            d = json.loads(dados or "{}")
            fontes[fonte] = {"nome": NOMES.get(fonte, fonte), "dados": d if consultado else None,
                             "consultado": consultado or None,
                             "atual": bool(consultado) and agora - consultado <= VALIDADE_S.get(fonte, 6 * 3600),
                             "erro": erro or None}
        for f in ("receptor", "openmeteo", "inmet", "cemaden"):
            fontes.setdefault(f, {"nome": NOMES[f], "dados": None, "consultado": None, "atual": False,
                                  "erro": None if (f != "receptor" or self.receptor_url) else "receptor não configurado"})
        placar = self.placar()
        prev = {k: v for k, v in fontes.items() if k in ("openmeteo", "inmet") and v["atual"]}
        with self.hub._trava:
            local = chuva_medida_local(self._db, agora)       # pluviômetro Physis (TIPO:PLUV), se houver
        achar = getattr(self.hub, "local_da_instalacao", None)
        lugar = achar() if achar else None     # o local único do cliente, com fonte (ou "nao_informado") e polígono
        return {"ok": True, "local": self.local(), "lugar": lugar, "fontes": fontes, "placar": placar,
                "combinada": self.combinada(prev, placar), "agora": agora, "chuva_local": local}


def receptor_local(base: str, timeout: float = 5.0):
    """Função que grava a localização no receptor V6 (POST /api/localizacao, lat e lon em formulário)."""
    def enviar(lat: float, lon: float):
        corpo = urllib.parse.urlencode({"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"}).encode()
        req = urllib.request.Request(base.rstrip("/") + "/api/localizacao", data=corpo, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read().decode() or "{}")
                return bool(j.get("ok")), "receptor atualizado: a previsão dele passa a ser deste lugar"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, f"receptor inacessível: {exc}"
    return enviar


_NUNCA = object()


class Agendador:
    """Quando consultar cada fonte, sem ninguém clicar em "Consultar agora" (pedido de 15/11/2026).

    - ao ligar o hub, se já há local: consulta logo;
    - quando o local muda (Início, Planejador ou Monitoramento, pela função única hub.local_da_instalacao): esquece a
      previsão do lugar antigo e consulta logo;
    - depois, cada fonte no seu ritmo (INTERVALO_S);
    - com erro de rede, espera o dobro a cada erro seguido (do PISO_S até o TETO_S);
    - nunca chama a mesma fonte com menos de PISO_S de intervalo (limites publicados: ver PISO_S).
    Sem local, município ou UF, o erro fica guardado (aparece na tela) e a fonte volta só no ritmo normal ou quando o
    local mudar. O relógio vem de fora (`passo(agora)`) para os testes usarem um relógio falso."""

    def __init__(self, clima: Clima, intervalos: dict | None = None, pisos: dict | None = None, tetos: dict | None = None):
        self.clima = clima
        self.intervalos = {f: s for f, s in (intervalos or INTERVALO_S).items()
                           if f != "receptor" or clima.receptor_url}      # sem receptor configurado, nada a consultar
        self.pisos, self.tetos = dict(pisos or PISO_S), dict(tetos or TETO_S)
        self.proximo = {f: 0.0 for f in self.intervalos}
        self.falhas = {f: 0 for f in self.intervalos}
        try:
            self.ultima = clima.ultimas_chamadas()
        except Exception:          # noqa: BLE001 — sem histórico, só não há piso herdado
            self.ultima = {}
        self.marca = _NUNCA
        self.mudou: set[str] = set()     # fontes com local novo ainda não consultado (piso curto, PISO_MUDANCA_S)

    def _marca_do_local(self):
        loc = self.clima.local()
        if not loc:
            return None
        return tuple(str(loc.get(k) or "") for k in ("lat", "lon", "municipio", "uf", "ibge", "cemaden_estacao"))

    def espera_erro(self, fonte: str) -> float:
        n = max(1, self.falhas[fonte])
        return float(min(self.tetos.get(fonte, 6 * 3600), self.pisos.get(fonte, 60) * 2 ** (n - 1)))

    def passo(self, agora: float) -> dict[str, str]:
        """Faz as consultas que venceram. Devolve {fonte: motivo} do que foi tentado agora."""
        try:   # "Consultar agora" na tela também conta para o piso
            for f, t in self.clima.ultimas_chamadas().items():
                if t > (self.ultima.get(f) or 0.0):
                    self.ultima[f] = t
        except Exception:          # noqa: BLE001
            pass
        marca = self._marca_do_local()
        if marca != self.marca:
            if self.marca is not _NUNCA and self.marca is not None:
                self.clima.esquecer_previsoes()           # previsão do lugar antigo não fica na tela
            self.marca = marca
            for f in FONTES_DO_LOCAL:
                if f in self.proximo:
                    self.proximo[f], self.falhas[f] = 0.0, 0
                    self.mudou.add(f)
        feitas: dict[str, str] = {}
        for fonte, intervalo in self.intervalos.items():
            if agora < self.proximo[fonte]:
                continue
            ult, piso = self.ultima.get(fonte), self.pisos.get(fonte, 60)
            if fonte in self.mudou:
                piso = min(piso, PISO_MUDANCA_S)            # local novo: consulta já (ainda com um mínimo)
            if ult is not None and agora - ult < piso:
                self.proximo[fonte] = ult + piso           # cedo demais para esta fonte: espera o piso
                continue
            try:
                motivo = self.clima.consultar_motivo(fonte)
            except Exception:          # noqa: BLE001 — uma fonte com defeito não pode parar as outras
                motivo = "erro_rede"
            feitas[fonte] = motivo
            self.mudou.discard(fonte)
            if motivo in ("ok", "erro_rede"):
                self.ultima[fonte] = agora
            if motivo == "erro_rede":
                self.falhas[fonte] += 1
                self.proximo[fonte] = agora + self.espera_erro(fonte)
            else:
                self.falhas[fonte] = 0
                self.proximo[fonte] = agora + intervalo
        return feitas


def rodar(clima: Clima, parar: threading.Event, passo: float = 10.0, relogio=None) -> None:
    """Laço de fundo do hub (servidor.main liga numa thread). Olha o local a cada `passo` segundos (consulta barata ao
    banco) e deixa o Agendador decidir. Erros não derrubam o hub."""
    ag = Agendador(clima)
    relogio = relogio or clima._agora
    while not parar.is_set():
        try:
            ag.passo(relogio())
        except Exception:          # noqa: BLE001
            pass
        parar.wait(passo)
