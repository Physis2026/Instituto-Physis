"""Endereço e coordenadas a partir do CEP, consultados pelo SERVIDOR (nunca pelo navegador). Pedido de 15/11/2026:
"CEP deve ser obrigatório, latitude e longitude opcionais e preenchidas automaticamente com o CEP".

Regras:
- LGPD: vai para o provedor SÓ o CEP (8 dígitos, no caminho da URL). Nada de nome, e-mail, sessão ou outro dado; o
  User-Agent é genérico, sem e-mail pessoal.
- Provedor por PHYSIS_CEP_PROVEDOR (lista em ordem, separada por vírgula): "brasilapi" (BrasilAPI CEP v2, que pode
  trazer coordenadas), "viacep" (endereço, município e código IBGE, sem coordenadas), "nominatim" (instância própria
  da Fase 2 em PHYSIS_NOMINATIM_URL; a pública só se a política de uso permitir: no máximo 1 pedido por segundo e
  User-Agent descritivo) ou "desligado". Padrão: "brasilapi,viacep".
  [CONFERIR] termos de uso de cada provedor na página oficial antes de ligar em produção (não conferidos daqui):
  BrasilAPI (https://brasilapi.com.br/docs), ViaCEP (https://viacep.com.br), Nominatim (https://operations.osmfoundation.org/policies/nominatim/).
- Coordenadas só quando o provedor devolve. Centróide do município: só com uma base aberta do IBGE de licença conferida
  embutida (ainda não há); sem ela, lat/lon ficam vazias e a tela diz "coordenadas não encontradas — marque no mapa".
  Nunca um ponto inventado.
- Cache no SQLite (tabela cep_cache, 30 dias); limite de pedidos por IP no servidor (categoria "cep").
- Sem internet ou provedor desligado: o CEP continua obrigatório, o endereço é digitado e as coordenadas são opcionais.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

CACHE_S = 30 * 24 * 3600
TEMPO_S = 6
USER_AGENT = "PhysisHub/1 (consulta de CEP; servidor do cliente)"     # genérico, sem e-mail pessoal
PROVEDORES = ("brasilapi", "viacep", "nominatim")
_RE = re.compile(r"^\d{8}$")
_ULTIMO_NOMINATIM = [0.0]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS cep_cache (cep TEXT PRIMARY KEY, dados TEXT NOT NULL, quando REAL NOT NULL);
"""


def limpar(cep) -> str:
    """Só os dígitos do CEP."""
    return re.sub(r"\D", "", str(cep or ""))


def valido(cep) -> bool:
    """CEP com 8 dígitos (aceita a máscara 00000-000)."""
    s = str(cep or "").strip()
    return bool(re.fullmatch(r"\d{5}-?\d{3}", s)) and _RE.match(limpar(s)) is not None and limpar(s) != "00000000"


def mascara(cep) -> str:
    d = limpar(cep)[:8]
    return d[:5] + ("-" + d[5:] if len(d) > 5 else "")


def provedores_config(valor: str | None = None) -> list[str]:
    v = os.environ.get("PHYSIS_CEP_PROVEDOR", "brasilapi,viacep") if valor is None else valor
    lst = [p.strip().lower() for p in str(v).split(",") if p.strip()]
    if "desligado" in lst:
        return []
    return [p for p in lst if p in PROVEDORES]


def _http_json(url: str) -> dict | list | None:
    """GET só com a URL (o CEP no caminho ou na consulta); sem cookie, sem cabeçalho além do User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TEMPO_S) as r:          # noqa: S310 (URL fixa por provedor)
            return json.loads(r.read(512 * 1024).decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _num(v):
    try:
        x = float(str(v).replace(",", "."))
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def url_de(provedor: str, cep: str) -> str:
    if provedor == "brasilapi":
        return f"https://brasilapi.com.br/api/cep/v2/{cep}"
    if provedor == "viacep":
        return f"https://viacep.com.br/ws/{cep}/json/"
    base = os.environ.get("PHYSIS_NOMINATIM_URL", "").rstrip("/")
    if not base:
        return ""
    return f"{base}/search?postalcode={cep[:5]}-{cep[5:]}&country=br&format=json&limit=1"


def interpretar(provedor: str, j) -> dict | None:
    """Resposta do provedor → {endereco, bairro, municipio, uf, ibge, lat, lon}. None = não achou."""
    if provedor == "brasilapi" and isinstance(j, dict) and j.get("cep"):
        co = ((j.get("location") or {}).get("coordinates") or {})
        lat, lon = _num(co.get("latitude")), _num(co.get("longitude"))
        return {"endereco": j.get("street") or "", "bairro": j.get("neighborhood") or "", "municipio": j.get("city") or "",
                "uf": (j.get("state") or "")[:2].upper(), "ibge": "", "lat": lat, "lon": lon}
    if provedor == "viacep" and isinstance(j, dict) and not j.get("erro") and j.get("cep"):
        return {"endereco": j.get("logradouro") or "", "bairro": j.get("bairro") or "", "municipio": j.get("localidade") or "",
                "uf": (j.get("uf") or "")[:2].upper(), "ibge": str(j.get("ibge") or ""), "lat": None, "lon": None}
    if provedor == "nominatim" and isinstance(j, list) and j:
        a = j[0]
        return {"endereco": "", "bairro": "", "municipio": "", "uf": "", "ibge": "", "lat": _num(a.get("lat")), "lon": _num(a.get("lon"))}
    return None


class ServicoCEP:
    """Consulta de CEP com cache. buscar(url) é trocável nos testes (provedor falso)."""

    def __init__(self, hub, provedores: list[str] | None = None, buscar=None, relogio=None):
        self.hub, self.provedores = hub, provedores_config() if provedores is None else provedores
        self.buscar, self.relogio = buscar or _http_json, relogio or time.time
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    def consultar(self, cep_txt: str) -> tuple[int, dict]:
        if not valido(cep_txt):
            return 400, {"ok": False, "erro": "CEP inválido: use 8 dígitos (00000-000)."}
        cep, agora = limpar(cep_txt), self.relogio()
        with self.hub._trava:
            r = self.hub._db.execute("SELECT dados, quando FROM cep_cache WHERE cep=?", (cep,)).fetchone()
        if r and agora - r[1] < CACHE_S:
            d = json.loads(r[0])
            d["cache"] = True
            return 200, d
        if not self.provedores:
            return 200, self._vazio(cep, "Consulta de CEP desligada neste servidor: digite o endereço; as coordenadas são opcionais (marque no mapa).")
        achado, usados = None, []
        for p in self.provedores:
            url = url_de(p, cep)
            if not url:
                continue
            if p == "nominatim":                              # política de uso: no máximo 1 pedido por segundo
                espera = 1.0 - (agora - _ULTIMO_NOMINATIM[0])
                if espera > 0:
                    time.sleep(min(espera, 1.0))
                _ULTIMO_NOMINATIM[0] = self.relogio()
            r = interpretar(p, self.buscar(url))
            usados.append(p)
            if not r:
                continue
            if achado is None:
                achado = dict(r, provedor=p)
            else:                                             # completa o que faltou (ex.: IBGE do ViaCEP)
                for k, v in r.items():
                    if v not in (None, "") and achado.get(k) in (None, ""):
                        achado[k] = v
            if achado.get("lat") is not None and achado.get("ibge"):
                break
        if achado is None:
            return 200, self._vazio(cep, "CEP não encontrado agora (sem internet ou o provedor não respondeu): digite o endereço; as coordenadas são opcionais.", usados)
        tem = achado.get("lat") is not None and achado.get("lon") is not None
        d = {"ok": True, "cep": mascara(cep), "endereco": achado["endereco"], "bairro": achado["bairro"], "municipio": achado["municipio"],
             "uf": achado["uf"], "ibge": achado["ibge"], "lat": achado["lat"] if tem else None, "lon": achado["lon"] if tem else None,
             "fonte_coordenadas": "cep" if tem else None, "provedor": achado["provedor"], "provedores": usados,
             "aviso": "" if tem else "coordenadas não encontradas — marque no mapa"}
        with self.hub._trava:
            self.hub._db.execute("INSERT OR REPLACE INTO cep_cache(cep, dados, quando) VALUES(?,?,?)", (cep, json.dumps(d, ensure_ascii=False), agora))
            self.hub._db.commit()
        return 200, d

    @staticmethod
    def _vazio(cep, aviso, usados=()):
        return {"ok": False, "cep": mascara(cep), "endereco": "", "bairro": "", "municipio": "", "uf": "", "ibge": "", "lat": None, "lon": None,
                "fonte_coordenadas": None, "provedor": None, "provedores": list(usados), "aviso": aviso}
