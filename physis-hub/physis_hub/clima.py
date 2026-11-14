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

    def consultar(self, fonte: str) -> bool:
        loc = self.local()
        try:
            if fonte == "receptor":
                if not self.receptor_url:
                    return False
                dados = ler_receptor(self.buscar(self.receptor_url + "/api/estado"))
            elif not loc:
                return False
            elif fonte == "openmeteo":
                dados = ler_openmeteo(self.buscar(_url("openmeteo").format(lat=loc["lat"], lon=loc["lon"])))
            elif fonte == "inmet":
                if not loc.get("ibge"):
                    self._guardar(fonte, None, "falta o código IBGE do município (informe município e UF)")
                    return False
                dados = ler_inmet(self.buscar(_url("inmet").format(ibge=loc["ibge"])), loc["ibge"])
            elif fonte == "cemaden":
                if not loc.get("uf") or not loc.get("ibge"):
                    self._guardar(fonte, None, "falta o município e a UF do lugar")
                    return False
                dados = ler_cemaden(self.buscar(_url("cemaden").format(uf=loc["uf"])), loc, self._agora())
            else:
                return False
        except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
            self._guardar(fonte, None, f"sem resposta: {exc}")
            return False
        self._guardar(fonte, dados)
        self._apostar(fonte, dados)
        agora = datetime.fromtimestamp(self._agora(), FUSO)
        if fonte == "cemaden" and dados.get("mm_24h") is not None and agora.hour < 3:
            # entre 0 h e 3 h, o acumulado de 24 h é praticamente a chuva do dia que acabou
            self.observar((agora - timedelta(days=1)).strftime("%Y-%m-%d"), "cemaden", dados["mm_24h"])
        return True

    def consultar_tudo(self) -> dict:
        return {f: self.consultar(f) for f in ("receptor", "openmeteo", "inmet", "cemaden")}

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
            self._db.execute("INSERT INTO clima_observado(dia,origem,mm,atualizado) VALUES(?,?,?,?) "
                             "ON CONFLICT(dia,origem) DO UPDATE SET mm=excluded.mm, atualizado=excluded.atualizado",
                             (dia, origem, float(mm), self._agora()))
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
        return {"ok": True, "local": self.local(), "fontes": fontes, "placar": placar,
                "combinada": self.combinada(prev, placar), "agora": agora}


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


def rodar(clima: Clima, parar: threading.Event, passo: float = 30.0) -> None:
    """Laço de fundo: cada fonte no seu ritmo. Erros não derrubam o hub."""
    ultimo = {f: 0.0 for f in INTERVALO_S}
    while not parar.is_set():
        agora = time.time()
        for fonte, intervalo in INTERVALO_S.items():
            if agora - ultimo[fonte] >= intervalo:
                ultimo[fonte] = agora
                try:
                    clima.consultar(fonte)
                except Exception:          # noqa: BLE001 — uma fonte com defeito não pode parar as outras
                    pass
        parar.wait(passo)
